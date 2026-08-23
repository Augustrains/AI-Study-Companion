"""能力诊断端到端冒烟测试。

**这个文件存在的原因**：之前给 `QuestionPlanningInput` 加了两个必填字段，
改了测试、改了取题逻辑，唯独漏了 `workflow.py` 里那个构造调用，于是
`load_questions` 一进去就 TypeError，诊断整整两轮都起不来——而所有单元测试
依然全绿，因为没有任何一个测试真正跑过那张 LangGraph 图。

所以这里刻意用**真的 LangGraph**跑完整的 `start_diagnosis`，只把 LLM 换成桩。
不需要 API key，不需要 qdrant，不需要 embedding 模型。

在项目根目录执行：

    python3.11 tests/test_diagnosis_smoke.py
"""

from __future__ import annotations

import collections
import importlib
import pkgutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.common import api as common_api  # noqa: E402
from modules.diagnosis.agent import DiagnosticAgent  # noqa: E402
from modules.diagnosis.services import (  # noqa: E402
    AssessmentService,
    DiagnosisResultStore,
    GeneratedQuestionBank,
    _allocate_question_budget,
)
from modules.diagnosis.workflow import DiagnosisWorkflow  # noqa: E402
from sdk.llm_client import LLMClient  # noqa: E402

QUESTION_DIR = ROOT / "data" / "question_new"
PASSED = 0


def check(label: str, condition: bool, extra: object = "") -> None:
    global PASSED
    assert condition, f"FAIL: {label} {extra}"
    PASSED += 1
    print(f"  ok  {label}")


class StubLLM(LLMClient):
    """返回空响应，强制走规则出题计划——也就是模型不可用时的真实路径。"""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return ""


def build_workflow(stub: StubLLM) -> DiagnosisWorkflow:
    return DiagnosisWorkflow(
        question_bank=GeneratedQuestionBank(QUESTION_DIR),
        result_store=DiagnosisResultStore(),
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(stub),
        knowledge_point_catalog=common_api.knowledge_points.JsonKnowledgePointCatalog(QUESTION_DIR / "知识点"),
    )


print("== 诊断能真的跑起来 ==")

stub = StubLLM()
result = build_workflow(stub).start_diagnosis(
    user_id="demo_user", book_id="ml-001", learning_goal="能够独立完成基础练习"
)

check("start_diagnosis 不抛异常", isinstance(result, dict))
check("返回了诊断 ID", bool(result.get("diagnostic_id")))
check("真的出了题（漏传构造参数时这里为 0 或直接崩）", len(result["questions"]) > 0, len(result["questions"]))

tags = [question["tag"] for question in result["questions"]]
distribution = collections.Counter(tags)
check(
    "题目覆盖多个知识点，而不是全压在字母序最前的那一两个上",
    len(distribution) >= 6,
    dict(distribution),
)
check("每道题都有题干", all(question["title"].strip() for question in result["questions"]))
check("每道题都有选项", all(question["options"] for question in result["questions"]))

print("== 复测上下文进了提示词 ==")
check("提示词里有复测情况", any("复测情况" in prompt for prompt in stub.prompts), stub.prompts[:1])
check("第 1 轮说明没有历史记录", any("第 1 次诊断" in prompt for prompt in stub.prompts))

print("== 题量分配：轮转发牌而不是先到先得 ==")
many = {f"kp-{index:02d}": 4 for index in range(26)}
granted = _allocate_question_budget(many, 8, 1)
check("26 个知识点各想要 4 道、预算 8 → 覆盖 8 个知识点", sum(1 for value in granted.values() if value) == 8)
check("总量不超预算", sum(granted.values()) == 8)
second_round = [key for key, value in _allocate_question_budget(many, 8, 2).items() if value]
first_round = [key for key, value in granted.items() if value]
check("第 2 轮起点轮换，覆盖不同的知识点", second_round != first_round, (first_round[:3], second_round[:3]))

mixed = {"weak": 4, "ok": 2, "mastered": 1}
check("预算充足时各拿各的量", _allocate_question_budget(mixed, 8, 1) == {"weak": 4, "ok": 2, "mastered": 1})
check("预算紧张时先保证覆盖面", _allocate_question_budget(mixed, 3, 1) == {"weak": 1, "ok": 1, "mastered": 1})
check("预算超过需求时不会多发", sum(_allocate_question_budget(mixed, 100, 1).values()) == 7)
check("空输入不炸", _allocate_question_budget({}, 8, 1) == {} and _allocate_question_budget({"a": 0}, 8, 1) == {"a": 0})

print("== 所有模块都能导入 ==")
# 上面那个 bug 属于「改了共享数据结构、漏改调用方」。逐个导入模块至少能挡住
# 导入期就暴露的同类问题（签名不匹配、模块名写错、循环依赖）。
skipped = {"modules.material_qa.services"}  # 依赖 qdrant / embedding，跳过
failures: list[str] = []
for module_info in pkgutil.walk_packages([str(ROOT / "modules")], prefix="modules."):
    if module_info.name in skipped:
        continue
    try:
        importlib.import_module(module_info.name)
    except Exception as error:  # noqa: BLE001
        failures.append(f"{module_info.name}: {type(error).__name__}: {error}")
check("modules 下所有模块导入成功", not failures, failures)

print(f"\n全部通过：{PASSED} 项断言")
