"""Command-line entry point for the request triage service."""

import argparse
import sys
from pathlib import Path

from src.artifact_generator import ArtifactWriteError, write_artifacts
from src.config import Settings
from src.csv_reader import InputCsvError, load_requests
from src.gemini_client import GeminiClient, GeminiConfigurationError
from src.processor import RequestProcessor
from src.schemas import ValidationStatus


def main(argv: list[str] | None = None) -> int:
    """Run CSV processing and write the resulting artifacts."""
    parser = argparse.ArgumentParser(description="Process internal AI requests.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/input_requests.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
    )
    arguments = parser.parse_args(argv)

    try:
        requests = load_requests(arguments.input)
        gemini_client = GeminiClient(Settings())
        processed_requests = RequestProcessor(gemini_client).process_requests(requests)
        write_artifacts(processed_requests, arguments.output_dir)
    except (InputCsvError, GeminiConfigurationError, ArtifactWriteError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    valid_count = sum(
        request.metadata.validation_status is ValidationStatus.VALID
        for request in processed_requests
    )
    repaired_count = sum(
        request.metadata.validation_status is ValidationStatus.REPAIRED
        for request in processed_requests
    )
    fallback_count = sum(
        request.metadata.validation_status is ValidationStatus.FALLBACK
        for request in processed_requests
    )
    clarification_count = sum(
        request.classification.needs_clarification for request in processed_requests
    )

    print(f"Processed: {len(processed_requests)}")
    print(f"Valid results: {valid_count}")
    print(f"Repaired results: {repaired_count}")
    print(f"Fallback results: {fallback_count}")
    print(f"Needs clarification: {clarification_count}")
    print(f"Output directory: {arguments.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
