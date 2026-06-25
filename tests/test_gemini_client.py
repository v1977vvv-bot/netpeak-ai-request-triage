from unittest.mock import MagicMock, patch

import httpx
import pytest
from google.genai import errors
from google.genai._gaos.lib import compat_errors
from pydantic import ValidationError

from src.config import Settings
from src.gemini_client import (
    API_ERROR_CODE,
    CLASSIFICATION_TEMPERATURE,
    EMPTY_OUTPUT_ERROR_CODE,
    JSON_MIME_TYPE,
    RATE_LIMITED_ERROR_CODE,
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


def classification_validation_error() -> ValidationError:
    with pytest.raises(ValidationError) as raised_error:
        RequestClassification.model_validate_json('{"category":"unknown"}')
    return raised_error.value


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


@patch("src.gemini_client.genai.Client")
def test_model_name_returns_configured_model(client_class: MagicMock) -> None:
    settings = Settings(
        gemini_api_key="test-api-key",
        gemini_model="configured-model",
        _env_file=None,
    )

    client = GeminiClient(settings)

    assert client.model_name == "configured-model"


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


@patch("src.gemini_client.build_repair_prompt")
@patch("src.gemini_client.genai.Client")
def test_repair_classification_returns_raw_structured_output(
    client_class: MagicMock,
    build_repair_prompt: MagicMock,
) -> None:
    settings = Settings(gemini_api_key="test-api-key", _env_file=None)
    sdk_client = client_class.return_value
    sdk_client.interactions.create.return_value.output_text = "not validated JSON"
    build_repair_prompt.return_value = "repair prompt"
    request = incoming_request()
    invalid_response = '{"category":"unknown"}'
    validation_error = classification_validation_error()

    result = GeminiClient(settings).repair_classification(
        request,
        invalid_response,
        validation_error,
    )

    build_repair_prompt.assert_called_once_with(
        request,
        invalid_response,
        validation_error,
    )
    sdk_client.interactions.create.assert_called_once_with(
        model="gemini-2.5-flash",
        input="repair prompt",
        generation_config={"temperature": CLASSIFICATION_TEMPERATURE},
        response_format={
            "type": "text",
            "mime_type": JSON_MIME_TYPE,
            "schema": RequestClassification.model_json_schema(),
        },
    )
    assert result == "not validated JSON"


@patch("src.gemini_client.genai.Client")
def test_classify_request_rejects_empty_output(client_class: MagicMock) -> None:
    settings = Settings(gemini_api_key="test-api-key", _env_file=None)
    client_class.return_value.interactions.create.return_value.output_text = "   "

    with pytest.raises(GeminiClientError, match="empty") as raised_error:
        GeminiClient(settings).classify_request(incoming_request())

    assert raised_error.value.code == EMPTY_OUTPUT_ERROR_CODE


@patch("src.gemini_client.genai.Client")
def test_classify_request_wraps_sdk_error(client_class: MagicMock) -> None:
    settings = Settings(gemini_api_key="test-api-key", _env_file=None)
    original_error = errors.APIError(503, {"message": "service unavailable"})
    client_class.return_value.interactions.create.side_effect = original_error

    with pytest.raises(GeminiClientError) as raised_error:
        GeminiClient(settings).classify_request(incoming_request())

    assert raised_error.value.__cause__ is original_error
    assert raised_error.value.code == API_ERROR_CODE


@patch("src.gemini_client.genai.Client")
def test_classify_request_wraps_interactions_rate_limit_error(
    client_class: MagicMock,
) -> None:
    settings = Settings(gemini_api_key="test-api-key", _env_file=None)
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
    response = httpx.Response(429, request=request)
    original_error = compat_errors.RateLimitError(
        "Quota exceeded.",
        response=response,
        body={"message": "quota exceeded"},
    )
    client_class.return_value.interactions.create.side_effect = original_error

    with pytest.raises(GeminiClientError) as raised_error:
        GeminiClient(settings).classify_request(incoming_request())

    assert raised_error.value.__cause__ is original_error
    assert raised_error.value.code == RATE_LIMITED_ERROR_CODE


@patch("src.gemini_client.sleep")
@patch("src.gemini_client.monotonic", return_value=100.0)
@patch("src.gemini_client.genai.Client")
def test_first_api_call_does_not_sleep(
    client_class: MagicMock,
    monotonic_mock: MagicMock,
    sleep_mock: MagicMock,
) -> None:
    settings = Settings(
        gemini_api_key="test-api-key",
        gemini_min_request_interval_seconds=13.0,
        _env_file=None,
    )
    sdk_client = client_class.return_value
    sdk_client.interactions.create.return_value.output_text = '{"priority":"medium"}'

    GeminiClient(settings).classify_request(incoming_request())

    sleep_mock.assert_not_called()
    monotonic_mock.assert_called_once()


@patch("src.gemini_client.sleep")
@patch("src.gemini_client.monotonic", side_effect=[100.0, 105.0, 113.0])
@patch("src.gemini_client.genai.Client")
def test_second_api_call_waits_for_remaining_interval(
    client_class: MagicMock,
    monotonic_mock: MagicMock,
    sleep_mock: MagicMock,
) -> None:
    settings = Settings(
        gemini_api_key="test-api-key",
        gemini_min_request_interval_seconds=13.0,
        _env_file=None,
    )
    sdk_client = client_class.return_value
    sdk_client.interactions.create.return_value.output_text = '{"priority":"medium"}'
    client = GeminiClient(settings)

    client.classify_request(incoming_request())
    client.classify_request(incoming_request())

    sleep_mock.assert_called_once_with(8.0)
    assert sdk_client.interactions.create.call_count == 2
    assert monotonic_mock.call_count == 3
