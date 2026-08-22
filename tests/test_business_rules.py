"""业务规则回归测试。

覆盖这一轮修复的四件事，都不需要 langgraph / qdrant / embedding / 真实 LLM：

  1. 学习目标接口（POST/GET /api/learner-goals）
  2. 每周时长真的约束排课（LearningPlanModule._apply_time_budget）
  3. 诊断出题在模型不可用时回退规则计划，而不是让诊断 502
  4. 学习画像不再覆盖诊断测出来的掌握度
  5. 实际用时校准排课节奏（pace factor）
  6. 改目标 / 完成任务后自动重排在途计划

在项目根目录执行：

    python3.11 tests/test_business_rules.py
"""

import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# sdk.llm_client 会在导入时读环境变量并建 httpx 客户端；这里只测不依赖模型的逻辑，
# 用桩替换掉，避免测试要求配置 API key。
_sdk = types.ModuleType("sdk")
_llm = types.ModuleType("sdk.llm_client")


class LLMClient:  # noqa: D101
    def generate(self, prompt: str) -> str:  # noqa: D102
        return ""


class NullLLMClient(LLMClient):  # noqa: D101
    pass


_llm.LLMClient = LLMClient
_llm.NullLLMClient = NullLLMClient
sys.modules.setdefault("sdk", _sdk)
sys.modules["sdk.llm_client"] = _llm

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from modules.common import api as common_api  # noqa: E402
from modules.common import errors as common_errors  # noqa: E402
from modules.common.errors import ExternalServiceError  # noqa: E402
from modules.diagnosis.agent import DiagnosticAgent  # noqa: E402
from modules.diagnosis.models import QuestionPlanningInput  # noqa: E402
from modules.learner_goals.api import build_router as build_goal_router  # noqa: E402
from modules.learner_goals.module import LearnerGoalModule  # noqa: E402
from modules.diagnosis.models import STATUSES  # noqa: E402
from modules.learning_plan.module import LearningPlanModule  # noqa: E402
from modules.memory.models import EvidenceSummary, KnowledgePointMemory  # noqa: E402
from modules.memory.module import MemoryModule  # noqa: E402
from modules.memory.repository import JsonMemoryRepository  # noqa: E402

PASSED = 0


def check(label: str, condition: bool, extra: object = "") -> None:
    global PASSED
    assert condition, f"FAIL: {label} {extra}"
    PASSED += 1
    print(f"  ok  {label}")


# ============================== 1. 学习目标 ==============================

print("== 学习目标 ==")

goal_path = Path(tempfile.mkdtemp(prefix="goals-")) / "goals.json"
goal_module = LearnerGoalModule(goal_path)
goal_app = FastAPI()


