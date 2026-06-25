"""Synchronous Gemini client for structured request classification."""

from time import monotonic, sleep

from google import genai
from google.genai import errors
from google.genai._gaos.lib import compat_errors
from pydantic import ValidationError

from src.config import Settings
from src.prompt_builder import build_classification_prompt, build_repair_prompt
from src.schemas import IncomingRequest, RequestClassification

JSON_MIME_TYPE = "application/json"
CLASSIFICATION_TEMPERATURE = 0.1
API_ERROR_CODE = "api_error"
RATE_LIMITED_ERROR_CODE = "rate_limited"
EMPTY_OUTPUT_ERROR_CODE = "empty_output"


class GeminiConfigurationError(RuntimeError):
    """Raised when Gemini client settings are incomplete."""


class GeminiClientError(RuntimeError):
    """Raised when Gemini cannot return a usable structured response."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class GeminiClient:
    """Call Gemini for one structured request classification."""

    def __init__(self, settings: Settings) -> None:
        api_key = settings.gemini_api_key
        if api_key is None or not api_key.strip():
            raise GeminiConfigurationError(
                "GEMINI_API_KEY must be set to use the Gemini client."
            )

        normalized_api_key = api_key.strip()
        self._settings = settings
        self._min_request_interval_seconds = (
            settings.gemini_min_request_interval_seconds
        )
        self._last_request_started_at: float | None = None
        self._client = genai.Client(api_key=normalized_api_key)

    @property
    def model_name(self) -> str:
        """Return the configured Gemini model name."""
        return self._settings.gemini_model

    def classify_request(self, request: IncomingRequest) -> str:
        """Return the raw structured JSON text produced by Gemini."""
        prompt = build_classification_prompt(request)
        return self._generate_structured_response(prompt)

    def repair_classification(
        self,
        request: IncomingRequest,
        invalid_response: str,
        validation_error: ValidationError,
    ) -> str:
        """Return raw JSON text intended to repair an invalid response."""
        prompt = build_repair_prompt(request, invalid_response, validation_error)
        return self._generate_structured_response(prompt)

    def _generate_structured_response(self, prompt: str) -> str:
        """Send one structured-output request and return its raw text."""
        self._wait_for_request_slot()

        try:
            interaction = self._client.interactions.create(
                model=self.model_name,
                input=prompt,
                generation_config={"temperature": CLASSIFICATION_TEMPERATURE},
                response_format={
                    "type": "text",
                    "mime_type": JSON_MIME_TYPE,
                    "schema": RequestClassification.model_json_schema(),
                },
            )
        # Interactions API uses compat APIError subclasses for quota and transport
        # failures in google-genai 2.10.0, including RateLimitError.
        except (errors.APIError, compat_errors.APIError) as error:
            error_code = (
                RATE_LIMITED_ERROR_CODE if _is_rate_limited(error) else API_ERROR_CODE
            )
            raise GeminiClientError(
                "Gemini API request failed while generating a structured response.",
                code=error_code,
            ) from error

        output_text = interaction.output_text
        if output_text is None or not output_text.strip():
            raise GeminiClientError(
                "Gemini returned an empty structured response.",
                code=EMPTY_OUTPUT_ERROR_CODE,
            )

        return output_text

    def _wait_for_request_slot(self) -> None:
        """Wait until the configured minimum interval has elapsed."""
        if self._last_request_started_at is not None:
            elapsed = monotonic() - self._last_request_started_at
            remaining = self._min_request_interval_seconds - elapsed
            if remaining > 0:
                sleep(remaining)

        self._last_request_started_at = monotonic()


def _is_rate_limited(
    error: errors.APIError | compat_errors.APIError,
) -> bool:
    if isinstance(error, compat_errors.RateLimitError):
        return True
    if isinstance(error, errors.APIError):
        return error.code == 429
    if isinstance(error, compat_errors.APIStatusError):
        return error.status_code == 429
    return False
