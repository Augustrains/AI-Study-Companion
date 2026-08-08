from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from domain.learner_profile import LearnerProfile


class JsonLearnerProfileRepository:
    """学习者画像的 JSON 文件仓储。
    这个类负责把 ``LearnerProfile`` 对象持久化到本地 JSON 文件中。
    JSON 的逻辑结构如下：

    .. code-block:: json

        {
          "用户 ID": {
            "学习领域": {"user_id": "...", "learning_domain": "..."}
          }
        }

    外层先按用户区分，内层再按学习领域区分，因此同一个用户可以在
    不同学习领域分别保存画像。
    """

    # 默认将数据保存到项目根目录下的 data/profiles/learner_profiles.json。
    DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "profiles" / "learner_profiles.json"

    def __init__(self, path: str | Path | None = None) -> None:
        # 允许调用方传入自定义路径，便于测试或切换存储位置；不传时使用默认路径。
        self.path = Path(path) if path is not None else self.DEFAULT_PATH

    def exists(self, user_id: str, learning_domain: str | None = None) -> bool:
        """判断指定用户的画像是否存在。

        实际判断委托给 ``get``：能成功读取并转换成画像就视为存在，
        文件不存在、数据格式错误或领域不匹配都会返回 False。
        """
        return self.get(user_id, learning_domain) is not None

    def get(self, user_id: str, learning_domain: str | None = None) -> LearnerProfile | None:
        """读取一个学习者画像。

        ``learning_domain`` 为空时，会返回该用户找到的第一个画像；
        指定领域时，只返回该领域对应的画像。任何异常数据都会被视为
        “没有可用画像”，而不是让读取流程直接中断。
        """
        profiles = self._read_all()
        # 先定位用户。不存在时 profiles.get 会返回 None。
        user_profiles = profiles.get(user_id)
        # 这里同时处理新格式和旧格式，具体选择逻辑集中在辅助方法中。
        payload = self._select_profile(user_profiles, learning_domain)
        if not isinstance(payload, dict):
            return None
        try:
            # 将 JSON 字典还原成 LearnerProfile 对象，供业务层使用。
            return LearnerProfile.from_dict(payload)
        except (TypeError, KeyError):
            # 字段缺失或字段类型不符合模型要求时，安全地返回 None。
            return None

    def save(self, profile: LearnerProfile) -> LearnerProfile:
        """保存一个画像，并返回传入的画像对象。

        保存前会自动维护创建时间和更新时间。对于同一用户、同一学习领域，
        新画像会完整替换旧画像，不会与旧字典逐字段合并。
        """
        if not profile.learning_domain:
            # 学习领域是内层字典的键，也是区分画像的必要信息。
            raise ValueError("learning_domain is required")

        # 使用带时区的 UTC 时间，避免不同机器的本地时区造成时间歧义。
        now = datetime.now(timezone.utc).isoformat()
        if not profile.created_at:
            # 首次保存才设置创建时间；再次保存时保留原创建时间。
            profile.created_at = now
        # 每次保存都刷新更新时间。
        profile.updated_at = now

        profiles = self._read_all()
        # 将用户已有数据统一成“学习领域 -> 画像字典”的新格式，
        # 同时把旧版单画像格式转换后再继续保存。
        user_profiles = self._normalize_user_profiles(profiles.get(profile.user_id))
        # 保存是指定学习领域下的完整替换，而不是局部更新。
        user_profiles[profile.learning_domain] = profile.to_dict()
        profiles[profile.user_id] = user_profiles
        # 如果父目录不存在，先递归创建目录。
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # TODO: 当前所有画像集中在一个 JSON 文件中，保存时会整体重写文件；
        # 后续可改为 SQLite、独立画像文件等方案，实现真正的增量更新。
        self.path.write_text(
            # ensure_ascii=False 让中文保持可读；indent=2 便于人工查看和调试。
            json.dumps(profiles, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return profile

    @staticmethod
    def _select_profile(user_profiles: object, learning_domain: str | None) -> dict | None:
        """从某个用户的数据中选择一个画像。

        该方法兼容两种格式：
        1. 旧格式：``{user_id: profile_dict}``；  一个用户只对应一个画像
        2. 新格式：``{user_id: {learning_domain: profile_dict}}``。  一个用户可以有多个领域画像
        """
        if not isinstance(user_profiles, dict):
            # 用户不存在，或用户对应的数据不是字典。
            return None
        # 旧格式的画像本身会直接包含 user_id 字段，可据此识别。
        if "user_id" in user_profiles:
            if learning_domain and user_profiles.get("learning_domain") != learning_domain:
                # 指定领域与旧画像记录的领域不一致。
                return None
            return user_profiles
        if learning_domain:
            # 新格式下按领域精确查找。
            payload = user_profiles.get(learning_domain)
            return payload if isinstance(payload, dict) else None
        # 未指定领域时，返回第一个值为字典的画像。
        return next((item for item in user_profiles.values() if isinstance(item, dict)), None)

    @staticmethod
    def _normalize_user_profiles(user_profiles: object) -> dict[str, dict]:
        """将用户画像数据统一转换为新格式。

        返回值始终是 ``{学习领域: 画像字典}``。这样 ``save`` 就可以使用
        同一套写入逻辑，无需关心磁盘上的数据是新格式还是旧格式。
        """
        if not isinstance(user_profiles, dict):
            # 用户没有历史数据，返回空字典供 save 添加新画像。
            return {}
        if "user_id" in user_profiles:
            # 旧格式只有一个画像：提取其学习领域作为新的内层键。
            previous_domain = str(user_profiles.get("learning_domain", "")).strip()
            return {previous_domain: user_profiles} if previous_domain else {}
        # 新格式：只保留值为字典的合法画像，过滤掉异常数据。
        return {key: value for key, value in user_profiles.items() if isinstance(value, dict)}

    def _read_all(self) -> dict[str, dict]:
        """读取整个 JSON 文件，并在读取失败时返回空字典。

        读取失败包括文件不存在、文件无法访问以及 JSON 内容损坏。
        这里选择容错返回空数据，使应用可以继续运行；后续保存时可能会
        用新的合法内容覆盖原文件。
        """
        if not self.path.exists():
            # 首次运行时文件通常还不存在。
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # OSError：文件读写失败；JSONDecodeError：文件内容不是合法 JSON。
            return {}
        # 顶层必须是字典，否则不符合本仓储约定的数据结构。
        return payload if isinstance(payload, dict) else {}
