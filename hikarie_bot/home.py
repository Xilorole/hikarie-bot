"""Build the App Home: a page per tab (my page, collection, ranking, how to play) switched by buttons on top.

Like the modals, every page is rendered from the engine's results, recomputed from the stored events when the
Home is opened; nothing here is stored. Views are dictionaries (slack_sdk has no model of some blocks used).
A Home view holds at most HOME_BLOCK_MAX blocks.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import ClassVar

from dateutil.relativedelta import relativedelta

from hikarie_bot.db_data.badges import KIRIBANS
from hikarie_bot.db_data.items import ITEM_IMAGE_URLS, ITEM_POINT_CAP, Items
from hikarie_bot.engine import TEAM_GOAL_PER_BIZDAY, BadgeEngine, Outlook, TeamProgress
from hikarie_bot.modals import (
    BADGES,
    BADGES_BY_TYPE,
    ITEMS,
    KIRIBAN_BADGE_TYPE_ID,
    _mrkdwn,
    _progress_bar,
    attendance_by_day,
    attendance_history_blocks,
    badge_types_to_show,
    bullet_list,
    divided,
    item_section,
    outlook_lines,
    render,
)
from hikarie_bot.utils import LEVELS, get_level, is_jp_bizday

HOME_BLOCK_MAX = 100  # Slack refuses a Home view with more blocks
RANKING_SIZE = 5
RECENT_BADGES = 3
DAYS_AGO_MAX = 7  # up to this many days ago a badge says days; then weeks within a month, then months


class HomeTab:
    """The tabs of the Home and the action IDs of their buttons."""

    MY_PAGE = "HOME_TAB_MY_PAGE"
    COLLECTION = "HOME_TAB_COLLECTION"
    RANKING = "HOME_TAB_RANKING"
    HOW_TO_PLAY = "HOME_TAB_HOW_TO_PLAY"
    LABELS: ClassVar[dict[str, str]] = {
        MY_PAGE: "マイページ",
        COLLECTION: "図鑑",
        RANKING: "ランキング",
        HOW_TO_PLAY: "あそびかた",
    }


class HomeActionID:
    """The action IDs of the buttons on the Home's pages (other than the tabs)."""

    ARRIVE = "HOME_ARRIVE"
    PICK_ITEM = "HOME_PICK_ITEM"


def _section(text: str, accessory: dict | None = None) -> dict:
    block = {"type": "section", "text": _mrkdwn(text)}
    if accessory:
        block["accessory"] = accessory
    return block


def _context(text: str) -> dict:
    return {"type": "context", "elements": [_mrkdwn(text)]}


def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text}}


def _button(text: str, action_id: str, *, primary: bool = False) -> dict:
    button = {"type": "button", "text": {"type": "plain_text", "text": text}, "action_id": action_id}
    if primary:
        button["style"] = "primary"
    return button


DIVIDER = {"type": "divider"}


def tab_bar(selected: str) -> dict:
    """Return the buttons that switch the tabs, the selected one highlighted."""
    return {
        "type": "actions",
        "block_id": "HOME_TABS",
        "elements": [
            _button(label, action_id, primary=action_id == selected) for action_id, label in HomeTab.LABELS.items()
        ],
    }


def home_view(engine: BadgeEngine, user_id: str, now: datetime, tab: str = HomeTab.MY_PAGE) -> dict:
    """Build the user's Home on a tab; now is an aware datetime in JST."""
    pages = {
        HomeTab.MY_PAGE: my_page_blocks,
        HomeTab.COLLECTION: collection_blocks,
        HomeTab.RANKING: ranking_blocks,
        HomeTab.HOW_TO_PLAY: how_to_play_blocks,
    }
    blocks = [tab_bar(tab), *pages[tab](engine, user_id, now)]
    return {"type": "home", "private_metadata": tab, "blocks": blocks[:HOME_BLOCK_MAX]}


# --- my page ---
# Every part of my page is a header with one kind of content below it: today, status, next goals,
# attendance history and recent badges, in that order.


def picked_today(engine: BadgeEngine, user_id: str, today: date) -> str | None:
    """Return the ID of the item the user picked today, if any."""
    user = engine.users.get(user_id)
    return next((held.pick.item_id for held in user.items if held.pick.day == today), None) if user else None


