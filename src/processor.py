"""Orchestrate validation, repair, and fallback for Gemini classifications."""

from datetime import UTC, datetime

from pydantic import ValidationError

from src.gemini_client import (
    API_ERROR_CODE,
    EMPTY_OUTPUT_ERROR_CODE,
    RATE_LIMITED_ERROR_CODE,
    GeminiClient,
    GeminiClientError,
)
from src.prompt_builder import PROMPT_VERSION
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

MAX_REPAIR_ATTEMPTS = 1
INITIAL_ERROR_MESSAGES = {
    RATE_LIMITED_ERROR_CODE: (
        "Gemini rate limit or quota prevented the initial request."
    ),
    API_ERROR_CODE: "Gemini API error prevented the initial request.",
    EMPTY_OUTPUT_ERROR_CODE: "Gemini returned an empty initial response.",
}
REPAIR_ERROR_MESSAGES = {
    RATE_LIMITED_ERROR_CODE: (
        "Initial output was invalid and Gemini rate limit or quota prevented repair."
    ),
    API_ERROR_CODE: (
        "Initial output was invalid and Gemini API error prevented repair."
    ),
    EMPTY_OUTPUT_ERROR_CODE: (
        "Initial output was invalid and Gemini returned an empty repair response."
    ),
}


class RequestProcessor:
    """Validate Gemini output and provide one repair attempt or fallback."""

    def __init__(self, gemini_client: GeminiClient) -> None:
        self._gemini_client = gemini_client

    def process_request(self, request: IncomingRequest) -> ProcessedRequest:
        """Process one request into a validated classification and metadata."""
        try:
            raw_response = self._gemini_client.classify_request(request)
        except GeminiClientError as error:
            return self._build_fallback_result(
                request,
                retry_count=0,
                processing_error=INITIAL_ERROR_MESSAGES[error.code],
            )

        try:
            classification = RequestClassification.model_validate_json(raw_response)
        except ValidationError as validation_error:
            return self._repair_or_fallback(
                request,
                raw_response,
                validation_error,
            )

        return self._build_processed_result(
            request,
            classification,
            validation_status=ValidationStatus.VALID,
            retry_count=0,
        )

    def process_requests(
        self,
        requests: list[IncomingRequest],
    ) -> list[ProcessedRequest]:
        """Process requests sequentially while preserving their source order."""
        return [self.process_request(request) for request in requests]

    def _repair_or_fallback(
        self,
        request: IncomingRequest,
        invalid_response: str,
        validation_error: ValidationError,
    ) -> ProcessedRequest:
        try:
            repaired_response = self._gemini_client.repair_classification(
                request,
                invalid_response,
                validation_error,
            )
        except GeminiClientError as error:
            return self._build_fallback_result(
                request,
                retry_count=MAX_REPAIR_ATTEMPTS,
                processing_error=REPAIR_ERROR_MESSAGES[error.code],
            )

        try:
            classification = RequestClassification.model_validate_json(
                repaired_response
            )
        except ValidationError:
            return self._build_fallback_result(
                request,
                retry_count=MAX_REPAIR_ATTEMPTS,
                processing_error=(
                    "Initial output and repaired output failed validation."
                ),
            )

        return self._build_processed_result(
            request,
            classification,
            validation_status=ValidationStatus.REPAIRED,
            retry_count=MAX_REPAIR_ATTEMPTS,
        )

    def _build_processed_result(
        self,
        request: IncomingRequest,
        classification: RequestClassification,
        *,
        validation_status: ValidationStatus,
        retry_count: int,
        processing_error: str | None = None,
    ) -> ProcessedRequest:
        metadata = ProcessingMetadata(
            model=self._gemini_client.model_name,
            prompt_version=PROMPT_VERSION,
            processed_at=datetime.now(UTC),
            validation_status=validation_status,
            retry_count=retry_count,
            processing_error=processing_error,
        )
        return ProcessedRequest(
            request=request,
            classification=classification,
            metadata=metadata,
        )

    def _build_fallback_result(
        self,
        request: IncomingRequest,
        *,
        retry_count: int,
        processing_error: str,
    ) -> ProcessedRequest:
        classification = RequestClassification(
            category=RequestCategory.QUESTION_CONSULTATION,
            target_department=None,
            priority=Priority.MEDIUM,
            short_summary=(
                "Не вдалося надійно класифікувати запит; потрібна ручна перевірка."
            ),
            requested_actions=[],
            needs_clarification=True,
            clarifying_questions=["Яка мета запиту та який очікуваний результат?"],
            confidence=ConfidenceLevel.LOW,
            routing_recommendation="Manual triage",
            scope_reason=None,
        )
        return self._build_processed_result(
            request,
            classification,
            validation_status=ValidationStatus.FALLBACK,
            retry_count=retry_count,
            processing_error=processing_error,
        )
