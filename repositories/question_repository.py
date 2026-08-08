from __future__ import annotations

import json
from pathlib import Path

from domain.models import Question


class QuestionRepository:
    """读取静态题库；默认题库位置由仓储层负责。"""

    DEFAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "questions"

    def __init__(self, questions_dir: str | Path | None = None) -> None:
        self.questions_dir = Path(questions_dir) if questions_dir is not None else self.DEFAULT_DIR

    def get_diagnosis_questions(self, book_id: str, learning_goal: str) -> list[Question]:
        del learning_goal  # 预留：后续按目标筛选题目难度和范围。
        path = self.questions_dir / f"{book_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"未找到题库: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [Question(**item) for item in payload["questions"]]
