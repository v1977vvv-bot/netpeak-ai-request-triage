from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.schemas import (
    IncomingRequest,
    ProcessingMetadata,
    RequestClassification,
    ReviewQueueItem,
)


def classification_data() -> dict[str, object]:
    return {
        "category": "автоматизація",
        "target_department": "AI Unit",
        "priority": "medium",
        "short_summary": "Автоматизувати внутрішній процес",
        "requested_actions": ["Оцінити процес"],
        "needs_clarification": True,
        "clarifying_questions": ["Який очікуваний результат?"],
        "confidence": "high",
    }


def test_incoming_request_rejects_empty_raw_text() -> None:
    with pytest.raises(ValidationError):
        IncomingRequest(
            id="request-1",
            channel="email",
            timestamp="2026-01-15 10:30",
            raw_text="   ",
        )


def test_incoming_request_strips_string_fields() -> None:
    request = IncomingRequest(
        id="  request-1  ",
        channel="  email  ",
        timestamp="  2026-01-15 10:30  ",
        raw_text="  Потрібна автоматизація  ",
    )

    assert request.id == "request-1"
    assert request.channel == "email"
    assert request.timestamp == "2026-01-15 10:30"
    assert request.raw_text == "Потрібна автоматизація"


def test_request_classification_rejects_unknown_category() -> None:
    data = classification_data()
    data["category"] = "невідома категорія"

    with pytest.raises(ValidationError):
        RequestClassification.model_validate(data)


def test_request_classification_clears_unneeded_questions() -> None:
    data = classification_data()
    data["needs_clarification"] = False

    classification = RequestClassification.model_validate(data)

    assert classification.clarifying_questions == []


def test_unneeded_questions_bypass_maximum_length_validation() -> None:
    data = classification_data()
    data["needs_clarification"] = False
    data["clarifying_questions"] = ["Питання 1", "Питання 2", "Питання 3", "Питання 4"]

    classification = RequestClassification.model_validate(data)

    assert classification.clarifying_questions == []
    assert data["clarifying_questions"] == [
        "Питання 1",
        "Питання 2",
        "Питання 3",
        "Питання 4",
    ]


def test_request_classification_rejects_more_than_three_questions() -> None:
    data = classification_data()
    data["clarifying_questions"] = ["Питання 1", "Питання 2", "Питання 3", "Питання 4"]

    with pytest.raises(ValidationError):
        RequestClassification.model_validate(data)


def test_request_classification_clears_scope_reason_for_in_scope_category() -> None:
    data = classification_data()
    data["scope_reason"] = "Не має залишитися"

    classification = RequestClassification.model_validate(data)

    assert classification.scope_reason is None


def test_request_classification_normalizes_blank_optional_text() -> None:
    data = classification_data()
    data["target_department"] = "   "
    data["routing_recommendation"] = "   "
    data["scope_reason"] = "   "

    classification = RequestClassification.model_validate(data)

    assert classification.target_department is None
    assert classification.routing_recommendation is None
    assert classification.scope_reason is None


def test_out_of_scope_classification_preserves_scope_reason() -> None:
    data = classification_data()
    data["category"] = "поза скоупом"
    data["scope_reason"] = "Запит не належить до компетенції AI-юніту"

    classification = RequestClassification.model_validate(data)

    assert classification.scope_reason == "Запит не належить до компетенції AI-юніту"


def test_processing_metadata_rejects_negative_retry_count() -> None:
    with pytest.raises(ValidationError):
        ProcessingMetadata(
            model="gemini-2.5-flash",
            prompt_version="1.0",
            processed_at=datetime.now(UTC),
            validation_status="valid",
            retry_count=-1,
        )


def test_processing_metadata_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        ProcessingMetadata(
            model="gemini-2.5-flash",
            prompt_version="1.0",
            processed_at=datetime(2026, 1, 15, 10, 30),
            validation_status="valid",
        )


def test_review_queue_item_rejects_empty_review_reasons() -> None:
    with pytest.raises(ValidationError):
        ReviewQueueItem(
            request_id="request-1",
            raw_text="Потрібна додаткова перевірка",
            review_reasons=[],
            clarifying_questions=[],
            confidence="low",
            created_at=datetime.now(UTC),
        )
