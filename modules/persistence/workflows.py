from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from modules.common.errors import ConflictError, ResourceNotFoundError

from .database import Database
from .tables import WorkflowSessionRow


@dataclass(frozen=True)
class WorkflowSession:
    workflow_id: str
    user_id: str
    workflow_type: str
    learning_domain: str
    status: str
    created_at: str
    updated_at: str


class WorkflowSessionRepository:
    """Durable owner registry for resumable LangGraph workflows."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _model(row: WorkflowSessionRow) -> WorkflowSession:
        return WorkflowSession(
            workflow_id=row.workflow_id,
            user_id=row.user_id,
            workflow_type=row.workflow_type,
            learning_domain=row.learning_domain,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def create(
        self,
        *,
        workflow_id: str,
        user_id: str,
        workflow_type: str,
        learning_domain: str,
        status: str = "started",
    ) -> WorkflowSession:
        now = self.now()
        with self.database.session() as session:
            if session.get(WorkflowSessionRow, workflow_id) is not None:
                raise ConflictError(
                    "workflow already exists",
                    details={"workflow_id": workflow_id},
                )
            row = WorkflowSessionRow(
                workflow_id=workflow_id,
                user_id=user_id,
                workflow_type=workflow_type,
                learning_domain=learning_domain,
                status=status,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        return self._model(row)

    def require_owned(
        self,
        workflow_id: str,
        *,
        actor_user_id: str,
        workflow_type: str | None = None,
    ) -> WorkflowSession:
        with self.database.session() as session:
            row = session.get(WorkflowSessionRow, workflow_id)
            if (
                row is None
                or row.user_id != actor_user_id
                or (workflow_type is not None and row.workflow_type != workflow_type)
            ):
                raise ResourceNotFoundError(
                    "workflow not found",
                    details={"workflow_id": workflow_id},
                )
            return self._model(row)

    def update_status(self, workflow_id: str, status: str) -> None:
        with self.database.session() as session:
            row = session.get(WorkflowSessionRow, workflow_id)
            if row is None:
                raise ResourceNotFoundError(
                    "workflow not found",
                    details={"workflow_id": workflow_id},
                )
            row.status = status
            row.updated_at = self.now()
