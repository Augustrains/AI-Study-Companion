"""Create the learner-goal table and import the legacy goals.json rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import inspect

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from modules.common.config import Settings
from modules.common.database import create_mysql_engine
from modules.learner_goals.models import LearnerGoal
from modules.learner_goals.repository import MysqlLearnerGoalRepository


DEFAULT_SOURCE = PROJECT_DIR / "data" / "learner_goals" / "goals.json"


def read_goals(path: Path) -> list[LearnerGoal]:
    if not path.exists():
        return []
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return [LearnerGoal.from_dict(row) for row in payload.values() if isinstance(row, dict)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--apply", action="store_true", help="create the table and import rows")
    args = parser.parse_args()

    goals = read_goals(args.source)
    print(f"source={args.source}")
    print(f"rows={len(goals)}")
    for goal in goals:
        print(f"  user_id={goal.user_id} book_id={goal.book_id} weekly_hours={goal.weekly_hours}")

    if not args.apply:
        print("dry-run only; pass --apply to write MySQL")
        return

    engine = create_mysql_engine(Settings.from_env())
    try:
        if "learning_goal" not in inspect(engine).get_table_names():
            raise RuntimeError("existing learning_goal table was not found")
        repository = MysqlLearnerGoalRepository(engine)
        for goal in goals:
            repository.upsert(goal)
        verified = sum(
            repository.get(user_id=goal.user_id, book_id=goal.book_id) is not None
            for goal in goals
        )
        print(f"table_exists={'learning_goal' in inspect(engine).get_table_names()}")
        print(f"imported={len(goals)}")
        print(f"verified={verified}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
