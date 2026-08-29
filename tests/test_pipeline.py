from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tuva_synthetic.generation import GenerationConfig, generate_canonical
from tuva_synthetic.pipeline import build_payer_dataset


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("payer", ("aetna", "priority_health", "hcci"))
def test_clean_cohort_has_realistic_geography_and_adjudication(payer: str) -> None:
    dataset = generate_canonical(GenerationConfig(
        payer=payer,
        member_count=500,
        start_date=date(2024, 1, 1),
        end_date=date(2025, 12, 31),
        seed=20260829,
    ))
    members = {row["member_id"]: row for row in dataset.members}
    providers = {row["npi"]: row for row in dataset.providers}
    facilities = {row["npi"]: row for row in dataset.facilities}

    assert sum(
        row["provider_state"] == members[row["member_id"]]["state"]
        for row in dataset.medical_claim_lines
    ) / len(dataset.medical_claim_lines) >= .72
    assert all(
        providers[member["pcp_npi"]]["state"] == member["state"]
        for member in dataset.members
    )
    assert all(
        facilities[row["facility_npi"]]["facility_type"] == "Acute Care Hospital"
        for row in dataset.medical_claim_lines
        if row["setting"] == "inpatient"
    )
    assert all(
        float(row.get(field) or 0) >= 0
        for row in dataset.medical_claim_lines
        for field in (
            "allowed_amount", "plan_paid_amount", "member_paid_amount",
            "coinsurance_amount", "copay_amount", "deductible_amount",
            "other_payer_amount",
        )
    )
    assert all(
        row["paid_date"] <= row["file_date"]
        for row in (*dataset.medical_claim_lines, *dataset.pharmacy_claims)
    )


@pytest.mark.parametrize("payer", ("aetna", "priority_health", "hcci"))
def test_connector_profile_has_raw_locators_and_only_native_adr(payer: str) -> None:
    generated = build_payer_dataset(
        payer=payer,
        member_count=500,
        start_date=date(2024, 1, 1),
        end_date=date(2025, 12, 31),
        seed=20260829,
        schema_root=REPOSITORY_ROOT / "schemas",
        issue_profile="connector_eval",
    )
    classes = {row["dq_test_name"] for row in generated.issue_manifest}

    assert all(row.get("source_table") for row in generated.issue_manifest)
    assert all(
        row.get("source_claim_key") is not None
        or row.get("source_member_key") is not None
        for row in generated.issue_manifest
    )
    assert "medical_claim__facility_npi_null_for_inpatient_claim" not in classes
    assert "medical_claim__rendering_npi_invalid" not in classes
    assert "connector__select_paid_after_rejected_pharmacy_transaction" not in classes
    if payer in {"aetna", "priority_health"}:
        assert "connector__select_final_action_replacement" in classes
        assert "connector__remove_voided_claim" in classes
        assert "eligibility__overlapping_enrollment_spans" in classes
    else:
        assert "connector__select_final_action_replacement" not in classes
        assert "connector__remove_voided_claim" not in classes
        assert "connector__duplicate_eligibility_source_row" in classes


def test_partial_month_generation_stays_inside_requested_dates() -> None:
    generated = build_payer_dataset(
        payer="priority_health",
        member_count=100,
        start_date=date(2025, 3, 15),
        end_date=date(2025, 5, 20),
        seed=20260829,
        schema_root=REPOSITORY_ROOT / "schemas",
        issue_profile="connector_eval",
    )
    starts = [row["first_service_date"] for row in generated.canonical.medical_claim_lines]
    fills = [row["fill_date"] for row in generated.canonical.pharmacy_claims]

    assert min((*starts, *fills)) >= date(2025, 3, 15)
    assert max((*starts, *fills)) <= date(2025, 5, 20)
