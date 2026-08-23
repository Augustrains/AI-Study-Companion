import os
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.common.config import Settings


class EmbeddingConfigTest(unittest.TestCase):
    def test_bge_m3_is_the_default_embedding_and_uses_a_separate_index(self):
        project_dir = Path("D:/study-companion-config-test")
        with patch.dict(os.environ, {}, clear=True), patch("modules.common.config.Path.exists", return_value=False):
            settings = Settings.from_env(project_dir)

            self.assertEqual(settings.embedding_model, "BAAI/bge-m3")
            self.assertEqual(settings.qdrant_path, settings.data_dir / "qdrant-bge-m3")

    def test_downloaded_bge_m3_directory_is_preferred(self):
        project_dir = Path("D:/study-companion-config-test")
        with patch.dict(os.environ, {}, clear=True), patch("modules.common.config.Path.exists", return_value=True):
            local_model = project_dir / "models" / "bge-m3"

            settings = Settings.from_env(project_dir)

            self.assertEqual(settings.embedding_model, str(local_model.resolve()))


if __name__ == "__main__":
    unittest.main()