def today_blocks(engine: BadgeEngine, user_id: str, now: datetime) -> list[dict]:
    """Describe today's arrival with its buttons: register it, and look at (once arrived, pick) the day's items.

    Once today's item is picked, it shows as in the collection (without its story) instead of the item button.
    """
    today = now.date()
    item_button = _button("今日のアイテム", HomeActionID.PICK_ITEM)
    arrival = engine.arrival_of(user_id, today)
    if arrival is not None:
        text = f"{arrival.time:%H:%M} に出社登録済み（{arrival.rank}番目・+{arrival.score_sum}pt）"
        if (item_id := picked_today(engine, user_id, today)) in ITEMS:
            item = ITEMS[item_id]
            name = f"*今日のアイテム*  {item.name}（効果は次の出社から）"
            return [_section(text), item_section(name, item.effect, None, ITEM_IMAGE_URLS.get(item.id), item.name)]
        return [_section(text, item_button)]
    if not is_jp_bizday(today):
        return [_section("お休みの日です。次の営業日にまた会いましょう")]
    if not 6 <= now.hour < 18:  # noqa: PLR2004
        return [_section("出社登録は 6:00〜18:00 にできます", item_button)]
    return [
        _section("まだ出社登録していません。アイテムは登録のあとに選べます（候補は今も見られます）"),
        {"type": "actions", "elements": [_button("出社した", HomeActionID.ARRIVE, primary=True), item_button]},
    ]


def status_fields(engine: BadgeEngine, user_id: str, today: date) -> dict:
    """Show the level, the points, the progress to the next level and the held item, two to a row."""
    user = engine.users.get(user_id)
    score = user.score if user else 0
    level = get_level(score)
    rate = int(100 * level.progress_points / level.span)
    progress = "最高レベル" if level.is_max else f"`{_progress_bar(rate)}` {rate}%（あと{level.points_to_next}pt）"
    held = engine.held_item(user_id, today)
    if held is None:
        item = "なし"
    else:
        until = f"{held.last_day:%-m/%-d}まで" if held.last_day else "次の出社で使う"
        item = f"{ITEMS[held.pick.item_id].name}（{until}）"
    return {
        "type": "section",
        "fields": [
            _mrkdwn(f"*かたがき*\n{level.name}（Lv{level.number}）"),
            _mrkdwn(f"*ポイント*\n累計 {score}pt"),
            _mrkdwn(f"*つぎのレベルまで*\n{progress}"),
            _mrkdwn(f"*所持アイテム*\n{item}"),
        ],
    }


def team_progress_text(team: TeamProgress) -> str:
    """Describe everyone's arrivals this week as a bar against the goal."""
    rate = min(100, int(100 * team.count / team.goal)) if team.goal else 0
    state = "達成！" if team.reached else f"あと{team.goal - team.count}回"
    return f"今週のみんなの出社 `{_progress_bar(rate)}` {team.count} / {team.goal}回（{state}）"


def goal_lines(engine: BadgeEngine, outlook: Outlook, now: datetime) -> list[str]:
    """List the user's next goals and the week's team progress (shown even before the team goal applies)."""
    team = engine.week_progress(now)
    return [*outlook_lines(outlook), *([team_progress_text(team)] if team.goal else [])]


def when(day: date, today: date) -> str:
    """Say how long ago a day was, coarser the older it is.

    今日, 昨日 or N日前 up to DAYS_AGO_MAX days, N週前 within a month, Nヶ月前 within a year, else 1年以上前.
    """
    days = (today - day).days
    if days <= DAYS_AGO_MAX:
        return {0: "今日", 1: "昨日"}.get(days, f"{days}日前")
    ago = relativedelta(today, day)
    if ago.years:
        return "1年以上前"
    return f"{days // 7}週前" if ago.months == 0 else f"{ago.months}ヶ月前"


def recent_badge_lines(engine: BadgeEngine, user_id: str, today: date) -> list[str]:
    """List the badges the user earned most recently, newest first, with when they were earned."""
    tallies = sorted(
        ((tally.last, badge_id) for (owner, badge_id), tally in engine.user_badges.items() if owner == user_id),
        reverse=True,
    )[:RECENT_BADGES]
    return [
        f"[{BADGES[badge_id].score}pt] {BADGES[badge_id].message}  {when(last.date(), today)}"
        for last, badge_id in tallies
    ]


