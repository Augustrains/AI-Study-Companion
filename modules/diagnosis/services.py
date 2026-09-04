"""Application and domain services for the diagnosis module.

The workflow owns orchestration and LangGraph state transitions.  This module
owns reusable diagnosis operations so graph nodes do not contain business
rules or persistence details.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Iterable

from modules.common import api as common_api
from modules.common.errors import ResourceNotFoundError

from .mastery_rules import calculate_mastery_update
from .models import (
    AnswerRecord,
    AnswerResult,
    DiagnosisResult,
    KnowledgePointResult,
    KnowledgePointQuestionPlan,
    Question,
    QuestionPlanningInput,
    STATUSES,
    TASK_MODES,
)


def _review_due(review_state: dict[str, Any]) -> bool:
    value = review_state.get("next_review_at") or review_state.get("nextReviewAt")
    if not value:
        return False
    try:
        scheduled = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return scheduled <= datetime.now(scheduled.tzinfo)


def _eligible_question_counts(agent_input: QuestionPlanningInput) -> dict[str, int]:
    if not agent_input.knowledge_point_catalog:
        return dict(agent_input.available_question_counts)
    goal = "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", agent_input.learning_goal.lower()))
    for phrase in ("理解", "掌握", "学习", "复习", "熟悉", "巩固", "基础", "知识点", "相关", "以及"):
        goal = goal.replace(phrase, "")
    goal_pairs = {goal[index:index + 2] for index in range(max(0, len(goal) - 1))}
    matched = set()
    for point_id, item in agent_input.knowledge_point_catalog.items():
        name = "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", item.get("name", "").lower()))
        description = "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", item.get("description", "").lower()))
        if len(goal_pairs & {name[i:i + 2] for i in range(max(0, len(name) - 1))}) >= 2 or len(
            goal_pairs & {description[i:i + 2] for i in range(max(0, len(description) - 1))}
        ) >= 4:
            matched.add(point_id)
    remembered = {
        point_id
        for point_id, level in agent_input.knowledge_point_mastery.items()
        if level != "掌握" or _review_due(agent_input.knowledge_point_review.get(point_id, {}))
    }
    eligible = (matched | remembered) & set(agent_input.available_question_counts)
    return {
        point_id: count
        for point_id, count in agent_input.available_question_counts.items()
        if not eligible or point_id in eligible
    }


def build_question_planning_prompt(agent_input: QuestionPlanningInput) -> str:
    points = [
        {
            "knowledgePointId": point_id,
            "name": agent_input.knowledge_point_catalog.get(point_id, {}).get("name", ""),
            "description": agent_input.knowledge_point_catalog.get(point_id, {}).get("description", ""),
            "mastery": agent_input.knowledge_point_mastery.get(point_id, "未测评"),
            "review": agent_input.knowledge_point_review.get(point_id, {}),
            "availableQuestionCount": count,
        }
        for point_id, count in _eligible_question_counts(agent_input).items()
    ]
    # 复测上下文：让模型知道这是第几轮、已经考过多少题。
    # 取题时本来就会把做过的题排到候选池末尾，但那是「事后过滤」；
    # 把轮次告诉模型，它才能在**分配题量**这一层就往没考过的知识点倾斜。
    # 已答题目 ID 只给数量不给全量列表——几十上百个 ID 塞进提示词既占上下文
    # 又对「每个知识点出几道」这个决策没有帮助。
    round_number = max(1, int(agent_input.diagnosis_round or 1))
    answered_count = len(agent_input.answered_question_ids or [])
    if round_number <= 1:
        review_context = "这是该用户在本书上的第 1 次诊断，没有历史答题记录。"
    else:
        review_context = (
            f"这是第 {round_number} 轮复测，该用户此前已作答 {answered_count} 道题。"
            "同一知识点的题目会优先出没做过的，题池用尽才回收旧题；"
            "因此请优先把题量分配给尚未充分验证、或已到期需要复习的知识点，"
            "不要把题量集中在上一轮已经答对过的地方。"
        )

    return f"""你是 Study Companion 的自适应选题 Agent。请决定每个知识点的题量和 taskMode。

