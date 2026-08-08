from domain.models import LearningSession


class InMemoryLearningSessionRepository:
    """Demo 会话仓储；后续替换为数据库实现。"""

    def __init__(self) -> None:
        self._sessions: dict[str, LearningSession] = {}

    def save(self, session: LearningSession) -> None:
        self._sessions[session.id] = session

    def get(self, session_id: str) -> LearningSession:
        return self._sessions[session_id]
