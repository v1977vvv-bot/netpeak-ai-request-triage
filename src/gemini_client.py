"""Synchronous Gemini client for structured request classification."""

from google import genai
from google.genai import errors

from src.config import Settings
from src.prompt_builder import build_classification_prompt
from src.schemas import IncomingRequest, RequestClassification

JSON_MIME_TYPE = "application/json"
CLASSIFICATION_TEMPERATURE = 0.1


class GeminiConfigurationError(RuntimeError):
    """Raised when Gemini client settings are incomplete."""


class GeminiClientError(RuntimeError):
    """Raised when Gemini cannot return a usable structured response."""


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
        self._client = genai.Client(api_key=normalized_api_key)

    def classify_request(self, request: IncomingRequest) -> str:
        """Return the raw structured JSON text produced by Gemini."""
        prompt = build_classification_prompt(request)

        try:
            interaction = self._client.interactions.create(
                model=self._settings.gemini_model,
                input=prompt,
                generation_config={"temperature": CLASSIFICATION_TEMPERATURE},
                response_format={
                    "type": "text",
                    "mime_type": JSON_MIME_TYPE,
                    "schema": RequestClassification.model_json_schema(),
                },
            )
        # APIError is the stable public SDK exception; internal transports vary.
        except errors.APIError as error:
            raise GeminiClientError(
                "Gemini API request failed while classifying the request."
            ) from error

        output_text = interaction.output_text
        if output_text is None or not output_text.strip():
            raise GeminiClientError("Gemini returned an empty structured response.")

        return output_text
