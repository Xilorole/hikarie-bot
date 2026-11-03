"""Render user-facing Slack messages and issue Block Kit Builder URLs for visual checks.

By default the messages are rendered from a synthetic in-memory dataset, so no
real database or Slack data is touched. ``--database-url`` renders from an
existing database instead; it is opened read-only and never committed.
"""

import json
import random
import sys
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

import asyncclick as click
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.constants import JST
from hikarie_bot.db_data.items import WEEKLY_PASS, offers
from hikarie_bot.engine import ArrivalResult, BadgeEngine, Outlook, TeamProgress
from hikarie_bot.modals import (
    achievement_view,
    goals_message,
    goals_text,
    initial_message,
    item_pick_view,
    item_picked_message,
    item_review_view,
    notice_view,
    point_get_message,
    registry_message,
    render,
)
from hikarie_bot.picks import held_notice, picked_notice
from hikarie_bot.settings import get_settings
from hikarie_bot.usage import describe_usage, last_full_week, usage_report
from hikarie_bot.utils import is_jp_bizday, leveled_up

# Without a workspace ID the builder opens in the workspace the browser is signed in to; an unknown ID fails.
BLOCK_KIT_BUILDER_URL = "https://app.slack.com/block-kit-builder"

SYNTHETIC_START = datetime(2025, 4, 7, tzinfo=JST)
SYNTHETIC_MIN_DAYS = 15
SYNTHETIC_MAX_DAYS = 120
SYNTHETIC_USERS = [f"U0PREVIEW{i}" for i in range(1, 6)]
SYNTHETIC_ATTENDANCE_RATE = 0.7
LEVEL_UP_USER = "U0PREVIEWL"


def create_block_kit_url(payload: dict[str, Any], workspace_id: str | None = None) -> str:
    """Create a Block Kit Builder URL for a message (``{"blocks": ...}``) or a view payload."""
    encoded = urllib.parse.quote(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    workspace = f"/{workspace_id}" if workspace_id else ""
    return f"{BLOCK_KIT_BUILDER_URL}{workspace}#{encoded}"


def create_clickable_link(url: str, display_text: str) -> str:
    """Create a clickable terminal link using the OSC 8 escape sequence."""
    return f"\033]8;;{url}\033\\{display_text}\033]8;;\033\\"


@dataclass
class PreviewContext:
    """The data a preview is rendered from."""

    engine: BadgeEngine
    reference: datetime
    fastest_user_id: str
    user_id: str
    level_up_user_id: str | None


@dataclass
class Preview:
    """A user-facing message and how to render it."""

    name: str
    description: str
    render: Callable[[PreviewContext], dict[str, Any] | None]


def _team(context: PreviewContext, hour: int = 23) -> TeamProgress:
    """Return the week's progress at an hour of the reference day, shown even before the team goal applies."""
    return context.engine.week_progress(context.reference.replace(hour=hour, minute=0))


def _point_get_blocks(_context: PreviewContext, arrival: ArrivalResult) -> dict[str, Any]:
    return {"blocks": render(point_get_message(arrival))}


def _outlook(context: PreviewContext, arrival: ArrivalResult) -> Outlook:
    """Return the arrival's outlook with the week's progress, shown even before the team goal applies."""
    return replace(context.engine.outlook(arrival), team=context.engine.week_progress(arrival.time))


def _arrival_goals(context: PreviewContext) -> dict[str, Any] | None:
    arrival = context.engine.arrival_of(context.user_id, context.reference.date())
    return None if arrival is None else {"blocks": render(goals_message(_outlook(context, arrival)))}


def _point_get(context: PreviewContext, user_id: str | None) -> dict[str, Any] | None:
    arrival = None if user_id is None else context.engine.arrival_of(user_id, context.reference.date())
    return None if arrival is None else _point_get_blocks(context, arrival)


def _registry(context: PreviewContext) -> dict[str, Any]:
    return {"blocks": render(registry_message(context.engine.arrivals_on(context.reference.date()), _team(context)))}


def _point_get_item(context: PreviewContext) -> dict[str, Any] | None:
    arrival = next(
        (
            arrival
            for arrival in context.engine.arrivals_on(context.reference.date())
            if any(effect.points for effect in arrival.item_effects)
        ),
        None,
    )
    return None if arrival is None else _point_get_blocks(context, arrival)


def _item_pick(context: PreviewContext) -> dict[str, Any]:
    day = context.reference.date()
    return item_pick_view(offers(context.user_id, day), "C0PREVIEW", "0000000000.000000", day)


def _item_review(context: PreviewContext) -> dict[str, Any]:
    offered = offers(context.user_id, context.reference.date())
    return item_review_view(offered, picked_notice(offered[1].id), offered[1].id)


def _item_review_held(context: PreviewContext) -> dict[str, Any]:
    offered = offers(context.user_id, context.reference.date())
    notice = held_notice(WEEKLY_PASS, context.reference.date() + timedelta(days=4))
    return item_review_view(offered, notice)


def _item_picked(context: PreviewContext) -> dict[str, Any]:
    item = offers(context.user_id, context.reference.date())[0]
    return {"blocks": render(item_picked_message(context.user_id, item))}


def _achievement(context: PreviewContext) -> dict[str, Any]:
    now = context.reference.replace(hour=18)
    outlook = replace(context.engine.status_outlook(context.user_id, now), team=context.engine.week_progress(now))
    return achievement_view(context.engine, context.user_id, jst_datetime=now, outlook=outlook).to_dict()


def _arrive_shortcut(context: PreviewContext) -> dict[str, Any]:
    text = "出社登録しました。<#C0PREVIEW> の今日の投稿のスレッドで確認できます"
    arrival = context.engine.arrival_of(context.user_id, context.reference.date())
    if arrival is not None:
        text += f"\n\n*つぎのもくひょう*\n{goals_text(_outlook(context, arrival))}"
    return notice_view(text)


def _weekly_usage(context: PreviewContext) -> dict[str, Any]:
    text = describe_usage(usage_report(context.engine, last_full_week(context.reference.date())))
    return {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]}


