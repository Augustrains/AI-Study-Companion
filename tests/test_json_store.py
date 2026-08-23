import json
import unittest
from pathlib import Path

from modules.common import api as common_api
from tests.test_support import test_directory


class JsonStoreTest(unittest.TestCase):
    def test_save_modes(self) -> None:
        with test_directory("json-store-modes") as directory:
            path = Path(directory) / "records.json"
            store = common_api.json_storage.JsonStore()

            store.save(path=path, content=["first"], mode="overwrite")
            store.save(path=path, content="last", mode="append")
            store.save(path=path, content="middle", mode="insert", index=1)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                ["first", "middle", "last"],
            )

    def test_upsert_mode_writes_nested_key_path(self) -> None:
        with test_directory("json-store-upsert") as directory:
            path = Path(directory) / "profiles.json"
            store = common_api.json_storage.JsonStore()

            store.save(
                path=path,
                content={"background": "old"},
                mode="upsert",
                key_path=["user_001", "machine_learning"],
            )
            store.save(
                path=path,
                content={"background": "new"},
                mode="upsert",
                key_path=["user_001", "machine_learning"],
            )

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["user_001"]["machine_learning"]["background"], "new")


if __name__ == "__main__":
    unittest.main()
