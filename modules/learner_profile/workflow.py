"""Learner-profile LangGraph workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .field_rules import apply_profile_corrections, normalize_profile
from .models import LearnerProfile
from modules.common import api as common_api

if False:  # pragma: no cover
    from modules.memory.module import MemoryModule


#读取学习者画像，保存
class JsonLearnerProfileRepository:
    def __init__(self, reader: common_api.json_storage.JsonContentReader, store: common_api.json_storage.JsonStore) -> None:
        self.reader, self.store, self.path = reader, store, reader.path

    def exists(self, user_id: str, learning_domain: str | None = None) -> bool:
        return self.get(user_id, learning_domain) is not None

    def get(self, user_id: str, learning_domain: str | None = None) -> LearnerProfile | None:
        # 没有画像文件表示用户尚未创建画像，不应被当作存储故障。
        # A learner profile is a required confirmed resource.  Missing or empty
        # files must surface as storage errors; an absent profile in a valid
        # object is represented by ``None`` below.
        content = self.reader.read()
        if not isinstance(content, dict):
            raise common_api.errors.StorageReadError("learner profile resource must be a JSON object")
        user_profiles = content.get(user_id)
        if not isinstance(user_profiles, dict):
            return None
        payload = user_profiles.get(learning_domain) if learning_domain else next((item for item in user_profiles.values() if isinstance(item, dict)), None)
        if not isinstance(payload, dict):
            return None
        try:
            return common_api.serialization.from_data(LearnerProfile, payload)
        except (TypeError, KeyError, common_api.errors.SerializationAppError):
            return None

    def save(self, profile: LearnerProfile) -> LearnerProfile:
        if not profile.learning_domain:
            raise common_api.errors.ValidationAppError("learning_domain is required", details={"field": "learning_domain"})
        now = datetime.now(timezone.utc).isoformat()
        if not profile.created_at:
            profile.created_at = now
        profile.updated_at = now
        self.store.save(path=self.path, content=common_api.serialization.to_data(profile), mode="upsert", key_path=[profile.user_id, profile.learning_domain])
        return profile


class LearnerProfileState(TypedDict, total=False):
    workflow_id: str
    raw_profile: dict[str, Any]
    draft_profile: dict[str, Any]
    review_action: str
    corrections: dict[str, Any]
    saved_profile: dict[str, Any]
    status: str

#使用langraph定义画像确认流程
def build_learner_profile_graph(*, repository: JsonLearnerProfileRepository, checkpointer: Any, memory: "MemoryModule | None" = None, knowledge_point_catalog: common_api.knowledge_points.JsonKnowledgePointCatalog | None = None):
    def catalog_ids(state: LearnerProfileState) -> list[str] | None:
        if knowledge_point_catalog is None:
            return None
        return knowledge_point_catalog.ids(state["raw_profile"]["learning_domain"])

    #规范化
    def draft(state: LearnerProfileState) -> dict[str, Any]:
        return {"draft_profile": normalize_profile(state["raw_profile"], catalog_ids(state)).to_dict(), "status": "pending_confirmation"}
    
    #流程核心
    def review(state: LearnerProfileState) -> dict[str, Any]:
        decision = interrupt({
            "type": "learner_profile_review",
            "workflow_id": state["workflow_id"],
            "draft_profile": state["draft_profile"],
            "allowed_actions": ["approve", "edit", "reject"],
        })
        if not isinstance(decision, dict):
            raise ValueError("profile review must be a JSON object")
        action = str(decision.get("action", "")).strip()
        if action not in {"approve", "edit", "reject"}:
            raise ValueError(f"unsupported profile review action: {action}")
        
        #处理修改内容
        corrections = decision.get("corrections") or {}
        if action == "edit":
            revised = apply_profile_corrections(state["draft_profile"], corrections, catalog_ids(state))
            return {"review_action": action, "corrections": corrections, "draft_profile": revised.to_dict(), "status": "approved"}
        return {"review_action": action, "corrections": {}, "status": "rejected" if action == "reject" else "approved"}

    def commit(state: LearnerProfileState) -> dict[str, Any]:
        saved = repository.save(LearnerProfile.from_dict(state["draft_profile"]))
        if memory is not None:
            memory.sync_learner_profile(saved)
        return {"saved_profile": saved.to_dict(), "status": "completed"}

    builder = StateGraph(LearnerProfileState)
    builder.add_node("draft", draft)
    builder.add_node("review", review)
    builder.add_node("commit", commit)
    builder.add_node("reject", lambda _: {"status": "rejected"})  #拒绝节点不做任何持久化操作
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "review")
    builder.add_conditional_edges("review", lambda state: "reject" if state["review_action"] == "reject" else "commit", {"commit": "commit", "reject": "reject"})
    builder.add_edge("commit", END)
    builder.add_edge("reject", END)
    return builder.compile(checkpointer=checkpointer)


#包装 LangGraph 的启动和恢复逻辑
class LearnerProfileWorkflow:
    def __init__(self, repository: JsonLearnerProfileRepository, checkpointer: Any | None = None, memory: "MemoryModule | None" = None, knowledge_point_catalog: common_api.knowledge_points.JsonKnowledgePointCatalog | None = None) -> None:
        self.repository = repository
        self.knowledge_point_catalog = knowledge_point_catalog
        self.graph = build_learner_profile_graph(repository=repository, checkpointer=checkpointer or InMemorySaver(), memory=memory, knowledge_point_catalog=knowledge_point_catalog)

    def knowledge_points(self, learning_domain: str) -> list[dict[str, str]]:
        return self.knowledge_point_catalog.as_dicts(learning_domain) if self.knowledge_point_catalog else []

    @staticmethod
    def _config(workflow_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": workflow_id}}

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_id = f"profile_{uuid4().hex[:10]}"
        result = self.graph.invoke({"workflow_id": workflow_id, "raw_profile": payload, "status": "started"}, config=self._config(workflow_id))
        return result["__interrupt__"][0].value

    def review(self, workflow_id: str, *, action: str, corrections: dict[str, Any] | None = None) -> LearnerProfile | None:
        result = self.graph.invoke(Command(resume={"action": action, "corrections": corrections or {}}), config=self._config(workflow_id))
        if result["status"] == "rejected":
            return None
        return LearnerProfile.from_dict(result["saved_profile"])

    def get(self, user_id: str, learning_domain: str | None = None) -> LearnerProfile | None:
        return self.repository.get(user_id, learning_domain)

    def start_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.start(payload)

    def review_workflow(self, workflow_id: str, *, action: str, corrections: dict[str, Any] | None = None) -> LearnerProfile | None:
        return self.review(workflow_id, action=action, corrections=corrections)


__all__ = [
    "JsonLearnerProfileRepository",
    "LearnerProfileState",
    "LearnerProfileWorkflow",
    "build_learner_profile_graph",
]