PREVIEWS = [
    Preview(
        "initial_message",
        "毎朝の出社確認メッセージ",
        lambda context: {"blocks": render(initial_message(_team(context, hour=6)))},
    ),
    Preview("registry_message", "出社登録後に更新される出社確認メッセージ", _registry),
    Preview(
        "point_get_fastest",
        "最速出社時のポイント獲得メッセージ",
        lambda context: _point_get(context, context.fastest_user_id),
    ),
    Preview(
        "point_get",
        "出社登録時のポイント獲得メッセージ",
        lambda context: _point_get(context, context.user_id),
    ),
    Preview(
        "point_get_level_up",
        "レベルアップ時のポイント獲得メッセージ",
        lambda context: _point_get(context, context.level_up_user_id),
    ),
    Preview("point_get_item", "アイテム効果つきのポイント獲得メッセージ", _point_get_item),
    Preview("arrival_goals", "出社登録の直後に本人にだけ送る、つぎのもくひょう (ephemeral)", _arrival_goals),
    Preview("achievement_view", "ステータスモーダル (旧: 実績確認モーダル)", _achievement),
    Preview("item_pick_view", "今日のアイテムを選ぶモーダル", _item_pick),
    Preview("item_review_view", "獲得後に今日のアイテムを見返すモーダル", _item_review),
    Preview("item_review_held", "期限付きアイテムを持っていて選べない日のモーダル", _item_review_held),
    Preview("arrive_shortcut", "ショートカットから出社登録したときのモーダル", _arrive_shortcut),
    Preview("weekly_usage", "ログチャンネルに毎週送る利用状況", _weekly_usage),
    Preview("item_picked_message", "アイテム獲得をスレッドに知らせるメッセージ", _item_picked),
]
PREVIEW_NAMES = [preview.name for preview in PREVIEWS]


def _bizdays(start: datetime) -> list[datetime]:
    return [day for offset in range(SYNTHETIC_MAX_DAYS) if is_jp_bizday((day := start + timedelta(days=offset)).date())]


def build_synthetic_context() -> PreviewContext:
    """Compute deterministic arrivals that end on a level-up day (no database)."""
    engine = BadgeEngine()
    rng = random.Random(0)  # noqa: S311
    for index, day in enumerate(_bizdays(SYNTHETIC_START)):
        arrivals = [(LEVEL_UP_USER, time(9, rng.randint(0, 59)))]
        arrivals += [
            (user_id, time(rng.randint(7, 10), rng.randint(0, 59)))
            for user_id in SYNTHETIC_USERS
            if rng.random() < SYNTHETIC_ATTENDANCE_RATE
        ]
        for user_id, arrival in sorted(arrivals, key=lambda item: item[1]):
            engine.add(user_id, datetime.combine(day.date(), arrival, tzinfo=JST))
        # everyone who arrived picks the first item offered, unless they still hold one
        for user_id, _ in arrivals:
            if engine.held_item(user_id, day.date()) is None:
                engine.pick(user_id, day.date(), offers(user_id, day.date())[0].id)
        level_up = engine.arrival_of(LEVEL_UP_USER, day.date())
        level_up_day = level_up is not None and leveled_up(level_up.previous_score, level_up.current_score)
        if index + 1 >= SYNTHETIC_MIN_DAYS and level_up_day and len(arrivals) >= 3:  # noqa: PLR2004
            break
    else:
        msg = "Synthetic data did not reach a level-up day"
        raise RuntimeError(msg)

    ordered = [arrival.user_id for arrival in engine.arrivals_on(day.date())]
    return PreviewContext(
        engine=engine,
        reference=day,
        fastest_user_id=ordered[0],
        user_id=next(user_id for user_id in ordered[1:] if user_id != LEVEL_UP_USER),
        level_up_user_id=LEVEL_UP_USER,
    )


