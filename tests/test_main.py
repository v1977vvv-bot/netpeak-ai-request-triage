from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.artifact_generator import ArtifactPaths, ArtifactWriteError
from src.csv_reader import InputCsvError
from src.gemini_client import GeminiConfigurationError
from src.main import main
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


def incoming_request(request_id: str) -> IncomingRequest:
    return IncomingRequest(
        id=request_id,
        channel="email",
        timestamp="2026-06-25",
        raw_text=f"Запит {request_id}",
    )


def processed_request(
    request_id: str,
    status: ValidationStatus,
    *,
    needs_clarification: bool = False,
) -> ProcessedRequest:
    return ProcessedRequest(
        request=incoming_request(request_id),
        classification=RequestClassification(
            category=RequestCategory.AUTOMATION,
            target_department=None,
            priority=Priority.MEDIUM,
            short_summary=f"Результат {request_id}",
            requested_actions=[],
            needs_clarification=needs_clarification,
            clarifying_questions=(
                ["Що потрібно уточнити?"] if needs_clarification else []
            ),
            confidence=(
                ConfidenceLevel.LOW if needs_clarification else ConfidenceLevel.HIGH
            ),
            routing_recommendation=None,
        ),
        metadata=ProcessingMetadata(
            model="test-model",
            prompt_version="v1",
            processed_at=datetime.now(UTC),
            validation_status=status,
            retry_count=0 if status is ValidationStatus.VALID else 1,
            processing_error=(
                "Fallback reason." if status is ValidationStatus.FALLBACK else None
            ),
        ),
    )


@patch("src.main.write_artifacts")
@patch("src.main.RequestProcessor")
@patch("src.main.GeminiClient")
@patch("src.main.Settings")
@patch("src.main.load_requests")
def test_main_success(
    load_requests: MagicMock,
    settings_class: MagicMock,
    gemini_client_class: MagicMock,
    processor_class: MagicMock,
    write_artifacts: MagicMock,
    capsys,
) -> None:
    source_requests = [
        incoming_request("REQ-001"),
        incoming_request("REQ-002"),
        incoming_request("REQ-003"),
    ]
    results = [
        processed_request("REQ-001", ValidationStatus.VALID),
        processed_request("REQ-002", ValidationStatus.REPAIRED),
        processed_request(
            "REQ-003",
            ValidationStatus.FALLBACK,
            needs_clarification=True,
        ),
    ]
    load_requests.return_value = source_requests
    processor_class.return_value.process_requests.return_value = results
    write_artifacts.return_value = ArtifactPaths(
        output_json=Path("custom-output/output.json"),
        report_markdown=Path("custom-output/report.md"),
        review_queue_json=Path("custom-output/review_queue.json"),
    )

    exit_code = main(["--input", "custom.csv", "--output-dir", "custom-output"])

    assert exit_code == 0
    load_requests.assert_called_once_with(Path("custom.csv"))
    gemini_client_class.assert_called_once_with(settings_class.return_value)
    processor_class.assert_called_once_with(gemini_client_class.return_value)
    processor_class.return_value.process_requests.assert_called_once_with(
        source_requests
    )
    write_artifacts.assert_called_once_with(results, Path("custom-output"))
    output = capsys.readouterr().out
    assert "Processed: 3" in output
    assert "Valid results: 1" in output
    assert "Repaired results: 1" in output
    assert "Fallback results: 1" in output
    assert "Needs clarification: 1" in output
    assert "Output directory: custom-output" in output


@patch("src.main.GeminiClient")
@patch("src.main.load_requests")
def test_main_handles_input_csv_error(
    load_requests: MagicMock,
    gemini_client_class: MagicMock,
    capsys,
) -> None:
    load_requests.side_effect = InputCsvError("invalid CSV")

    exit_code = main([])

    assert exit_code == 1
    assert "invalid CSV" in capsys.readouterr().err
    gemini_client_class.assert_not_called()


@patch("src.main.GeminiClient")
@patch("src.main.Settings")
@patch("src.main.load_requests")
def test_main_handles_configuration_error(
    load_requests: MagicMock,
    settings_class: MagicMock,
    gemini_client_class: MagicMock,
    capsys,
) -> None:
    load_requests.return_value = [incoming_request("REQ-001")]
    gemini_client_class.side_effect = GeminiConfigurationError("missing key")

    exit_code = main([])

    assert exit_code == 1
    assert "missing key" in capsys.readouterr().err
    gemini_client_class.assert_called_once_with(settings_class.return_value)


@patch("src.main.write_artifacts")
@patch("src.main.RequestProcessor")
@patch("src.main.GeminiClient")
@patch("src.main.Settings")
@patch("src.main.load_requests")
def test_main_handles_artifact_write_error(
    load_requests: MagicMock,
    settings_class: MagicMock,
    gemini_client_class: MagicMock,
    processor_class: MagicMock,
    write_artifacts: MagicMock,
    capsys,
) -> None:
    requests = [incoming_request("REQ-001")]
    results = [processed_request("REQ-001", ValidationStatus.VALID)]
    load_requests.return_value = requests
    processor_class.return_value.process_requests.return_value = results
    write_artifacts.side_effect = ArtifactWriteError("cannot write output")

    exit_code = main([])

    assert exit_code == 1
    assert "cannot write output" in capsys.readouterr().err
    gemini_client_class.assert_called_once_with(settings_class.return_value)
