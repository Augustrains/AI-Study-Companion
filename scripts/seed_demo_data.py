"""
生成体验账号（demo_user）的演示数据。

用法（在项目根目录执行）：
    python3.11 scripts/seed_demo_data.py            # 写入演示数据
    python3.11 scripts/seed_demo_data.py --dry-run  # 只打印将要写入的内容，不落盘
    python3.11 scripts/seed_demo_data.py --reset    # 先清除 demo_user 已有的记忆再写入

设计说明：
    - 全部通过项目自身的模块写入（MemoryModule / LearningRecordModule / LearningPlanModule），
      不直接拼 JSON，因此字段结构与校验规则始终和后端保持一致。
    - 只写 user_id == demo_user 的数据，不会触碰其他用户的记录。
    - 可重复执行：学习记录按 client_request_id 幂等，记忆与计划按 key upsert。

配套的前端登录凭据见项目根目录 README.md（demo@study.local / demo1234），
前端 src/services/session.ts 中的 DEMO_ACCOUNT.userId 必须与此处的 DEMO_USER_ID 一致。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from modules.learning_record.field_rules import validate_learning_activity  # noqa: E402
from modules.learning_record.models import LearningActivity  # noqa: E402
from modules.learning_record.module import LearningRecordModule  # noqa: E402
from modules.memory.models import EvidenceSummary, KnowledgePointMemory, LearnerMemory  # noqa: E402
from modules.memory.repository import JsonMemoryRepository  # noqa: E402

DEMO_USER_ID = "demo_user"
DEMO_BOOK_ID = "ml"
DEMO_DOMAIN = "ml-001"  # MemoryModule._domain("machine_learning") 的结果

NOW = datetime.now(timezone.utc)


def iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


# --------------------------------------------------------------------------
# 1. 掌握度与复习计划（LearnerMemory）
#    知识点 ID 从真实题库读取，保证和诊断出题、能力图谱完全对得上。
# --------------------------------------------------------------------------
KNOWLEDGE_POINT_SOURCE = PROJECT_DIR / "data" / "question_new" / "知识点" / "机器学习知识点.json"

# 按学习顺序挑选的演示知识点，覆盖四种掌握等级和三种复习状态。
# (真实知识点 ID, 掌握等级, 掌握分, 置信度, 记忆状态, 稳定天数, 下次复习距今天数)
KNOWLEDGE_POINT_PLAN = [
    ("kp-ml-intro", "掌握", 0.88, 0.92, "稳定保持", 15.0, 9.0),
    ("kp-ml-regression-intro", "熟悉", 0.74, 0.81, "延迟复测通过", 7.0, 3.0),
    ("kp-ml-linear-polynomial-regression", "熟悉", 0.66, 0.70, "首次验证", 2.0, -1.0),   # 已到期
    ("kp-ml-logistic-regression", "了解", 0.41, 0.63, "首次验证", 1.0, -2.0),            # 已到期
    ("kp-ml-classification-intro", "了解", 0.52, 0.58, "未验证", 0.0, None),
    ("kp-ml-kmeans", "不会", 0.18, 0.45, "未验证", 0.0, None),
]


def load_knowledge_point_names() -> dict[str, str]:
    """从题库的知识点清单里读取真实名称，避免脚本里再写死一份。"""
    payload = json.loads(KNOWLEDGE_POINT_SOURCE.read_text(encoding="utf-8"))
    return {
        str(item.get("knowledge_point_id", "")): str(item.get("name", ""))
        for item in payload.get("knowledge_points", [])
    }


def build_memory() -> LearnerMemory:
    names = load_knowledge_point_names()
    missing = [point_id for point_id, *_ in KNOWLEDGE_POINT_PLAN if point_id not in names]
    if missing:
        raise SystemExit(f"知识点 ID 在题库中不存在，请检查 {KNOWLEDGE_POINT_SOURCE.name}: {missing}")

    memory = LearnerMemory(user_id=DEMO_USER_ID, learning_domain=DEMO_DOMAIN)
    points = []
    for point_id, level, score, confidence, status, stability, review_in in KNOWLEDGE_POINT_PLAN:
        points.append(
            KnowledgePointMemory(
                knowledge_point_id=point_id,
                name=names[point_id],
                description=f"{names[point_id]}：体验账号预置的演示掌握度数据。",
                mastery_level=level,
                mastery_score=score,
                confidence=confidence,
                memory_status=status,
                memory_stability_days=stability,
                evidence_summary=EvidenceSummary(
                    accepted_evidence_count=4,
                    effective_evidence_weight=3.2,
                    independent_correct_count=3 if score > 0.6 else 1,
                    delayed_correct_count=1 if stability >= 2 else 0,
                    delayed_failure_count=0 if score > 0.6 else 1,
                    guided_evidence_count=1,
                ),
                next_review_at=None if review_in is None else iso(-review_in),
                updated_at=iso(1),
                update_count=2,
                source="demo-seed",
            )
        )
    memory.knowledge_points = points
    memory.diagnosis_summary = {
        "diagnostic_id": "demo-diagnostic-001",
        "accuracy": 64,
        "correct_count": 7,
        "total_count": 11,
        "level": "熟悉",
    }
    memory.updated_at = iso(1)
    memory.update_count = 3
    return memory


# --------------------------------------------------------------------------
# 2. 学习事件（LearningActivity）—— 支撑「本周进度」的时长与正确率统计
# --------------------------------------------------------------------------
_EVENT_TEMPLATES = [
    # (任务 ID, 标题, 关联知识点, 学习秒数, 答对数, 总题数)
    ("demo-task-1", "机器学习概念：核心术语梳理", ["kp-ml-intro"], 1500, 5, 5),
    ("demo-task-2", "回归简介：从数据到模型", ["kp-ml-regression-intro"], 1800, 4, 5),
    ("demo-task-3", "线性回归与多项式回归练习", ["kp-ml-linear-polynomial-regression"], 1200, 3, 5),
    ("demo-task-4", "逻辑回归：分类边界补强", ["kp-ml-logistic-regression"], 2100, 2, 5),
    ("demo-task-5", "分类基础精读", ["kp-ml-classification-intro"], 1500, 4, 6),
    ("demo-task-6", "K-Means 聚类入门", ["kp-ml-kmeans"], 900, 2, 5),
]


def _build_events() -> list[tuple]:
    """
    把 6 条学习事件均匀铺在「本周一 ~ 今天」之间。
    后端 _weekly_progress 以周一为一周起点统计，写死「几天前」会导致
    在周中运行时有一部分事件落到上周、不计入本周进度，所以这里按运行日动态计算。
    """
    days_since_monday = NOW.weekday()  # 周一=0
    span = max(days_since_monday, 1)
    events = []
    for index, template in enumerate(_EVENT_TEMPLATES):
        # 最早一条落在本周一（略微往后偏移避免边界），最后一条落在今天
        ratio = index / (len(_EVENT_TEMPLATES) - 1)
        days_ago = round(span * (1 - ratio) - 0.05, 3)
        events.append((max(days_ago, 0.0), *template))
    return events


LEARNING_EVENTS = _build_events()


def seed_activities(records: LearningRecordModule, dry_run: bool) -> int:
    """
    直接构造 LearningActivity 落库，而不是走 record_learning_event。
    原因：record_learning_event 会把 result 固定成 {"task_status", "task_status_label"}，
    且 occurred_at 只能取当前时间，无法携带「本周进度」统计需要的
    duration_seconds / correct_count / total_count，也无法回填历史日期。
    这里仍然复用官方的 LearningActivity 模型与 validate_learning_activity 校验器，
    保证写入的结构与后端读取逻辑完全一致。
    """
    existing_request_ids = {
        activity.client_request_id
        for activity in records.list_activities(DEMO_USER_ID, page=1, page_size=500)["records"]
    }

    written = 0
    for days_ago, task_id, title, point_ids, seconds, correct, total in LEARNING_EVENTS:
        request_id = f"demo-seed-{task_id}"
        if request_id in existing_request_ids:
            print(f"  已存在，跳过：{title}")
            continue
        if dry_run:
            print(f"  [dry-run] 学习事件 {task_id} · {title} · {seconds}s · {correct}/{total}")
            written += 1
            continue

        occurred = iso(days_ago)
        activity = LearningActivity(
            id=f"activity_task_completed_{task_id}_demo",
            user_id=DEMO_USER_ID,
            created_at=occurred,
            updated_at=occurred,
            category="task",
            activity_type="task_completed",
            status="success",
            title="完成学习任务",
            description=f"{title} 计划 已完成",
            occurred_at=occurred,
            book_id=DEMO_BOOK_ID,
            plan_id="demo-plan-001",
            task_id=task_id,
            knowledge_point_ids=list(point_ids),
            result={
                "task_status": "completed",
                "task_status_label": "已完成",
                # 「本周进度」卡片读取的三个字段
                "duration_seconds": seconds,
                "correct_count": correct,
                "total_count": total,
            },
            detail={"task_title": title, "source": "demo-seed"},
            client_request_id=request_id,
            source="web",
        )
        validated = validate_learning_activity(activity)
        records.store.save(path=records.reader.path, content=validated, mode="append")
        written += 1
    return written


# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="生成体验账号的演示数据")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要写入的内容")
    parser.add_argument("--reset", action="store_true", help="先清除 demo_user 已有的掌握度记忆")
    args = parser.parse_args()

    print(f"体验账号 user_id = {DEMO_USER_ID}，学习内容 = {DEMO_BOOK_ID}（{DEMO_DOMAIN}）")
    print(f"数据目录：{PROJECT_DIR / 'data'}")
    print()

    repository = JsonMemoryRepository()
    records = LearningRecordModule()

    print("① 写入掌握度与复习计划（data/memory/learner_memories.json）")
    memory = build_memory()
    for point in memory.knowledge_points:
        due = "未安排复习" if not point.next_review_at else ("已到期" if point.next_review_at < NOW.isoformat() else f"复习于 {point.next_review_at[:10]}")
        print(f"  {point.name}（{point.knowledge_point_id}｜{point.mastery_level}，掌握分 {point.mastery_score}）· {due}")
    if not args.dry_run:
        if args.reset:
            existing = repository.get(DEMO_USER_ID, DEMO_DOMAIN)
            if existing is not None:
                print("  已清除原有记忆记录")
        repository.upsert(memory)
    print()

    print("② 写入学习事件（data/learning_record/activities.json）")
    count = seed_activities(records, args.dry_run)
    print(f"  共 {count} 条学习事件")
    print()

    if args.dry_run:
        print("dry-run 结束，未写入任何文件。")
    else:
        print("演示数据写入完成。用 demo@study.local / demo1234 登录即可看到。")
    print()
    print("说明：学习计划（data/learning_plan/plans.json）不在此脚本内预置，")
    print("     因为计划应由「能力诊断 → 提交校准」的真实流程生成；")
    print("     体验账号登录后走一次诊断即可得到一份真实计划。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
