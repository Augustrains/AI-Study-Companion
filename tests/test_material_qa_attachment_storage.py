import unittest
from types import SimpleNamespace

from modules.common.errors import ConfigurationError, ValidationAppError
from modules.material_qa.attachment_storage import OssAttachmentStorage


class _FakeBucket:
    def __init__(self) -> None:
        self.uploads = []
        self.deletes = []

    def put_object(self, key, content, headers=None):
        self.uploads.append((key, content, headers))

    def delete_object(self, key):
        self.deletes.append(key)


class OssAttachmentStorageTest(unittest.TestCase):
    def test_from_settings_reports_missing_configuration(self) -> None:
        settings = SimpleNamespace(
            oss_endpoint="",
            oss_region="",
            oss_bucket="",
            oss_prefix="material-qa",
            oss_access_key_id="",
            oss_access_key_secret="",
        )

        with self.assertRaises(ConfigurationError) as context:
            OssAttachmentStorage.from_settings(settings)  # type: ignore[arg-type]

        self.assertIn("STUDY_COMPANION_OSS_BUCKET", context.exception.details["variables"])

    def test_upload_returns_public_url(self) -> None:
        bucket = _FakeBucket()
        storage = OssAttachmentStorage(bucket=bucket, prefix="material-qa/")

        storage.public_base_url = "https://study-files.oss-cn-beijing.aliyuncs.com"
        url = storage.save(
            user_id="12",
            file_name="diagram.PNG",
            file_type="image/png",
            content=b"image-bytes",
        )

        self.assertRegex(url, r"^https://study-files\.oss-cn-beijing\.aliyuncs\.com/material-qa/12/\d{4}/\d{2}/[0-9a-f]{32}\.png$")
        self.assertEqual(bucket.uploads[0][1:], (b"image-bytes", {"Content-Type": "image/png"}))

    def test_rejects_empty_content(self) -> None:
        storage = OssAttachmentStorage(bucket=_FakeBucket())

        with self.assertRaises(ValidationAppError):
            storage.save(user_id="12", file_name="x.png", file_type="image/png", content=b"")

    def test_delete_restores_object_name_from_public_url(self) -> None:
        bucket = _FakeBucket()
        storage = OssAttachmentStorage(bucket=bucket, public_base_url="https://example.invalid")

        storage.delete(file_url="https://example.invalid/material-qa/12/file.pdf")

        self.assertEqual(bucket.deletes, ["material-qa/12/file.pdf"])


if __name__ == "__main__":
    unittest.main()
