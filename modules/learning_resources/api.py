"""知识点延伸学习资源接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from .module import LearningResourceModule


class LearningResourceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    platform: str
    url: str
    language: str = "zh"
    kind: str = "video"
    note: str = ""


class KnowledgePointResourceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    knowledge_point_id: str = Field(alias="knowledgePointId")
    resources: list[LearningResourceResponse] = Field(default_factory=list)


class ResourceCatalogResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[KnowledgePointResourceResponse] = Field(default_factory=list)


def build_router(module: LearningResourceModule) -> APIRouter:
    router = APIRouter(tags=["learning-resources"])

    @router.get("/api/learning-resources", response_model=ResourceCatalogResponse)
    def list_resources(
        knowledge_point_ids: str | None = Query(default=None, alias="knowledgePointIds", description="逗号分隔；不传则返回全部已收录知识点"),
    ) -> ResourceCatalogResponse:
        """按知识点查询延伸学习资源。未收录的知识点返回空列表，由前端展示空态。"""
        if knowledge_point_ids:
            wanted = [item.strip() for item in knowledge_point_ids.split(",") if item.strip()]
            data = module.for_knowledge_points(wanted)
        else:
            data = module.catalog()
        return ResourceCatalogResponse(
            items=[
                KnowledgePointResourceResponse(
                    knowledgePointId=point_id,
                    resources=[LearningResourceResponse(**item) for item in items],
                )
                for point_id, items in data.items()
            ]
        )

    return router
