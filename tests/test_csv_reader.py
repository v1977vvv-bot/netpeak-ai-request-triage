from pathlib import Path

import pytest

from src.csv_reader import InputCsvError, load_requests
from src.schemas import IncomingRequest

HEADER = "id,channel,timestamp,raw_text\n"


def write_csv(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    path.write_text(content, encoding=encoding, newline="")


def test_load_requests_returns_valid_models_in_source_order(tmp_path: Path) -> None:
    csv_path = tmp_path / "requests.csv"
    write_csv(
        csv_path,
        HEADER
        + 'request-1,email,2026-01-15 10:30,"  Перший запит  "\n'
        + "request-2,chat,2026-01-15 11:00,Другий запит\n",
    )

    requests = load_requests(csv_path)

    assert all(isinstance(request, IncomingRequest) for request in requests)
    assert [request.id for request in requests] == ["request-1", "request-2"]
    assert requests[0].raw_text == "Перший запит"


def test_load_requests_ignores_additional_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "requests.csv"
    write_csv(
        csv_path,
        "id,channel,timestamp,raw_text,author\n"
        "request-1,email,2026-01-15,Потрібна допомога,Olena\n",
    )

    request = load_requests(csv_path)[0]

    assert request.id == "request-1"
    assert "author" not in request.model_fields_set


def test_load_requests_returns_empty_list_for_header_only_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "requests.csv"
    write_csv(csv_path, HEADER)

    assert load_requests(csv_path) == []


def test_load_requests_rejects_missing_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "missing.csv"

    with pytest.raises(InputCsvError, match=r"missing\.csv"):
        load_requests(csv_path)


def test_load_requests_rejects_directory_path(tmp_path: Path) -> None:
    with pytest.raises(InputCsvError, match="not a file"):
        load_requests(tmp_path)


def test_load_requests_rejects_file_without_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    write_csv(csv_path, "")

    with pytest.raises(InputCsvError, match="no header"):
        load_requests(csv_path)


def test_load_requests_reports_missing_required_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "requests.csv"
    write_csv(csv_path, "id,channel,timestamp\nrequest-1,email,2026-01-15\n")

    with pytest.raises(InputCsvError, match="raw_text"):
        load_requests(csv_path)


def test_load_requests_reports_invalid_record_context(tmp_path: Path) -> None:
    csv_path = tmp_path / "requests.csv"
    write_csv(csv_path, HEADER + "request-7,email,2026-01-15,   \n")

    with pytest.raises(InputCsvError) as error:
        load_requests(csv_path)

    message = str(error.value)
    assert "line 2" in message
    assert "request-7" in message
    assert "raw_text" in message


def test_load_requests_rejects_row_with_missing_value(tmp_path: Path) -> None:
    csv_path = tmp_path / "requests.csv"
    write_csv(csv_path, HEADER + "request-1,email,2026-01-15\n")

    with pytest.raises(InputCsvError) as error:
        load_requests(csv_path)

    assert "line 2" in str(error.value)
    assert "request-1" in str(error.value)


def test_load_requests_reads_utf8_bom(tmp_path: Path) -> None:
    csv_path = tmp_path / "requests.csv"
    write_csv(
        csv_path,
        HEADER + "request-1,email,2026-01-15,Текст запиту\n",
        encoding="utf-8-sig",
    )

    requests = load_requests(csv_path)

    assert [request.id for request in requests] == ["request-1"]


def test_load_requests_reports_malformed_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "requests.csv"
    write_csv(csv_path, HEADER + 'request-1,email,2026-01-15,"Незакритий текст\n')

    with pytest.raises(InputCsvError) as error:
        load_requests(csv_path)

    message = str(error.value)
    assert "Malformed CSV" in message
    assert "line" in message


def test_load_requests_reports_invalid_utf8(tmp_path: Path) -> None:
    csv_path = tmp_path / "requests.csv"
    csv_path.write_bytes(b"\xff\xfe\x00\x00")

    with pytest.raises(InputCsvError, match="not valid UTF-8"):
        load_requests(csv_path)
