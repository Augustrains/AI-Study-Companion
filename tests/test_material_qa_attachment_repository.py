import unittest

from modules.common.errors import ResourceNotFoundError
from modules.material_qa.attachment_repository import InMemoryMaterialQaAttachmentRepository


class InMemoryMaterialQaAttachmentRepositoryTest(unittest.TestCase):
    def test_create_and_read_attachment_for_owner(self) -> None:
        repository = InMemoryMaterialQaAttachmentRepository()

        created = repository.create(
            user_id="1",
            message_id=10,
            file_name="cnn.png",
            file_type="image/png",
            file_size=128,
            file_url="https://example.invalid/a.png",
        )

        self.assertEqual(created.id, 1)
        self.assertEqual(repository.get_by_id(user_id="1", attachment_id=1), created)
        self.assertIsNone(repository.get_by_id(user_id="2", attachment_id=1))

    def test_list_is_scoped_by_owner_and_message(self) -> None:
        repository = InMemoryMaterialQaAttachmentRepository()
        repository.create(
            user_id="1", message_id=10, file_name="a.png", file_type="image/png",
            file_size=1, file_url="https://example.invalid/a.png",
        )
        repository.create(
            user_id="1", message_id=11, file_name="b.pdf", file_type="application/pdf",
            file_size=2, file_url="https://example.invalid/b.pdf",
        )
        repository.create(
            user_id="2", message_id=10, file_name="c.png", file_type="image/png",
            file_size=3, file_url="https://example.invalid/c.png",
        )

        rows = repository.list_by_message_id(user_id="1", message_id=10)

        self.assertEqual([row.file_name for row in rows], ["a.png"])

    def test_delete_is_owner_scoped(self) -> None:
        repository = InMemoryMaterialQaAttachmentRepository()
        created = repository.create(
            user_id="1", message_id=10, file_name="cnn.png", file_type="image/png",
            file_size=128, file_url="https://example.invalid/cnn.png",
        )

        with self.assertRaises(ResourceNotFoundError):
            repository.delete(user_id="2", attachment_id=created.id)

        deleted = repository.delete(user_id="1", attachment_id=created.id)
        self.assertEqual(deleted.file_url, "https://example.invalid/cnn.png")
        self.assertIsNone(repository.get_by_id(user_id="1", attachment_id=created.id))


if __name__ == "__main__":
    unittest.main()
