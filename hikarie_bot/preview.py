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
from zoneinfo import ZoneInfo

import asyncclick as click
from loguru import logger
from slack_sdk import WebClient
from sqlalchemy import create_engine, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from hikarie_bot.curd import initially_insert_badge_data, insert_arrival_action
from hikarie_bot.database import BaseSchema
from hikarie_bot.modals import (
    AchievementView,
    AlreadyRegisteredMessage,
    FastestArrivalMessage,
    InitialMessage,
    PointGetMessage,
    RegistryMessage,
    WeeklyMessage,
)
from hikarie_bot.models import GuestArrivalInfo, User
from hikarie_bot.settings import SLACK_BOT_TOKEN, SLACK_WORKSPACE_ID
from hikarie_bot.utils import is_jp_bizday

JST = ZoneInfo("Asia/Tokyo")
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

    session: Session
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


def _arrival_of(context: PreviewContext, user_id: str) -> GuestArrivalInfo | None:
    start = context.reference.replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        context.session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.user_id == user_id)
        .filter(GuestArrivalInfo.arrival_time >= start.replace(tzinfo=None))
        .filter(GuestArrivalInfo.arrival_time < (start + timedelta(days=1)).replace(tzinfo=None))
        .one_or_none()
    )


def _point_get(context: PreviewContext, user_id: str | None, *, initial_arrival: bool) -> dict[str, Any] | None:
    # PointGetMessage shows the user's latest score, so it only renders on the user's latest arrival day.
    if user_id is None or _arrival_of(context, user_id) is None:
        return None
    message = PointGetMessage(
        session=context.session,
        user_id=user_id,
        jst_datetime=context.reference,
        initial_arrival=initial_arrival,
    )
    return {"blocks": message.render()}


def _registry(context: PreviewContext) -> dict[str, Any]:
    end_of_day = context.reference.replace(hour=18, minute=0, second=0, microsecond=0)
    return {"blocks": RegistryMessage(session=context.session, jst_datetime=end_of_day).render()}


def _already_registered(context: PreviewContext) -> dict[str, Any] | None:
    arrival = _arrival_of(context, context.user_id)
    if arrival is None:
        return None
    return {"blocks": AlreadyRegisteredMessage(user_id=context.user_id, jst_datetime=arrival.arrival_time).render()}


def _fastest_arrival(context: PreviewContext) -> dict[str, Any] | None:
    arrival = _arrival_of(context, context.fastest_user_id)
    if arrival is None:
        return None
    message = FastestArrivalMessage(user_id=context.fastest_user_id, jst_datetime=arrival.arrival_time)
    return {"blocks": message.render()}


def _weekly(context: PreviewContext) -> dict[str, Any]:
    # The weekly report covers the seven days before report_date; end it on the reference day.
    report_date = (context.reference + timedelta(days=1)).replace(hour=6, minute=0)
    return {"blocks": WeeklyMessage(session=context.session, report_date=report_date).render()}


def _achievement(context: PreviewContext) -> dict[str, Any]:
    return AchievementView(session=context.session, user_id=context.user_id, jst_datetime=context.reference).to_dict()


PREVIEWS = [
    Preview("initial_message", "毎朝の出社確認メッセージ", lambda _: {"blocks": InitialMessage().render()}),
    Preview("registry_message", "出社登録後に更新される出社確認メッセージ", _registry),
    Preview(
        "point_get_fastest",
        "最速出社時のポイント獲得メッセージ",
        lambda context: _point_get(context, context.fastest_user_id, initial_arrival=True),
    ),
    Preview(
        "point_get",
        "出社登録時のポイント獲得メッセージ",
        lambda context: _point_get(context, context.user_id, initial_arrival=False),
    ),
    Preview(
        "point_get_level_up",
        "レベルアップ時のポイント獲得メッセージ",
        lambda context: _point_get(context, context.level_up_user_id, initial_arrival=False),
    ),
    Preview("already_registered", "出社登録済みメッセージ", _already_registered),
    Preview("fastest_arrival", "最速出社メッセージ", _fastest_arrival),
    Preview("weekly_message", "週次レポート", _weekly),
    Preview("achievement_view", "実績確認モーダル", _achievement),
]
PREVIEW_NAMES = [preview.name for preview in PREVIEWS]


def _bizdays(start: datetime) -> list[datetime]:
    return [day for offset in range(SYNTHETIC_MAX_DAYS) if is_jp_bizday((day := start + timedelta(days=offset)).date())]


