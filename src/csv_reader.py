"""Read and validate incoming requests from CSV files."""

import csv
from pathlib import Path

from pydantic import ValidationError

from src.schemas import IncomingRequest

REQUIRED_COLUMNS: frozenset[str] = frozenset({"id", "channel", "timestamp", "raw_text"})


class InputCsvError(ValueError):
    """Raised when the request CSV cannot be safely read or validated."""


def load_requests(csv_path: Path | str) -> list[IncomingRequest]:
    """Load validated requests from a UTF-8 CSV file in source order."""
    path = Path(csv_path)

    if not path.exists():
        raise InputCsvError(f"CSV file does not exist: {path}")
    if not path.is_file():
        raise InputCsvError(f"CSV path is not a file: {path}")

    requests: list[IncomingRequest] = []
    reader: csv.DictReader | None = None

    try:
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file, strict=True)
            fieldnames = reader.fieldnames

            if fieldnames is None:
                raise InputCsvError(f"CSV file has no header: {path}")

            missing_columns = REQUIRED_COLUMNS.difference(fieldnames)
            if missing_columns:
                missing = ", ".join(sorted(missing_columns))
                raise InputCsvError(
                    f"CSV file {path} is missing required columns: {missing}"
                )

            for row in reader:
                request_id = row.get("id")
                request_context = (
                    f", request id {request_id!r}"
                    if isinstance(request_id, str)
                    else ""
                )
                request_data = {column: row.get(column) for column in REQUIRED_COLUMNS}

                try:
                    requests.append(IncomingRequest.model_validate(request_data))
                except ValidationError as error:
                    raise InputCsvError(
                        f"Invalid record in {path} at CSV line {reader.line_num}"
                        f"{request_context}: {error}"
                    ) from error
    except UnicodeDecodeError as error:
        raise InputCsvError(f"CSV file is not valid UTF-8: {path}: {error}") from error
    except csv.Error as error:
        if reader is not None:
            raise InputCsvError(
                f"Malformed CSV file {path} at CSV line {reader.line_num}: {error}"
            ) from error
        raise InputCsvError(f"Malformed CSV file {path}: {error}") from error
    except OSError as error:
        raise InputCsvError(f"Could not read CSV file {path}: {error}") from error

    return requests
