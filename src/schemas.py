"""Domain schemas for request triage and processing results."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class RequestCategory(StrEnum):
    """Supported categories for internal requests."""

    AUTOMATION = "автоматизація"
    INTEGRATION = "інтеграція"
    REPORTING_ANALYTICS = "звіт/аналітика"
    BUG_SUPPORT = "баг/підтримка"
    QUESTION_CONSULTATION = "питання/консультація"
    OUT_OF_SCOPE = "поза скоупом"


class Priority(StrEnum):
    """Business priority assigned to a request."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfidenceLevel(StrEnum):
    """Confidence in the classification result."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ValidationStatus(StrEnum):
    """Outcome of validating an LLM response."""

    VALID = "valid"
    REPAIRED = "repaired"
    FALLBACK = "fallback"


class SchemaModel(BaseModel):
    """Shared strict behavior for domain models."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
    )


class IncomingRequest(SchemaModel):
    """Raw request received from an input source."""

    id: str = Field(min_length=1, description="Source request identifier.")
    channel: str = Field(
        min_length=1,
        description="Channel where the request originated.",
    )
    timestamp: str = Field(
        description="Original timestamp value from the input source.",
    )
    raw_text: str = Field(
        min_length=1,
        description="Request text after edge-whitespace normalization.",
    )


class RequestClassification(SchemaModel):
    """Structured business classification produced for an incoming request."""

    category: RequestCategory
    target_department: str | None
    priority: Priority
    short_summary: str = Field(min_length=1)
    requested_actions: list[NonEmptyText]
    needs_clarification: bool
    clarifying_questions: list[NonEmptyText] = Field(
        default_factory=list,
        max_length=3,
    )
    confidence: ConfidenceLevel
    routing_recommendation: str | None = None
    scope_reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def discard_unneeded_questions(cls, data: object) -> object:
        """Discard clarification questions before field constraints are applied."""
        if not isinstance(data, dict) or data.get("needs_clarification") is not False:
            return data

        normalized_data = data.copy()
        normalized_data["clarifying_questions"] = []
        return normalized_data

    @field_validator(
        "target_department",
        "routing_recommendation",
        "scope_reason",
        mode="before",
    )
    @classmethod
    def empty_optional_text_to_none(cls, value: object) -> object:
        """Normalize blank optional text fields to null."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def normalize_scope_reason(self) -> Self:
        """Keep scope details consistent with the selected category."""
        if self.category is not RequestCategory.OUT_OF_SCOPE:
            self.scope_reason = None

        return self


class ProcessingMetadata(SchemaModel):
    """Technical metadata captured while processing a request."""

    model: str
    prompt_version: str
    processed_at: datetime
    validation_status: ValidationStatus
    retry_count: int = Field(default=0, ge=0)
    processing_error: str | None = None

    @field_validator("processed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Reject timestamps that cannot be mapped to an absolute instant."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("processed_at must include timezone information")
        return value


class ProcessedRequest(SchemaModel):
    """Complete request record prepared for future JSON output."""

    request: IncomingRequest
    classification: RequestClassification
    metadata: ProcessingMetadata


class ReviewQueueItem(SchemaModel):
    """Request data prepared for future manual review."""

    request_id: str
    raw_text: str
    review_reasons: list[NonEmptyText] = Field(min_length=1)
    clarifying_questions: list[NonEmptyText]
    confidence: ConfidenceLevel
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Reject timestamps that cannot be mapped to an absolute instant."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include timezone information")
        return value