def build_database_context(session: Session, user_id: str | None, date: datetime | None) -> PreviewContext:
    """Compute the arrivals of an existing database and pick the reference day and users."""
    engine = compute_arrivals(session)
    if date is None:
        if not engine.results:
            msg = "The database has no arrivals"
            raise click.ClickException(msg)
        date = engine.results[-1].time
    arrivals = engine.arrivals_on(date.date())
    ordered = [arrival.user_id for arrival in arrivals]
    if user_id is None:
        if not ordered:
            msg = f"No arrivals on {date:%Y-%m-%d}; pass --user-id or another --date"
            raise click.ClickException(msg)
        user_id = ordered[-1]
    level_up_user_id = next(
        (arrival.user_id for arrival in arrivals if leveled_up(arrival.previous_score, arrival.current_score)),
        None,
    )
    return PreviewContext(
        engine=engine,
        reference=date.replace(hour=18, minute=0, second=0, microsecond=0),
        fastest_user_id=ordered[0] if ordered else user_id,
        user_id=user_id,
        level_up_user_id=level_up_user_id,
    )


def _read_only_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database not in {None, "", ":memory:"}:
        return f"sqlite:///file:{Path(url.database).resolve()}?mode=ro&uri=true"
    return database_url


def resolve_workspace_id(workspace_id: str | None) -> str | None:
    """Return the team ID from the option or SLACK_WORKSPACE_ID, or None to leave it out of the URLs."""
    return workspace_id or get_settings().slack_workspace_id or None


@click.command()
@click.argument("names", nargs=-1, type=click.Choice(PREVIEW_NAMES))
@click.option(
    "--workspace-id",
    help="Slack team ID to put in the Block Kit Builder URLs (default: none, which opens the signed-in workspace).",
)
@click.option("--database-url", help="Render from this database (read-only) instead of synthetic data.")
@click.option("--user-id", help="With --database-url: the user to render user-specific messages for.")
@click.option(
    "--date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="With --database-url: the day to render (default: the latest arrival day).",
)
@click.option("--output-dir", type=click.Path(path_type=Path), default=Path("test_modals"), show_default=True)
def preview(  # noqa: PLR0913, PLR0917
    names: tuple[str, ...],
    workspace_id: str | None,
    database_url: str | None,
    user_id: str | None,
    date: datetime | None,
    output_dir: Path,
) -> None:
    """Render user-facing messages and print Block Kit Builder URLs.

    NAMES selects messages to render (default: all).
    """
    team_id = resolve_workspace_id(workspace_id)
    logger.disable("hikarie_bot")
    if database_url is None:
        context = build_synthetic_context()
    else:
        engine = create_engine(_read_only_url(database_url))
        try:
            with Session(engine) as session:
                context = build_database_context(session, user_id, date.replace(tzinfo=JST) if date else None)
        finally:
            engine.dispose()
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = [preview for preview in PREVIEWS if not names or preview.name in names]
    lines = [f"# Block Kit previews ({'synthetic data' if database_url is None else 'database'})", ""]
    click.echo(f"📅 {context.reference:%Y-%m-%d} / user: {context.user_id}")
    for item in selected:
        payload = item.render(context)
        if payload is None:
            click.echo(f"⏭️  {item.name}: no matching data for this day")
            continue
        (output_dir / f"{item.name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        url = create_block_kit_url(payload, team_id)
        link = f": {create_clickable_link(url, '🔗 open')}" if sys.stdout.isatty() else ""
        click.echo(f"✅ {item.name} ({item.description}){link}")
        click.echo(f"   {url}")
        lines.append(f"- [{item.name}]({url}) — {item.description}")
    index = output_dir / "previews.md"
    index.write_text("\n".join(lines) + "\n")
    click.echo(f"📂 JSON and {index.name} saved in: {output_dir.resolve()}")