@goal_app.exception_handler(common_errors.AppError)
async def _goal_error(_request: Request, exc: common_errors.AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


goal_app.include_router(build_goal_router(goal_module))
goals = TestClient(goal_app, raise_server_exceptions=False)

response = goals.get("/api/learner-goals?userId=demo_user&bookId=ml")
check("没设过目标返回 exists=false 而不是 404", response.status_code == 200 and response.json()["exists"] is False, response.text)

response = goals.post(
    "/api/learner-goals",
    json={"bookId": "ml", "targetLevel": "能够解决进阶应用问题", "weeklyHours": 12, "userId": "demo_user"},
)
check("保存目标", response.status_code == 200, response.text)
check("响应是 camelCase", response.json()["weeklyHours"] == 12, response.text)

response = goals.get("/api/learner-goals?userId=demo_user&bookId=ml")
check("能读回同一份（页面回填依赖它）", response.json()["goal"]["weeklyHours"] == 12, response.text)

goals.post(
    "/api/learner-goals",
    json={"bookId": "ml", "targetLevel": "能够复述核心概念", "weeklyHours": 3, "userId": "demo_user"},
)
response = goals.get("/api/learner-goals?userId=demo_user&bookId=ml")
check("改目标是覆盖不是追加", response.json()["goal"]["targetLevel"] == "能够复述核心概念", response.text)

response = goals.get("/api/learner-goals?userId=other_user&bookId=ml")
check("目标按用户隔离", response.json()["exists"] is False, response.text)

response = goals.post(
    "/api/learner-goals",
    json={"bookId": "ml", "targetLevel": "随便编一个", "weeklyHours": 5, "userId": "demo_user"},
)
check("非法目标水平被拒", response.status_code == 400, response.text)

response = goals.post("/api/learner-goals", json={"bookId": "ml", "targetLevel": "能够复述核心概念", "weeklyHours": 5})
check("缺 userId 被拒，不再静默按 user_001 处理", response.status_code == 422, response.text)

check("每周 3 小时 → 每天约 26 分钟", goal_module.daily_minutes_budget(user_id="demo_user", book_id="ml") == 26)
check("没设目标时不给预算", goal_module.daily_minutes_budget(user_id="nobody", book_id="ml") is None)


# ============================== 2. 每周时长约束排课 ==============================

print("== 每周时长 → 按天摊课 ==")

plan = {
    "tasks": [
        {"id": "t1", "minutes": 30},
        {"id": "t2", "minutes": 25},
        {"id": "t3", "minutes": 40},
        {"id": "t4", "minutes": 20},
    ],
    "advice": ["原有建议"],
}

untouched = LearningPlanModule._apply_time_budget(dict(plan), daily_budget=None)
check("没设目标时计划原样返回", untouched.get("timeBudget") is None and untouched["tasks"] == plan["tasks"])

scheduled = LearningPlanModule._apply_time_budget(dict(plan), daily_budget=60)
per_day: dict[str, int] = {}
for task in scheduled["tasks"]:
    per_day[task["expectedCompletionDate"]] = per_day.get(task["expectedCompletionDate"], 0) + task["minutes"]
check("任务一个不少", len(scheduled["tasks"]) == 4)
check("任务时长一分钟没被压缩", sum(t["minutes"] for t in scheduled["tasks"]) == 115)
check("每天总时长不超预算", all(value <= 60 for value in per_day.values()), per_day)
check("115 分钟 / 每天 60 分钟 → 摊 2 天", len(per_day) == 2, per_day)
check(
    "汇总正确",
    {key: scheduled["timeBudget"][key] for key in ("dailyMinutes", "totalMinutes", "estimatedDays")}
    == {"dailyMinutes": 60, "totalMinutes": 115, "estimatedDays": 2},
    scheduled["timeBudget"],
)
check("原有建议保留", "原有建议" in scheduled["advice"])
check("追加一条时间说明", any("预计 2 天完成" in item for item in scheduled["advice"]), scheduled["advice"])

check(
    "每周时长调高 → 更快做完",
    LearningPlanModule._apply_time_budget(dict(plan), daily_budget=200)["timeBudget"]["estimatedDays"] == 1,
)
check(
    "每周时长调低 → 摊更多天（这就是之前填 3 小时和 15 小时没区别的地方）",
    LearningPlanModule._apply_time_budget(dict(plan), daily_budget=20)["timeBudget"]["estimatedDays"] == 4,
)

oversized = LearningPlanModule._apply_time_budget(
    {"tasks": [{"id": "a", "minutes": 10}, {"id": "b", "minutes": 90}], "advice": []}, daily_budget=30
)
check(
    "单个超长任务独占一天且不被切碎",
    oversized["tasks"][1]["minutes"] == 90
    and oversized["tasks"][0]["expectedCompletionDate"] != oversized["tasks"][1]["expectedCompletionDate"],
)

check("单任务上限：没填偏好时用默认 30 分钟", LearningPlanModule._max_task_minutes(None) == 30)
check("单任务上限：跟随单次学习时长偏好", LearningPlanModule._max_task_minutes(90) == 90)
check("单任务上限：选 2 小时就能排 2 小时的任务", LearningPlanModule._max_task_minutes(120) == 120)
check(
    "单任务上限：不再被每日预算压短（长任务由排课独占一天，不该被砍）",
    LearningPlanModule._max_task_minutes(120, 25) == 120,
)
check("单任务上限：硬顶 2 小时", LearningPlanModule._max_task_minutes(600) == 120)
check("单任务上限：不低于 5 分钟", LearningPlanModule._max_task_minutes(1) == 5)

print("== 任务时长跟随单次学习时长偏好 ==")
weakest, familiar, mastered = STATUSES[0], STATUSES[2], STATUSES[-1]
check(
    "没填偏好时和过去接近（30/23→25/15）",
    LearningPlanModule._minutes_for(weakest) == 30 and LearningPlanModule._minutes_for(mastered) == 15,
    (LearningPlanModule._minutes_for(weakest), LearningPlanModule._minutes_for(mastered)),
)
check(
    "选 2 小时：薄弱知识点排满 2 小时",
    LearningPlanModule._minutes_for(weakest, 120) == 120,
    LearningPlanModule._minutes_for(weakest, 120),
)
check(
    "选 2 小时：熟悉的排 90 分钟、已掌握的排 60 分钟",
    LearningPlanModule._minutes_for(familiar, 120) == 90 and LearningPlanModule._minutes_for(mastered, 120) == 60,
    (LearningPlanModule._minutes_for(familiar, 120), LearningPlanModule._minutes_for(mastered, 120)),
)
check(
    "选 15 分钟：任务跟着变短，不会硬塞长任务",
    LearningPlanModule._minutes_for(weakest, 15) == 15 and LearningPlanModule._minutes_for(mastered, 15) >= 5,
)
check("任务时长按 5 分钟取整", all(LearningPlanModule._minutes_for(status, value) % 5 == 0 for status in (weakest, familiar, mastered) for value in (15, 30, 45, 60, 90, 120)))


# ============================== 3. 诊断出题兜底 ==============================

print("== 诊断出题：模型不可用时回退规则计划 ==")

planning_input = QuestionPlanningInput(
    learning_goal="能够独立完成基础练习",
    knowledge_point_mastery={"kp-ml-intro": "熟悉", "kp-ml-kmeans": "不会"},
    knowledge_point_memory={},
    available_question_counts={"kp-ml-intro": 4, "kp-ml-kmeans": 4},
    knowledge_point_catalog={},
    answered_question_ids=[],
    diagnosis_round=1,
)


class UnreachableLLM(LLMClient):
    def generate(self, prompt: str) -> str:
        raise ExternalServiceError("llm unreachable", details={"status": 401})


class TimeoutLLM(LLMClient):
    def generate(self, prompt: str) -> str:
        raise TimeoutError("read timeout")


class WorkingLLM(LLMClient):
    def generate(self, prompt: str) -> str:
        return json.dumps(
            {
                "selections": [
                    {"knowledgePointId": "kp-ml-intro", "questionCount": 1, "taskMode": "independent"},
                    {"knowledgePointId": "kp-ml-kmeans", "questionCount": 4, "taskMode": "remediation"},
                ]
            }
        )


fallback = {item.knowledge_point_id: item.question_count for item in DiagnosticAgent(UnreachableLLM()).plan_questions(planning_input)}
check("模型返回 502 时不再抛异常（诊断第一步就挂就是这里）", bool(fallback))
check("规则计划仍然排得出题", sum(fallback.values()) > 0, fallback)
check("薄弱知识点排的题更多", fallback["kp-ml-kmeans"] > fallback["kp-ml-intro"], fallback)
check(
    "超时之类的非 AppError 也兜住",
    sum(item.question_count for item in DiagnosticAgent(TimeoutLLM()).plan_questions(planning_input)) > 0,
)
working = {item.knowledge_point_id: item.question_count for item in DiagnosticAgent(WorkingLLM()).plan_questions(planning_input)}
check("模型可用时仍然按模型的计划走", working == {"kp-ml-intro": 1, "kp-ml-kmeans": 4}, working)


# ============================== 4. 画像不再覆盖掌握度 ==============================

print("== 学习画像不再写掌握度 ==")

memory_path = Path(tempfile.mkdtemp(prefix="memory-")) / "memories.json"
repository = JsonMemoryRepository(
    reader=common_api.json_storage.JsonContentReader(memory_path),
    store=common_api.json_storage.JsonStore(),
)
memory_module = MemoryModule(repository)


def make_point(point_id: str, level: str, score: float, confidence: float, source: str) -> KnowledgePointMemory:
    return KnowledgePointMemory(
        knowledge_point_id=point_id,
        name="",
        description="",
        mastery_level=level,
        mastery_score=score,
        confidence=confidence,
        memory_status="未验证",
        memory_stability_days=0.0,
        evidence_summary=EvidenceSummary(),
        next_review_at=None,
        updated_at=repository.now(),
        update_count=1,
        source=source,
    )


seeded = memory_module.get_learner_memory("demo_user", "machine_learning")
seeded.knowledge_points.append(make_point("kp-ml-kmeans", "不会", 0.18, 0.45, "diagnosis"))
seeded.knowledge_points.append(make_point("kp-ml-intro", "掌握", 0.88, 0.92, "diagnosis"))
memory_module._save(seeded)


class _Preferences:
    def to_dict(self) -> dict[str, str]:
        return {"content_style": "concise"}


class _Profile:
    user_id = "demo_user"
    learning_domain = "machine_learning"
    known_knowledge_point_ids = ["kp-ml-regression-intro"]
    known_knowledge_point_note = "自学过"
    current_confusions = "分不清分类和回归"
    preferences = _Preferences()


synced = memory_module.sync_learner_profile(_Profile())
points = {item.knowledge_point_id: item for item in synced.knowledge_points}
check("保存画像不再删掉没勾选的知识点（原实现会全删）", {"kp-ml-kmeans", "kp-ml-intro"} <= set(points), sorted(points))
check("诊断测出的低分没被抬成满分（原实现会写 1.0）", points["kp-ml-kmeans"].mastery_score == 0.18)
check("诊断测出的高分原样保留", points["kp-ml-intro"].mastery_score == 0.88)
check("自述会的新知识点落成冷启动先验", "kp-ml-regression-intro" in points)
prior = points["kp-ml-regression-intro"]
check(
    "先验是低置信未验证，不是满分",
    prior.mastery_score == 0.5 and prior.confidence == 0.3 and prior.memory_status == "未验证" and prior.mastery_level == "了解",
    (prior.mastery_level, prior.mastery_score, prior.confidence, prior.memory_status),
)
check(
    "困惑与偏好照常同步",
    synced.current_confusions == "分不清分类和回归" and synced.preferences == {"content_style": "concise"},
)


class _ProfileClaimingKnown(_Profile):
    known_knowledge_point_ids = ["kp-ml-kmeans"]


reclaimed = {item.knowledge_point_id: item for item in memory_module.sync_learner_profile(_ProfileClaimingKnown()).knowledge_points}
check(
    "自述「我会」不覆盖已经测过的知识点",
    reclaimed["kp-ml-kmeans"].mastery_score == 0.18 and reclaimed["kp-ml-kmeans"].source == "diagnosis",
    (reclaimed["kp-ml-kmeans"].mastery_score, reclaimed["kp-ml-kmeans"].source),
)


# ============================== 5. 实际速度校准 ==============================

print("== 实际用时校准排课节奏 ==")


class _FakeRecords:
    """按给定的「实际 / 计划」比值伪造完成记录。"""

    def __init__(self, ratios: list[float], book_id: str = "ml") -> None:
        self.rows = [
            types.SimpleNamespace(book_id=book_id, result={"planned_minutes": 20, "duration_seconds": int(20 * r * 60)})
            for r in ratios
        ]

    def list_activities(self, user_id: str, **_kwargs: object) -> dict[str, object]:
        return {"records": self.rows}


bare = LearningPlanModule.__new__(LearningPlanModule)
bare.learning_record = None
check("没有学习记录 → 不校准", bare.pace_factor("u", "ml") == 1.0)

bare.learning_record = _FakeRecords([2.0, 2.0])
check("样本不足 3 条 → 不校准（两条记录不算规律）", bare.pace_factor("u", "ml") == 1.0)

bare.learning_record = _FakeRecords([1.8, 2.0, 2.2, 2.0])
check("稳定慢 2 倍 → 校准倍数 2.0", bare.pace_factor("u", "ml") == 2.0, bare.pace_factor("u", "ml"))

bare.learning_record = _FakeRecords([1.0, 1.0, 1.0, 72.0])
check("一次误填 24 小时不带偏结果（用中位数不用均值）", bare.pace_factor("u", "ml") == 1.0)

bare.learning_record = _FakeRecords([0.1, 0.1, 0.1])
check("校准倍数下限 0.5", bare.pace_factor("u", "ml") == 0.5)
bare.learning_record = _FakeRecords([9, 9, 9])
check("校准倍数上限 3.0", bare.pace_factor("u", "ml") == 3.0)

bare.learning_record = _FakeRecords([2, 2, 2], book_id="dl")
check("只统计当前这本书的记录", bare.pace_factor("u", "ml") == 1.0)

bare.learning_record = types.SimpleNamespace(
    list_activities=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
)
check("记录读不出来时不影响生成计划", bare.pace_factor("u", "ml") == 1.0)

even = {"tasks": [{"id": "t1", "minutes": 30}, {"id": "t2", "minutes": 30}, {"id": "t3", "minutes": 30}], "advice": []}
normal = LearningPlanModule._apply_time_budget(dict(even), daily_budget=60, pace_factor=1.0)
check("速度正常：90 分钟 / 每天 60 → 2 天", normal["timeBudget"]["estimatedDays"] == 2)
slow = LearningPlanModule._apply_time_budget(dict(even), daily_budget=60, pace_factor=2.0)
check("慢 2 倍：每天只排得下一个任务 → 3 天", slow["timeBudget"]["estimatedDays"] == 3, slow["timeBudget"])
check(
    "任务自己的分钟数没被校准值改写（改写会让下一轮比值自我抹平）",
    [task["minutes"] for task in slow["tasks"]] == [30, 30, 30],
)
check("给出按实际速度折算的总时长", slow["timeBudget"]["adjustedTotalMinutes"] == 180)
check("提示里说明了放慢的原因", any("放慢排课" in item for item in slow["advice"]), slow["advice"])
fast = LearningPlanModule._apply_time_budget(dict(even), daily_budget=60, pace_factor=0.5)
check("比估计快 → 1 天做完", fast["timeBudget"]["estimatedDays"] == 1)

mixed = {
    "tasks": [
        {"id": "a", "minutes": 30, "status": "completed", "expectedCompletionDate": "2020-01-01"},
        {"id": "b", "minutes": 30, "status": "todo"},
        {"id": "c", "minutes": 30, "status": "todo"},
    ],
    "advice": [],
}
partial = LearningPlanModule._apply_time_budget(dict(mixed), daily_budget=30, pace_factor=1.0, only_unfinished=True)
partial_by = {task["id"]: task for task in partial["tasks"]}
check("重排冻结已完成任务的日期", partial_by["a"]["expectedCompletionDate"] == "2020-01-01")
check("重排只挪未完成的任务", partial_by["b"]["expectedCompletionDate"] != partial_by["c"]["expectedCompletionDate"])
check("总时长只算未完成的部分", partial["timeBudget"]["totalMinutes"] == 60)

once = LearningPlanModule._apply_time_budget(dict(even), daily_budget=60, pace_factor=1.0)
twice = LearningPlanModule._apply_time_budget(once, daily_budget=120, pace_factor=1.0)
thrice = LearningPlanModule._apply_time_budget(twice, daily_budget=30, pace_factor=1.0)
schedule_advice = [item for item in thrice["advice"] if item.startswith(LearningPlanModule.SCHEDULE_ADVICE_PREFIX)]
check("重排多次仍然只保留一条排课说明", len(schedule_advice) == 1, thrice["advice"])
check("说明反映最新一次的预算", "30 分钟" in schedule_advice[0], schedule_advice[0])


# ============================== 6. 改目标自动重排 ==============================

print("== 改目标后自动重排在途计划 ==")

workspace = Path(tempfile.mkdtemp(prefix="reschedule-"))
plans_path = workspace / "plans.json"
plans_path.write_text(
    json.dumps(
        {
            "ml:diag1": {
                "bookId": "ml",
                "diagnosticId": "diag1",
                "userId": "demo_user",
                "plan": {
                    "book": {"title": "机器学习"},
                    "goal": "g",
                    "goalLevel": "l",
                    "advice": [],
                    "resources": [],
                    "tasks": [
                        {"id": "t1", "minutes": 40, "status": "completed", "expectedCompletionDate": "2020-01-01"},
                        {"id": "t2", "minutes": 40, "status": "todo"},
                        {"id": "t3", "minutes": 40, "status": "todo"},
                        {"id": "t4", "minutes": 40, "status": "todo"},
                    ],
                },
            }
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

reschedule_goals = LearnerGoalModule(workspace / "goals.json")
plan_module = LearningPlanModule.__new__(LearningPlanModule)
plan_module.reader = common_api.json_storage.JsonContentReader(plans_path)
plan_module.store = common_api.json_storage.JsonStore()
plan_module.learner_goals = reschedule_goals
plan_module.learning_record = None

reschedule_app = FastAPI()


@reschedule_app.exception_handler(common_errors.AppError)
async def _reschedule_error(_request: Request, exc: common_errors.AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


reschedule_app.include_router(build_goal_router(reschedule_goals, plan_module))
scheduler_client = TestClient(reschedule_app, raise_server_exceptions=False)

response = scheduler_client.post(
    "/api/learner-goals",
    json={"bookId": "ml", "targetLevel": "能够独立完成基础练习", "weeklyHours": 14, "userId": "demo_user"},
)
check("保存目标顺带重排在途计划", response.json()["rescheduled"] is True, response.text)
first_days = response.json()["estimatedDays"]
check("每周 14 小时 → 每天 120 分钟 → 3 个未完成任务 1 天排完", first_days == 1, response.json())
check("首次保存不提示重做诊断", response.json()["planRefreshSuggested"] is False)

response = scheduler_client.post(
    "/api/learner-goals",
    json={"bookId": "ml", "targetLevel": "能够独立完成基础练习", "weeklyHours": 5, "userId": "demo_user"},
)
check("调低每周时长 → 重排且需要更多天", response.json()["rescheduled"] and response.json()["estimatedDays"] > first_days, response.json())

persisted = json.loads(plans_path.read_text(encoding="utf-8"))["ml:diag1"]["plan"]
persisted_by = {task["id"]: task for task in persisted["tasks"]}
check("已完成任务的日期没被改写", persisted_by["t1"]["expectedCompletionDate"] == "2020-01-01")
check("未完成任务拿到新日期", persisted_by["t2"].get("expectedCompletionDate") not in (None, "2020-01-01"))
check("重排结果真的落盘了", persisted.get("timeBudget", {}).get("dailyMinutes") == 43, persisted.get("timeBudget"))

response = scheduler_client.post(
    "/api/learner-goals",
    json={"bookId": "ml", "targetLevel": "能够指导他人 / 应对面试", "weeklyHours": 5, "userId": "demo_user"},
)
check("只改目标水平 → 提示可以重做诊断", response.json()["planRefreshSuggested"] is True, response.json())
check("只改目标水平 → 不自动重生成任务（重生成会清掉完成进度）", response.json()["rescheduled"] is False)
check("任务内容原样保留", len(json.loads(plans_path.read_text(encoding="utf-8"))["ml:diag1"]["plan"]["tasks"]) == 4)

response = scheduler_client.post(
    "/api/learner-goals",
    json={"bookId": "ml", "targetLevel": "能够指导他人 / 应对面试", "weeklyHours": 9, "userId": "other_user"},
)
check("别人改目标不会动到我的计划", response.json()["rescheduled"] is False, response.json())

print(f"\n全部通过：{PASSED} 项断言")
