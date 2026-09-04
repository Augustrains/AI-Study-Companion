from datetime import date
import unittest

from modules.diagnosis.repository import MySqlDiagnosisRepository
from modules.learning_plan.agent import WeeklyLearningPlanAgent, WeeklyPlanningInput
from modules.learning_plan.bkt import BktMasteryEstimator
from modules.learning_plan.materials import ReadingMaterialService
from modules.learning_plan.mastery_fusion import MasteryFusion
from modules.learning_plan.bkt import BktEstimate
from modules.learning_plan.module import LearningPlanModule


class FakePlanRepository:
    def __init__(self):
        self.saved_days = []

    def load_weekly_context(self, *, user_id: int, book_id: int):
        return {
            "user_id": user_id,
            "book": {"id": book_id, "book_name": "测试教材"},
            "goal": {"id": 4, "goal": "掌握基础知识", "aim_level": 2, "daily_minutes": 40},
            "points": [
                {"knowledge_point_id": 7, "knowledge_point_name": "线性回归", "chapter_title": "第一章", "course_order": 1, "mastery_score": 0.2, "aim_score": 0.8, "confidence": 0.3},
                {"knowledge_point_id": 8, "knowledge_point_name": "模型评估", "chapter_title": "第二章", "course_order": 2, "mastery_score": 0.7, "aim_score": 0.8, "confidence": 0.3},
            ],
            "outcomes": {7: [False, True], 8: [True, True]},
            "question_ids": {7: [101, 102], 8: [103]},
        }

    def replace_weekly_plan(self, *, context, days):
        self.saved_days = days
        return 99

    def load_active_weekly_plan(self, *, user_id: int, book_id: int):
        return None


class WeeklyLearningPlanTest(unittest.TestCase):
    def test_bkt_returns_more_opportunities_for_a_larger_gap(self):
        estimator = BktMasteryEstimator()
        weak = estimator.estimate(current_mastery=0.2, target_mastery=0.8, outcomes=[])
        near_target = estimator.estimate(current_mastery=0.7, target_mastery=0.8, outcomes=[])
        self.assertGreater(weak.expected_practice_count, near_target.expected_practice_count)
        self.assertGreater(near_target.expected_practice_count, 0)

    def test_bkt_handles_a_full_mastery_goal_without_log_zero(self):
        estimate = BktMasteryEstimator().estimate(current_mastery=0.0, target_mastery=1.0, outcomes=[])
        self.assertGreater(estimate.expected_practice_count, 0)
        self.assertLess(estimate.mastery_score, 1.0)

    def test_weekly_plan_uses_fixed_diagnostic_and_stays_within_daily_budget(self):
        repository = FakePlanRepository()
        result = LearningPlanModule(repository).generate_weekly(user_id=1, book_id=2, start_date=date(2026, 9, 2))
        self.assertEqual(result["plan_id"], 99)
        self.assertEqual(len(result["days"]), 7)
        for day in result["days"]:
            self.assertEqual(day["items"][0]["minutes"], 10)
            self.assertEqual(day["items"][0]["source"], "review_due")
            self.assertLessEqual(day["planned_minutes"], 40)

    def test_plan_requires_reading_before_practice_and_limits_each_point_to_one_practice_per_day(self):
        repository = FakePlanRepository()
        context = repository.load_weekly_context(user_id=1, book_id=2)
        module = LearningPlanModule(repository)
        workloads = [module._workload(point, context) for point in context["points"]]
        result = WeeklyLearningPlanAgent().build(
            WeeklyPlanningInput(context=context, workloads=workloads, start_date=date(2026, 9, 2))
        )

        read_points: set[int] = set()
        for day in result["days"]:
            learning_items = day["items"][1:]
            if learning_items:
                self.assertEqual(day["items"][0]["knowledge_point_id"], learning_items[0]["knowledge_point_id"])
            practiced_today: set[int] = set()
            for item in learning_items:
                point_id = item["knowledge_point_id"]
                if item["title"].startswith("阅读："):
                    read_points.add(point_id)
                if item["title"].startswith("练习："):
                    self.assertIn(point_id, read_points)
                    self.assertNotIn(point_id, practiced_today)
                    practiced_today.add(point_id)

    def test_replanned_window_can_start_from_the_next_day(self):
        repository = FakePlanRepository()
        context = repository.load_weekly_context(user_id=1, book_id=2)
        module = LearningPlanModule(repository)
        workloads = [module._workload(point, context) for point in context["points"]]
        result = WeeklyLearningPlanAgent().build(
            WeeklyPlanningInput(context=context, workloads=workloads, start_date=date(2026, 9, 3), plan_days=6)
        )
        self.assertEqual(len(result["days"]), 6)
        self.assertEqual(result["days"][0]["date"], "2026-09-03")

    def test_seven_day_window_limits_new_knowledge_points_to_priority_focus_set(self):
        repository = FakePlanRepository()
        context = repository.load_weekly_context(user_id=1, book_id=2)
        workloads = [
            {"knowledge_point_id": index, "knowledge_point_name": f"知识点{index}", "chapter_title": "章节", "course_order": index, "expected_practice_count": 8, "priority_score": float(10 - index), "question_ids": []}
            for index in range(1, 6)
        ]
        result = WeeklyLearningPlanAgent().build(
            WeeklyPlanningInput(context=context, workloads=workloads, start_date=date(2026, 9, 2))
        )
        introduced = {
            item["knowledge_point_id"]
            for day in result["days"]
            for item in day["items"]
            if item["title"].startswith("阅读：")
        }
        self.assertEqual(introduced, {1, 2, 3})
        self.assertTrue({4, 5}.issubset(set(result["deferred_knowledge_point_ids"])))

    def test_due_next_review_time_creates_a_review_task_before_new_learning(self):
        repository = FakePlanRepository()
        context = repository.load_weekly_context(user_id=1, book_id=2)
        workloads = [
            {
                "knowledge_point_id": 7,
                "knowledge_point_name": "线性回归",
                "chapter_title": "第一章",
                "course_order": 1,
                "expected_practice_count": 3,
                "priority_score": 5.0,
                "next_review_at": "2026-09-03T09:00:00",
                "question_ids": [101],
            }
        ]
        result = WeeklyLearningPlanAgent().build(
            WeeklyPlanningInput(context=context, workloads=workloads, start_date=date(2026, 9, 3), plan_days=1)
        )

        self.assertEqual(result["days"][0]["items"][1]["title"], "复习：线性回归（3分钟）")
        self.assertEqual(result["days"][0]["items"][1]["source"], "spaced_review")

    def test_mastery_fusion_uses_rule_confidence_without_overwriting_bkt(self):
        fused = MasteryFusion().combine(
            bkt=BktEstimate(mastery_score=0.40, predicted_correct_rate=0.52, learning_rate=0.12, expected_practice_count=8, confidence=0.30),
            rule_update={"mastery_score": 0.80, "confidence": 0.60, "next_review_at": "2026-09-04T00:00:00+00:00"},
        )
        self.assertGreater(fused.mastery_score, 0.40)
        self.assertLess(fused.mastery_score, 0.80)
        self.assertGreater(fused.confidence, 0.60)
        self.assertEqual(fused.next_review_at, "2026-09-04T00:00:00+00:00")


