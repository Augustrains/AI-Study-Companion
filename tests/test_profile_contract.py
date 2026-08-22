"""前端学习画像的可选值 ↔ 后端校验规则 的契约测试。

**这个文件存在的原因**：我把画像页的「单次学习时长」做成了 10–120、步长 5 的滑块，
而后端 `PREFERENCE_SCHEMA` 只接受 15/30/45/60 四个值。用户拖到 75 分钟保存，
拿到一句没头没尾的 `field validation failed`。

前端渲染什么选项、后端接受什么取值，这两处必须一致。人工同步迟早会漂移，
所以这里直接把 TSX 里的选项列表读出来，跟后端 schema 对拍，并且逐个真的跑一遍校验。

在项目根目录执行：

    python3.11 tests/test_profile_contract.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.learner_profile.field_rules import (  # noqa: E402
    PREFERENCE_SCHEMA,
    PROFILE_SCHEMA,
    SESSION_DURATION_CHOICES,
    normalize_profile,
    parse_profile_payload,
)

VIEW = ROOT / "front" / "frontend" / "src" / "components" / "LearnerProfileView.tsx"
PASSED = 0


def check(label: str, condition: bool, extra: object = "") -> None:
    global PASSED
    assert condition, f"FAIL: {label} {extra}"
    PASSED += 1
    print(f"  ok  {label}")


def read_view() -> str:
    assert VIEW.exists(), f"找不到画像页：{VIEW}"
    return VIEW.read_text(encoding="utf-8")


def option_values(source: str, const_name: str) -> set[str]:
    """从 `const NAME = [...]` 里抽出所有 value: "xxx"。"""
    match = re.search(rf"const {const_name}[^=]*=\s*\[(.*?)\];", source, re.S)
    assert match, f"没在画像页里找到 {const_name}"
    return set(re.findall(r'value:\s*"([^"]+)"', match.group(1)))


def number_values(source: str, const_name: str) -> set[int]:
    match = re.search(rf"const {const_name}\s*=\s*\[([^\]]*)\];", source, re.S)
    assert match, f"没在画像页里找到 {const_name}"
    return {int(item) for item in re.findall(r"\d+", match.group(1))}


source = read_view()

print("== 前端选项与后端取值一致 ==")

pairs = [
    ("自评水平", "SELF_LEVELS", PROFILE_SCHEMA["self_assessed_level"].choices),
    ("讲解风格", "CONTENT_STYLES", PREFERENCE_SCHEMA["content_style"].choices),
    ("难度倾向", "DIFFICULTIES", PREFERENCE_SCHEMA["difficulty"].choices),
    ("学习频率", "FREQUENCIES", PREFERENCE_SCHEMA["learning_frequency"].choices),
]
for label, const_name, allowed in pairs:
    values = option_values(source, const_name)
    check(f"{label}：前端每个选项后端都接受", values <= set(allowed), sorted(values - set(allowed)))

durations = number_values(source, "SESSION_DURATIONS")
check("单次学习时长：前端档位后端全部接受", durations <= SESSION_DURATION_CHOICES, sorted(durations - SESSION_DURATION_CHOICES))
check(
    "单次学习时长：后端允许的档位前端也全都给了（不然用户选不到）",
    SESSION_DURATION_CHOICES <= durations,
    sorted(SESSION_DURATION_CHOICES - durations),
)
check("单次学习时长包含 90 分钟和 2 小时", {90, 120} <= durations, sorted(durations))

activities = option_values(source, "ACTIVITY_TYPES")
check("学习方式选项非空", len(activities) >= 2, sorted(activities))


print("== 每个选项真的能存进去 ==")


def payload(**overrides: object) -> dict[str, object]:
    base = {
        "user_id": "demo_user",
        "learning_domain": "machine_learning",
        "background": "学过 Python",
        "self_assessed_level": "none",
        "known_knowledge_point_ids": [],
        "unknown_knowledge_point_ids": [],
        "current_confusions": "不会概念",
        "additional_requirements": "多实际练习",
        "preferences": {
            "activity_types": sorted(activities),
            "content_style": "concise",
            "difficulty": "easy",
            "session_duration_minutes": 30,
            "learning_frequency": "frequent",
        },
    }
    preferences = dict(base["preferences"])  # type: ignore[arg-type]
    for key, value in overrides.items():
        if key in preferences:
            preferences[key] = value
        else:
            base[key] = value
    base["preferences"] = preferences
    return base


# 这一组正是截图里那份表单的取值，加上当时会失败的 75 分钟已改成合法档位。
parse_profile_payload(payload())
check("截图里那份表单现在能保存", True)

for minutes in sorted(durations):
    parse_profile_payload(payload(session_duration_minutes=minutes))
check(f"{len(durations)} 个时长档位逐个校验通过", True, sorted(durations))

for const_name, key in (("SELF_LEVELS", "self_assessed_level"), ("CONTENT_STYLES", "content_style"), ("DIFFICULTIES", "difficulty"), ("FREQUENCIES", "learning_frequency")):
    for value in sorted(option_values(source, const_name)):
        parse_profile_payload(payload(**{key: value}))
check("四组下拉选项的每个取值逐个校验通过", True)

failed = False
try:
    parse_profile_payload(payload(session_duration_minutes=75))
except Exception:
    failed = True
check("档位以外的值仍然被拒（75 分钟）", failed)


print("== 画像不再把未勾选的知识点写成未掌握 ==")

catalog = [f"kp-ml-{index:02d}" for index in range(26)]
profile = normalize_profile(payload(known_knowledge_point_ids=[], unknown_knowledge_point_ids=[]), catalog)
check(
    "什么都没勾时，unknown 是空的而不是整本书 26 个",
    profile.unknown_knowledge_point_ids == [],
    profile.unknown_knowledge_point_ids,
)
check("known 也是空的", profile.known_knowledge_point_ids == [])

partial = normalize_profile(
    payload(known_knowledge_point_ids=["kp-ml-01"], unknown_knowledge_point_ids=["kp-ml-02"]),
    catalog,
)
check("显式传进来的 known 保留", partial.known_knowledge_point_ids == ["kp-ml-01"], partial.known_knowledge_point_ids)
check("显式传进来的 unknown 保留", partial.unknown_knowledge_point_ids == ["kp-ml-02"], partial.unknown_knowledge_point_ids)
check("没提到的 24 个知识点两边都不出现", len(partial.known_knowledge_point_ids) + len(partial.unknown_knowledge_point_ids) == 2)

outside = normalize_profile(payload(known_knowledge_point_ids=["不在目录里的ID"]), catalog)
check("目录里没有的知识点 ID 被丢掉", outside.known_knowledge_point_ids == [])

print(f"\n全部通过：{PASSED} 项断言")