规则：
1. 只能使用输入中的 knowledgePointId。
2. questionCount 必须是 0 到 min(4, availableQuestionCount) 的整数，总数不得超过 8。
3. taskMode 只能是 diagnostic、guided_practice、independent、retrieval、remediation、challenge。
4. 优先选择与学习目标相关、薄弱或到期复习的知识点。
5. 只输出 JSON，不要输出解释。

学习目标：{agent_input.learning_goal or '未指定'}
复测情况：{review_context}
候选知识点：{json.dumps(points, ensure_ascii=False)}

输出格式：
{{"selections":[{{"knowledgePointId":"知识点ID","questionCount":2,"taskMode":"diagnostic"}}]}}
"""


def _fallback_question_plan(agent_input: QuestionPlanningInput) -> list[KnowledgePointQuestionPlan]:
    count_by_level = {"未测试": 4, "未测评": 4, "不会": 4, "了解": 3, "熟悉": 2, "掌握": 1}
    mode_by_level = {
        "未测试": "diagnostic", "未测评": "diagnostic", "不会": "remediation",
        "了解": "guided_practice", "熟悉": "independent", "掌握": "challenge",
    }
    result = []
    for point_id, available in _eligible_question_counts(agent_input).items():
        level = agent_input.knowledge_point_mastery.get(point_id, "未测评")
        mode = "retrieval" if level == "掌握" and _review_due(
            agent_input.knowledge_point_review.get(point_id, {})
        ) else mode_by_level.get(level, "diagnostic")
        result.append(KnowledgePointQuestionPlan(point_id, min(count_by_level.get(level, 3), available, 4), mode))
    return result


def parse_question_plan(
    response: str,
    agent_input: QuestionPlanningInput,
    maximum_total: int,
) -> list[KnowledgePointQuestionPlan]:
    fallback = {item.knowledge_point_id: item for item in _fallback_question_plan(agent_input)}
    raw_items: list[Any] = []
    try:
        text = response.strip()
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:-1]).strip()
        payload = json.loads(text)
        raw_items = payload.get("selections", []) if isinstance(payload, dict) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    by_id = {
        str(item.get("knowledgePointId", "")): item
        for item in raw_items
        if isinstance(item, dict)
    }
    eligible = _eligible_question_counts(agent_input)

    # 每个知识点「想要」几道题、用什么模式（模型给了就用模型的，否则用规则默认）
    wanted: dict[str, int] = {}
    modes: dict[str, str] = {}
    for point_id, available in eligible.items():
        raw = by_id.get(point_id, {})
        default = fallback[point_id]
        mode = str(raw.get("taskMode", ""))
        if mode not in TASK_MODES or (mode == "retrieval" and not _review_due(agent_input.knowledge_point_review.get(point_id, {}))):
            mode = default.task_mode
        try:
            count = int(raw.get("questionCount", default.question_count))
        except (TypeError, ValueError):
            count = default.question_count
        wanted[point_id] = min(max(0, count), available, 4)
        modes[point_id] = mode

    granted = _allocate_question_budget(wanted, maximum_total, agent_input.diagnosis_round)
    return [KnowledgePointQuestionPlan(point_id, granted.get(point_id, 0), modes[point_id]) for point_id in eligible]


def _allocate_question_budget(wanted: dict[str, int], maximum_total: int, diagnosis_round: int = 1) -> dict[str, int]:
    """把有限的题量按「轮转发牌」分配给各知识点，而不是先到先得。

    原实现是顺序遍历、`remaining` 减到 0 为止：26 个知识点各想要 4 道、
    总预算 8 道时，**按字母序排在最前面的两个知识点会吃掉全部 8 道**，
    其余 24 个一道都没有。首次诊断因此只覆盖 2/26 个知识点，
    测不出用户的整体水平——诊断的意义就在于广度。

    现在改成一轮一轮发：每轮给还没发够的知识点各发 1 道，发到预算用完为止。
    - 想要得多的（薄弱、未测评）会在更多轮里拿到题，自然分到更多；
    - 想要得少的（已掌握）拿 1 道点到为止；
    - 预算不够覆盖全部知识点时，至少能覆盖 maximum_total 个不同的知识点。

    diagnosis_round 决定发牌的起始位置：第 2 轮复测从上一轮的下一个知识点开始，
    这样连续几次诊断能轮换着覆盖不同的知识点，而不是每次都测同样那几个。
    """

    order = [point_id for point_id in wanted if wanted[point_id] > 0]
    if not order or maximum_total <= 0:
        return {point_id: 0 for point_id in wanted}

    # 按「想要的题量」从多到少排序，同数量时保持原顺序，保证结果确定可复现。
    order.sort(key=lambda point_id: -wanted[point_id])
    # 轮换起点：第 N 轮从第 (N-1) 个知识点开始发，避免每轮都从同一个开始。
    offset = max(0, int(diagnosis_round or 1) - 1) % len(order)
    order = order[offset:] + order[:offset]

    granted = {point_id: 0 for point_id in wanted}
    remaining = maximum_total
    while remaining > 0:
        progressed = False
        for point_id in order:
            if remaining <= 0:
                break
            if granted[point_id] >= wanted[point_id]:
                continue
            granted[point_id] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            # 所有知识点都发到了各自想要的上限，预算还有剩余，正常结束。
            break
    return granted


class GeneratedQuestionBank:
    """Load the generated bilingual Quiz catalog."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.items_path = self.root / "题目" / "curriculum_items.jsonl"
        self.localization_path = self.root / "题目" / "quiz_localization_zh_review.csv"
        self.mapping_path = self.root / "题目-知识点映射" / "quiz_knowledge_mapping_candidates.csv"
        self.taxonomy_path = self.root / "题目-教材映射" / "knowledge_taxonomy.json"

    def get_question_inventory(self, book_id: str) -> dict[str, int]:
        """Return generated quiz availability for each mapped knowledge point."""

        target = {"machine_learning": "ml-001", "deep_learning": "dl-001"}.get(book_id, book_id)
        taxonomy = json.loads(self.taxonomy_path.read_text(encoding="utf-8"))
        valid_points = {row["knowledge_point_id"] for row in taxonomy}
        mapping_by_item: dict[str, list[str]] = defaultdict(list)
        for row in self._read_csv(self.mapping_path):
            if row.get("knowledge_point_id") in valid_points:
                mapping_by_item[row.get("learning_item_id", "")].append(row["knowledge_point_id"])
        counts: dict[str, int] = defaultdict(int)
        for line in self.items_path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("item_type") != "quiz_question":
                continue
            repository = item.get("source", {}).get("repository_name", "")
            if {"ML-For-Beginners": "ml-001", "AI-For-Beginners": "dl-001"}.get(repository, "") != target:
                continue
            for point_id in mapping_by_item.get(str(item.get("learning_item_id", "")), []):
                counts[point_id] += 1
        return dict(sorted(counts.items()))

    def get_questions(
        self,
        book_id: str,
        *,
        max_questions_per_knowledge_point: int = 4,
        question_plan: dict[str, dict[str, Any]],
        exclude_question_ids: set[str] | None = None,
        rotation_seed: str = "",
    ) -> tuple[list[Question], dict[str, str]]:
        """
        按知识点选题。

        exclude_question_ids：该用户此前已作答过的题目 ID。
            这些题会被降级到候选池末尾，只有在未做过的题不够用时才回收，
            从而让复测拿到新题而不是每次重复同一批。
        rotation_seed：确定性打乱种子（一般传 user_id + 轮次）。
            同一 seed 结果可复现，便于排查；不同轮次自然换一批题。
        """
        target = {"machine_learning": "ml-001", "deep_learning": "dl-001"}.get(book_id, book_id)
        taxonomy = json.loads(self.taxonomy_path.read_text(encoding="utf-8"))
        valid_points = {row["knowledge_point_id"] for row in taxonomy}
        mapping_by_item: dict[str, list[str]] = defaultdict(list)
        for row in self._read_csv(self.mapping_path):
            if row.get("knowledge_point_id") in valid_points:
                mapping_by_item[row.get("learning_item_id", "")].append(row["knowledge_point_id"])
        localizations = {row.get("learning_item_id", ""): row for row in self._read_csv(self.localization_path)}
        seen = set(exclude_question_ids or ())

        # 第一步：收集每个知识点下的全部候选题，不再边遍历边截断。
        candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for line in self.items_path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("item_type") != "quiz_question":
                continue
            repository = item.get("source", {}).get("repository_name", "")
            item_book = {"ML-For-Beginners": "ml-001", "AI-For-Beginners": "dl-001"}.get(repository, "")
            if item_book != target:
                continue
            item_id = str(item.get("learning_item_id", ""))
            points = [
                point
                for point in mapping_by_item.get(item_id, [])
                if point in question_plan and int(question_plan[point].get("question_count", 0)) > 0
            ]
            if not points:
                continue
            candidates[points[0]].append({"item": item, "item_id": item_id, "points": points})

        # 第二步：每个知识点内部先按「是否做过」分层，再在层内确定性打乱后取前 N 道。
        counts: dict[str, int] = defaultdict(int)
        questions: list[Question] = []
        answers: dict[str, str] = {}
        for point_id in sorted(candidates):
            wanted = min(
                int(question_plan[point_id].get("question_count", 0)),
                max_questions_per_knowledge_point,
            )
            if wanted <= 0:
                continue
            pool = candidates[point_id]
            unseen = [entry for entry in pool if entry["item_id"] not in seen]
            reused = [entry for entry in pool if entry["item_id"] in seen]
            self._shuffle_in_place(unseen, f"{rotation_seed}:{point_id}:unseen")
            self._shuffle_in_place(reused, f"{rotation_seed}:{point_id}:reused")
            # 未做过的优先；不够时才回收做过的
            for entry in (unseen + reused)[:wanted]:
                item, item_id, points = entry["item"], entry["item_id"], entry["points"]
                loc = localizations.get(item_id, {})
                options = item.get("options", [])
                parsed = [
                    {
                        "id": str(option.get("key", "")),
                        "text": loc.get(f"zh_option_{str(option.get('key', '')).lower()}")
                        or str(option.get("text", "")),
                    }
                    for option in options
                ]
                planned_mode = str(question_plan[points[0]].get("task_mode", ""))
                questions.append(Question(id=item_id, title=loc.get("zh_stem") or str(item.get("stem", "")), tag=points[0], book_id=target, knowledge_point_ids=points, task_mode=planned_mode or "diagnostic", options=parsed, source=str(item.get("source", {}).get("source_url", ""))))
                answers[item_id] = next((str(option.get("key", "")) for option in options if option.get("is_correct")), "")
                for point in points:
                    counts[point] += 1
        return questions, answers

    @staticmethod
    def _shuffle_in_place(entries: list[dict[str, Any]], seed: str) -> None:
        """按 seed 做确定性打乱：同一 seed 顺序可复现，不同轮次顺序不同。"""
        import random

        random.Random(seed).shuffle(entries)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        import csv
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))


