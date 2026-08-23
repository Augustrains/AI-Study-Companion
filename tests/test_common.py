import os
import unittest
from dataclasses import dataclass
from pathlib import Path

from modules.common.config import Settings
from modules.common.errors import ConfigurationError, SerializationAppError
from modules.common.serialization import from_data, to_data
from modules.common.schema_validator import FieldSpec, validate_fields


@dataclass
class Child:
    name: str


@dataclass
class Parent:
    child: Child
    enabled: bool = False


class CommonUtilitiesTest(unittest.TestCase):
    def test_schema_validator_checks_type_null_range_and_unknown_fields(self):
        schema = {
            "age": FieldSpec(field_type=int, required=True, nullable=False, min_value=0, max_value=120),
            "name": FieldSpec(field_type=str, required=True, min_length=2, max_length=10),
        }
        with self.assertRaisesRegex(Exception, "field validation failed"):
            validate_fields({"age": 130, "name": "", "extra": 1}, schema)

    def test_schema_validator_returns_valid_data_and_defaults(self):
        schema = {
            "name": FieldSpec(field_type=str, required=True),
            "tags": FieldSpec(field_type=list, item_type=str, default=list),
        }
        self.assertEqual(validate_fields({"name": "demo"}, schema), {"name": "demo", "tags": []})

    def test_nested_dataclass_round_trip(self):
        value = Parent(Child("demo"), True)
        payload = to_data(value)
        self.assertEqual(payload, {"child": {"name": "demo"}, "enabled": True})
        self.assertEqual(from_data(Parent, payload), value)

    def test_deserialization_rejects_wrong_types_and_unknown_fields(self):
        with self.assertRaises(SerializationAppError):
            from_data(Parent, {"child": {"name": "demo"}, "enabled": "yes"})
        with self.assertRaises(SerializationAppError):
            from_data(Parent, {"child": {"name": "demo"}, "extra": 1})

    def test_settings_read_environment(self):
        original_data = os.environ.get("STUDY_COMPANION_DATA_DIR")
        original_port = os.environ.get("STUDY_COMPANION_BACKEND_PORT")
        try:
            os.environ["STUDY_COMPANION_DATA_DIR"] = "D:/study-data"
            os.environ["STUDY_COMPANION_BACKEND_PORT"] = "9000"
            settings = Settings.from_env(Path.cwd())
            self.assertEqual(settings.data_dir, Path("D:/study-data").resolve())
            self.assertEqual(settings.backend_port, 9000)
        finally:
            for name, value in (("STUDY_COMPANION_DATA_DIR", original_data), ("STUDY_COMPANION_BACKEND_PORT", original_port)):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_settings_reject_invalid_port(self):
        original = os.environ.get("STUDY_COMPANION_BACKEND_PORT")
        try:
            os.environ["STUDY_COMPANION_BACKEND_PORT"] = "bad"
            with self.assertRaises(ConfigurationError):
                Settings.from_env()
        finally:
            if original is None:
                os.environ.pop("STUDY_COMPANION_BACKEND_PORT", None)
            else:
                os.environ["STUDY_COMPANION_BACKEND_PORT"] = original
