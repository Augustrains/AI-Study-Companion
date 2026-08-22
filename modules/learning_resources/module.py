"""
知识点延伸学习资源。

数据源：data/learning_resources/resources.json
    按 knowledge_point_id 映射到一组已核实的外部学习资源（B 站 / YouTube / MOOC / 在线教材）。

维护约定：
    - 只写入**实际访问核实过**的链接。资源文件里的每条都经过人工/工具校验，
      不要凭印象或让模型直接生成 URL，失效或指向错误内容的链接比没有链接更糟。
    - 新增资源时补充 title / platform / url / language / kind / note 六个字段即可，
      不需要改动本模块代码。
    - 知识点 ID 必须与 data/question_new/知识点/*.json 中的真实 ID 一致，
      否则前端按知识点查询时取不到。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LearningResourceModule:
    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "learning_resources" / "resources.json"

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else self.DEFAULT_PATH

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        resources = payload.get("resources")
        return resources if isinstance(resources, dict) else {}

    def for_knowledge_point(self, knowledge_point_id: str) -> list[dict[str, Any]]:
        """返回某个知识点的资源列表；没有收录时返回空列表，由前端展示空态。"""
        return list(self._read().get(str(knowledge_point_id), []))

    def for_knowledge_points(self, knowledge_point_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        """批量查询，用于任务详情（一个任务可能关联多个知识点）。"""
        data = self._read()
        return {point_id: list(data.get(point_id, [])) for point_id in knowledge_point_ids}

    def catalog(self) -> dict[str, list[dict[str, Any]]]:
        """全部已收录资源，供「学习资源」页面按知识点浏览。"""
        return self._read()

    def covered_knowledge_point_ids(self) -> set[str]:
        return set(self._read().keys())