class AssessmentService:
    """记录答题事实，并按知识点调用掌握度规则。"""

    def answer_result(
        self,
        questions: Iterable[Question],
        answers: dict[str, str],
        correct_answers: dict[str, str],
        answer_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> AnswerResult:
        records: list[AnswerRecord] = []
        metadata = answer_metadata or {}
        for question in questions:
            submitted = answers.get(question.id, "")
            submitted_id = self._to_option_id(question, submitted)
            expected = correct_answers.get(question.id, "")
            is_correct = bool(submitted) and self._normalize(submitted_id) == self._normalize(expected)
            answer_meta = metadata.get(question.id, {})
            records.append(
                AnswerRecord(
                    question=question,
                    submitted_answer=submitted_id,
                    correct_answer=expected,
                    is_correct=is_correct,
                    skipped=not bool(submitted),
                    hint_count=int(answer_meta.get("hint_count", 0)),
                    retry_count=int(answer_meta.get("retry_count", 0)),
                    is_independent=bool(answer_meta.get("is_independent", True)),
                    is_delayed_retrieval=bool(answer_meta.get("is_delayed_retrieval", question.task_mode == "retrieval")),
                    occurred_at=str(answer_meta.get("occurred_at") or datetime.now().astimezone().isoformat()),
                )
            )
        total = len(records)
        answered = sum(not item.skipped for item in records)
        correct = sum(item.is_correct for item in records)
        return AnswerResult(
            answer_records=records,
            total_questions=total,
            answered_questions=answered,
            skipped_questions=total - answered,
            correct_questions=correct,
            accuracy=round(correct / answered * 100, 2) if answered else 0.0,
            confidence="high" if answered == total else "medium" if answered else "low",
        )

    def diagnose(
        self,
        answer_result: AnswerResult,
        current_states: dict[str, dict[str, Any]] | None = None,
    ) -> list[KnowledgePointResult]:
        grouped: dict[str, list[AnswerRecord]] = defaultdict(list)
        for record in answer_result.answer_records:
            for point_id in record.question.knowledge_point_ids or [record.question.tag]:
                grouped[point_id].append(record)
        results: list[KnowledgePointResult] = []
        states = current_states or {}
        for knowledge_point_id, records in grouped.items():
            update = calculate_mastery_update(
                {
                    "currentState": states.get(knowledge_point_id, {}),
                    "evidence": [
                        {
                            "evidenceId": f"{record.question.id}:answer:{knowledge_point_id}",
                            "score": 1.0 if record.is_correct else 0.0,
                            "isCorrect": record.is_correct,
                            "evidenceStrength": "direct",
                            "taskMode": record.question.task_mode,
                            "hintCount": record.hint_count,
                            "retryCount": record.retry_count,
                            "isIndependent": record.is_independent,
                            "isDelayedRetrieval": record.is_delayed_retrieval,
                            "occurredAt": record.occurred_at,
                        }
                        for record in records
                    ],
                }
            )
            results.append(
                KnowledgePointResult(
                    knowledge_point_id=knowledge_point_id,
                    ai_status=update["masteryLevel"],
                    correct=sum(item.is_correct for item in records),
                    total=len(records),
                    mastery_score=update["masteryScore"],
                    memory_status=update["memoryStatus"],
                    memory_stability_days=update["memoryStabilityDays"],
                    confidence=update["confidence"],
                    evidence_ids=update["evidenceIds"],
                    evidence_summary=update["evidenceSummary"],
                    reason_codes=update["reasonCodes"],
                    algorithm_name=update["algorithmName"],
                    algorithm_version=update["algorithmVersion"],
                    next_review_at=update["nextReviewAt"],
                )
            )
        return results

    @staticmethod
    def _to_option_id(question: Question, answer: str) -> str:
        option_ids = {option["id"] for option in question.options}
        if answer in option_ids:
            return answer
        normalized = AssessmentService._normalize(answer)
        return next(
            (
                option["id"]
                for option in question.options
                if AssessmentService._normalize(option["text"]) == normalized
            ),
            answer,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(value.strip().lower().split())

class DiagnosisResultStore:
    """用户确认后的诊断结果仓库。"""

    def __init__(self) -> None:
        self._results: dict[str, DiagnosisResult] = {}

    def save(self, result: DiagnosisResult) -> None:
        self._results[result.diagnosis_id] = result

    def get(self, diagnosis_id: str) -> DiagnosisResult:
        try:
            return self._results[diagnosis_id]
        except KeyError as exc:
            raise ResourceNotFoundError(
                f"diagnosis result not found: {diagnosis_id}",
                details={"resource": "diagnosis_result", "diagnosis_id": diagnosis_id},
            ) from exc


class DiagnosisService:
    """Reusable transformations and commit operations for diagnosis runs."""

    @staticmethod
    def questions_from_state(items: list[dict[str, Any]]) -> list[Question]:
        return [
            Question(
                id=item["id"],
                title=item["title"],
                tag=item["tag"],
                book_id=item.get("book_id", ""),
                chapter_id=item.get("chapter_id", ""),
                section_ids=item.get("section_ids", []),
                knowledge_point_ids=item.get("knowledge_point_ids", []),
                task_mode=item.get("task_mode", "diagnostic"),
                options=list(item.get("options", [])),
                source=item.get("source", ""),
            )
            for item in items
        ]

    @staticmethod
    def question_payload(question: Question) -> dict[str, Any]:
        return {
            "id": question.id,
            "title": question.title,
            "tag": question.tag,
            "book_id": question.book_id,
            "chapter_id": question.chapter_id,
            "section_ids": question.section_ids,
            "knowledge_point_ids": question.knowledge_point_ids,
            "task_mode": question.task_mode,
            "source": question.source,
            "options": question.options,
        }

    @staticmethod
    def summary(
        learning_goal: str,
        answer_result: AnswerResult,
        results: list[KnowledgePointResult],
    ) -> dict[str, Any]:
        statuses = [item.ai_status for item in results if item.ai_status in STATUSES]
        level = max(statuses, key=STATUSES.index) if statuses else STATUSES[0]
        return {
            "level": level,
            "accuracy": f"{round(answer_result.accuracy)}%",
            "confidence": answer_result.confidence,
            "evidence": f"依据 {answer_result.answered_questions} 道有效作答，评估 {len(results)} 个知识点。",
            "answer_performance": (
                f"共完成 {answer_result.answered_questions}/{answer_result.total_questions} 道题，"
                f"答对 {answer_result.correct_questions} 道。"
            ),
            "generated_at": datetime.now().astimezone().isoformat(),
            "related_scope": f"{learning_goal}及其前置知识点",
        }

    @staticmethod
    def final_result(
        diagnosis_id: str,
        user_id: str,
        book_id: str,
        learning_goal: str,
        draft_results: list[dict[str, Any]],
        answer_result: dict[str, Any],
        calibration: str,
        calibration_reason: str,
    ) -> DiagnosisResult:
        calibrations = DiagnosisService.calibrations(draft_results, calibration)
        results = [KnowledgePointResult(**item) for item in draft_results]
        for result in results:
            result.calibrated_status = calibrations.get(result.knowledge_point_id)
        return DiagnosisResult(
            diagnosis_id=diagnosis_id,
            user_id=user_id,
            book_id=book_id,
            learning_goal=learning_goal,
            answer_result=common_api.serialization.from_data(AnswerResult, answer_result),
            results=results,
            calibration=calibration,
            calibration_reason=calibration_reason,
        )

    @staticmethod
    def calibrations(results: list[dict[str, Any]], calibration: str) -> dict[str, str]:
        if calibration == "same":
            return {}
        delta = -1 if calibration == "lower" else 1
        statuses = STATUSES[1:]
        return {
            item["knowledge_point_id"]: statuses[
                max(0, min(len(statuses) - 1, statuses.index(item["ai_status"]) + delta))
            ]
            for item in results
        }
