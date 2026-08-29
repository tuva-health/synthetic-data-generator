"""Serialization for generated payer tables and private validation artifacts."""

from __future__ import annotations

import csv
import gzip
import io
import json
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from tuva_synthetic.model import OutputTable, Row, ValidationResult
from tuva_synthetic.validation import as_dict


def _serialize(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return value


def write_table(table: OutputTable, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{table.name.lower()}.csv.gz"
    with path.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gzip_handle:
            with io.TextIOWrapper(gzip_handle, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=table.columns, extrasaction="raise")
                writer.writeheader()
                for row in table.rows:
                    writer.writerow({column: _serialize(row.get(column)) for column in table.columns})
    return path


def write_tables(tables: Iterable[OutputTable], output_dir: Path) -> dict[str, Path]:
    return {table.name: write_table(table, output_dir) for table in tables}


def write_issue_manifest(rows: Iterable[Row], path: Path) -> Path:
    rows = tuple(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = (
        "issue_id", "dq_test_name", "domain", "payer", "setting",
        "person_id", "member_id",
        "claim_id", "original_claim_id", "line_number", "adjustment_sequence",
        "source_system", "source_table", "source_member_key_column",
        "source_member_key", "source_claim_key_column", "source_claim_key",
        "field", "original_value", "injected_value", "severity",
        "evaluation_phase", "expected_final_presence", "expected_failure_count",
        "collateral_tests", "tuva_core_dq_contract",
        "expected_connector_action", "pattern",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _serialize(row.get(column)) for column in columns})
    return path


def write_json(data: object, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, default=_serialize)
        handle.write("\n")
    return path


def write_validation_report(
    *,
    payer: str,
    summary: dict[str, object],
    results: Iterable[ValidationResult],
    row_counts: dict[str, int],
    path: Path,
) -> Path:
    return write_json({
        "payer": payer,
        "summary": summary,
        "row_counts": row_counts,
        "checks": [as_dict(result) for result in results],
        "passed": all(result.passed for result in results),
    }, path)
