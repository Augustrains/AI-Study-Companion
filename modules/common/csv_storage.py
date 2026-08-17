"""通用 CSV 文件读取工具。"""

from __future__ import annotations

import csv
from pathlib import Path

from modules.common.errors import StorageReadError


class CsvContentReader:
    """读取原始 CSV 内容，不感知具体业务模型。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> list[dict[str, str]]:
        """读取 CSV，并将每一行返回为字典。"""
        if not self.path.exists():
            raise StorageReadError(f"CSV resource does not exist: {self.path}")
        try:
            with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        except OSError as exc:
            raise StorageReadError(f"CSV resource cannot be read: {self.path}", cause=exc) from exc
