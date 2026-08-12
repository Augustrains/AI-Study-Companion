from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


TEST_DATA_ROOT = Path(__file__).resolve().parent / ".test-data"


@contextmanager
def test_directory(name: str) -> Iterator[Path]:
    """Create an isolated writable test directory inside the workspace."""
    directory = TEST_DATA_ROOT / name
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        yield directory
    finally:
        if directory.exists():
            shutil.rmtree(directory)


# This helper is imported by test modules; prevent pytest from collecting the
# imported callable as a parameterized test function.
test_directory.__test__ = False
