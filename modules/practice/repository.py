from __future__ import annotations

import json
import random
import time
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from modules.common.errors import ValidationAppError
from modules.learning_record.module import LearningRecordModule


class PracticeRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._question_id_bounds: dict[int, tuple[int, int]] = {}
        # 进度计算涉及答题、任务和排行榜聚合；短缓存避免重复打开页面时反复全量统计。
        self._achievement_progress_cache: dict[int, tuple[float, dict[str, Any]]] = {}

    def _ensure_resumable_session_schema(self) -> None:
        """Keep free-practice sessions reopenable on legacy databases."""

        with self.engine.begin() as connection:
            columns = {
                str(row[0])
                for row in connection.execute(text(
                    "SELECT COLUMN_NAME FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = 'diagnostic_session'"
                )).fetchall()
            }
            if "completed_at" not in columns:
                connection.execute(text("ALTER TABLE diagnostic_session ADD COLUMN completed_at DATETIME NULL"))

    @staticmethod
    def _period_start(period: str) -> str:
        return "DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)" if period == "week" else "DATE_FORMAT(CURDATE(), '%Y-%m-01')"

    @staticmethod
    def _question(row: Any) -> dict[str, Any]:
        options = json.loads(row["options_json"] or "[]")
        return {"id": int(row["id"]), "content": row["stem"], "options": options, "type": "single"}

    def start(self, *, user_id: int, book_id: int) -> dict[str, Any]:
        self._ensure_resumable_session_schema()
        now = datetime.now().replace(microsecond=0)
        with self.engine.begin() as connection:
            exists = connection.execute(text("SELECT user_id FROM users WHERE user_id=:id"), {"id": user_id}).first()
            if not exists:
                raise ValidationAppError("user does not exist")
            active = connection.execute(text(
                "SELECT id FROM diagnostic_session WHERE user_id=:u AND book_id=:b "
                "AND session_type=2 AND completed_at IS NULL ORDER BY updated_at DESC, id DESC LIMIT 1"
            ), {"u": user_id, "b": book_id}).first()
            if active:
                session_id = int(active[0])
                return {"sessionId": session_id, "question": self.next_question(session_id=session_id, user_id=user_id), "resumed": True}
            session_id = connection.execute(text(
                "INSERT INTO diagnostic_session (user_id,book_id,session_type,total_questions,correct_count,created_at,updated_at) "
                "VALUES (:u,:b,2,0,0,:now,:now)"
            ), {"u": user_id, "b": book_id, "now": now}).lastrowid
        return {"sessionId": int(session_id), "question": self.next_question(session_id=int(session_id), user_id=user_id), "resumed": False}

    def resolve_book_id(self, book: str) -> int:
        aliases = {"ml": "ML-For-Beginners", "ml-001": "ML-For-Beginners", "dl": "AI-For-Beginners", "dl-001": "AI-For-Beginners"}
        if book.isdigit():
            return int(book)
        name = aliases.get(book, book)
        with self.engine.connect() as connection:
            value = connection.execute(text("SELECT id FROM books WHERE book_name=:name LIMIT 1"), {"name": name}).scalar()
        if value is None:
            raise ValidationAppError("book does not exist", details={"book_id": book})
        return int(value)

    def next_question(self, *, session_id: int, user_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            session = connection.execute(text("SELECT book_id FROM diagnostic_session WHERE id=:s AND user_id=:u AND session_type=2"), {"s": session_id, "u": user_id}).mappings().first()
            if not session:
                raise ValidationAppError("practice session does not exist")
            book_id = int(session["book_id"])
            bounds = self._question_id_bounds.get(book_id)
            if bounds is None:
                bounds_row = connection.execute(text(
                    "SELECT MIN(id) AS min_id, MAX(id) AS max_id FROM questions "
                    "WHERE book_id=:b AND item_type='quiz_question'"
                ), {"b": book_id}).mappings().one()
                if bounds_row["min_id"] is None:
                    return None
                bounds = (int(bounds_row["min_id"]), int(bounds_row["max_id"]))
                self._question_id_bounds[book_id] = bounds
            pivot = random.randint(*bounds)
            statement = text(
                "SELECT q.id,q.stem,q.options_json FROM questions q "
                "WHERE q.book_id=:b AND q.item_type='quiz_question' AND q.id>=:pivot "
                "AND NOT EXISTS (SELECT 1 FROM diagnostic_answer a WHERE a.session_id=:s AND a.question_id=q.id) "
                "ORDER BY q.id LIMIT 1"
            )
            row = connection.execute(statement, {"b": book_id, "s": session_id, "pivot": pivot}).mappings().first()
            if row is None and pivot > bounds[0]:
                row = connection.execute(statement, {"b": book_id, "s": session_id, "pivot": bounds[0]}).mappings().first()
            return self._question(row) if row else None

    def answer(self, *, session_id: int, user_id: int, question_id: int, answer: str) -> dict[str, Any]:
        now = datetime.now().replace(microsecond=0)
        with self.engine.begin() as connection:
            row = connection.execute(text(
                "SELECT q.correct_answer_json,q.explanation FROM questions q JOIN diagnostic_session s ON s.book_id=q.book_id "
                "WHERE s.id=:s AND s.user_id=:u AND s.session_type=2 AND q.id=:q"
            ), {"s": session_id, "u": user_id, "q": question_id}).mappings().first()
            if not row:
                raise ValidationAppError("question does not belong to practice session")
            duplicate = connection.execute(text("SELECT id FROM diagnostic_answer WHERE session_id=:s AND question_id=:q"), {"s": session_id, "q": question_id}).first()
            if duplicate:
                raise ValidationAppError("question has already been answered")
            raw = json.loads(row["correct_answer_json"] or '""')
            if isinstance(raw, dict):
                expected = str(raw.get("correctOptionKey") or raw.get("answer") or "")
            elif isinstance(raw, list) and len(raw) == 1:
                expected = str(raw[0])
            else:
                expected = str(raw)
            correct = answer.strip() == expected.strip()
            connection.execute(text(
                "INSERT INTO diagnostic_answer (session_id,question_id,submitted_answer,correct_answer,is_correct,created_at,updated_at) "
                "VALUES (:s,:q,:a,:e,:c,:now,:now)"
            ), {"s": session_id, "q": question_id, "a": answer, "e": expected, "c": int(correct), "now": now})
            connection.execute(text("UPDATE diagnostic_session SET total_questions=total_questions+1,correct_count=correct_count+:c,updated_at=:now WHERE id=:s"), {"c": int(correct), "now": now, "s": session_id})
            stats = connection.execute(text("SELECT total_questions,correct_count FROM diagnostic_session WHERE id=:s"), {"s": session_id}).mappings().one()
        # 新作答可能影响答题、连对和周榜勋章，下一次检查必须绕过旧缓存。
        self._achievement_progress_cache.pop(user_id, None)
        total, count = int(stats["total_questions"]), int(stats["correct_count"])
        return {"correct": correct, "correctAnswer": expected, "explanation": row["explanation"] or "", "statistics": {"answerCount": total, "correctCount": count, "accuracy": round(count * 100 / total, 1)}}

    def finish(self, *, session_id: int, user_id: int) -> dict[str, Any]:
        self._ensure_resumable_session_schema()
        with self.engine.begin() as connection:
            row = connection.execute(text("SELECT total_questions,correct_count FROM diagnostic_session WHERE id=:s AND user_id=:u AND session_type=2"), {"s": session_id, "u": user_id}).mappings().first()
            if not row:
                raise ValidationAppError("practice session does not exist")
            # The update must share this transaction: the connection is closed when
            # the context manager exits, so using it afterwards makes "结束本轮" fail.
            connection.execute(
                text("UPDATE diagnostic_session SET completed_at=:now, updated_at=:now WHERE id=:s"),
                {"now": datetime.now().replace(microsecond=0), "s": session_id},
            )
            total, correct = int(row["total_questions"]), int(row["correct_count"])
        return {"sessionId": session_id, "answerCount": total, "correctCount": correct, "accuracy": round(correct * 100 / total, 1) if total else 0}

    def leaderboard(self, *, period: str, limit: int) -> list[dict[str, Any]]:
        period_start = self._period_start(period)
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT u.user_id,COALESCE(u.nickname,u.username) name,COALESCE(p.answer_count,0) answer_count,"
                "COALESCE(p.correct_count,0) correct_count,COALESCE(d.study_seconds,0) study_seconds,"
                "COALESCE(d.completed_task_count,0) completed_task_count FROM users u "
                "LEFT JOIN (SELECT s.user_id,COUNT(a.id) answer_count,SUM(a.is_correct) correct_count "
                "FROM diagnostic_session s JOIN diagnostic_answer a ON a.session_id=s.id "
                f"WHERE s.session_type=2 AND a.created_at>={period_start} GROUP BY s.user_id) p ON p.user_id=u.user_id "
                "LEFT JOIN (SELECT lp.user_id,COUNT(i.id) completed_task_count,"
                "SUM(CASE WHEN i.started_at IS NOT NULL AND i.completed_at>i.started_at "
                "THEN LEAST(TIMESTAMPDIFF(SECOND,i.started_at,i.completed_at),14400) ELSE 0 END) study_seconds "
                "FROM learning_plan_day_item i JOIN learning_plan_day lpd ON lpd.id=i.learning_plan_day_id "
                "JOIN learning_plan lp ON lp.id=lpd.plan_id WHERE i.status='completed' "
                f"AND i.completed_at>={period_start} GROUP BY lp.user_id) d ON d.user_id=u.user_id "
                "WHERE p.user_id IS NOT NULL OR d.user_id IS NOT NULL ORDER BY answer_count DESC,study_seconds DESC LIMIT :lim"
            ), {"lim": limit}).mappings().all()
            # 无限答题记录按发生顺序读取，用于同时计算累计题数和历史最长连对。
            answer_rows = connection.execute(text(
                "SELECT s.user_id,a.is_correct FROM diagnostic_session s JOIN diagnostic_answer a ON a.session_id=s.id "
                f"WHERE s.session_type=2 AND a.created_at>={period_start} ORDER BY s.user_id,a.created_at,a.id"
            )).mappings().all()
        streaks: dict[int, int] = {}
        streak_bonus: dict[int, int] = {}
        for answer in answer_rows:
            uid = int(answer["user_id"])
            streaks[uid] = streaks.get(uid, 0) + 1 if answer["is_correct"] else 0
            if streaks[uid] and streaks[uid] % 5 == 0:
                streak_bonus[uid] = streak_bonus.get(uid, 0) + 10
        result = []
        for item in rows:
            uid, answers = int(item["user_id"]), int(item["answer_count"])
            correct, seconds = int(item["correct_count"] or 0), int(item["study_seconds"] or 0)
            tasks = int(item.get("completed_task_count") or 0)
            bonus = streak_bonus.get(uid, 0)
            score = answers * 2 + correct * 8 + (seconds // 600) * 5 + tasks * 20 + bonus
            result.append({"userId": uid, "name": item["name"], "answers": answers, "correct": correct, "accuracy": round(correct * 100 / answers, 1) if answers else 0, "studySeconds": seconds, "taskCount": tasks, "streakBonus": bonus, "score": score})
        result.sort(key=lambda item: (-item["score"], -item["answers"], item["userId"]))
        for index, item in enumerate(result):
            item["rank"] = index + 1
        return result

    def overview(self, *, user_id: int, period: str) -> dict[str, Any]:
        period_start = self._period_start(period)
        with self.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT COUNT(a.id) AS answer_count, COALESCE(SUM(a.is_correct),0) AS correct_count "
                "FROM diagnostic_session s LEFT JOIN diagnostic_answer a ON a.session_id=s.id "
                f"AND a.created_at>={period_start} "
                "WHERE s.user_id=:user_id AND s.session_type=2"
            ), {"user_id": user_id}).mappings().one()
            study_seconds = connection.execute(text(
                "SELECT COALESCE(SUM(LEAST(TIMESTAMPDIFF(SECOND,i.started_at,i.completed_at),14400)),0) "
                "FROM learning_plan_day_item i JOIN learning_plan_day d ON d.id=i.learning_plan_day_id "
                "JOIN learning_plan p ON p.id=d.plan_id WHERE p.user_id=:user_id AND i.status='completed' "
                "AND i.started_at IS NOT NULL AND i.completed_at>i.started_at "
                f"AND i.completed_at>={period_start}"
            ), {"user_id": user_id}).scalar_one()
        total, correct = int(row["answer_count"]), int(row["correct_count"])
        return {"answerCount": total, "correctCount": correct, "accuracy": round(correct * 100 / total, 1) if total else 0, "studySeconds": int(study_seconds or 0)}

    def achievements(self, *, user_id: int) -> dict[str, Any]:
        """Fast-path: only read persisted definitions and earned records for initial rendering."""
        with self.engine.connect() as connection:
            exists = connection.execute(text("SELECT 1 FROM users WHERE user_id=:user_id"), {"user_id": user_id}).first()
            if not exists:
                raise ValidationAppError("user does not exist")
            rows = connection.execute(text(
                "SELECT d.id,d.code,d.name,d.description,d.icon,d.tone,d.target_value,"
                "ua.achieved_at,ua.notified_at FROM achievement_definitions d "
                "LEFT JOIN user_achievements ua ON ua.achievement_id=d.id AND ua.user_id=:user_id "
                "WHERE d.is_active=1 ORDER BY d.sort_order,d.id"
            ), {"user_id": user_id}).mappings().all()
        items = [{
            "id": int(row["id"]), "code": row["code"], "title": row["name"], "detail": row["description"],
            "icon": row["icon"], "tone": row["tone"], "current": int(row["target_value"]) if row["achieved_at"] else 0,
            "target": int(row["target_value"]), "progress": 100 if row["achieved_at"] else 0,
            "earned": row["achieved_at"] is not None,
            "earnedAt": row["achieved_at"].isoformat() if row["achieved_at"] else None,
            "statusText": "已获得" if row["achieved_at"] else "继续学习解锁",
        } for row in rows]
        newly_unlocked = [item for item, row in zip(items, rows) if item["earned"] and row["notified_at"] is None]
        return {"earnedCount": sum(item["earned"] for item in items), "totalCount": len(items), "items": items, "newlyUnlocked": newly_unlocked}

    def achievement_progress(self, *, user_id: int, force: bool = False) -> dict[str, Any]:
        """Calculate progress, persist newly earned awards, and return pending notices."""
        cached = self._achievement_progress_cache.get(user_id)
        if not force and cached and time.monotonic() - cached[0] < 300:
            return cached[1]
        with self.engine.begin() as connection:
            user_exists = connection.execute(
                text("SELECT 1 FROM users WHERE user_id=:user_id"), {"user_id": user_id}
            ).first()
            if not user_exists:
                raise ValidationAppError("user does not exist")

            answer_rows = connection.execute(text(
                "SELECT a.is_correct FROM diagnostic_session s "
                "JOIN diagnostic_answer a ON a.session_id=s.id "
                "WHERE s.user_id=:user_id AND s.session_type=2 "
                "ORDER BY a.created_at,a.id"
            ), {"user_id": user_id}).mappings().all()
            # 数据库中的已完成计划任务作为任务数量和学习时长的基础来源。
            learning_rows = connection.execute(text(
                "SELECT i.id task_id,CASE WHEN i.started_at IS NOT NULL AND i.completed_at>i.started_at "
                "THEN LEAST(TIMESTAMPDIFF(SECOND,i.started_at,i.completed_at),14400) ELSE 0 END study_seconds "
                "FROM learning_plan_day_item i JOIN learning_plan_day d ON d.id=i.learning_plan_day_id "
                "JOIN learning_plan p ON p.id=d.plan_id "
                "WHERE p.user_id=:user_id AND i.status='completed'"
            ), {"user_id": user_id}).mappings().all()

            definitions = connection.execute(text(
                "SELECT id,code,name,description,icon,tone,condition_type,target_value "
                "FROM achievement_definitions WHERE is_active=1 ORDER BY sort_order,id"
            )).mappings().all()

        total_answers = len(answer_rows)
        current_streak = 0
        longest_streak = 0
        for row in answer_rows:
            current_streak = current_streak + 1 if row["is_correct"] else 0
            longest_streak = max(longest_streak, current_streak)

        database_task_seconds = {str(row["task_id"]): int(row["study_seconds"] or 0) for row in learning_rows}
        event_task_seconds: dict[str, int] = {}
        try:
            # 前端完成任务时会把用户填写的 duration_seconds 写入学习记录；同一任务
            # 若有多次记录只采用最大值，并限制单任务最多计入 4 小时。
            activities = LearningRecordModule().list_activities(
                str(user_id), activity_type="task_completed", page_size=10000
            )["records"]
            for activity in activities:
                task_id = str(activity.task_id or activity.id)
                event_task_seconds[task_id] = max(
                    event_task_seconds.get(task_id, 0),
                    min(int((activity.result or {}).get("duration_seconds", 0) or 0), 14400),
                )
        except Exception:
            # Database-backed progress still works if the optional activity file is unavailable.
            event_task_seconds = {}
        # 合并两种来源，优先采用用户完成任务时提交的实际学习时长。
        all_task_ids = set(database_task_seconds) | set(event_task_seconds)
        completed_tasks = len(all_task_ids)
        study_seconds = sum(event_task_seconds.get(task_id, database_task_seconds.get(task_id, 0)) for task_id in all_task_ids)
        # 排行榜勋章直接复用本周综合成长榜，保证页面排名和解锁条件一致。
        weekly_entry = next(
            (item for item in self.leaderboard(period="week", limit=100) if item["userId"] == user_id),
            None,
        )
        weekly_rank = int(weekly_entry["rank"]) if weekly_entry else 0

        # condition_type 与定义表中的字段对应；以后新增同类勋章只需插入定义数据。
        metric_values = {
            "answer_count": total_answers,
            "longest_correct_streak": longest_streak,
            "completed_task_count": completed_tasks,
            "study_seconds": study_seconds,
            "weekly_rank": weekly_rank,
        }

        def qualifies(condition_type: str, current: int, target: int) -> bool:
            if condition_type == "weekly_rank":
                return 0 < current <= target
            return current >= target

        with self.engine.begin() as connection:
            for definition in definitions:
                current = metric_values.get(str(definition["condition_type"]), 0)
                if qualifies(str(definition["condition_type"]), current, int(definition["target_value"])):
                    # 唯一键 (user_id, achievement_id) 配合 INSERT IGNORE 保证并发检查时
                    # 每枚勋章也只会发放一次。
                    connection.execute(text(
                        "INSERT IGNORE INTO user_achievements (user_id,achievement_id,achieved_at) "
                        "VALUES (:user_id,:achievement_id,NOW())"
                    ), {"user_id": user_id, "achievement_id": int(definition["id"])})
            awards = connection.execute(text(
                "SELECT achievement_id,achieved_at,notified_at FROM user_achievements WHERE user_id=:user_id"
            ), {"user_id": user_id}).mappings().all()

        award_by_id = {int(row["achievement_id"]): row for row in awards}
        items = []
        for definition in definitions:
            identifier = int(definition["id"])
            condition_type = str(definition["condition_type"])
            current = metric_values.get(condition_type, 0)
            target = int(definition["target_value"])
            award = award_by_id.get(identifier)
            if condition_type == "study_seconds":
                status_text = f"已学习 {current // 3600} 小时 {(current % 3600) // 60} 分钟"
            elif condition_type == "completed_task_count":
                status_text = f"{current} / {target} 个任务"
            elif condition_type == "longest_correct_streak":
                status_text = f"最长连续答对 {current} 题"
            elif condition_type == "weekly_rank":
                status_text = "本周尚未上榜" if current == 0 else f"当前第 {current} 名"
            else:
                status_text = f"{current} / {target} 题"
            progress = (
                100 if condition_type == "weekly_rank" and 0 < current <= target
                else min(99, round(target * 100 / current)) if condition_type == "weekly_rank" and current
                else min(100, round(current * 100 / target)) if target else 0
            )
            items.append({
                "id": identifier,
                "code": definition["code"],
                "title": definition["name"],
                "detail": definition["description"],
                "icon": definition["icon"],
                "tone": definition["tone"],
                "current": current,
                "target": target,
                "progress": progress,
                "earned": award is not None,
                "earnedAt": award["achieved_at"].isoformat() if award else None,
                "statusText": status_text,
            })
        # notified_at 为空的获奖记录会交给前端弹窗；确认后便不会再次返回。
        newly_unlocked = [item for item in items if item["earned"] and award_by_id[item["id"]]["notified_at"] is None]
        result = {
            "earnedCount": sum(1 for item in items if item["earned"]),
            "totalCount": len(items),
            "items": items,
            "newlyUnlocked": newly_unlocked,
        }
        self._achievement_progress_cache[user_id] = (time.monotonic(), result)
        return result

    def acknowledge_achievement(self, *, user_id: int, achievement_id: int) -> dict[str, Any]:
        with self.engine.begin() as connection:
            # COALESCE 保留第一次通知确认时间，重复确认不会篡改原始时间。
            result = connection.execute(text(
                "UPDATE user_achievements SET notified_at=COALESCE(notified_at,NOW()) "
                "WHERE user_id=:user_id AND achievement_id=:achievement_id"
            ), {"user_id": user_id, "achievement_id": achievement_id})
        if result.rowcount == 0:
            raise ValidationAppError("achievement has not been earned")
        # 缓存中的 newlyUnlocked 已失效，下一次读取需要反映确认后的状态。
        self._achievement_progress_cache.pop(user_id, None)
        return {"acknowledged": True, "achievementId": achievement_id}
