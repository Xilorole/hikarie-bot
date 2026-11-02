import json
import urllib.parse
from pathlib import Path

import pytest
from asyncclick.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hikarie_bot.database import BaseSchema
from hikarie_bot.models import ArrivalEvent
from hikarie_bot.preview import (
    PREVIEWS,
    build_database_context,
    build_synthetic_context,
    create_block_kit_url,
    preview,
)


def test_create_block_kit_url_round_trips_payload() -> None:
    """The URL fragment decodes back to the original payload, including Japanese text."""
    payload = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "出社しました <@U1>"}}]}
    url = create_block_kit_url(payload, "T0123")

    base, fragment = url.split("#", 1)
    assert base == "https://app.slack.com/block-kit-builder/T0123"
    assert json.loads(urllib.parse.unquote(fragment)) == payload


def test_synthetic_context_renders_every_preview() -> None:
    """Synthetic data ends on a day where every message, including a level-up, can be rendered."""
    context = build_synthetic_context()
    payloads = {item.name: item.render(context) for item in PREVIEWS}

    assert all(payload is not None for payload in payloads.values())
    assert payloads["achievement_view"]["type"] == "modal"
    assert "LvUP!" in payloads["point_get_level_up"]["blocks"][0]["text"]["text"]
    assert "最速" in payloads["point_get_fastest"]["blocks"][0]["text"]["text"]
    assert all(len(payload["blocks"]) <= 50 for name, payload in payloads.items() if name != "achievement_view")


@pytest.mark.asyncio
async def test_preview_reads_database_without_writing(tmp_path: Path) -> None:
    """--database-url renders from an existing SQLite file and leaves it unchanged."""
    database = tmp_path / "data.db"
    engine = create_engine(f"sqlite:///{database}")
    BaseSchema.metadata.create_all(engine)
    results = build_synthetic_context().engine.results
    with Session(engine) as session:
        session.add_all(ArrivalEvent(user_id=r.user_id, occurred_at=r.time, source="button") for r in results)
        session.commit()
    engine.dispose()
    before = database.read_bytes()

    output_dir = tmp_path / "out"
    result = await CliRunner().invoke(
        preview,
        ["--workspace-id", "T0123", "--database-url", f"sqlite:///{database}", "--output-dir", str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    assert database.read_bytes() == before
    assert results
    assert (output_dir / "achievement_view.json").exists()
    assert "block-kit-builder/T0123#" in (output_dir / "previews.md").read_text()


def test_database_context_defaults_to_latest_arrival_day() -> None:
    """Without --date, the latest arrival day and its last arrival's user are used."""
    synthetic = build_synthetic_context()
    engine = create_engine("sqlite://")
    BaseSchema.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            ArrivalEvent(user_id=r.user_id, occurred_at=r.time, source="button") for r in synthetic.engine.results
        )
        context = build_database_context(session, user_id=None, date=None)

    assert context.reference.date() == synthetic.reference.date()
    assert context.fastest_user_id == synthetic.fastest_user_id
    assert context.level_up_user_id == synthetic.level_up_user_id
