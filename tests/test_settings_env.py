from __future__ import annotations

import os

from modules.common.config import Settings


def test_settings_loads_project_dotenv_before_reading_global_configuration(
    tmp_path,
) -> None:
    names = [
        "STUDY_COMPANION_ALLOW_DEV_IDENTITY",
        "STUDY_COMPANION_DATABASE_URL",
        "STUDY_COMPANION_JWT_SECRET",
    ]
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ.pop(name, None)
    try:
        (tmp_path / ".env").write_text(
            "STUDY_COMPANION_ALLOW_DEV_IDENTITY=false\n"
            "STUDY_COMPANION_DATABASE_URL=sqlite+pysqlite:///configured.sqlite3\n"
            "STUDY_COMPANION_JWT_SECRET=dotenv-secret\n",
            encoding="utf-8",
        )

        settings = Settings.from_env(tmp_path)

        assert settings.allow_dev_identity is False
        assert settings.database_url.endswith("configured.sqlite3")
        assert settings.jwt_secret == "dotenv-secret"
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
