import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.artifact_generator import (
    ArtifactWriteError,
    build_report,
    build_review_queue,
    write_artifacts,
)
from src.schemas import (
    ConfidenceLevel,
    IncomingRequest,
    Priority,
    ProcessedRequest,
    ProcessingMetadata,
    RequestCategory,
    RequestClassification,
    ValidationStatus,
)


def processed_request(
    request_id: str,
    *,
    category: RequestCategory = RequestCategory.AUTOMATION,
    priority: Priority = Priority.MEDIUM,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    needs_clarification: bool = False,
    validation_status: ValidationStatus = ValidationStatus.VALID,
    department: str | None = "аналітика",
    summary: str = "Автоматизувати внутрішній звіт",
) -> ProcessedRequest:
    questions = ["Який очікуваний результат?"] if needs_clarification else []
    return ProcessedRequest(
        request=IncomingRequest(
            id=request_id,
            channel="email",
            timestamp="2026-06-25",
            raw_text=f"Український текст запиту {request_id}",
        ),
        classification=RequestClassification(
            category=category,
            target_department=department,
            priority=priority,
            short_summary=summary,
            requested_actions=["Опрацювати запит"],
            needs_clarification=needs_clarification,
            clarifying_questions=questions,
            confidence=confidence,
            routing_recommendation=(
                "Manual triage"
                if validation_status is ValidationStatus.FALLBACK
                else "AI automation backlog"
            ),
            scope_reason=(
                "Запит не стосується AI-юніту."
                if category is RequestCategory.OUT_OF_SCOPE
                else None
            ),
        ),
        metadata=ProcessingMetadata(
            model="test-model",
            prompt_version="v1",
            processed_at=datetime(2026, 6, 25, 12, 0, tzinfo=UTC),
            validation_status=validation_status,
            retry_count=(
                1
                if validation_status
                in {ValidationStatus.REPAIRED, ValidationStatus.FALLBACK}
                else 0
            ),
            processing_error=(
                "Safe fallback reason."
                if validation_status is ValidationStatus.FALLBACK
                else None
            ),
        ),
    )


def test_write_artifacts_creates_all_files_with_ordered_json(
    tmp_path: Path,
) -> None:
    requests = [
        processed_request("REQ-001"),
        processed_request(
            "REQ-002",
            validation_status=ValidationStatus.REPAIRED,
            summary="Перевірити український звіт",
        ),
    ]

    paths = write_artifacts(requests, tmp_path / "nested" / "output")

    assert paths.output_json.is_file()
    assert paths.report_markdown.is_file()
    assert paths.review_queue_json.is_file()

    output_text = paths.output_json.read_text(encoding="utf-8")
    output_data = json.loads(output_text)
    assert output_data["total_requests"] == 2
    assert [item["request"]["id"] for item in output_data["requests"]] == [
        "REQ-001",
        "REQ-002",
    ]
    assert "український" in output_text.lower()
    assert "\\u" not in output_text
    processed_at = datetime.fromisoformat(
        output_data["requests"][0]["metadata"]["processed_at"]
    )
    assert processed_at.utcoffset() is not None


def test_build_review_queue_applies_all_review_rules_without_duplicates() -> None:
    requests = [
        processed_request(
            "clarification",
            needs_clarification=True,
            confidence=ConfidenceLevel.MEDIUM,
        ),
        processed_request(
            "fallback",
            needs_clarification=True,
            confidence=ConfidenceLevel.LOW,
            validation_status=ValidationStatus.FALLBACK,
        ),
        processed_request(
            "ambiguous-scope",
            category=RequestCategory.OUT_OF_SCOPE,
            confidence=ConfidenceLevel.MEDIUM,
        ),
        processed_request(
            "clear-scope",
            category=RequestCategory.OUT_OF_SCOPE,
            confidence=ConfidenceLevel.HIGH,
        ),
    ]

    queue = build_review_queue(
        requests,
        created_at=datetime(2026, 6, 25, 12, 0, tzinfo=UTC),
    )

    assert [item.request_id for item in queue] == [
        "clarification",
        "fallback",
        "ambiguous-scope",
    ]
    fallback_item = next(item for item in queue if item.request_id == "fallback")
    assert len(fallback_item.review_reasons) == len(set(fallback_item.review_reasons))


def test_write_artifacts_writes_empty_review_queue(tmp_path: Path) -> None:
    paths = write_artifacts([processed_request("REQ-001")], tmp_path)

    assert json.loads(paths.review_queue_json.read_text(encoding="utf-8")) == []


def test_build_report_contains_required_sections_and_safe_values() -> None:
    requests = [
        processed_request(
            "REQ-HIGH",
            priority=Priority.HIGH,
            department=None,
            summary="Терміновий | звіт\nдля керівництва",
        ),
        processed_request(
            "REQ-FALLBACK",
            confidence=ConfidenceLevel.LOW,
            needs_clarification=True,
            validation_status=ValidationStatus.FALLBACK,
        ),
    ]

    report = build_report(requests)

    required_sections = [
        "# Звіт обробки AI-запитів",
        "## Загальний підсумок",
        "## Розподіл за категоріями",
        "## Розподіл за пріоритетами",
        "## Розподіл за відділами",
        "## Запити, що потребують уточнення",
        "## Високопріоритетні запити",
        "## Запити поза скоупом",
        "## Технічні зауваження",
    ]
    assert all(section in report for section in required_sections)
    assert all(category.value in report for category in RequestCategory)
    assert report.index("| high |") < report.index("| medium |")
    assert report.index("| medium |") < report.index("| low |")
    assert "Не визначено" in report
    assert "`REQ-HIGH`" in report
    assert "`REQ-FALLBACK`" in report
    assert "Терміновий \\| звіт для керівництва" in report
    assert "Safe fallback reason." not in report


def test_write_artifacts_wraps_os_error(tmp_path: Path) -> None:
    original_error = OSError("disk unavailable")

    with (
        patch.object(Path, "write_text", side_effect=original_error),
        pytest.raises(ArtifactWriteError) as raised_error,
    ):
        write_artifacts([processed_request("REQ-001")], tmp_path)

    assert raised_error.value.__cause__ is original_error
