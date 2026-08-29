"""End-to-end payer generation pipeline."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from tuva_synthetic.generation import GenerationConfig, generate_canonical
from tuva_synthetic.issues import IssueManifest, inject_connector_eval_issues
from tuva_synthetic.model import CanonicalDataset, OutputTable, ValidationResult
from tuva_synthetic.validation import failures, validate_canonical, validate_output_tables


SEED_OFFSET = {"aetna": 101, "priority_health": 211, "hcci": 307}


@dataclass(frozen=True)
class GeneratedPayerDataset:
    payer: str
    canonical: CanonicalDataset
    issue_manifest: IssueManifest
    tables: tuple[OutputTable, ...]
    validations: tuple[ValidationResult, ...]


def _adapt(payer: str, dataset: CanonicalDataset, schema_root: Path) -> dict[str, OutputTable]:
    if payer == "aetna":
        from tuva_synthetic.adapters.aetna import adapt
    elif payer == "priority_health":
        from tuva_synthetic.adapters.priority_health import adapt
    elif payer == "hcci":
        from tuva_synthetic.adapters.hcci import adapt
    else:
        raise ValueError(f"Unknown payer: {payer}")
    return adapt(dataset, schema_root)


def _source_locators(payer: str, manifest: IssueManifest) -> IssueManifest:
    table_by_domain = {
        "aetna": {
            "medical_claim": "universal_medical_dental",
            "pharmacy_claim": "universal_pharmacy",
            "eligibility": "universal_medical_eligibility",
        },
        "priority_health": {
            "medical_claim": "medical_claims",
            "pharmacy_claim": "pharmacy_claims",
            "eligibility": "eligibility",
        },
        "hcci": {
            "pharmacy_claim": "pharmacy_claims",
            "eligibility": "member_enrollment",
        },
    }
    output: list[dict[str, object]] = []
    claim_key_columns = {
        ("aetna", "medical_claim"): "src_clm_id",
        ("aetna", "pharmacy_claim"): "rx_claim_id",
        ("priority_health", "medical_claim"): "APCD_PYR_CLAIM_CNTRL_NUM",
        ("priority_health", "pharmacy_claim"): "APCD_Payer_Claim_Control_Number",
        ("hcci", "medical_claim"): "Z_CLMID",
        ("hcci", "pharmacy_claim"): "Z_CLMID",
    }
    member_key_columns = {
        ("aetna", "eligibility"): "member_id",
        ("priority_health", "eligibility"): "APCD_MBR_PAT_ID",
        ("hcci", "eligibility"): "Z_PATID",
    }
    for item in manifest:
        row = copy.deepcopy(item)
        domain = str(row.get("domain"))
        if payer == "hcci" and domain == "medical_claim":
            setting = row.get("setting")
            row["source_table"] = (
                "medical_claims_inpatient"
                if setting == "inpatient"
                else "medical_claims_physician"
                if setting == "professional"
                else "medical_claims_outpatient"
            )
        else:
            row["source_table"] = table_by_domain[payer].get(domain)
        row["source_claim_key_column"] = claim_key_columns.get((payer, domain))
        row["source_member_key_column"] = member_key_columns.get((payer, domain))
        if payer == "hcci":
            from tuva_synthetic.adapters.hcci import _claim_hash, _member_hash

            row["source_member_key"] = _member_hash(row)
            row["source_claim_key"] = (
                _claim_hash(row) if domain in {"medical_claim", "pharmacy_claim"} else None
            )
        else:
            row["source_member_key"] = row.get("member_id")
            row["source_claim_key"] = row.get("claim_id")
        output.append(row)
    return tuple(output)


def _validate_manifest_locators(
    manifest: IssueManifest,
    tables: tuple[OutputTable, ...],
) -> ValidationResult:
    tables_by_name = {table.name: table for table in tables}
    requested = {
        (str(row.get("source_table")), str(column))
        for row in manifest
        for column in (
            row.get("source_claim_key_column"),
            row.get("source_member_key_column"),
        )
        if column
    }
    indexes: dict[tuple[str, str], set[object]] = {}
    for table_name, column in requested:
        table = tables_by_name.get(table_name)
        if table is None or column not in table.columns:
            indexes[(table_name, column)] = set()
        else:
            indexes[(table_name, column)] = {
                row.get(column) for row in table.rows if row.get(column) is not None
            }
    missing = 0
    for row in manifest:
        table_name = str(row.get("source_table"))
        claim_column = row.get("source_claim_key_column")
        member_column = row.get("source_member_key_column")
        if claim_column and row.get("source_claim_key") not in indexes.get(
            (table_name, str(claim_column)), set()
        ):
            missing += 1
        elif member_column and row.get("source_member_key") not in indexes.get(
            (table_name, str(member_column)), set()
        ):
            missing += 1
    return ValidationResult(
        check="private_issue_manifest_source_locators",
        passed=missing == 0,
        observed=missing,
        expected="0 manifest rows without an exact raw source key",
    )


def build_payer_dataset(
    *,
    payer: str,
    member_count: int,
    start_date: date,
    end_date: date,
    seed: int,
    schema_root: Path,
    issue_profile: str = "connector_eval",
) -> GeneratedPayerDataset:
    payer_seed = seed + SEED_OFFSET[payer]
    clean = generate_canonical(GenerationConfig(
        payer=payer, member_count=member_count, start_date=start_date,
        end_date=end_date, seed=payer_seed,
    ))
    clean_results = validate_canonical(clean, expected_members=member_count)
    clean_failures = failures(clean_results)
    if clean_failures:
        details = "; ".join(f"{item.check}: {item.observed}" for item in clean_failures)
        raise RuntimeError(f"Clean canonical validation failed for {payer}: {details}")
    if issue_profile == "connector_eval":
        canonical, manifest = inject_connector_eval_issues(clean)
        manifest = _source_locators(payer, manifest)
        canonical_results = validate_canonical(
            canonical, expected_members=member_count, allow_injected_issues=True,
            issue_manifest=manifest,
        )
    elif issue_profile == "none":
        canonical, manifest = clean, ()
        canonical_results = clean_results
    else:
        raise ValueError(f"Unknown issue profile: {issue_profile}")
    tables_by_name = _adapt(payer, canonical, schema_root)
    tables = tuple(tables_by_name.values())
    allow_empty_tables = len(canonical.enrollment_months) / 12 < 500
    results = tuple(
        canonical_results
        + validate_output_tables(tables, allow_empty_tables=allow_empty_tables)
        + ([_validate_manifest_locators(manifest, tables)] if manifest else [])
    )
    failed = failures(results)
    if failed:
        details = "; ".join(f"{item.check}: {item.observed}" for item in failed)
        raise RuntimeError(f"Generated dataset validation failed for {payer}: {details}")
    return GeneratedPayerDataset(
        payer=payer, canonical=canonical, issue_manifest=manifest,
        tables=tables, validations=results,
    )