def build_synthetic_context(session: Session) -> PreviewContext:
    """Fill an empty database with deterministic arrivals that end on a level-up day."""
    initially_insert_badge_data(session)
    rng = random.Random(0)  # noqa: S311
    for index, day in enumerate(_bizdays(SYNTHETIC_START)):
        arrivals = [(LEVEL_UP_USER, time(9, rng.randint(0, 59)))]
        arrivals += [
            (user_id, time(rng.randint(7, 10), rng.randint(0, 59)))
            for user_id in SYNTHETIC_USERS
            if rng.random() < SYNTHETIC_ATTENDANCE_RATE
        ]
        for user_id, arrival in sorted(arrivals, key=lambda item: item[1]):
            insert_arrival_action(session, datetime.combine(day.date(), arrival, tzinfo=JST), user_id)
        level_up_user = session.query(User).filter(User.id == LEVEL_UP_USER).one()
        if index + 1 >= SYNTHETIC_MIN_DAYS and level_up_user.level_uped and len(arrivals) >= 3:  # noqa: PLR2004
            break
    else:
        msg = "Synthetic data did not reach a level-up day"
        raise RuntimeError(msg)

    ordered = [arrival.user_id for arrival in _arrivals_on(session, day)]
    return PreviewContext(
        session=session,
        reference=day,
        fastest_user_id=ordered[0],
        user_id=next(user_id for user_id in ordered[1:] if user_id != LEVEL_UP_USER),
        level_up_user_id=LEVEL_UP_USER,
    )


def _arrivals_on(session: Session, day: datetime) -> list[GuestArrivalInfo]:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    return (
        session.query(GuestArrivalInfo)
        .filter(GuestArrivalInfo.arrival_time >= start)
        .filter(GuestArrivalInfo.arrival_time < start + timedelta(days=1))
        .order_by(GuestArrivalInfo.arrival_time)
        .all()
    )


def build_database_context(session: Session, user_id: str | None, date: datetime | None) -> PreviewContext:
    """Pick the reference day and users from an existing database."""
    if date is None:
        latest = session.query(func.max(GuestArrivalInfo.arrival_time)).scalar()
        if latest is None:
            msg = "The database has no arrivals"
            raise click.ClickException(msg)
        date = latest.replace(tzinfo=JST)
    ordered = [arrival.user_id for arrival in _arrivals_on(session, date)]
    if user_id is None:
        if not ordered:
            msg = f"No arrivals on {date:%Y-%m-%d}; pass --user-id or another --date"
            raise click.ClickException(msg)
        user_id = ordered[-1]
    level_up_user_id = next(
        (
            user.id
            for user in session.query(User).filter(User.id.in_(ordered), User.level_uped.is_(True)).all()
            if _same_day(user.update_datetime, date)
        ),
        None,
    )
    return PreviewContext(
        session=session,
        reference=date.replace(hour=18, minute=0, second=0, microsecond=0),
        fastest_user_id=ordered[0] if ordered else user_id,
        user_id=user_id,
        level_up_user_id=level_up_user_id,
    )


def _same_day(value: datetime | None, day: datetime) -> bool:
    return value is not None and value.date() == day.date()


def _read_only_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database not in {None, "", ":memory:"}:
        return f"sqlite:///file:{Path(url.database).resolve()}?mode=ro&uri=true"
    return database_url


def resolve_workspace_id(workspace_id: str | None) -> str:
    """Resolve the team ID from the option, the environment, or auth.test (read-only)."""
    if workspace_id or SLACK_WORKSPACE_ID:
        return workspace_id or SLACK_WORKSPACE_ID
    if SLACK_BOT_TOKEN:
        return WebClient(token=SLACK_BOT_TOKEN).auth_test()["team_id"]
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
def preview(  # noqa: PLR0913
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
    engine = create_engine(_read_only_url(database_url) if database_url else "sqlite://")
    if database_url is None:
        BaseSchema.metadata.create_all(engine)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = [preview for preview in PREVIEWS if not names or preview.name in names]
    lines = [f"# Block Kit previews ({'synthetic data' if database_url is None else 'database'})", ""]
    try:
        with Session(engine) as session:
            if database_url is None:
                context = build_synthetic_context(session)
            else:
                context = build_database_context(session, user_id, date.replace(tzinfo=JST) if date else None)
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
            session.rollback()
    finally:
        engine.dispose()
    index = output_dir / "previews.md"
    index.write_text("\n".join(lines) + "\n")
    click.echo(f"📂 JSON and {index.name} saved in: {output_dir.resolve()}")
