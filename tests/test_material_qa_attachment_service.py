import unittest

from modules.common.errors import ResourceNotFoundError, ValidationAppError
from modules.material_qa.attachment_repository import InMemoryMaterialQaAttachmentRepository
from modules.material_qa.attachment_service import MaterialQaAttachmentService


class _MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def save(self, *, user_id: str, file_name: str, file_type: str, content: bytes) -> str:
        del file_type
        url = f"https://example.invalid/material-qa/{user_id}/{file_name}"
        self.objects[url] = content
        return url

    def delete(self, *, file_url: str) -> None:
        self.objects.pop(file_url, None)
        self.deleted.append(file_url)


class _FailingRepository(InMemoryMaterialQaAttachmentRepository):
    def create(self, **kwargs):
        del kwargs
        raise RuntimeError("database unavailable")


class MaterialQaAttachmentServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = _MemoryStorage()
        self.repository = InMemoryMaterialQaAttachmentRepository()
        self.service = MaterialQaAttachmentService(
            storage=self.storage,
            repository=self.repository,
        )

    def test_upload_saves_object_and_metadata(self) -> None:
        attachment = self.service.upload(
            user_id="1",
            message_id=10,
            file_name="cnn.PNG",
            file_type="image/png",
            content=b"image",
        )

        self.assertEqual(attachment.file_name, "cnn.PNG")
        self.assertEqual(attachment.file_size, 5)
        self.assertEqual(self.storage.objects[attachment.file_url], b"image")

    def test_upload_rejects_unsupported_or_mismatched_files(self) -> None:
        with self.assertRaises(ValidationAppError):
            self.service.upload(
                user_id="1", message_id=10, file_name="x.exe",
                file_type="application/octet-stream", content=b"x",
            )
        with self.assertRaises(ValidationAppError):
            self.service.upload(
                user_id="1", message_id=10, file_name="x.pdf",
                file_type="image/png", content=b"x",
            )

    def test_database_failure_removes_uploaded_object(self) -> None:
        service = MaterialQaAttachmentService(
            storage=self.storage,
            repository=_FailingRepository(),
        )

        with self.assertRaises(RuntimeError):
            service.upload(
                user_id="1", message_id=10, file_name="x.png",
                file_type="image/png", content=b"x",
            )

        self.assertEqual(self.storage.objects, {})
        self.assertEqual(self.storage.deleted, ["https://example.invalid/material-qa/1/x.png"])

    def test_delete_removes_metadata_and_object(self) -> None:
        attachment = self.service.upload(
            user_id="1", message_id=10, file_name="x.webp",
            file_type="image/webp", content=b"image",
        )

        deleted = self.service.delete(user_id="1", attachment_id=attachment.id)
        self.assertEqual(deleted.id, attachment.id)
        self.assertIn(attachment.file_url, self.storage.deleted)


if __name__ == "__main__":
    unittest.main()
