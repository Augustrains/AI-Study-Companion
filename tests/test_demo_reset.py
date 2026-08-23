"""体验账号重置脚本的测试。

最重要的一条断言是：**重置之后其他账号的数据一条不少**。
这个脚本会删数据，写错一个过滤条件就是把用户自己建的账号一起清掉。

全程在临时目录里跑，`reset_demo_account(data_dir=...)` 把数据目录注入进去，
不会碰到项目里真实的 data/。因此也不重建基线（seed=False）——重建要走
种子脚本的默认路径，那会写真实数据，属于「跑脚本」而不是「跑测试」。

在项目根目录执行：

    python3.11 tests/test_demo_reset.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.auth.module import AuthModule  # noqa: E402
from scripts.demo_reset import reset_demo_account  # noqa: E402

PASSED = 0


def check(label: str, condition: bool, extra: object = "") -> None:
    global PASSED
    assert condition, f"FAIL: {label} {extra}"
    PASSED += 1
    print(f"  ok  {label}")


def write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_fixture() -> Path:
    """造一份同时含体验账号和其他账号的数据目录。"""
    root = Path(tempfile.mkdtemp(prefix="demo-reset-"))
    write(
        root / "memory" / "learner_memories.json",
        {
            "demo_user:ml-001": {"user_id": "demo_user", "knowledge_points": [{"knowledge_point_id": "kp-ml-intro"}]},
            "user_001:ml-001": {"user_id": "user_001", "knowledge_points": [{"knowledge_point_id": "kp-ml-kmeans"}]},
            "local_abc:dl-001": {"user_id": "local_abc", "knowledge_points": []},
        },
    )
    write(
        root / "learning_record" / "activities.json",
        [{"id": f"a{index}", "user_id": user} for index, user in enumerate(["demo_user"] * 6 + ["user_001"] * 4 + ["local_abc"] * 2)],
    )
    write(
        root / "learning_plan" / "plans.json",
        {
            "ml:d1": {"bookId": "ml", "userId": "demo_user", "plan": {"tasks": []}},
            "ml:d2": {"bookId": "ml", "userId": "user_001", "plan": {"tasks": []}},
            "ml:legacy": {"bookId": "ml", "plan": {"tasks": []}},
        },
    )
    write(root / "learner_goals" / "goals.json", {"demo_user:ml": {"user_id": "demo_user"}, "user_001:ml": {"user_id": "user_001"}})
    write(root / "profiles" / "learner_profiles.json", {"demo_user": {"machine_learning": {}}, "user_001": {"machine_learning": {}}})

    auth_path = root / "auth" / "users.json"
    AuthModule(store_path=auth_path, token_secret="test", expose_code=False)
    payload = json.loads(auth_path.read_text(encoding="utf-8"))
    for user in payload["users"]:
        if user["user_id"] == "demo_user":
            # 模拟演示过程中改过体验账号的昵称
            user["nickname"] = "被改过的名字"
    payload["users"].append(
        {
            "user_id": "user_001",
            "nickname": "我的账号",
            "account": "me@example.com",
            "password_hash": "h",
            "password_salt": "s",
            "created_at": "2026-01-01T00:00:00+00:00",
            "iterations": 200000,
            "avatar_color": "",
        }
    )
    write(auth_path, payload)
    return root


def load(root: Path, relative: str) -> object:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def run_reset(root: Path, **kwargs: object) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = reset_demo_account(data_dir=root, seed=False, **kwargs)  # type: ignore[arg-type]
    return code, buffer.getvalue()


print("== 预演不写盘 ==")
workspace = build_fixture()
snapshot = {
    name: load(workspace, name)
    for name in (
        "memory/learner_memories.json",
        "learning_record/activities.json",
        "learning_plan/plans.json",
        "learner_goals/goals.json",
        "profiles/learner_profiles.json",
        "auth/users.json",
    )
}
code, _ = run_reset(workspace, dry_run=True)
check("--dry-run 返回 0", code == 0)
check("--dry-run 之后所有文件原封不动", {name: load(workspace, name) for name in snapshot} == snapshot)

print("== 真正清理 ==")
code, output = run_reset(workspace)
check("返回 0", code == 0, output[-300:])

memories = load(workspace, "memory/learner_memories.json")
check("demo_user 的掌握度已清", not any(str(key).startswith("demo_user:") for key in memories), list(memories))
check("其他账号的掌握度一条不少", set(memories) == {"user_001:ml-001", "local_abc:dl-001"}, list(memories))
check(
    "其他账号的掌握度内容也没被改动",
    memories["user_001:ml-001"] == snapshot["memory/learner_memories.json"]["user_001:ml-001"],
)

activities = load(workspace, "learning_record/activities.json")
check("demo_user 的学习记录已清", not any(item["user_id"] == "demo_user" for item in activities))
check("其他账号的 6 条记录一条不少", len(activities) == 6, len(activities))

plans = load(workspace, "learning_plan/plans.json")
check("demo_user 的计划已删", "ml:d1" not in plans)
check("其他账号的计划保留", "ml:d2" in plans)
check("没有 userId 的历史计划不删（判断不了归属就不动）", "ml:legacy" in plans, list(plans))

check("demo_user 的目标已删，其他保留", list(load(workspace, "learner_goals/goals.json")) == ["user_001:ml"])
check("demo_user 的画像已删，其他保留", list(load(workspace, "profiles/learner_profiles.json")) == ["user_001"])

users = {item["user_id"]: item for item in load(workspace, "auth/users.json")["users"]}
check("体验账号昵称恢复默认", users["demo_user"]["nickname"] == "体验账号", users["demo_user"]["nickname"])
check("恢复的是散列不是明文密码", "demo1234" not in json.dumps(users, ensure_ascii=False))
check("其他账号原样保留", users["user_001"]["nickname"] == "我的账号")

restored = AuthModule(store_path=workspace / "auth" / "users.json", token_secret="test", seed_demo_account=False)
check("重置后能用默认密码登录体验账号", restored.login(account="demo@study.local", password="demo1234").account.user_id == "demo_user")

print("== 备份 ==")
backups = sorted((workspace / "_demo_backup").iterdir())
check("生成了备份目录", len(backups) >= 1, [item.name for item in backups])
backed_up = json.loads((backups[-1] / "memory" / "learner_memories.json").read_text(encoding="utf-8"))
check("误触后能从备份里捞回 demo_user 的数据", "demo_user:ml-001" in backed_up, list(backed_up))

print("== 开关 ==")
fresh = build_fixture()
before = load(fresh, "learning_record/activities.json")
os.environ["DEMO_RESET_ENABLED"] = "false"
try:
    code, output = run_reset(fresh)
    check("DEMO_RESET_ENABLED=false 时直接跳过", code == 0 and "已跳过" in output, output)
    check("关掉之后什么都没动", load(fresh, "learning_record/activities.json") == before)
finally:
    os.environ.pop("DEMO_RESET_ENABLED", None)

print("== 重复执行 ==")
code, _ = run_reset(workspace)
check("对已经清干净的数据再跑一次不报错", code == 0)
check("其他账号仍然一条不少", len(load(workspace, "learning_record/activities.json")) == 6)

print(f"\n全部通过：{PASSED} 项断言")
