"""通用 JSON 文件读写工具。

本模块只处理 JSON 文件本身，不解释 JSON 数据的业务含义。
业务模块通过它读取和保存数据；底层读写异常统一转换为 common.errors 中的异常。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any, Literal, Sequence

from modules.common.errors import StorageReadError, StorageWriteError


# 支持的保存模式：覆盖、追加、插入和按路径更新。
SaveMode = Literal["overwrite", "append", "insert", "upsert"]

_JSON_STORAGE_LOCK = RLock()


class JsonContentReader:
    """读取原始 JSON 内容，不感知具体业务模型。"""

    def __init__(self, path: str | Path) -> None:
        """保存待读取的文件路径。"""
        self.path = Path(path)

    def read(self, *, allow_missing: bool = False, allow_empty: bool = False) -> Any:
        """读取并解析 JSON 文件。

        文件不存在时，``allow_missing=True`` 会返回空对象；否则抛出统一的
        StorageReadError。空文件、文件系统错误和 JSON 格式错误也会统一转换。
        """
        with _JSON_STORAGE_LOCK:
            if not self.path.exists():
                if allow_missing:
                    return {}
                raise StorageReadError(f"JSON resource does not exist: {self.path}")
            try:
                content = self.path.read_text(encoding="utf-8")
                if not content.strip():
                    if allow_empty:
                        return {}
                    raise StorageReadError(f"JSON resource is empty: {self.path}")
                return json.loads(content)
            except StorageReadError:
                raise
            except (OSError, json.JSONDecodeError) as exc:
                raise StorageReadError(f"JSON resource cannot be read: {self.path}") from exc


class JsonStore:
    """按照调用方指定的模式持久化 JSON 内容。"""

    def save(
        self,
        *,
        path: str | Path,
        content: Any,
        mode: SaveMode,
        key_path: Sequence[str] | None = None,
        index: int | None = None,
    ) -> Any:
        """修改并保存 JSON 内容，返回写入后的结果。"""
        target = Path(path)
        with _JSON_STORAGE_LOCK:
            if mode == "overwrite":
                result = content
            else:
            # 追加/插入默认从数组开始，upsert 默认从对象开始。
                if not target.exists():
                    existing = [] if mode in {"append", "insert"} else {}
                else:
                    existing = JsonContentReader(target).read()
                result = self._apply_mode(existing, content, mode=mode, key_path=key_path, index=index)
            self._write(target, result)
            return result

    @staticmethod
    def _apply_mode(
        existing: Any,
        content: Any,
        *,
        mode: SaveMode,
        key_path: Sequence[str] | None,
        index: int | None,
    ) -> Any:
        """在内存中应用保存模式，并校验数据结构是否匹配。"""
        if mode == "append":
            if not isinstance(existing, list):
                raise StorageWriteError("append mode requires a JSON array")
            return [*existing, content]
        if mode == "insert":
            if not isinstance(existing, list):
                raise StorageWriteError("insert mode requires a JSON array")
            if index is None or index < 0 or index > len(existing):
                raise StorageWriteError("insert index is out of range")
            return [*existing[:index], content, *existing[index:]]
        if mode == "upsert":
            if not isinstance(existing, dict):
                raise StorageWriteError("upsert mode requires a JSON object")
            if not key_path:
                raise StorageWriteError("upsert mode requires key_path")
            result = dict(existing)
            cursor = result
            for key in key_path[:-1]:
                child = cursor.get(key)
                if child is None:
                    child = {}
                    cursor[key] = child
                if not isinstance(child, dict):
                    raise StorageWriteError(f"cannot upsert through non-object key: {key}")
                cursor = child
            cursor[key_path[-1]] = content
            return result
        raise StorageWriteError(f"unsupported save mode: {mode}")

    @staticmethod
    def _write(path: Path, content: Any) -> None:
        """创建父目录并将 JSON 内容格式化写入文件。"""
        temporary_path: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(content, ensure_ascii=False, indent=2)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        except (OSError, TypeError, ValueError) as exc:
            raise StorageWriteError(f"JSON resource cannot be written: {path}") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
