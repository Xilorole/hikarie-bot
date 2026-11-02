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
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

import asyncclick as click
from loguru import logger
from slack_sdk import WebClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.engine import JST, BadgeEngine
from hikarie_bot.modals import (
    AchievementView,
    InitialMessage,
    PointGetMessage,
    RegistryMessage,
)
from hikarie_bot.settings import get_settings
from hikarie_bot.utils import is_jp_bizday, is_level_uped

BLOCK_KIT_BUILDER_URL = "https://app.slack.com/block-kit-builder/{workspace_id}#{payload}"

SYNTHETIC_START = datetime(2025, 4, 7, tzinfo=JST)
SYNTHETIC_MIN_DAYS = 15
SYNTHETIC_MAX_DAYS = 120
SYNTHETIC_USERS = [f"U0PREVIEW{i}" for i in range(1, 6)]
SYNTHETIC_ATTENDANCE_RATE = 0.7
LEVEL_UP_USER = "U0PREVIEWL"


def create_block_kit_url(payload: dict[str, Any], workspace_id: str) -> str:
    """Create a Block Kit Builder URL for a message (``{"blocks": ...}``) or a view payload."""
    encoded = urllib.parse.quote(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return BLOCK_KIT_BUILDER_URL.format(workspace_id=workspace_id, payload=encoded)


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


def _point_get(context: PreviewContext, user_id: str | None) -> dict[str, Any] | None:
    arrival = None if user_id is None else context.engine.arrival_of(user_id, context.reference.date())
    return None if arrival is None else {"blocks": PointGetMessage(arrival).render()}


def _registry(context: PreviewContext) -> dict[str, Any]:
    return {"blocks": RegistryMessage(context.engine.arrivals_on(context.reference.date())).render()}


def _achievement(context: PreviewContext) -> dict[str, Any]:
    return AchievementView(context.engine, context.user_id, jst_datetime=context.reference).to_dict()


PREVIEWS = [
    Preview("initial_message", "毎朝の出社確認メッセージ", lambda _: {"blocks": InitialMessage().render()}),
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
    Preview("achievement_view", "実績確認モーダル", _achievement),
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
        level_up = engine.arrival_of(LEVEL_UP_USER, day.date())
        leveled_up = level_up is not None and is_level_uped(level_up.previous_score, level_up.current_score)
        if index + 1 >= SYNTHETIC_MIN_DAYS and leveled_up and len(arrivals) >= 3:  # noqa: PLR2004
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
        (arrival.user_id for arrival in arrivals if is_level_uped(arrival.previous_score, arrival.current_score)),
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


def resolve_workspace_id(workspace_id: str | None) -> str:
    """Resolve the team ID from the option, the environment, or auth.test (read-only)."""
    settings = get_settings()
    if workspace_id := workspace_id or settings.slack_workspace_id:
        return workspace_id
    if settings.slack_bot_token:
        return WebClient(token=settings.slack_bot_token).auth_test()["team_id"]
    msg = "Pass --workspace-id, or set SLACK_WORKSPACE_ID or SLACK_BOT_TOKEN"
    raise click.ClickException(msg)


@click.command()
@click.argument("names", nargs=-1, type=click.Choice(PREVIEW_NAMES))
@click.option("--workspace-id", help="Slack team ID used in the Block Kit Builder URL (e.g. T0123456).")
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
