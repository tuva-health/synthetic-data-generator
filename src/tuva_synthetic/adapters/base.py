"""Shared schema loading and row projection helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable

from tuva_synthetic.model import OutputTable, Row


Transform = Callable[[Row], Any]


def load_schema(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def columns_from_schema(schema: dict[str, Any]) -> tuple[str, ...]:
    return tuple(column["name"] for column in schema["columns"])


def project_rows(
    *,
    table_name: str,
    schema: dict[str, Any],
    source_rows: Iterable[Row],
    transforms: dict[str, Transform] | None = None,
) -> OutputTable:
    """Project canonical rows with explicit overrides and schema defaults."""

    transforms = transforms or {}
    columns = columns_from_schema(schema)
    defaults = {column["name"]: column.get("default") for column in schema["columns"]}
    canonical = {
        column["name"]: column.get("canonical") for column in schema["columns"]
    }
    output: list[Row] = []
    for source in source_rows:
        row: Row = {}
        for name in columns:
            if name in transforms:
                value = transforms[name](source)
            elif canonical[name]:
                value = source.get(canonical[name], defaults[name])
            else:
                value = defaults[name]
            row[name] = value
        output.append(row)
    return OutputTable(
        name=table_name,
        columns=columns,
        rows=tuple(output),
        column_metadata=tuple(schema["columns"]),
    )
