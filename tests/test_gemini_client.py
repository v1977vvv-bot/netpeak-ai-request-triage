from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors

from src.config import Settings
from src.gemini_client import (
    CLASSIFICATION_TEMPERATURE,
    JSON_MIME_TYPE,
    GeminiClient,
    GeminiClientError,
    GeminiConfigurationError,
)
from src.schemas import IncomingRequest, RequestClassification


def incoming_request() -> IncomingRequest:
    return IncomingRequest(
        id="request-1",
        channel="email",
        timestamp="2026-06-25",
        raw_text="Потрібно автоматизувати звіт",
    )


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_client_rejects_missing_api_key(api_key: str | None) -> None:
    settings = Settings(gemini_api_key=api_key, _env_file=None)

    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY"):
        GeminiClient(settings)


@patch("src.gemini_client.genai.Client")
def test_client_uses_api_key_from_settings(client_class: MagicMock) -> None:
    settings = Settings(gemini_api_key="test-api-key", _env_file=None)

    GeminiClient(settings)

    client_class.assert_called_once_with(api_key="test-api-key")


@patch("src.gemini_client.genai.Client")
def test_client_strips_api_key_before_sdk_initialization(
    client_class: MagicMock,
) -> None:
    settings = Settings(gemini_api_key="  test-api-key  ", _env_file=None)

    GeminiClient(settings)

    client_class.assert_called_once_with(api_key="test-api-key")


@patch("src.gemini_client.build_classification_prompt")
@patch("src.gemini_client.genai.Client")
def test_classify_request_calls_gemini_with_structured_output(
    client_class: MagicMock,
    build_prompt: MagicMock,
) -> None:
    settings = Settings(
        gemini_api_key="test-api-key",
        gemini_model="test-gemini-model",
        _env_file=None,
    )
    sdk_client = client_class.return_value
    sdk_client.interactions.create.return_value.output_text = '{"priority":"medium"}'
    build_prompt.return_value = "classification prompt"
    request = incoming_request()

    result = GeminiClient(settings).classify_request(request)

    build_prompt.assert_called_once_with(request)
    sdk_client.interactions.create.assert_called_once_with(
        model="test-gemini-model",
        input="classification prompt",
        generation_config={"temperature": CLASSIFICATION_TEMPERATURE},
        response_format={
            "type": "text",
            "mime_type": JSON_MIME_TYPE,
            "schema": RequestClassification.model_json_schema(),
        },
    )
    assert result == '{"priority":"medium"}'


@patch("src.gemini_client.genai.Client")
def test_classify_request_rejects_empty_output(client_class: MagicMock) -> None:
    settings = Settings(gemini_api_key="test-api-key", _env_file=None)
    client_class.return_value.interactions.create.return_value.output_text = "   "

    with pytest.raises(GeminiClientError, match="empty"):
        GeminiClient(settings).classify_request(incoming_request())


@patch("src.gemini_client.genai.Client")
def test_classify_request_wraps_sdk_error(client_class: MagicMock) -> None:
    settings = Settings(gemini_api_key="test-api-key", _env_file=None)
    original_error = errors.APIError(503, {"message": "service unavailable"})
    client_class.return_value.interactions.create.side_effect = original_error

    with pytest.raises(GeminiClientError) as raised_error:
        GeminiClient(settings).classify_request(incoming_request())

    assert raised_error.value.__cause__ is original_error
