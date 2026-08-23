"""把体验账号恢复到演示基线。

    python3.11 scripts/demo_reset.py --dry-run   # 只打印会动哪些数据，不落盘
    python3.11 scripts/demo_reset.py             # 清掉 demo_user 的痕迹并重建基线
    python3.11 main.py --reset-demo              # 启动服务前先重置一次

基线不是快照文件，而是 scripts/seed_demo_data.py —— 每次重置都重新跑一遍种子脚本。
好处是基线永远只有一个定义，而且学习事件的日期是按「本周一到今天」动态生成的，
放几周再演示也不会变成上个月的数据。

护栏（刻意写死，不做成参数）：
    1. 用户 ID 硬编码为 demo_user。这种脚本一旦能传用户 ID，早晚会被传错。
    2. 动手之前把涉及的文件整体备份到 data/_demo_backup/<时间戳>/。
    3. 按条目过滤，其他账号的数据原样写回，不是把文件清空重建。
    4. 环境变量 DEMO_RESET_ENABLED=false 可以整体关掉，上线时应当关掉。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR = Path(os.getenv("STUDY_COMPANION_DATA_DIR", PROJECT_DIR / "data")).resolve()

# 唯一会被清理的账号。不接受命令行参数，见文件头护栏 1。
DEMO_USER_ID = "demo_user"
DEMO_ACCOUNT = "demo@study.local"
DEMO_NICKNAME = "体验账号"
DEMO_PASSWORD = "demo1234"


def say(message: str) -> None:
    """立即刷新的输出。

    直接用 print 有个坑：`python3.11 main.py --reset-demo | tee backend.log` 时
    stdout 是管道、走块缓冲，而 logging 走 stderr 立即刷新。
    结果就是重置的进度全被压在缓冲区里，日志上只看得到后面的启动信息，
    看起来像「重置根本没执行」——实际上执行了。
    """
    print(message, flush=True)


def _enabled() -> bool:
    return os.getenv("DEMO_RESET_ENABLED", "true").strip().lower() != "false"


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        say(f"  ! {path} 不是合法 JSON，跳过（不敢猜内容，留给你处理）")
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def backup(paths: list[Path], data_dir: Path, dry_run: bool) -> Path | None:
    """把要动的文件整体复制一份，误触时能捞回来。"""
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = data_dir / "_demo_backup" / stamp
    say(f"\n[备份] {len(existing)} 个文件 → {target}")
    if dry_run:
        return target
    for path in existing:
        destination = target / path.relative_to(data_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    return target


# ============================== 各文件的清理规则 ==============================


def purge_memories(path: Path, dry_run: bool) -> tuple[int, int]:
    """learner_memories.json：dict，键是 "{user_id}:{domain}"。"""
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return 0, 0
    removed = [key for key in payload if str(key).split(":", 1)[0] == DEMO_USER_ID]
    kept = {key: value for key, value in payload.items() if key not in removed}
    if not dry_run and removed:
        _write_json(path, kept)
    return len(removed), len(kept)


def purge_activities(path: Path, dry_run: bool) -> tuple[int, int]:
    """activities.json：list，每项带 user_id。"""
    payload = _read_json(path)
    if not isinstance(payload, list):
        return 0, 0
    kept = [item for item in payload if not (isinstance(item, dict) and item.get("user_id") == DEMO_USER_ID)]
    removed = len(payload) - len(kept)
    if not dry_run and removed:
        _write_json(path, kept)
    return removed, len(kept)


def purge_plans(path: Path, dry_run: bool) -> tuple[int, int]:
    """plans.json：dict，值里带 userId。

    注意：没有 userId 字段的历史计划**不删**。那是加 userId 归属之前生成的，
    没法判断属于谁，删掉就是破坏别人的数据；留着也不会被体验账号读到
    （get_saved 按 userId 过滤时不匹配）。
    """
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return 0, 0
    removed = [
        key for key, value in payload.items()
        if isinstance(value, dict) and value.get("userId") == DEMO_USER_ID
    ]
    kept = {key: value for key, value in payload.items() if key not in removed}
    if not dry_run and removed:
        _write_json(path, kept)
    return len(removed), len(kept)


def purge_goals(path: Path, dry_run: bool) -> tuple[int, int]:
    """goals.json：dict，键是 "{user_id}:{book_id}"。"""
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return 0, 0
    removed = [key for key in payload if str(key).split(":", 1)[0] == DEMO_USER_ID]
    kept = {key: value for key, value in payload.items() if key not in removed}
    if not dry_run and removed:
        _write_json(path, kept)
    return len(removed), len(kept)


def purge_profiles(path: Path, dry_run: bool) -> tuple[int, int]:
    """learner_profiles.json：dict，第一层键就是 user_id。"""
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return 0, 0
    removed = 1 if DEMO_USER_ID in payload else 0
    kept = {key: value for key, value in payload.items() if key != DEMO_USER_ID}
    if not dry_run and removed:
        _write_json(path, kept)
    return removed, len(kept)


def restore_demo_account(path: Path, dry_run: bool) -> tuple[bool, int]:
    """auth/users.json：只把体验账号的昵称和密码恢复成默认，其他账号一个不碰。

    密码用和认证模块相同的 PBKDF2 参数重新散列，不是直接写明文。
    """
    payload = _read_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("users"), list):
        return False, 0
    from modules.auth.services import PasswordHasher

    users = payload["users"]
    others = [item for item in users if isinstance(item, dict) and item.get("user_id") != DEMO_USER_ID]
    demo = next((item for item in users if isinstance(item, dict) and item.get("user_id") == DEMO_USER_ID), None)
    if demo is None:
        # 体验账号不存在也没关系：服务启动时 AuthModule 会自动建。
        return False, len(others)
    if not dry_run:
        password_hash, salt, iterations = PasswordHasher().hash(DEMO_PASSWORD)
        demo.update(
            nickname=DEMO_NICKNAME,
            account=DEMO_ACCOUNT,
            password_hash=password_hash,
            password_salt=salt,
            iterations=iterations,
            avatar_color="",
        )
        _write_json(path, {"users": [*others, demo]})
    return True, len(others)


# ============================== 入口 ==============================


# (显示名, 相对 data 目录的路径, 清理函数)
TARGETS: list[tuple[str, tuple[str, ...], Any]] = [
    ("掌握度与复习安排", ("memory", "learner_memories.json"), purge_memories),
    ("学习记录", ("learning_record", "activities.json"), purge_activities),
    ("学习计划", ("learning_plan", "plans.json"), purge_plans),
    ("学习目标", ("learner_goals", "goals.json"), purge_goals),
    ("学习画像", ("profiles", "learner_profiles.json"), purge_profiles),
]

AUTH_RELATIVE = ("auth", "users.json")


def reset_demo_account(
    *,
    dry_run: bool = False,
    seed: bool = True,
    quiet: bool = False,
    data_dir: Path | None = None,
) -> int:
    """清掉体验账号的痕迹并重建基线。返回值可直接作为进程退出码。

    data_dir 只用于测试：传入临时目录就能验证清理逻辑而不碰真实数据。
    正常运行时留空，走 STUDY_COMPANION_DATA_DIR 或项目下的 data/。
    """

    if not _enabled():
        say("DEMO_RESET_ENABLED=false，已跳过体验账号重置。")
        return 0

    root = Path(data_dir) if data_dir is not None else DATA_DIR
    targets = [(label, root.joinpath(*parts), handler) for label, parts, handler in TARGETS]
    auth_path = root.joinpath(*AUTH_RELATIVE)

    prefix = "[预演] " if dry_run else ""
    if not quiet:
        say(f"{prefix}重置体验账号 user_id = {DEMO_USER_ID}")
        say(f"{prefix}数据目录 = {root}")

    backup([path for _, path, _ in targets] + [auth_path], root, dry_run)

    say("\n[清理] 只删这个账号的条目，其他账号原样保留")
    total_removed = 0
    for label, path, handler in targets:
        if not path.exists():
            say(f"  - {label:12} 文件不存在，跳过")
            continue
        removed, kept = handler(path, dry_run)
        total_removed += removed
        say(f"  - {label:12} 删除 {removed} 条，保留其他账号 {kept} 条")

    if auth_path.exists():
        restored, others = restore_demo_account(auth_path, dry_run)
        say(f"  - {'体验账号凭据':12} {'已恢复默认昵称与密码' if restored else '账号不存在，启动时会自动创建'}，其他账号保留 {others} 个")

    if seed:
        say("\n[重建] 运行 scripts/seed_demo_data.py 写回演示基线")
        if dry_run:
            say("  （预演模式不实际写入）")
        else:
            from scripts import seed_demo_data

            saved_argv = sys.argv
            try:
                # 种子脚本自己用 argparse 解析参数，这里换掉 argv 以默认参数运行。
                sys.argv = ["seed_demo_data.py"]
                code = seed_demo_data.main()
            finally:
                sys.argv = saved_argv
            if code != 0:
                say("  ! 种子脚本返回非 0，基线可能不完整")
                return code

    say(f"\n{prefix}完成：清理 {total_removed} 条，体验账号已回到演示基线。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="把体验账号恢复到演示基线（只影响 demo_user）")
    parser.add_argument("--dry-run", action="store_true", help="只打印会动哪些数据，不写盘")
    parser.add_argument("--no-seed", action="store_true", help="只清理，不重建演示数据")
    args = parser.parse_args()
    return reset_demo_account(dry_run=args.dry_run, seed=not args.no_seed)


if __name__ == "__main__":
    raise SystemExit(main())