def my_page_blocks(engine: BadgeEngine, user_id: str, now: datetime, outlook: Outlook | None = None) -> list[dict]:
    """Build my page: today, status, next goals, attendance history and recent badges, each under a header."""
    today = now.date()
    outlook = outlook or engine.status_outlook(user_id, now)
    parts: list[list[dict]] = [
        [_header("今日"), *today_blocks(engine, user_id, now)],
        [_header("ステータス"), status_fields(engine, user_id, today)],
    ]
    if goals := goal_lines(engine, outlook, now):
        parts.append([_header("つぎのもくひょう"), bullet_list([(line, 0) for line in goals])])
    parts.append(render(attendance_history_blocks(attendance_by_day(engine, user_id, today))))
    if recent := recent_badge_lines(engine, user_id, today):
        parts.append([_header("最近のバッジ"), bullet_list([(line, 0) for line in recent])])
    blocks = [block for index, part in enumerate(parts) for block in ([DIVIDER] if index else []) + part]
    blocks.append(_context("バッジとアイテムの集まり具合は「図鑑」で見られます"))
    return blocks


# --- collection ---


@dataclass(frozen=True)
class Rarity:
    """How many of the users who ever arrived earned each badge."""

    holders: Counter
    users: int

    def rate(self, badge_id: int) -> int:
        """Return the percentage of users holding the badge."""
        return round(100 * self.holders[badge_id] / self.users) if self.users else 0


def rarity(engine: BadgeEngine) -> Rarity:
    """Count the holders of each badge among everyone who arrived."""
    return Rarity(Counter(badge_id for _, badge_id in engine.user_badges), len(engine.users))


def _text(text: str, *, bold: bool = False) -> dict:
    element = {"type": "text", "text": text}
    if bold:
        element["style"] = {"bold": True}
    return element


def _emoji(name: str) -> dict:
    return {"type": "emoji", "name": name}


BADGE_LEGEND = (
    "[pt]: もらえるポイント ／ %: 獲得率（これまでに出社登録した人のうち、持っている人の割合）"
    "／ ×: 獲得回数 ／ @: はじめて獲得した日"
)


EARNED_MARK, UNEARNED_MARK = "white_check_mark", "white_large_square"  # Slack emoji names


def badge_item(badge_id: int, engine: BadgeEngine, user_id: str, rarities: Rarity) -> dict:
    """Return a badge's list item: "[pt] name rarity", then for an earned badge (in bold) its count and first date."""
    badge = BADGES[badge_id]
    tally = engine.user_badges.get((user_id, badge_id))
    rate = f"  {rarities.rate(badge_id)}%"
    if tally is None:
        elements = [_emoji(UNEARNED_MARK), _text(f" [{badge.score}pt] {badge.message}{rate}")]
    else:
        elements = [
            _emoji(EARNED_MARK),
            _text(f" [{badge.score}pt] "),
            _text(badge.message, bold=True),
            _text(f"{rate}  ×{tally.count} @{tally.first:%y/%m/%d}"),
        ]
    return {"type": "rich_text_section", "elements": elements}


def collection_summary(engine: BadgeEngine, user_id: str) -> str:
    """Describe how many titles the user has reached and how much of the badges (kiribans aside) and items."""
    badge_ids = [
        badge.id
        for badge_type in badge_types_to_show()
        if badge_type.id != KIRIBAN_BADGE_TYPE_ID
        for badge in BADGES_BY_TYPE[badge_type.id]
    ]
    earned = sum((user_id, badge_id) in engine.user_badges for badge_id in badge_ids)
    rate = int(100 * earned / len(badge_ids))
    user = engine.users.get(user_id)
    picked = {held.pick.item_id for held in user.items} if user else set()
    level = max(level_reached_on(engine, user_id), default=0)
    return (
        f"*かたがき* {level} / {len(LEVELS)}\n"
        f"*バッジ* `{_progress_bar(rate)}` {earned} / {len(badge_ids)}（{rate}%）\n"
        f"*アイテム* {len(picked & set(ITEMS))} / {len(ITEMS)} 種類を獲得"
    )


def level_reached_on(engine: BadgeEngine, user_id: str) -> dict[int, date]:
    """Return the day the user first reached each level they have reached."""
    user = engine.users.get(user_id)
    reached: dict[int, date] = {}
    for result in user.results if user else []:
        for number in range(1, get_level(result.current_score).number + 1):
            reached.setdefault(number, result.time.date())
    return reached


def title_table(engine: BadgeEngine, user_id: str) -> dict:
    """Tabulate the titles up to the next level: the level, its starting points, the title and the day first reached.

    The next title is hidden and later ones are left out; the current one is bold and marked.
    """
    reached = level_reached_on(engine, user_id)
    current = max(reached, default=0)
    rows = [[_cell(_text(label, bold=True)) for label in ("Lv", "ポイント", "かたがき", "達成日")]]
    for number, (name, _) in enumerate(LEVELS[: current + 1], start=1):
        start = LEVELS[number - 2][1] if number > 1 else 0
        if number in reached:
            title = _text(f"{name}（いま）" if number == current else name, bold=number == current)
            day = f"{reached[number]:%y/%m/%d}"
        else:
            title, day = _text(UNKNOWN_EFFECT), "-"
        rows.append([_cell(_text(f"Lv{number}")), _cell(_text(f"{start}pt〜")), _cell(title), _cell(_text(day))])
    return {
        "type": "table",
        "column_settings": [{"align": "center"}, {"align": "right"}, {"is_wrapped": True}, {"align": "center"}],
        "rows": rows,
    }


