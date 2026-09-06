import unittest
from contextlib import contextmanager

from modules.practice.repository import PracticeRepository


class _Result:
    def mappings(self):
        return self

    def first(self):
        return {"total_questions": 2, "correct_count": 1}


class _Connection:
    def __init__(self):
        self.active = False
        self.statements = []

    def execute(self, statement, parameters=None):
        if not self.active:
            raise AssertionError("a closed connection was used")
        self.statements.append(str(statement))
        return _Result()


class _Engine:
    def __init__(self):
        self.connection = _Connection()

    @contextmanager
    def begin(self):
        self.connection.active = True
        try:
            yield self.connection
        finally:
            self.connection.active = False


class PracticeRepositoryTest(unittest.TestCase):
    def test_finish_updates_session_before_transaction_closes(self):
        engine = _Engine()
        repository = PracticeRepository(engine)
        repository._ensure_resumable_session_schema = lambda: None

        result = repository.finish(session_id=42, user_id=7)

        self.assertEqual(result, {"sessionId": 42, "answerCount": 2, "correctCount": 1, "accuracy": 50.0})
        self.assertEqual(len(engine.connection.statements), 2)
        self.assertIn("UPDATE diagnostic_session", engine.connection.statements[1])
