"""Fill the dev database with synthetic arrivals, so a dev user has points to try rebirths and the like.

    uv run python scripts/seed_dev_db.py                 # ADMIN of .env.dev up to Lv5 (enough for a rebirth)
    uv run python scripts/seed_dev_db.py --points 1400   # up to the upper limit (でんせつのしるし)

The user's arrivals are one per business day, ending yesterday, as many as it takes to reach --points;
--others fake users arrive on some of those days too. Arrivals are stored without a Slack post, so they
never reach Slack, and days the user already has are skipped. Only a database whose file name contains
"dev" is written to: never point this at production.
"""

import argparse
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

os.environ.setdefault("DOTENV_PATH", ".env.dev")

from sqlalchemy import select

from hikarie_bot.arrivals import compute_arrivals
from hikarie_bot.constants import JST
from hikarie_bot.database import get_db
from hikarie_bot.engine import compute
from hikarie_bot.models import ArrivalEvent
from hikarie_bot.settings import get_settings
from hikarie_bot.utils import get_level, is_jp_bizday

MAX_DAYS = 2000


def bizdays_until(last: date, count: int) -> list[date]:
    """Return the last `count` business days up to and including `last`, oldest first."""
    days: list[date] = []
    day = last
    while len(days) < count:
        if is_jp_bizday(day):
            days.append(day)
        day -= timedelta(days=1)
    return days[::-1]


def synthetic_arrivals(user: str, days: list[date], others: int) -> list[tuple[str, datetime]]:
    """Return the user's arrival on each day (08:00-09:59) and some fake users' (09:00-11:59), in time order."""
    rng = random.Random(0)  # noqa: S311  # synthetic data, not security
    arrivals = [
        (user, datetime.combine(day, time(8 + index % 2, rng.randint(0, 59)), tzinfo=JST))
        for index, day in enumerate(days)
    ]
    arrivals += [
        (f"U0DEVSEED{n}", datetime.combine(day, time(rng.randint(9, 11), rng.randint(0, 59)), tzinfo=JST))
        for day in days
        for n in range(1, others + 1)
        if rng.random() < 0.5  # noqa: PLR2004
    ]
    return sorted(arrivals, key=lambda arrival: arrival[1])


def plan(
    user: str, points: int, others: int, yesterday: date, existing: list[tuple[str, datetime]]
) -> list[tuple[str, datetime]]:
    """Return the fewest new arrivals that, with the existing ones, bring the user to `points`.

    A day a user already has keeps its stored arrival.
    """
    if user in (engine := compute(sorted(existing, key=lambda arrival: arrival[1]))).users and (
        engine.users[user].score >= points
    ):
        return []  # already there
    taken = {(user_id, at.astimezone(JST).date()) for user_id, at in existing}
    count = 1
    while count <= MAX_DAYS:
        new = [
            (user_id, at)
            for user_id, at in synthetic_arrivals(user, bizdays_until(yesterday, count), others)
            if (user_id, at.date()) not in taken
        ]
        engine = compute(sorted([*existing, *new], key=lambda arrival: arrival[1]))
        if engine.users[user].score >= points:
            return new
        count += max(1, count // 10)
    msg = f"{MAX_DAYS} days of arrivals do not reach {points}pt"
    raise SystemExit(msg)


def main() -> None:
    """Seed the dev database."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", help="the user to give points (default: ADMIN of the env file)")
    parser.add_argument("--points", type=int, default=111, help="the points to reach (default: 111, Lv5)")
    parser.add_argument("--others", type=int, default=3, help="fake users arriving on some of the days")
    args = parser.parse_args()

    settings = get_settings()
    user = args.user or settings.admin
    if not user or user == "UXXXX":
        sys.exit("set ADMIN in .env.dev (your user ID in the dev workspace) or pass --user")
    database = settings.database_url
    if "dev" not in Path(database.removeprefix("sqlite:///")).name:
        sys.exit(f"refusing to write to {database}: only a dev database (a file name containing 'dev') is seeded")

    yesterday = datetime.now(JST).date() - timedelta(days=1)
    with get_db() as session:
        existing = [
            (user_id, at.astimezone(JST))
            for user_id, at in session.execute(select(ArrivalEvent.user_id, ArrivalEvent.occurred_at))
        ]
        new = plan(user, args.points, args.others, yesterday, existing)
        session.add_all(ArrivalEvent(user_id=user_id, occurred_at=at, source="seed") for user_id, at in new)
        session.commit()
        engine = compute_arrivals(session)
    score = engine.users[user].score
    level = get_level(score)
    print(f"{database}: added {len(new)} arrivals; {user} now has {score}pt (Lv{level.number} {level.name})")


if __name__ == "__main__":
    main()