def badge_collection_blocks(engine: BadgeEngine, user_id: str) -> list[dict]:
    """List every badge type, its badges indented below it; one rich text block per type keeps the blocks few."""
    rarities = rarity(engine)
    blocks = []
    for badge_type in badge_types_to_show():
        if badge_type.id == KIRIBAN_BADGE_TYPE_ID:
            continue
        badges = BADGES_BY_TYPE[badge_type.id]
        title = {
            "type": "rich_text_section",
            "elements": [_text(badge_type.description, bold=True)],
        }
        items = {
            "type": "rich_text_list",
            "style": "bullet",
            "indent": 0,
            "elements": [badge_item(badge.id, engine, user_id, rarities) for badge in badges],
        }
        blocks.append({"type": "rich_text", "elements": [title, items]})
    return blocks


def kiriban_text(engine: BadgeEngine, user_id: str) -> str:
    """List the kiribans the user took and how far the next one is (kiribans number everyone's arrivals)."""
    taken = [kiriban.number for kiriban in KIRIBANS if (user_id, kiriban.id) in engine.user_badges]
    count = len(engine.results)
    upcoming = next((kiriban for kiriban in KIRIBANS if kiriban.number > count), None)
    taken_text = "、".join(f"{number}番" for number in taken) if taken else "まだありません"
    upcoming_text = f"次のキリ番 *{upcoming.number}番目* まで あと{upcoming.number - count}回" if upcoming else ""
    return f"*キリ番*  とったキリ番: {taken_text}\n{upcoming_text}"


def item_collection_blocks(engine: BadgeEngine, user_id: str) -> list[dict]:
    """Show every item beside its image: its name, and once picked how often, its effect and its story.

    Until the user picks an item, its effect and story read UNKNOWN_EFFECT. The story is an italic block quote.
    Items are divided by lines.
    """
    user = engine.users.get(user_id)
    picks = Counter(held.pick.item_id for held in user.items) if user else Counter()
    sections = []
    for item in Items:
        if picks[item.id]:
            name, effect, story = f"*{item.name}*  （{picks[item.id]}回獲得）", item.effect, item.flavor
        else:
            name, effect, story = f"*{item.name}*", UNKNOWN_EFFECT, UNKNOWN_EFFECT
        sections.append(item_section(name, effect, story, ITEM_IMAGE_URLS.get(item.id), item.name))
    return divided([[section] for section in sections])


def collection_blocks(engine: BadgeEngine, user_id: str, _now: datetime) -> list[dict]:
    """Build the collection: the totals, every title, every badge by type, the kiribans and every item."""
    return [
        _header("図鑑"),
        _section(collection_summary(engine, user_id)),
        DIVIDER,
        _header("かたがき"),
        _context("達成日: はじめて届いた日 ／ まだのかたがきは、届くと名前がわかります"),
        title_table(engine, user_id),
        DIVIDER,
        _header("バッジ"),
        _context(BADGE_LEGEND),
        *badge_collection_blocks(engine, user_id),
        _section(kiriban_text(engine, user_id)),
        DIVIDER,
        _header("アイテム"),
        *item_collection_blocks(engine, user_id),
    ]


# --- ranking ---


@dataclass(frozen=True)
class RankingEntry:
    """A user's place in a ranking (ties share a rank)."""

    rank: int
    user_id: str
    value: int


@dataclass(frozen=True)
class Ranking:
    """A ranking's top entries and, when below them, the viewing user's own entry."""

    title: str
    unit: str
    top: list[RankingEntry]
    own: RankingEntry | None


def ranking(title: str, totals: Counter, user_id: str, unit: str) -> Ranking:
    """Rank the totals, highest first; equal totals share a rank and the next rank skips (1, 1, 3)."""
    ordered = sorted(totals.items(), key=lambda entry: -entry[1])
    entries: list[RankingEntry] = []
    for index, (uid, value) in enumerate(ordered):
        rank = entries[-1].rank if entries and entries[-1].value == value else index + 1
        entries.append(RankingEntry(rank, uid, value))
    top = [entry for entry in entries if entry.rank <= RANKING_SIZE]
    own = next((entry for entry in entries if entry.user_id == user_id and entry.rank > RANKING_SIZE), None)
    return Ranking(title, unit, top, own)


