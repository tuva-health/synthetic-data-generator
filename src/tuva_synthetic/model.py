"""Canonical records shared by all payer adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


Row = dict[str, Any]


@dataclass(frozen=True)
class CanonicalDataset:
    """A coherent longitudinal cohort before payer-specific projection."""

    members: tuple[Row, ...]
    enrollment_months: tuple[Row, ...]
    providers: tuple[Row, ...]
    facilities: tuple[Row, ...]
    medical_claim_lines: tuple[Row, ...]
    pharmacy_claims: tuple[Row, ...]
    start_date: date
    end_date: date
    seed: int


@dataclass(frozen=True)
class OutputTable:
    """One ordered payer-shaped table ready for deterministic serialization."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    column_metadata: tuple[Row, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    check: str
    passed: bool
    observed: Any
    expected: str
