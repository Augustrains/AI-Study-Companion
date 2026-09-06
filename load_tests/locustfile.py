"""Mixed read/publish load profile for the material RAG API.

Run only against a disposable or staging data directory.  The publisher task
uses the ML corpus because DL units remain pending review by default.
"""

from __future__ import annotations

from locust import HttpUser, between, task


class MaterialQaReader(HttpUser):
    weight = 20
    wait_time = between(0.2, 1.0)

    @task
    def ask_material_question(self) -> None:
        self.client.post(
            "/api/rag/ask",
            json={
                "bookId": "ml",
                "userId": "load-reader",
                "question": "什么是监督学习？",
                "allowGeneralFallback": False,
            },
            name="rag_ask",
        )


class MaterialIndexPublisher(HttpUser):
    """Low-frequency competing publisher; expect one build or a 409 conflict."""

    weight = 1
    wait_time = between(10, 20)

    @task
    def rebuild_same_material(self) -> None:
        with self.client.post(
            "/api/rag/indexes/rebuild",
            json={"bookIds": ["ml"], "confirm": True},
            name="rag_rebuild",
            catch_response=True,
        ) as response:
            if response.status_code in {200, 409}:
                response.success()