class _RecordingCursor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, statement, parameters) -> None:
        self.calls.append((statement, parameters))


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self._cursor


class _DiagnosisRepositoryForTest(MySqlDiagnosisRepository):
    def __init__(self) -> None:
        self.cursor_instance = _RecordingCursor()

    def connection(self):
        return _RecordingConnection(self.cursor_instance)


class DailyDiagnosticTaskCompletionTest(unittest.TestCase):
    def test_confirmed_daily_diagnosis_marks_only_its_diagnostic_task_completed(self):
        repository = _DiagnosisRepositoryForTest()

        repository.complete_daily_diagnostic_task(session_id=123)

        statement, parameters = repository.cursor_instance.calls[0]
        self.assertIn("JOIN diagnostic_session", statement)
        self.assertIn("item.source = 'review_due'", statement)
        self.assertIn("item.status = 'completed'", statement)
        self.assertEqual(parameters[-1], 123)


class _GuideLlm:
    def __init__(self) -> None:
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return "统一学习讲义"


class ReadingMaterialServiceTest(unittest.TestCase):
    def test_ai_knowledge_point_resolves_to_its_specific_lesson_file(self):
        service = ReadingMaterialService(llm_client=_GuideLlm())

        materials = service._local_materials(service._book_root(1), "kp-ai-lesson-07")

        self.assertEqual(len(materials), 1)
        self.assertIn("07-ConvNets", materials[0]["path"])

    def test_ml_knowledge_point_resolves_from_its_taxonomy_name_to_lesson_file(self):
        service = ReadingMaterialService(llm_client=_GuideLlm())

        materials = service._local_materials(service._book_root(2), "kp-ml-classification-intro")

        self.assertEqual(len(materials), 1)
        self.assertIn("ml-unit-008.md", materials[0]["path"])

    def test_llm_prompt_makes_textbook_authoritative_over_web(self):
        llm = _GuideLlm()
        service = ReadingMaterialService(llm_client=llm)

        guide, generated_by = service._integrate(
            {"name": "卷积神经网络", "description": "测试知识点"},
            [{"title": "教材", "path": "local.md", "content": "教材事实"}],
            [{"title": "网页", "url": "https://example.com", "snippet": "不可靠网页摘要"}],
        )

        self.assertEqual((guide, generated_by), ("统一学习讲义", "llm"))
        self.assertIn("本地教材是唯一事实依据", llm.prompt)
        self.assertIn("网络文本只是未经验证的补充", llm.prompt)
