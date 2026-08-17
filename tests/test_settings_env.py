from __future__ import annotations

import os

import pytest

from modules.common.config import Settings
from modules.common.errors import ConfigurationError


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
            "STUDY_COMPANION_JWT_SECRET=dotenv-secret-with-at-least-32-characters\n",
            encoding="utf-8",
        )

        settings = Settings.from_env(tmp_path)

        assert settings.allow_dev_identity is False
        assert settings.auto_create_schema is False
        assert settings.database_url.endswith("configured.sqlite3")
        assert settings.jwt_secret == "dotenv-secret-with-at-least-32-characters"
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.mark.parametrize(
    "placeholder",
    [
        "replace-with-a-long-random-secret",
        "paste-generated-64-character-secret-here",
    ],
)
def test_production_identity_rejects_public_placeholder_secret(
    tmp_path,
    monkeypatch,
    placeholder: str,
) -> None:
    monkeypatch.setenv("STUDY_COMPANION_ALLOW_DEV_IDENTITY", "false")
    monkeypatch.setenv("STUDY_COMPANION_JWT_SECRET", placeholder)

    settings = Settings.from_env(tmp_path)

    with pytest.raises(ConfigurationError, match="non-placeholder"):
        _ = settings.jwt_secret


def test_production_identity_rejects_automatic_schema_creation(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("STUDY_COMPANION_ALLOW_DEV_IDENTITY", "false")
    monkeypatch.setenv("STUDY_COMPANION_AUTO_CREATE_SCHEMA", "true")

    settings = Settings.from_env(tmp_path)

    with pytest.raises(ConfigurationError, match="must be false"):
        _ = settings.auto_create_schema
