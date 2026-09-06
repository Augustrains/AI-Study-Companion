import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.material_qa.agent import MaterialQaAgent
from modules.material_qa.api import build_router
from modules.material_qa.attachment_repository import InMemoryMaterialQaAttachmentRepository
from modules.material_qa.attachment_service import MaterialQaAttachmentService
from modules.material_qa.repository import InMemoryMaterialQaMessageStore
from modules.material_qa.models import MaterialQaRetrievalResult
from modules.material_qa.workflow import MaterialQaWorkflow


class _Storage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def save(self, *, user_id: str, file_name: str, file_type: str, content: bytes) -> str:
        del file_type
        url = f"https://example.invalid/material-qa/{user_id}/{file_name}"
        self.objects[url] = content
        return url

    def delete(self, *, file_url: str) -> None:
        self.objects.pop(file_url, None)


class _Llm:
    model = "test"

    def generate(self, _prompt: str) -> str:
        return '{"refused": false, "answer": "ok"}'

    def generate_multimodal(self, _prompt: str, *, image_urls: list[str]) -> str:
        self.image_urls = image_urls
        return '{"refused": false, "answer": "ok"}'


class _EmptyRetriever:
    def retrieve(self, **_kwargs) -> MaterialQaRetrievalResult:
        return MaterialQaRetrievalResult(chunks=[])


class MaterialQaAttachmentApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = _Storage()
        repository = InMemoryMaterialQaAttachmentRepository()
        service = MaterialQaAttachmentService(storage=self.storage, repository=repository)
        workflow = MaterialQaWorkflow(
            agent=MaterialQaAgent(_Llm()),
            retriever=_EmptyRetriever(),
            message_store=InMemoryMaterialQaMessageStore(),
            attachment_service=service,
        )
        app = FastAPI()
        app.include_router(build_router(workflow, service))
        self.client = TestClient(app)

    def test_upload_list_sign_and_delete(self) -> None:
        uploaded = self.client.post(
            "/api/rag/attachments",
            data={"userId": "1", "messageId": "10"},
            files={"file": ("cnn.png", b"image", "image/png")},
        )
        self.assertEqual(uploaded.status_code, 200)
        body = uploaded.json()
        self.assertEqual(body["fileName"], "cnn.png")
        self.assertEqual(body["fileUrl"], "https://example.invalid/material-qa/1/cnn.png")
        attachment_id = body["id"]

        listed = self.client.get(
            "/api/rag/messages/10/attachments",
            params={"userId": "1"},
        )
        self.assertEqual(len(listed.json()), 1)

        deleted = self.client.delete(
            f"/api/rag/attachments/{attachment_id}",
            params={"userId": "1"},
        )
        self.assertEqual(deleted.json(), {"deleted": True})

    def test_question_and_attachment_share_the_saved_user_message(self) -> None:
        response = self.client.post(
            "/api/rag/conversations/qa-test/messages-with-attachment",
            data={
                "userId": "1",
                "bookId": "ml",
                "question": "请解释这张图",
                "answerMode": "direct",
            },
            files={"file": ("diagram.png", b"image", "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        user_message_id = response.json()["userMessageId"]
        self.assertIsInstance(user_message_id, int)
        listed = self.client.get(
            f"/api/rag/messages/{user_message_id}/attachments",
            params={"userId": "1"},
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["messageId"], user_message_id)


if __name__ == "__main__":
    unittest.main()
