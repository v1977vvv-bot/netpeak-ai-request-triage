from unittest.mock import MagicMock

from src.gemini_client import (
    EMPTY_OUTPUT_ERROR_CODE,
    RATE_LIMITED_ERROR_CODE,
    GeminiClient,
    GeminiClientError,
)
from src.processor import RequestProcessor
from src.schemas import (
    ConfidenceLevel,
    IncomingRequest,
    Priority,
    RequestCategory,
    RequestClassification,
    ValidationStatus,
)


def incoming_request(request_id: str = "request-1") -> IncomingRequest:
    return IncomingRequest(
        id=request_id,
        channel="email",
        timestamp="2026-06-25",
        raw_text="Потрібно автоматизувати звіт",
    )


def valid_classification(summary: str = "Автоматизувати звіт") -> str:
    return RequestClassification(
        category=RequestCategory.AUTOMATION,
        target_department="аналітика",
        priority=Priority.MEDIUM,
        short_summary=summary,
        requested_actions=["Автоматизувати формування звіту"],
        needs_clarification=False,
        confidence=ConfidenceLevel.HIGH,
        routing_recommendation="AI automation backlog",
    ).model_dump_json()


def gemini_client_mock() -> MagicMock:
    client = MagicMock(spec=GeminiClient)
    client.model_name = "test-model"
    return client


def test_process_request_accepts_valid_first_response() -> None:
    client = gemini_client_mock()
    client.classify_request.return_value = valid_classification()

    result = RequestProcessor(client).process_request(incoming_request())

    client.repair_classification.assert_not_called()
    assert result.metadata.validation_status is ValidationStatus.VALID
    assert result.metadata.retry_count == 0
    assert result.metadata.processing_error is None
    assert result.metadata.processed_at.utcoffset() is not None


def test_process_request_uses_one_successful_repair() -> None:
    client = gemini_client_mock()
    client.classify_request.return_value = '{"category":"unknown"}'
    client.repair_classification.return_value = valid_classification()

    result = RequestProcessor(client).process_request(incoming_request())

    assert result.metadata.validation_status is ValidationStatus.REPAIRED
    assert result.metadata.retry_count == 1
    assert result.metadata.processing_error is None
    client.repair_classification.assert_called_once()


def test_process_request_returns_fallback_after_invalid_repair() -> None:
    client = gemini_client_mock()
    client.classify_request.return_value = '{"category":"unknown"}'
    client.repair_classification.return_value = "not-json"

    result = RequestProcessor(client).process_request(incoming_request())

    assert result.metadata.validation_status is ValidationStatus.FALLBACK
    assert result.metadata.retry_count == 1
    assert result.classification.needs_clarification is True
    assert result.classification.confidence is ConfidenceLevel.LOW
    assert result.classification.routing_recommendation == "Manual triage"
    client.repair_classification.assert_called_once()


def test_process_request_returns_fallback_on_initial_client_error() -> None:
    client = gemini_client_mock()
    client.classify_request.side_effect = GeminiClientError(
        "API failed",
        code=RATE_LIMITED_ERROR_CODE,
    )

    result = RequestProcessor(client).process_request(incoming_request())

    client.repair_classification.assert_not_called()
    assert result.metadata.validation_status is ValidationStatus.FALLBACK
    assert result.metadata.retry_count == 0
    assert result.metadata.processing_error == (
        "Gemini rate limit or quota prevented the initial request."
    )


def test_process_request_returns_fallback_on_repair_client_error() -> None:
    client = gemini_client_mock()
    client.classify_request.return_value = '{"category":"unknown"}'
    client.repair_classification.side_effect = GeminiClientError(
        "Empty output",
        code=EMPTY_OUTPUT_ERROR_CODE,
    )

    result = RequestProcessor(client).process_request(incoming_request())

    assert result.metadata.validation_status is ValidationStatus.FALLBACK
    assert result.metadata.retry_count == 1
    assert result.metadata.processing_error == (
        "Initial output was invalid and Gemini returned an empty repair response."
    )


def test_process_requests_preserves_order() -> None:
    client = gemini_client_mock()
    client.classify_request.side_effect = [
        valid_classification("Перший результат"),
        valid_classification("Другий результат"),
    ]
    requests = [incoming_request("request-1"), incoming_request("request-2")]

    results = RequestProcessor(client).process_requests(requests)

    assert [result.request.id for result in results] == ["request-1", "request-2"]
