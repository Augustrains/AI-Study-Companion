import json
import os
import unittest
from unittest.mock import MagicMock, patch

import httpx

from modules.common.errors import ConfigurationError, ExternalServiceError
from sdk.llm_client import DeepSeekLLMClient


class DeepSeekLLMClientTest(unittest.TestCase):
    @patch("sdk.llm_client.httpx.Client")
    def test_generate_calls_opencode_chat_completions(self, mock_client_class):
        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": "  生成结果  "}}]
        }
        client = mock_client_class.return_value.__enter__.return_value
        client.post.return_value = response
        llm = DeepSeekLLMClient(api_key="secret", timeout=12)

        result = llm.generate("测试提示")

        self.assertEqual(result, "生成结果")
        mock_client_class.assert_called_once()
        client_options = mock_client_class.call_args.kwargs
        self.assertEqual(client_options["timeout"], 12)
        self.assertFalse(client_options["trust_env"])
        self.assertEqual(client_options["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(client_options["headers"]["User-Agent"], "StudyCompanion/1.0")
        client.post.assert_called_once_with(
            "https://opencode.ai/zen/go/v1/chat/completions",
            json={
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "测试提示"}],
                "stream": False,
            },
        )
        response.raise_for_status.assert_called_once_with()

    @patch("sdk.llm_client.httpx.Client")
    def test_generate_multimodal_sends_text_and_image_in_one_request(self, mock_client_class):
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "回答"}}]}
        client = mock_client_class.return_value.__enter__.return_value
        client.post.return_value = response
        llm = DeepSeekLLMClient(api_key="secret")

        result = llm.generate_multimodal(
            "解释图片",
            image_urls=["https://example.invalid/cnn.png"],
        )

        self.assertEqual(result, "回答")
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["messages"][0]["content"], [
            {"type": "text", "text": "解释图片"},
            {"type": "image_url", "image_url": {"url": "https://example.invalid/cnn.png"}},
        ])

    @patch("sdk.llm_client.httpx.Client")
    def test_generate_json_requests_a_json_object(self, mock_client_class):
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": '{"refused": false, "answer": "回答"}'}}]}
        client = mock_client_class.return_value.__enter__.return_value
        client.post.return_value = response

        result = DeepSeekLLMClient(api_key="secret").generate_json("只输出 JSON")

        self.assertIn('"answer"', result)
        self.assertEqual(client.post.call_args.kwargs["json"]["response_format"], {"type": "json_object"})

    @patch("sdk.llm_client.httpx.Client")
    def test_http_error_is_converted_to_external_service_error(self, mock_client_class):
        request = httpx.Request("POST", "https://opencode.ai/zen/go/v1/chat/completions")
        error_response = httpx.Response(401, request=request)
        response = MagicMock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "unauthorized",
            request=request,
            response=error_response,
        )
        client = mock_client_class.return_value.__enter__.return_value
        client.post.return_value = response

        with self.assertRaises(ExternalServiceError) as caught:
            DeepSeekLLMClient(api_key="invalid").generate("test")

        self.assertEqual(caught.exception.details["status_code"], 401)

    def test_generate_requires_api_key(self):
        with self.assertRaises(ConfigurationError):
            DeepSeekLLMClient().generate("test")

    def test_from_env_supports_generic_api_key(self):
        with patch.dict(
            os.environ,
            {
                "STUDY_COMPANION_LLM_API_KEY": "env-secret",
                "STUDY_COMPANION_LLM_MODEL": "custom-model",
            },
            clear=True,
        ):
            client = DeepSeekLLMClient.from_env()
        self.assertEqual(client.api_key, "env-secret")
        self.assertEqual(client.model, "custom-model")

    @patch("sdk.llm_client.dotenv_values")
    def test_project_env_key_takes_priority_over_legacy_process_key(self, mock_dotenv_values):
        mock_dotenv_values.return_value = {"DEEPSEEK_API_KEY": "project-key"}
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "legacy-process-key"}, clear=True):
            client = DeepSeekLLMClient.from_env()

        self.assertEqual(client.api_key, "project-key")


if __name__ == "__main__":
    unittest.main()