UNKNOWN_EFFECT = "？？？？？"
MEDALS = {1: "\N{FIRST PLACE MEDAL}", 2: "\N{SECOND PLACE MEDAL}", 3: "\N{THIRD PLACE MEDAL}"}
EMPTY_RANKING = "まだ記録がありません"


def _cell(*elements: dict) -> dict:
    return {"type": "rich_text", "elements": [{"type": "rich_text_section", "elements": list(elements)}]}


def _ranking_table(board: Ranking) -> list[dict]:
    """Write a ranking as a table: place, user and value (right-aligned)."""
    if not board.top:
        return [_section(f"*{board.title}*\n{EMPTY_RANKING}")]

    def row(entry: RankingEntry, place: str) -> list[dict]:
        return [
            _cell(_text(place)),
            _cell({"type": "user", "user_id": entry.user_id}),
            _cell(_text(f"{entry.value}{board.unit}", bold=True)),
        ]

    rows = [row(entry, MEDALS.get(entry.rank, f"{entry.rank}位")) for entry in board.top]
    if board.own:
        rows.append(row(board.own, f"{board.own.rank}位（あなた）"))
    table = {
        "type": "table",
        "column_settings": [{"align": "center"}, {"is_wrapped": True}, {"align": "right"}],
        "rows": rows,
    }
    return [_section(f"*{board.title}*"), table]


def ranking_blocks(engine: BadgeEngine, user_id: str, now: datetime) -> list[dict]:
    """Build the month's rankings: points, arrivals and fastest arrivals since the first of the month."""
    month = [result for result in engine.results if (result.time.year, result.time.month) == (now.year, now.month)]
    points, arrivals, fastest = Counter(), Counter(), Counter()
    for result in month:
        points[result.user_id] += result.score_sum
        arrivals[result.user_id] += 1
        fastest[result.user_id] += result.rank == 1
    fastest = Counter({uid: count for uid, count in fastest.items() if count})
    boards = [
        ranking("獲得ポイント", points, user_id, "pt"),
        ranking("出社回数", arrivals, user_id, "回"),
        ranking("最速出社", fastest, user_id, "回"),
    ]
    blocks = [_header(f"{now.month}月のランキング")]
    for index, board in enumerate(boards):
        blocks += [*([DIVIDER] if index else []), *_ranking_table(board)]
    blocks.append(_context("毎月1日にリセットされます。今月の出社登録だけで競うので、いつからでも上位を狙えます"))
    return blocks


# --- how to play ---


def how_to_play_blocks(_engine: BadgeEngine, _user_id: str, _now: datetime) -> list[dict]:
    """Build the rules: how to register, how points come, the items, the team goal and the levels."""
    windows = [(504, "6時台"), (501, "7〜9時"), (502, "9〜11時"), (503, "11〜18時")]
    window_text = "  ·  ".join(f"{label} +{BADGES[badge_id].score}pt" for badge_id, label in windows)
    levels = "  ".join(f"Lv{number} {threshold}" for number, (_, threshold) in enumerate(LEVELS, start=1))
    return [
        _header("あそびかた"),
        _section(
            "*1. 出社登録する*\n"
            "営業日の 6:00〜18:00 に、毎朝の投稿の「出社した」ボタン、ショートカット「出社した」、"
            "またはマイページのボタンで登録します。1日1回、その日はじめての登録だけが数えられます。"
        ),
        _section(
            "*2. バッジでポイントがたまる*\n"
            f"出社した時間帯でバッジがもらえます: {window_text}\n"
            "その日の一番乗り、5日連続、キリ番、ぞろ目の時刻など、ほかにもいろいろなバッジがあります。"
            "条件は「図鑑」の名前から推理してみてください。"
        ),
        _section(
            "*3. アイテムを使う*\n"
            "出社登録のあと、その日の候補3つから1つ選べます。効果は次の出社から。"
            f"持てるのは1つまでで、アイテムによる加点は1回の出社につき最大 +{ITEM_POINT_CAP}pt です。"
        ),
        _section(
            "*4. みんなで目標を目指す*\n"
            f"今週の全員の出社が「営業日 × {TEAM_GOAL_PER_BIZDAY}回」に届くと、そのあとの出社にボーナスがつきます。"
        ),
        DIVIDER,
        _section("*レベル表*  累計ポイントがこの値に届くと次のレベル"),
        _context(levels),
    ]
