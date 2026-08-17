"""Idempotent migrations from legacy JSON stores to SQL context memory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from modules.common import api as common_api
from modules.common.errors import (
    SerializationAppError,
    StorageReadError,
    StorageWriteError,
)
from modules.learner_profile.models import LearnerProfile
from modules.persistence.database import Database
from modules.persistence.tables import MigrationLedgerRow

from .events import MemoryEvent, MemoryEventType
from .models import EvidenceSummary, KnowledgePointMemory, LearnerMemory
from .module import MemoryModule

LEGACY_PROFILE_CONTEXT_MIGRATION_NAME = "legacy-profile-json-to-context-memory"
LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION = "1"
LEGACY_MEMORY_SQL_MIGRATION_NAME = "legacy-memory-json-to-sql-context-memory"
LEGACY_MEMORY_SQL_MIGRATION_VERSION = "1"


@dataclass(frozen=True)
class LegacyProfileMigrationResult:
    migration_name: str
    version: str
    scanned_files: int
    discovered_profiles: int
    migrated_profiles: int
    already_completed: bool


@dataclass(frozen=True)
class LegacyMemoryMigrationResult:
    migration_name: str
    version: str
    scanned_files: int
    discovered_memories: int
    migrated_memories: int
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


class LegacyMemorySqlMigration:
    """Backfill complete legacy ``LearnerMemory`` snapshots into SQL.

    Each snapshot is represented by one immutable ``LEGACY_SNAPSHOT`` event.
    The event identity is stable per migration version and aggregate, making a
    retry after a partial failure safe even though the completion ledger is
    deliberately written only after the whole file succeeds.
    """

    def __init__(
        self,
        *,
        database: Database,
        memory: MemoryModule,
        memory_path: str | Path,
        version: str = LEGACY_MEMORY_SQL_MIGRATION_VERSION,
    ) -> None:
        self.database = database
        self.memory = memory
        self.memory_path = Path(memory_path)
        self.version = str(version)

    def run(self) -> LegacyMemoryMigrationResult:
        files = self._source_files()
        snapshots = self._load_snapshots(files)
        source_checksum = self._source_checksum(snapshots)
        completed = self._completed_details()
        if completed is not None:
            recorded_checksum = str(completed.get("source_checksum", ""))
            if not recorded_checksum or recorded_checksum != source_checksum:
                raise StorageReadError(
                    "legacy learner memory changed after its completed migration",
                    details={
                        "path": str(self.memory_path),
                        "expected_checksum": recorded_checksum,
                        "actual_checksum": source_checksum,
                    },
                )
            return LegacyMemoryMigrationResult(
                migration_name=LEGACY_MEMORY_SQL_MIGRATION_NAME,
                version=self.version,
                scanned_files=int(completed.get("scanned_files", 0)),
                discovered_memories=int(completed.get("memory_count", 0)),
                migrated_memories=0,
                already_completed=True,
            )

        for snapshot in snapshots:
            self._apply_snapshot(snapshot)

        details = {
            "scanned_files": len(files),
            "memory_count": len(snapshots),
            "source_checksum": source_checksum,
        }
        self._record_completion(details)
        return LegacyMemoryMigrationResult(
            migration_name=LEGACY_MEMORY_SQL_MIGRATION_NAME,
            version=self.version,
            scanned_files=len(files),
            discovered_memories=len(snapshots),
            migrated_memories=len(snapshots),
            already_completed=False,
        )

    def _completed_details(self) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.get(
                MigrationLedgerRow,
                (LEGACY_MEMORY_SQL_MIGRATION_NAME, self.version),
            )
            return dict(row.details) if row is not None else None

    def _record_completion(self, details: dict[str, Any]) -> None:
        try:
            with self.database.session() as session:
                existing = session.get(
                    MigrationLedgerRow,
                    (LEGACY_MEMORY_SQL_MIGRATION_NAME, self.version),
                )
                if existing is not None:
                    return
                session.add(
                    MigrationLedgerRow(
                        migration_name=LEGACY_MEMORY_SQL_MIGRATION_NAME,
                        version=self.version,
                        details=details,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
        except IntegrityError:
            if self._completed_details() is None:
                raise

    def _source_files(self) -> list[Path]:
        if not self.memory_path.exists():
            return []
        if not self.memory_path.is_file() or self.memory_path.suffix.lower() != ".json":
            raise StorageReadError(
                "legacy learner memory source must be a JSON file",
                details={"path": str(self.memory_path)},
            )
        return [self.memory_path]

    def _load_snapshots(self, files: list[Path]) -> list[LearnerMemory]:
        snapshots: list[LearnerMemory] = []
        seen: dict[tuple[str, str], str] = {}
        for path in files:
            document = common_api.json_storage.JsonContentReader(path).read()
            for storage_key, payload in self._memory_candidates(document, path):
                try:
                    snapshot = common_api.serialization.from_data(
                        LearnerMemory,
                        payload,
                    )
                except (TypeError, KeyError, SerializationAppError) as exc:
                    raise StorageReadError(
                        "legacy learner memory cannot be deserialized",
                        details={"path": str(path), "location": storage_key},
                        cause=exc,
                    ) from exc
                if not snapshot.user_id or not snapshot.learning_domain:
                    raise StorageReadError(
                        "legacy learner memory requires user_id and learning_domain",
                        details={"path": str(path), "location": storage_key},
                    )
                if storage_key != "root":
                    expected_key = f"{snapshot.user_id}:{snapshot.learning_domain}"
                    if storage_key != expected_key:
                        raise StorageReadError(
                            "legacy learner memory owner does not match its JSON key",
                            details={"path": str(path), "location": storage_key},
                        )
                serialized = self._canonical(snapshot.to_dict())
                key = (snapshot.user_id, snapshot.learning_domain)
                previous = seen.get(key)
                if previous is not None:
                    if previous != serialized:
                        raise StorageReadError(
                            "conflicting legacy learner memory snapshots",
                            details={
                                "path": str(path),
                                "user_id": snapshot.user_id,
                                "learning_domain": snapshot.learning_domain,
                            },
                        )
                    continue
                seen[key] = serialized
                snapshots.append(snapshot)
        return snapshots

    @staticmethod
    def _memory_candidates(
        document: Any,
        path: Path,
    ) -> list[tuple[str, dict[str, Any]]]:
        if not isinstance(document, dict):
            raise StorageReadError(
                "legacy learner memory resource must be a JSON object",
                details={"path": str(path)},
            )
        if "user_id" in document and "learning_domain" in document:
            return [("root", dict(document))]
        candidates: list[tuple[str, dict[str, Any]]] = []
        for storage_key, payload in document.items():
            if not isinstance(payload, dict):
                raise StorageReadError(
                    "legacy learner memory snapshot must be a JSON object",
                    details={"path": str(path), "location": str(storage_key)},
                )
            candidates.append((str(storage_key), dict(payload)))
        return candidates

    def _apply_snapshot(self, snapshot: LearnerMemory) -> LearnerMemory:
        repository = self.memory.repository
        apply_event = getattr(repository, "apply_event", None)
        if not callable(apply_event):
            raise StorageWriteError(
                "legacy learner memory migration requires an event SQL repository"
            )

        current = self.memory.get_learner_memory(
            snapshot.user_id,
            snapshot.learning_domain,
        )
        list_events = getattr(repository, "list_events", None)
        current_event_types = (
            {str(event.event_type) for event in list_events(
                snapshot.user_id,
                current.learning_domain,
            )}
            if callable(list_events)
            else set()
        )
        normalized_domain = current.learning_domain
        legacy_payload = snapshot.to_dict()
        legacy_payload["learning_domain"] = normalized_domain
        normalized_snapshot = common_api.serialization.from_data(
            LearnerMemory,
            legacy_payload,
        )
        target = self._merge_with_current(
            normalized_snapshot,
            current,
            current_event_types=current_event_types,
        )
        occurred_at = normalized_snapshot.updated_at or (
            "legacy-memory:"
            + self.version
            + ":"
            + hashlib.sha256(
                self._canonical(legacy_payload).encode("utf-8")
            ).hexdigest()[:20]
        )
        if not target.updated_at:
            target.updated_at = occurred_at
        identity = hashlib.sha256(
            f"{target.user_id}\0{target.learning_domain}".encode()
        ).hexdigest()[:32]
        event = MemoryEvent(
            event_id=f"legacy-memory:{self.version}:{identity}",
            user_id=target.user_id,
            learning_domain=target.learning_domain,
            event_type=MemoryEventType.LEGACY_SNAPSHOT,
            source_type="legacy_json_memory",
            occurred_at=occurred_at,
            payload={"snapshot": legacy_payload},
            algorithm_version=self.version,
        )
        return apply_event(
            target,
            event,
            expected_version=current.state_version,
        )

    @staticmethod
    def _merge_with_current(
        legacy: LearnerMemory,
        current: LearnerMemory,
        *,
        current_event_types: set[str] | None = None,
    ) -> LearnerMemory:
        if current.state_version <= 0:
            return legacy

        result = common_api.serialization.from_data(
            LearnerMemory,
            legacy.to_dict(),
        )
        current_points = {
            item.knowledge_point_id: item for item in current.knowledge_points
        }
        result.knowledge_points = []
        for legacy_point in legacy.knowledge_points:
            current_point = current_points.pop(
                legacy_point.knowledge_point_id,
                None,
            )
            result.knowledge_points.append(
                LegacyMemorySqlMigration._merge_knowledge_point(
                    legacy_point,
                    current_point,
                )
                if current_point is not None
                else legacy_point
            )
        result.knowledge_points.extend(current_points.values())
        result.learning_goals = list(
            dict.fromkeys([*legacy.learning_goals, *current.learning_goals])
        )
        event_types = current_event_types or set()
        if MemoryEventType.DIAGNOSIS_CONFIRMED in event_types:
            result.diagnosis_summary = dict(current.diagnosis_summary)
        else:
            result.diagnosis_summary = (
                current.diagnosis_summary or legacy.diagnosis_summary
            )
        if MemoryEventType.PROFILE_DECLARED in event_types:
            # A post-cutover profile event is authoritative even when the user
            # explicitly cleared a field.  Truthiness fallback would resurrect
            # stale legacy declarations.
            result.current_confusions = current.current_confusions
            result.preferences = dict(current.preferences)
            result.self_assessed_level = current.self_assessed_level
            result.self_reported_known_knowledge_point_ids = list(
                current.self_reported_known_knowledge_point_ids
            )
            result.self_reported_unknown_knowledge_point_ids = list(
                current.self_reported_unknown_knowledge_point_ids
            )
            result.self_reported_knowledge_point_note = (
                current.self_reported_knowledge_point_note
            )
        else:
            result.current_confusions = (
                current.current_confusions or legacy.current_confusions
            )
            result.preferences = {**legacy.preferences, **current.preferences}
            result.self_assessed_level = (
                current.self_assessed_level
                if current.self_assessed_level != "unknown"
                else legacy.self_assessed_level
            )
            result.self_reported_known_knowledge_point_ids = (
                current.self_reported_known_knowledge_point_ids
                or legacy.self_reported_known_knowledge_point_ids
            )
            result.self_reported_unknown_knowledge_point_ids = (
                current.self_reported_unknown_knowledge_point_ids
                or legacy.self_reported_unknown_knowledge_point_ids
            )
            result.self_reported_knowledge_point_note = (
                current.self_reported_knowledge_point_note
                or legacy.self_reported_knowledge_point_note
            )
        result.completed_task_count = (
            legacy.completed_task_count + current.completed_task_count
        )
        if (current.last_activity_at or "") > (legacy.last_activity_at or ""):
            result.last_activity_at = current.last_activity_at
            result.last_completed_task_id = current.last_completed_task_id
        result.update_count = legacy.update_count + current.update_count
        result.updated_at = max(legacy.updated_at or "", current.updated_at or "")
        return result

    @staticmethod
    def _merge_knowledge_point(
        legacy: KnowledgePointMemory,
        current: KnowledgePointMemory,
    ) -> KnowledgePointMemory:
        """Merge an old baseline with non-overlapping post-cutover evidence."""

        current_is_newer = (current.updated_at or "") >= (legacy.updated_at or "")
        newer, older = (current, legacy) if current_is_newer else (legacy, current)
        result = common_api.serialization.from_data(
            KnowledgePointMemory,
            newer.to_dict(),
        )
        result.name = newer.name or older.name
        result.description = newer.description or older.description
        result.evidence_summary = EvidenceSummary(
            accepted_evidence_count=(
                legacy.evidence_summary.accepted_evidence_count
                + current.evidence_summary.accepted_evidence_count
            ),
            effective_evidence_weight=(
                legacy.evidence_summary.effective_evidence_weight
                + current.evidence_summary.effective_evidence_weight
            ),
            independent_correct_count=(
                legacy.evidence_summary.independent_correct_count
                + current.evidence_summary.independent_correct_count
            ),
            delayed_correct_count=(
                legacy.evidence_summary.delayed_correct_count
                + current.evidence_summary.delayed_correct_count
            ),
            delayed_failure_count=(
                legacy.evidence_summary.delayed_failure_count
                + current.evidence_summary.delayed_failure_count
            ),
            guided_evidence_count=(
                legacy.evidence_summary.guided_evidence_count
                + current.evidence_summary.guided_evidence_count
            ),
        )
        result.update_count = legacy.update_count + current.update_count
        result.evidence_ids = list(
            dict.fromkeys([*legacy.evidence_ids, *current.evidence_ids])
        )
        result.reason_codes = list(
            dict.fromkeys([*legacy.reason_codes, *current.reason_codes])
        )
        return result

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _source_checksum(snapshots: list[LearnerMemory]) -> str:
        canonical_snapshots = [
            snapshot.to_dict()
            for snapshot in sorted(
                snapshots,
                key=lambda item: (item.user_id, item.learning_domain),
            )
        ]
        canonical = LegacyMemorySqlMigration._canonical(
            {"snapshots": canonical_snapshots}
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def migrate_legacy_memory_to_sql(
    *,
    database: Database,
    memory: MemoryModule,
    memory_path: str | Path,
    version: str = LEGACY_MEMORY_SQL_MIGRATION_VERSION,
) -> LegacyMemoryMigrationResult:
    """Run the versioned full-memory JSON-to-SQL backfill."""

    return LegacyMemorySqlMigration(
        database=database,
        memory=memory,
        memory_path=memory_path,
        version=version,
    ).run()


__all__ = [
    "LEGACY_MEMORY_SQL_MIGRATION_NAME",
    "LEGACY_MEMORY_SQL_MIGRATION_VERSION",
    "LEGACY_PROFILE_CONTEXT_MIGRATION_NAME",
    "LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION",
    "LegacyMemoryMigrationResult",
    "LegacyMemorySqlMigration",
    "LegacyProfileContextMigration",
    "LegacyProfileMigrationResult",
    "migrate_legacy_memory_to_sql",
    "migrate_legacy_profiles_to_context_memory",
]
