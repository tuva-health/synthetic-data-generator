"""Structural, relational, financial, and distributional validation."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from itertools import chain
from typing import Iterable

from tuva_synthetic.model import CanonicalDataset, OutputTable, Row, ValidationResult


def _result(check: str, passed: bool, observed: object, expected: str) -> ValidationResult:
    return ValidationResult(check=check, passed=passed, observed=observed, expected=expected)


def summarize(dataset: CanonicalDataset) -> dict[str, object]:
    member_years = len(dataset.enrollment_months) / 12
    medical_claims = {row["original_claim_id"] for row in dataset.medical_claim_lines}
    inpatient_claims = {
        row["original_claim_id"] for row in dataset.medical_claim_lines
        if row["setting"] == "inpatient" and row.get("adjustment_sequence") == 0
    }
    conditions = Counter(condition for member in dataset.members for condition in member["conditions"])
    return {
        "members": len(dataset.members),
        "member_months": len(dataset.enrollment_months),
        "member_years": round(member_years, 2),
        "medical_claims": len(medical_claims),
        "medical_claim_lines": len(dataset.medical_claim_lines),
        "pharmacy_claims": len(dataset.pharmacy_claims),
        "inpatient_claims": len(inpatient_claims),
        "medical_claims_per_1000_member_years": round(len(medical_claims) / member_years * 1000, 1) if member_years else 0,
        "inpatient_admissions_per_1000_member_years": round(len(inpatient_claims) / member_years * 1000, 1) if member_years else 0,
        "pharmacy_fills_per_member_year": round(len(dataset.pharmacy_claims) / member_years, 2) if member_years else 0,
        "condition_prevalence": {
            key: round(value / len(dataset.members), 4) for key, value in sorted(conditions.items())
        },
        "age_bands": dict(sorted(Counter(member["age_band"] for member in dataset.members).items())),
        "claim_settings": dict(sorted(Counter(row["setting"] for row in dataset.medical_claim_lines).items())),
        "source_systems": dict(sorted(Counter(member["source_system"] for member in dataset.members).items())),
    }


def validate_canonical(
    dataset: CanonicalDataset,
    *,
    expected_members: int | None = None,
    allow_injected_issues: bool = False,
    issue_manifest: Iterable[Row] = (),
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    member_ids = [member["member_id"] for member in dataset.members]
    person_ids = [member["person_id"] for member in dataset.members]
    results.append(_result(
        "member_count", expected_members is None or len(member_ids) == expected_members,
        len(member_ids), f"exactly {expected_members}" if expected_members is not None else "positive",
    ))
    results.append(_result("unique_member_ids", len(member_ids) == len(set(member_ids)), len(set(member_ids)), "one per member"))
    results.append(_result("unique_person_ids", len(person_ids) == len(set(person_ids)), len(set(person_ids)), "one per member"))

    member_set = set(member_ids)
    enrollment_members = {row["member_id"] for row in dataset.enrollment_months}
    results.append(_result("every_member_enrolled", member_set <= enrollment_members, len(member_set - enrollment_members), "0 missing members"))
    results.append(_result(
        "claim_members_resolve",
        all(row["member_id"] in member_set for row in dataset.medical_claim_lines),
        sum(row["member_id"] not in member_set for row in dataset.medical_claim_lines), "0",
    ))
    results.append(_result(
        "pharmacy_members_resolve",
        all(row["member_id"] in member_set for row in dataset.pharmacy_claims),
        sum(row["member_id"] not in member_set for row in dataset.pharmacy_claims), "0",
    ))

    claim_lines: dict[str, list[Row]] = defaultdict(list)
    for row in dataset.medical_claim_lines:
        claim_lines[f"{row['original_claim_id']}|{row.get('adjustment_sequence', 0)}"].append(row)
    duplicate_keys = 0
    for rows in claim_lines.values():
        keys = [(row["line_number"], row["source_system"]) for row in rows]
        duplicate_keys += len(keys) - len(set(keys))
    results.append(_result("medical_transaction_line_grain", duplicate_keys == 0, duplicate_keys, "0 duplicate line keys"))

    financial_failures = 0
    component_failures = 0
    for row in dataset.medical_claim_lines:
        if row["claim_status"] in {"denied", "reversal", "void"} or not row.get("final_action", True):
            continue
        allowed = float(row.get("allowed_amount") or 0)
        components = sum(float(row.get(field) or 0) for field in (
            "plan_paid_amount", "member_paid_amount", "other_payer_amount"
        ))
        member_components = sum(float(row.get(field) or 0) for field in (
            "coinsurance_amount", "copay_amount", "deductible_amount"
        ))
        if abs(allowed - components) > .03:
            financial_failures += 1
        if abs(float(row.get("member_paid_amount") or 0) - member_components) > .03:
            component_failures += 1
    known_financial_issues = sum(
        row.get("dq_test_name") == "medical_claim__paid_amount_gt_allowed_amount"
        for row in issue_manifest
    )
    results.append(_result(
        "medical_allowed_financial_identity",
        financial_failures <= known_financial_issues if allow_injected_issues else financial_failures == 0,
        financial_failures, f"0 except {known_financial_issues} documented injections" if allow_injected_issues else "0",
    ))
    results.append(_result(
        "medical_member_cost_share_identity", component_failures == 0,
        component_failures, "0",
    ))

    monetary_fields = (
        "charge_amount", "allowed_amount", "plan_paid_amount",
        "member_paid_amount", "coinsurance_amount", "copay_amount",
        "deductible_amount", "other_payer_amount",
    )
    negative_final_amounts = sum(
        1
        for row in dataset.medical_claim_lines
        if row.get("final_action", True)
        and row.get("claim_status") not in {"reversal", "void"}
        for field in monetary_fields
        if float(row.get(field) or 0) < 0
    )
    results.append(_result(
        "nonnegative_final_medical_amounts",
        negative_final_amounts == 0,
        negative_final_amounts,
        "0 negative final-action amounts",
    ))

    positive_lines = sum(row["line_number"] <= 0 for row in dataset.medical_claim_lines)
    results.append(_result("positive_medical_line_numbers", positive_lines == 0, positive_lines, "0 invalid"))
    valid_dates = sum(row["first_service_date"] > row["last_service_date"] for row in dataset.medical_claim_lines)
    results.append(_result("medical_service_date_order", valid_dates == 0, valid_dates, "0 reversed ranges"))
    file_date_failures = sum(
        row.get("paid_date") is not None
        and row.get("file_date") is not None
        and row["paid_date"] > row["file_date"]
        for row in chain(dataset.medical_claim_lines, dataset.pharmacy_claims)
    )
    results.append(_result(
        "adjudication_precedes_source_file_date",
        file_date_failures == 0,
        file_date_failures,
        "0 paid dates after file dates",
    ))

    active_member_months = {
        (row["member_id"], row["enrollment_month"])
        for row in dataset.enrollment_months
    }
    uncovered_claim_lines = sum(
        (
            row["member_id"],
            row["first_service_date"].replace(day=1),
        ) not in active_member_months
        for row in dataset.medical_claim_lines
        if row.get("adjustment_sequence", 0) == 0
    )
    documented_uncovered = sum(
        row.get("dq_test_name") == "medical_claim__no_matching_eligibility_span"
        for row in issue_manifest
    )
    results.append(_result(
        "medical_claim_months_are_enrolled",
        uncovered_claim_lines <= documented_uncovered if allow_injected_issues else uncovered_claim_lines == 0,
        uncovered_claim_lines,
        f"0 except {documented_uncovered} documented injections" if allow_injected_issues else "0",
    ))

    members_by_id = {row["member_id"]: row for row in dataset.members}
    provider_rows = [
        row for row in dataset.medical_claim_lines
        if row.get("provider_state") and row.get("member_id") in members_by_id
    ]
    same_state_rate = (
        sum(
            row["provider_state"] == members_by_id[row["member_id"]]["state"]
            for row in provider_rows
        ) / len(provider_rows)
        if provider_rows else 0
    )
    results.append(_result(
        "provider_geography_is_plausible",
        same_state_rate >= .72,
        round(same_state_rate, 4),
        ">= 72% of medical lines have a rendering provider in the member state",
    ))
    facilities_by_npi = {row["npi"]: row for row in dataset.facilities}
    incompatible_inpatient_facilities = sum(
        row.get("setting") == "inpatient"
        and facilities_by_npi.get(row.get("facility_npi"), {}).get("facility_type") != "Acute Care Hospital"
        for row in dataset.medical_claim_lines
    )
    results.append(_result(
        "inpatient_facility_type_is_plausible",
        incompatible_inpatient_facilities == 0,
        incompatible_inpatient_facilities,
        "0 inpatient lines outside acute-care hospitals",
    ))

    summary = summarize(dataset)
    member_years = float(summary["member_years"])
    admissions = float(summary["inpatient_admissions_per_1000_member_years"])
    rx_rate = float(summary["pharmacy_fills_per_member_year"])
    claim_rate = float(summary["medical_claims_per_1000_member_years"])
    period_month_count = (
        (dataset.end_date.year - dataset.start_date.year) * 12
        + dataset.end_date.month - dataset.start_date.month + 1
    )
    minimum_exposure = len(dataset.members) * period_month_count / 12 * .55
    results.append(_result(
        "minimum_longitudinal_exposure",
        member_years >= minimum_exposure,
        member_years,
        f">= {round(minimum_exposure, 2)} member-years (55% of maximum period exposure)",
    ))
    results.append(_result("commercial_medical_claim_rate", 1_500 <= claim_rate <= 8_500, claim_rate, "1,500-8,500 claims per 1,000 member-years"))
    results.append(_result(
        "commercial_inpatient_rate",
        member_years < 500 or 8 <= admissions <= 180,
        admissions,
        "8-180 admissions per 1,000 member-years when exposure is >= 500 member-years",
    ))
    results.append(_result("pharmacy_fill_rate", .4 <= rx_rate <= 14, rx_rate, "0.4-14 fills per member-year"))

    manifest = list(issue_manifest)
    if allow_injected_issues:
        issue_ids = [row["issue_id"] for row in manifest]
        results.append(_result("issue_manifest_not_empty", bool(manifest), len(manifest), "> 0"))
        results.append(_result("unique_issue_ids", len(issue_ids) == len(set(issue_ids)), len(issue_ids) - len(set(issue_ids)), "0 duplicates"))
        required_issue_classes = {
            "medical_claim__place_of_service_code_null_for_professional_claim",
            "medical_claim__drg_code_count_ne_one_for_acute_inpatient_claim",
            "pharmacy_claim__ndc_code_invalid",
        }
        payer_label = str(dataset.members[0].get("payer") if dataset.members else "")
        if payer_label in {"Aetna", "Priority Health"}:
            required_issue_classes.update({
                "connector__select_final_action_replacement",
                "connector__remove_voided_claim",
            })
        elif payer_label == "HCCI Commercial":
            required_issue_classes.add("connector__duplicate_eligibility_source_row")
        actual_classes = {row["dq_test_name"] for row in manifest}
        require_complete_profile = (
            len(dataset.members) >= 500 and period_month_count >= 12
        )
        results.append(_result(
            "required_connector_eval_issue_classes",
            required_issue_classes <= actual_classes or not require_complete_profile,
            sorted(required_issue_classes - actual_classes), "all required classes present",
        ))
        rate = len(manifest) / max(len(dataset.medical_claim_lines) + len(dataset.pharmacy_claims) + len(dataset.enrollment_months), 1)
        results.append(_result(
            "issue_density_is_nuanced",
            member_years < 500 or .0001 <= rate <= .035,
            round(rate, 5),
            "0.01%-3.5% of raw records when exposure is >= 500 member-years",
        ))
    return results


def validate_output_tables(
    tables: Iterable[OutputTable],
    *,
    allow_empty_tables: bool = False,
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    names: list[str] = []
    for table in tables:
        names.append(table.name)
        expected = set(table.columns)
        malformed = sum(set(row) != expected for row in table.rows)
        metadata = {str(column["name"]): column for column in table.column_metadata}
        overlength_values = 0
        for column in table.columns:
            field = metadata.get(column, {})
            source_type = str(
                field.get("type")
                or field.get("normalized_data_type")
                or field.get("data_type")
                or ""
            ).lower()
            limit = field.get("length") or field.get("size")
            if not limit or source_type not in {"string", "varchar", "character"}:
                continue
            overlength_values += sum(
                value is not None and len(str(value)) > int(limit)
                for value in (row.get(column) for row in table.rows)
            )
        results.append(_result(
            f"{table.name}__rows_present",
            len(table.rows) > 0 or allow_empty_tables,
            len(table.rows),
            "> 0 unless total cohort exposure is below 500 member-years",
        ))
        results.append(_result(f"{table.name}__exact_columns", malformed == 0, malformed, "0 malformed rows"))
        results.append(_result(f"{table.name}__unique_columns", len(table.columns) == len(set(table.columns)), len(table.columns), "no duplicate names"))
        results.append(_result(
            f"{table.name}__declared_string_lengths",
            overlength_values == 0,
            overlength_values,
            "0 overlength values",
        ))
    results.append(_result("unique_output_table_names", len(names) == len(set(names)), names, "unique"))
    return results


def failures(results: Iterable[ValidationResult]) -> list[ValidationResult]:
    return [result for result in results if not result.passed]


def as_dict(result: ValidationResult) -> dict[str, object]:
    return {
        "check": result.check,
        "passed": result.passed,
        "observed": result.observed,
        "expected": result.expected,
    }
