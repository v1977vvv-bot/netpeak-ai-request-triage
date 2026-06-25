"""Generate JSON and Markdown artifacts from processed requests."""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.schemas import (
    ConfidenceLevel,
    Priority,
    ProcessedRequest,
    RequestCategory,
    ReviewQueueItem,
    ValidationStatus,
)

OUTPUT_JSON_FILENAME = "output.json"
REPORT_FILENAME = "report.md"
REVIEW_QUEUE_FILENAME = "review_queue.json"


@dataclass(frozen=True)
class ArtifactPaths:
    """Paths of artifacts created during one processing run."""

    output_json: Path
    report_markdown: Path
    review_queue_json: Path


class ArtifactWriteError(RuntimeError):
    """Raised when output artifacts cannot be written."""


def build_review_queue(
    processed_requests: list[ProcessedRequest],
    *,
    created_at: datetime,
) -> list[ReviewQueueItem]:
    """Build ordered manual-review items from processed requests."""
    review_queue: list[ReviewQueueItem] = []

    for processed_request in processed_requests:
        classification = processed_request.classification
        reasons: list[str] = []

        if classification.needs_clarification:
            reasons.append("Запит потребує уточнення.")
        if classification.confidence is ConfidenceLevel.LOW:
            reasons.append("Низька впевненість класифікації.")
        if processed_request.metadata.validation_status is ValidationStatus.FALLBACK:
            reasons.append(
                "Застосовано fallback після помилки або невалідної відповіді LLM."
            )
        if (
            classification.category is RequestCategory.OUT_OF_SCOPE
            and classification.confidence is not ConfidenceLevel.HIGH
        ):
            reasons.append("Запит поза скоупом має неоднозначну класифікацію.")

        if reasons:
            review_queue.append(
                ReviewQueueItem(
                    request_id=processed_request.request.id,
                    raw_text=processed_request.request.raw_text,
                    review_reasons=reasons,
                    clarifying_questions=classification.clarifying_questions,
                    confidence=classification.confidence,
                    created_at=created_at,
                )
            )

    return review_queue


def build_report(processed_requests: list[ProcessedRequest]) -> str:
    """Build an aggregated Ukrainian Markdown report."""
    status_counts = Counter(
        request.metadata.validation_status for request in processed_requests
    )
    clarification_count = sum(
        request.classification.needs_clarification for request in processed_requests
    )

    category_counts = Counter(
        request.classification.category for request in processed_requests
    )
    priority_counts = Counter(
        request.classification.priority for request in processed_requests
    )
    department_counts = Counter(
        request.classification.target_department for request in processed_requests
    )

    clarification_requests = [
        request
        for request in processed_requests
        if request.classification.needs_clarification
    ]
    high_priority_requests = [
        request
        for request in processed_requests
        if request.classification.priority is Priority.HIGH
    ]
    out_of_scope_requests = [
        request
        for request in processed_requests
        if request.classification.category is RequestCategory.OUT_OF_SCOPE
    ]
    fallback_requests = [
        request
        for request in processed_requests
        if request.metadata.validation_status is ValidationStatus.FALLBACK
    ]

    lines = [
        "# Звіт обробки AI-запитів",
        "",
        "## Загальний підсумок",
        "",
        f"- Усього запитів: {len(processed_requests)}",
        f"- Валідних результатів: {status_counts[ValidationStatus.VALID]}",
        f"- Виправлених результатів: {status_counts[ValidationStatus.REPAIRED]}",
        f"- Fallback-результатів: {status_counts[ValidationStatus.FALLBACK]}",
        f"- Потребують уточнення: {clarification_count}",
        "",
        "## Розподіл за категоріями",
        "",
        "| Значення | Кількість |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {_escape_markdown(category.value)} | {category_counts[category]} |"
        for category in RequestCategory
    )

    lines.extend(
        [
            "",
            "## Розподіл за пріоритетами",
            "",
            "| Значення | Кількість |",
            "|---|---:|",
        ]
    )
    lines.extend(
        f"| {priority.value} | {priority_counts[priority]} |"
        for priority in (Priority.HIGH, Priority.MEDIUM, Priority.LOW)
    )

    lines.extend(
        [
            "",
            "## Розподіл за відділами",
            "",
            "| Значення | Кількість |",
            "|---|---:|",
        ]
    )
    named_departments = sorted(
        department for department in department_counts if department is not None
    )
    lines.extend(
        f"| {_escape_markdown(department)} | {department_counts[department]} |"
        for department in named_departments
    )
    if None in department_counts or not processed_requests:
        lines.append(f"| Не визначено | {department_counts[None]} |")

    lines.extend(["", "## Запити, що потребують уточнення", ""])
    lines.extend(_build_request_list(clarification_requests, include_questions=True))

    lines.extend(["", "## Високопріоритетні запити", ""])
    lines.extend(_build_request_list(high_priority_requests, include_questions=True))

    lines.extend(["", "## Запити поза скоупом", ""])
    lines.extend(_build_request_list(out_of_scope_requests, include_questions=True))

    lines.extend(["", "## Технічні зауваження", ""])
    if fallback_requests:
        lines.append("Fallback застосовано для запитів:")
        lines.extend(f"- `{request.request.id}`" for request in fallback_requests)
    else:
        lines.append("Fallback не застосовувався.")

    return "\n".join(lines) + "\n"


def write_artifacts(
    processed_requests: list[ProcessedRequest],
    output_dir: Path | str,
) -> ArtifactPaths:
    """Write all processing artifacts and return their paths."""
    directory = Path(output_dir)
    paths = ArtifactPaths(
        output_json=directory / OUTPUT_JSON_FILENAME,
        report_markdown=directory / REPORT_FILENAME,
        review_queue_json=directory / REVIEW_QUEUE_FILENAME,
    )
    generated_at = datetime.now(UTC)
    output_payload = {
        "generated_at": generated_at.isoformat(),
        "total_requests": len(processed_requests),
        "requests": [request.model_dump(mode="json") for request in processed_requests],
    }
    review_queue = build_review_queue(
        processed_requests,
        created_at=generated_at,
    )

    try:
        directory.mkdir(parents=True, exist_ok=True)
        paths.output_json.write_text(
            json.dumps(output_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.report_markdown.write_text(
            build_report(processed_requests),
            encoding="utf-8",
        )
        paths.review_queue_json.write_text(
            json.dumps(
                [item.model_dump(mode="json") for item in review_queue],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as error:
        raise ArtifactWriteError(
            f"Could not write output artifacts to {directory}: {error}"
        ) from error

    return paths


def _build_request_list(
    processed_requests: list[ProcessedRequest],
    *,
    include_questions: bool = False,
) -> list[str]:
    if not processed_requests:
        return ["Немає."]

    lines: list[str] = []
    for processed_request in processed_requests:
        classification = processed_request.classification
        lines.append(
            f"- `{processed_request.request.id}` — "
            f"{_escape_markdown(classification.short_summary)}"
        )
        if include_questions:
            for question in classification.clarifying_questions:
                lines.append(f"  - Уточнення: {_escape_markdown(question)}")
    return lines


def _escape_markdown(value: str) -> str:
    normalized = " ".join(value.split())
    return normalized.replace("|", r"\|")
