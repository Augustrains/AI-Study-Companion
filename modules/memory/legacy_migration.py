"""Idempotent migration from legacy JSON learner profiles to SQL memory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from modules.common import api as common_api
from modules.common.errors import SerializationAppError, StorageReadError
from modules.learner_profile.models import LearnerProfile
from modules.persistence.database import Database
from modules.persistence.tables import MigrationLedgerRow

from .module import MemoryModule

LEGACY_PROFILE_CONTEXT_MIGRATION_NAME = "legacy-profile-json-to-context-memory"
LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION = "1"


@dataclass(frozen=True)
class LegacyProfileMigrationResult:
    migration_name: str
    version: str
    scanned_files: int
    discovered_profiles: int
    migrated_profiles: int
    already_completed: bool


@dataclass(frozen=True)
class _ProfileCandidate:
    payload: dict[str, Any]
    location: str


class LegacyProfileContextMigration:
    """Backfill legacy profile declarations into the durable memory aggregate.

    A ledger row is written only after every profile has synchronized. Profile
    events are deterministic, including for old records without ``updated_at``,
    so retrying a partially failed run does not create another memory version.
    """

    def __init__(
        self,
        *,
        database: Database,
        memory: MemoryModule,
        profiles_path: str | Path,
        version: str = LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION,
    ) -> None:
        self.database = database
        self.memory = memory
        self.profiles_path = Path(profiles_path)
        self.version = str(version)

    def run(self) -> LegacyProfileMigrationResult:
        completed = self._completed_details()
        if completed is not None:
            return LegacyProfileMigrationResult(
                migration_name=LEGACY_PROFILE_CONTEXT_MIGRATION_NAME,
                version=self.version,
                scanned_files=int(completed.get("scanned_files", 0)),
                discovered_profiles=int(completed.get("profile_count", 0)),
                migrated_profiles=0,
                already_completed=True,
            )

        files = self._source_files()
        profiles = self._load_profiles(files)
        for profile in profiles:
            self.memory.sync_learner_profile(profile)

        details = {
            "scanned_files": len(files),
            "profile_count": len(profiles),
        }
        self._record_completion(details)
        return LegacyProfileMigrationResult(
            migration_name=LEGACY_PROFILE_CONTEXT_MIGRATION_NAME,
            version=self.version,
            scanned_files=len(files),
            discovered_profiles=len(profiles),
            migrated_profiles=len(profiles),
            already_completed=False,
        )

    def _completed_details(self) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.get(
                MigrationLedgerRow,
                (LEGACY_PROFILE_CONTEXT_MIGRATION_NAME, self.version),
            )
            return dict(row.details) if row is not None else None

    def _record_completion(self, details: dict[str, Any]) -> None:
        try:
            with self.database.session() as session:
                existing = session.get(
                    MigrationLedgerRow,
                    (LEGACY_PROFILE_CONTEXT_MIGRATION_NAME, self.version),
                )
                if existing is not None:
                    return
                session.add(
                    MigrationLedgerRow(
                        migration_name=LEGACY_PROFILE_CONTEXT_MIGRATION_NAME,
                        version=self.version,
                        details=details,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
        except IntegrityError:
            # Another process may have completed the same idempotent migration
            # between the initial ledger read and this insert.
            if self._completed_details() is None:
                raise

    def _source_files(self) -> list[Path]:
        if not self.profiles_path.exists():
            return []
        if self.profiles_path.is_file():
            if self.profiles_path.suffix.lower() != ".json":
                raise StorageReadError(
                    "legacy learner profile source must be a JSON file",
                    details={"path": str(self.profiles_path)},
                )
            return [self.profiles_path]
        if not self.profiles_path.is_dir():
            raise StorageReadError(
                "legacy learner profile source is not a directory",
                details={"path": str(self.profiles_path)},
            )
        return sorted(
            path
            for path in self.profiles_path.rglob("*.json")
            if path.is_file()
        )

    def _load_profiles(self, files: list[Path]) -> list[LearnerProfile]:
        profiles: list[LearnerProfile] = []
        seen: dict[tuple[str, str], str] = {}
        for path in files:
            document = common_api.json_storage.JsonContentReader(path).read()
            for candidate in self._profile_candidates(document, path):
                profile = self._deserialize(candidate, path)
                serialized = self._canonical(profile.to_dict())
                key = (profile.user_id, profile.learning_domain)
                previous = seen.get(key)
                if previous is not None:
                    if previous != serialized:
                        raise StorageReadError(
                            "conflicting legacy learner profiles",
                            details={
                                "path": str(path),
                                "location": candidate.location,
                                "user_id": profile.user_id,
                                "learning_domain": profile.learning_domain,
                            },
                        )
                    continue
                seen[key] = serialized
                profiles.append(profile)
        return profiles

    def _profile_candidates(
        self,
        document: Any,
        path: Path,
    ) -> list[_ProfileCandidate]:
        if isinstance(document, list):
            candidates: list[_ProfileCandidate] = []
            for index, payload in enumerate(document):
                if not isinstance(payload, dict):
                    self._invalid_document(path, f"[{index}]")
                candidates.append(_ProfileCandidate(dict(payload), f"[{index}]"))
            return candidates

        if not isinstance(document, dict):
            self._invalid_document(path, "root")
        if self._looks_like_complete_profile(document):
            return [_ProfileCandidate(dict(document), "root")]

        candidates = []
        for user_id, domains in document.items():
            user_location = str(user_id)
            if not isinstance(domains, dict):
                self._invalid_document(path, user_location)
            if self._looks_like_complete_profile(domains):
                payload = self._with_owner_defaults(
                    domains,
                    user_id=str(user_id),
                    learning_domain=None,
                    path=path,
                    location=user_location,
                )
                candidates.append(_ProfileCandidate(payload, user_location))
                continue
            for learning_domain, raw_profile in domains.items():
                location = f"{user_id}.{learning_domain}"
                if not isinstance(raw_profile, dict):
                    self._invalid_document(path, location)
                payload = self._with_owner_defaults(
                    raw_profile,
                    user_id=str(user_id),
                    learning_domain=str(learning_domain),
                    path=path,
                    location=location,
                )
                candidates.append(_ProfileCandidate(payload, location))
        return candidates

    @staticmethod
    def _looks_like_complete_profile(payload: dict[str, Any]) -> bool:
        return "user_id" in payload and "learning_domain" in payload

    @staticmethod
    def _with_owner_defaults(
        payload: dict[str, Any],
        *,
        user_id: str,
        learning_domain: str | None,
        path: Path,
        location: str,
    ) -> dict[str, Any]:
        result = dict(payload)
        existing_user_id = result.get("user_id")
        if existing_user_id is not None and existing_user_id != user_id:
            raise StorageReadError(
                "legacy learner profile owner does not match its JSON key",
                details={"path": str(path), "location": location},
            )
        result.setdefault("user_id", user_id)
        if learning_domain is not None:
            existing_domain = result.get("learning_domain")
            if existing_domain is not None and existing_domain != learning_domain:
                raise StorageReadError(
                    "legacy learner profile domain does not match its JSON key",
                    details={"path": str(path), "location": location},
                )
            result.setdefault("learning_domain", learning_domain)
        return result

    def _deserialize(
        self,
        candidate: _ProfileCandidate,
        path: Path,
    ) -> LearnerProfile:
        try:
            profile = LearnerProfile.from_dict(candidate.payload)
        except (TypeError, KeyError, SerializationAppError) as exc:
            raise StorageReadError(
                "legacy learner profile cannot be deserialized",
                details={"path": str(path), "location": candidate.location},
                cause=exc,
            ) from exc
        if not profile.user_id or not profile.learning_domain:
            raise StorageReadError(
                "legacy learner profile requires user_id and learning_domain",
                details={"path": str(path), "location": candidate.location},
            )
        if not profile.updated_at:
            digest = hashlib.sha256(
                self._canonical(profile.to_dict()).encode("utf-8")
            ).hexdigest()[:20]
            profile.updated_at = f"legacy-profile:{self.version}:{digest}"
        return profile

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _invalid_document(path: Path, location: str) -> None:
        raise StorageReadError(
            "legacy learner profile resource has an unsupported structure",
            details={"path": str(path), "location": location},
        )


def migrate_legacy_profiles_to_context_memory(
    *,
    database: Database,
    memory: MemoryModule,
    profiles_path: str | Path,
    version: str = LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION,
) -> LegacyProfileMigrationResult:
    """Run the versioned legacy profile backfill."""

    return LegacyProfileContextMigration(
        database=database,
        memory=memory,
        profiles_path=profiles_path,
        version=version,
    ).run()


__all__ = [
    "LEGACY_PROFILE_CONTEXT_MIGRATION_NAME",
    "LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION",
    "LegacyProfileContextMigration",
    "LegacyProfileMigrationResult",
    "migrate_legacy_profiles_to_context_memory",
]
