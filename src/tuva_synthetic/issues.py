"""Controlled, nuanced source-data problems for connector evaluation."""

from __future__ import annotations

import copy
import calendar
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Callable, Iterable

from tuva_synthetic.generation import synthetic_npi
from tuva_synthetic.model import CanonicalDataset, Row


IssueManifest = tuple[Row, ...]
TUVA_CORE_DQ_CONTRACT = "tuva-core 1.0.0@22bb5766c8890d9b4d66fdefb21dc532e3da785e"


def _choose(rows: Iterable[Row], rng: random.Random, rate: float, limit: int | None = None) -> list[Row]:
    candidates = list(rows)
    rng.shuffle(candidates)
    if not candidates:
        return []
    count = max(1, round(len(candidates) * rate))
    if limit is not None:
        count = min(count, limit)
    return candidates[:count]


def _manifest_row(
    *,
    issue_id: str,
    dq_test_name: str,
    domain: str,
    row: Row,
    field: str,
    original: object,
    injected: object,
    severity: int | str,
    expected_action: str,
    pattern: str,
    evaluation_phase: str = "post_connector_input_dq",
    expected_final_presence: bool | None = True,
    collateral_tests: tuple[str, ...] = (),
) -> Row:
    return {
        "issue_id": issue_id,
        "dq_test_name": dq_test_name,
        "domain": domain,
        "payer": row.get("payer"),
        "setting": row.get("setting"),
        "member_id": row.get("member_id"),
        "person_id": row.get("person_id"),
        "claim_id": row.get("claim_id"),
        "original_claim_id": row.get("original_claim_id"),
        "line_number": row.get("line_number"),
        "adjustment_sequence": row.get("adjustment_sequence"),
        "source_system": row.get("source_system"),
        "field": field,
        "original_value": original,
        "injected_value": injected,
        "severity": severity,
        "evaluation_phase": evaluation_phase,
        "expected_final_presence": expected_final_presence,
        "expected_failure_count": 1,
        "collateral_tests": list(collateral_tests),
        "tuva_core_dq_contract": TUVA_CORE_DQ_CONTRACT,
        "expected_connector_action": expected_action,
        "pattern": pattern,
    }


def _inject_scalar(
    *,
    selected: list[Row],
    manifest: list[Row],
    issue_prefix: str,
    dq_test_name: str,
    domain: str,
    field: str,
    replacement: object | Callable[[Row], object],
    severity: str,
    expected_action: str,
    pattern: str,
    collateral_tests: tuple[str, ...] = (),
) -> None:
    for index, row in enumerate(selected, 1):
        original = copy.deepcopy(row.get(field))
        injected = replacement(row) if callable(replacement) else replacement
        row[field] = injected
        manifest.append(_manifest_row(
            issue_id=f"{issue_prefix}-{index:05d}", dq_test_name=dq_test_name,
            domain=domain, row=row, field=field, original=original,
            injected=copy.deepcopy(injected), severity=severity,
            expected_action=expected_action, pattern=pattern,
            collateral_tests=collateral_tests,
        ))


def _inject_one_cent_paid_over_allowed(
    *,
    selected: list[Row],
    manifest: list[Row],
    issue_prefix: str,
    dq_test_name: str,
    domain: str,
) -> None:
    """Create a literal one-cent variance without unrelated cost-share noise."""

    cost_share_fields = (
        "member_paid_amount", "coinsurance_amount", "copay_amount",
        "deductible_amount", "other_payer_amount",
    )
    for index, row in enumerate(selected, 1):
        original = {
            "plan_paid_amount": row.get("plan_paid_amount"),
            **{field: row.get(field) for field in cost_share_fields},
        }
        for field in cost_share_fields:
            row[field] = 0.0
        row["plan_paid_amount"] = round(float(row["allowed_amount"]) + .01, 2)
        injected = {
            "plan_paid_amount": row["plan_paid_amount"],
            **{field: row[field] for field in cost_share_fields},
        }
        manifest.append(_manifest_row(
            issue_id=f"{issue_prefix}-{index:05d}",
            dq_test_name=dq_test_name,
            domain=domain,
            row=row,
            field="adjudicated_amounts",
            original=original,
            injected=injected,
            severity=2,
            expected_action="surface rather than round away the one-cent inconsistency",
            pattern="zero member responsibility leaves paid exactly $0.01 above allowed",
        ))


def _minority_source(rows: Iterable[Row]) -> str | None:
    counts = Counter(row.get("source_system") for row in rows if row.get("source_system"))
    return min(counts, key=counts.get) if counts else None


def _claim_groups(rows: Iterable[Row]) -> dict[str, list[Row]]:
    grouped: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row["original_claim_id"])].append(row)
    return grouped


def _month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def _add_adr_sequences(
    medical: list[Row],
    rng: random.Random,
    manifest: list[Row],
    payer: str,
) -> None:
    """Add medical ADR histories only where the public layout exposes them."""

    if payer not in {"aetna", "priority_health"}:
        return

    groups = _claim_groups(medical)
    medical_minority_source = _minority_source(medical)
    reserved_claim_ids = {
        str(row["claim_id"]) for row in manifest if row.get("claim_id")
    }
    eligible = [
        rows for rows in groups.values()
        if rows and all(row["claim_status"] == "paid" for row in rows)
        and rows[0].get("source_system") == medical_minority_source
        and str(rows[0].get("claim_id")) not in reserved_claim_ids
    ]
    rng.shuffle(eligible)
    replacement_groups = eligible[: max(1, round(len(eligible) * .035))]
    cursor = len(manifest) + 1
    for group in replacement_groups:
        original_claim_id = group[0]["original_claim_id"]
        for row in group:
            row["final_action"] = False
            reversal = copy.deepcopy(row)
            replacement = copy.deepcopy(row)
            reversal_paid_date = row["paid_date"] + timedelta(days=6)
            reversal.update({
                "adjustment_sequence": 1, "final_action": False,
                "claim_status": "reversal", "denied_flag": 0,
                "paid_date": reversal_paid_date,
                "file_name": f"adjustment_{reversal_paid_date:%Y%m}.csv",
                "file_date": date(
                    reversal_paid_date.year,
                    reversal_paid_date.month,
                    calendar.monthrange(
                        reversal_paid_date.year, reversal_paid_date.month
                    )[1],
                ),
            })
            for field in (
                "charge_amount", "allowed_amount", "plan_paid_amount",
                "member_paid_amount", "coinsurance_amount", "copay_amount",
                "deductible_amount", "other_payer_amount",
            ):
                reversal[field] = round(-float(reversal.get(field) or 0), 2)
            replacement_paid_date = row["paid_date"] + timedelta(days=12)
            replacement.update({
                "adjustment_sequence": 2, "final_action": True,
                "claim_status": "replacement", "denied_flag": 0,
                "paid_date": replacement_paid_date,
                "file_name": f"adjustment_{replacement_paid_date:%Y%m}.csv",
                "file_date": date(
                    replacement_paid_date.year,
                    replacement_paid_date.month,
                    calendar.monthrange(
                        replacement_paid_date.year, replacement_paid_date.month
                    )[1],
                ),
            })
            for field in (
                "charge_amount", "allowed_amount", "plan_paid_amount",
                "member_paid_amount", "other_payer_amount",
            ):
                replacement[field] = round(float(replacement.get(field) or 0) * .97, 2)
            replacement["member_paid_amount"] = round(
                replacement["allowed_amount"] - replacement["plan_paid_amount"]
                - float(replacement.get("other_payer_amount") or 0), 2
            )
            components = sum(float(replacement.get(field) or 0) for field in (
                "coinsurance_amount", "copay_amount", "deductible_amount"
            ))
            if components:
                ratio = replacement["member_paid_amount"] / components
                replacement["coinsurance_amount"] = round(float(replacement["coinsurance_amount"]) * ratio, 2)
                replacement["copay_amount"] = round(float(replacement["copay_amount"]) * ratio, 2)
                replacement["deductible_amount"] = round(
                    replacement["member_paid_amount"] - replacement["coinsurance_amount"] - replacement["copay_amount"], 2
                )
            medical.extend((reversal, replacement))
        manifest.append(_manifest_row(
            issue_id=f"ADR-REPLACE-{cursor:05d}",
            dq_test_name="connector__select_final_action_replacement",
            domain="medical_claim", row=group[0], field="adjustment_sequence",
            original=0, injected="0 original, 1 reversal, 2 replacement",
            severity="behavioral", expected_action="retain only the replacement transaction at the claim-line grain",
            pattern=f"minority source system; stable original_claim_id {original_claim_id}",
            evaluation_phase="post_connector_final_action",
            expected_final_presence=True,
        ))
        cursor += 1

    remaining = [group for group in eligible if group not in replacement_groups]
    void_groups = remaining[: max(1, round(len(remaining) * .010))]
    for group in void_groups:
        for row in group:
            row["final_action"] = False
            reversal = copy.deepcopy(row)
            void_paid_date = row["paid_date"] + timedelta(days=18)
            reversal.update({
                "adjustment_sequence": 1,
                "final_action": True,
                "claim_status": "void",
                "paid_date": void_paid_date,
                "file_name": f"adjustment_{void_paid_date:%Y%m}.csv",
                "file_date": date(
                    void_paid_date.year,
                    void_paid_date.month,
                    calendar.monthrange(void_paid_date.year, void_paid_date.month)[1],
                ),
            })
            for field in (
                "charge_amount", "allowed_amount", "plan_paid_amount",
                "member_paid_amount", "coinsurance_amount", "copay_amount",
                "deductible_amount", "other_payer_amount",
            ):
                reversal[field] = round(-float(reversal.get(field) or 0), 2)
            medical.append(reversal)
        manifest.append(_manifest_row(
            issue_id=f"ADR-VOID-{cursor:05d}",
            dq_test_name="connector__remove_voided_claim",
            domain="medical_claim", row=group[0], field="claim_status",
            original="paid", injected="paid followed by void",
            severity="behavioral", expected_action="exclude the voided claim from the final-action Input Layer",
            pattern="complete claim reversal without replacement",
            evaluation_phase="post_connector_final_action",
            expected_final_presence=False,
        ))
        cursor += 1


def inject_connector_eval_issues(
    dataset: CanonicalDataset,
    *,
    seed: int | None = None,
) -> tuple[CanonicalDataset, IssueManifest]:
    """Return a dirty copy plus a private row-level ground-truth manifest.

    Problems are deliberately sparse and clustered by source system, period,
    provider, or claim so that they resemble source-system defects rather than
    obvious uniformly-random corruption.
    """

    rng = random.Random(dataset.seed + 91_337 if seed is None else seed)
    members = copy.deepcopy(list(dataset.members))
    enrollment = copy.deepcopy(list(dataset.enrollment_months))
    medical = copy.deepcopy(list(dataset.medical_claim_lines))
    pharmacy = copy.deepcopy(list(dataset.pharmacy_claims))
    providers = copy.deepcopy(list(dataset.providers))
    facilities = copy.deepcopy(list(dataset.facilities))
    manifest: list[Row] = []
    minority = _minority_source(medical)
    original_claim_groups = _claim_groups(medical)
    payer_label = str(members[0].get("payer") if members else "")
    payer = {
        "Aetna": "aetna",
        "Priority Health": "priority_health",
        "HCCI Commercial": "hcci",
    }.get(payer_label, payer_label.lower().replace(" ", "_"))

    professional_by_quarter = Counter(
        (row["first_service_date"].year, (row["first_service_date"].month - 1) // 3 + 1)
        for row in medical
        if row["claim_type"] == "professional" and row["source_system"] == minority
    )
    cluster_quarter = (
        max(professional_by_quarter, key=professional_by_quarter.get)
        if professional_by_quarter else None
    )
    clustered_professional = [
        row for row in medical
        if row["claim_type"] == "professional"
        and row["source_system"] == minority
        and cluster_quarter is not None
        and (
            row["first_service_date"].year,
            (row["first_service_date"].month - 1) // 3 + 1,
        ) == cluster_quarter
    ]
    cluster_label = (
        f"{cluster_quarter[0]} Q{cluster_quarter[1]}"
        if cluster_quarter else "the busiest source quarter"
    )
    _inject_scalar(
        selected=_choose(clustered_professional, rng, .055, limit=180), manifest=manifest,
        issue_prefix="MC-POS-NULL", dq_test_name="medical_claim__place_of_service_code_null_for_professional_claim",
        domain="medical_claim", field="place_of_service", replacement=None, severity=2,
        expected_action="map the source faithfully, detect, and investigate before downstream use",
        pattern=f"clustered in {cluster_label} in the minority source system",
    )
    _inject_scalar(
        selected=_choose((row for row in clustered_professional if row.get("place_of_service")), rng, .018, limit=60),
        manifest=manifest, issue_prefix="MC-POS-INVALID",
        dq_test_name="medical_claim__place_of_service_code_invalid", domain="medical_claim",
        field="place_of_service", replacement="1O", severity=2,
        expected_action="preserve the source value and surface the terminology failure",
        pattern="letter O substituted for zero in one legacy feed",
    )
    diagnosis_candidates = [
        row for row in medical
        if row["source_system"] == minority
        and row["claim_type"] == "professional"
        and len(original_claim_groups[str(row["original_claim_id"])]) == 1
        and len(row["diagnosis_codes"]) >= 2
    ]
    for index, row in enumerate(_choose(diagnosis_candidates, rng, .006, limit=90), 1):
        original = list(row["diagnosis_codes"])
        row["diagnosis_codes"][1] = "E11O"
        manifest.append(_manifest_row(
            issue_id=f"MC-DX-INVALID-{index:05d}",
            dq_test_name="medical_claim__diagnosis_code_2_to_25_invalid", domain="medical_claim",
            row=row, field="diagnosis_codes[1]", original=original[1], injected="E11O",
            severity=2, expected_action="retain and flag the invalid secondary diagnosis",
            pattern="valid-looking ICD-10-CM code with letter O replacing zero",
        ))

    institutional = [row for row in medical if row["claim_type"] == "institutional" and row["source_system"] == minority]
    _inject_scalar(
        selected=_choose((row for row in institutional if row.get("revenue_code")), rng, .004, limit=70),
        manifest=manifest, issue_prefix="MC-REV-INVALID",
        dq_test_name="medical_claim__revenue_center_code_invalid", domain="medical_claim",
        field="revenue_code", replacement=lambda row: "O" + str(row["revenue_code"])[1:], severity=2,
        expected_action="retain and flag the unrecognized revenue code",
        pattern="OCR-like character substitution in a legacy institutional extract",
    )
    _inject_scalar(
        selected=_choose((row for row in institutional if row.get("bill_type")), rng, .002, limit=35),
        manifest=manifest, issue_prefix="MC-TOB-INVALID",
        dq_test_name="medical_claim__bill_type_code_invalid", domain="medical_claim",
        field="bill_type", replacement="13I", severity=2,
        expected_action="retain and flag invalid type of bill",
        pattern="letter I in the third position",
        collateral_tests=(
            "medical_claim__bill_type_code_count_ne_one_for_institutional_claim",
        ),
    )

    inpatient_groups = [
        group for group in original_claim_groups.values()
        if len(group) > 1 and group[0]["setting"] == "inpatient" and group[0].get("drg_code")
    ]
    rng.shuffle(inpatient_groups)
    for index, group in enumerate(inpatient_groups[: max(1, round(len(inpatient_groups) * .028))], 1):
        target = group[-1]
        original = target["drg_code"]
        target["drg_code"] = str((int(original) + 1) % 999).zfill(3)
        manifest.append(_manifest_row(
            issue_id=f"MC-DRG-MULTI-{index:05d}",
            dq_test_name="medical_claim__drg_code_count_ne_one_for_acute_inpatient_claim",
            domain="medical_claim", row=target, field="drg_code", original=original,
            injected=target["drg_code"], severity=2,
            expected_action="do not silently choose a DRG; surface claim-level inconsistency",
            pattern="one late ancillary line carries a neighboring valid-looking DRG",
        ))

    multi_line_groups = (
        [group for group in original_claim_groups.values() if len(group) > 1]
        if payer == "priority_health"
        else []
    )
    rng.shuffle(multi_line_groups)
    for index, group in enumerate(multi_line_groups[: max(1, round(len(multi_line_groups) * .004))], 1):
        target = group[-1]
        original = target["billing_npi"]
        target["billing_npi"] = synthetic_npi(88_000 + index)
        manifest.append(_manifest_row(
            issue_id=f"MC-BILLING-NPI-MULTI-{index:05d}",
            dq_test_name="medical_claim__billing_npi_has_multiple_values_per_claim",
            domain="medical_claim", row=target, field="billing_npi", original=original,
            injected=target["billing_npi"], severity=2,
            expected_action="preserve line detail and flag the claim-level inconsistency",
            pattern="only the final service line is attributed to a different valid NPI",
        ))

    _inject_scalar(
        selected=_choose((
            row for row in medical
            if row["source_system"] == minority
            and len(original_claim_groups[str(row["original_claim_id"])]) == 1
        ), rng, .0012, limit=65),
        manifest=manifest, issue_prefix="MC-PAID-EARLY",
        dq_test_name="medical_claim__paid_date_before_claim_end_date", domain="medical_claim",
        field="paid_date", replacement=lambda row: row["last_service_date"] - timedelta(days=1), severity=2,
        expected_action="retain and flag the temporal inconsistency",
        pattern="one-day timing discrepancy concentrated in a migrated adjudication feed",
    )
    _inject_one_cent_paid_over_allowed(
        selected=_choose((row for row in medical if row["claim_status"] == "paid" and row["allowed_amount"] > 0), rng, .0008, limit=45),
        manifest=manifest,
        issue_prefix="MC-PAID-GT-ALLOWED",
        dq_test_name="medical_claim__paid_amount_gt_allowed_amount",
        domain="medical_claim",
    )
    enrollment_by_member: dict[str, list[Row]] = defaultdict(list)
    for row in enrollment:
        enrollment_by_member[row["member_id"]].append(row)
    delayed_members = (
        [
            rows for rows in enrollment_by_member.values()
            if min(row["enrollment_month"] for row in rows) > dataset.start_date
        ]
        if payer != "hcci"
        else []
    )
    rng.shuffle(delayed_members)
    no_eligibility_count = min(len(delayed_members), max(1, round(len(dataset.members) * .002)))
    for index, member_rows in enumerate(delayed_members[:no_eligibility_count], 1):
        member_id = member_rows[0]["member_id"]
        candidates = [
            row for row in medical
            if row["member_id"] == member_id
            and row["claim_type"] == "professional"
            and len(original_claim_groups[str(row["original_claim_id"])]) == 1
        ]
        if not candidates:
            continue
        row = rng.choice(candidates)
        first_enrollment = min(item["enrollment_month"] for item in member_rows)
        original = row["first_service_date"]
        shifted = first_enrollment - timedelta(days=1)
        duration = row["last_service_date"] - row["first_service_date"]
        row["first_service_date"] = shifted
        row["claim_line_start_date"] = shifted
        row["claim_first_date"] = shifted
        row["last_service_date"] = shifted + duration
        row["claim_line_end_date"] = shifted + duration
        manifest.append(_manifest_row(
            issue_id=f"MC-NO-ELIG-{index:05d}",
            dq_test_name="medical_claim__no_matching_eligibility_span", domain="medical_claim",
            row=row, field="first_service_date", original=original, injected=shifted,
            severity=2, expected_action="surface the claim with no matching eligibility rather than invent coverage",
            pattern="claim occurs one day before a plausible midyear coverage start",
        ))

    members_for_demographic_drift = [
        rows for rows in enrollment_by_member.values()
        if rows and str(rows[0].get("relation_code")) == "18"
    ]
    rng.shuffle(members_for_demographic_drift)
    sex_drift_count = max(1, round(len(dataset.members) * .0018))
    overlap_count = max(1, round(len(dataset.members) * .0012))
    for index, member_rows in enumerate(members_for_demographic_drift[:sex_drift_count], 1):
        row = member_rows[-1]
        original = row["sex"]
        row["sex"] = "F" if original == "M" else "M"
        manifest.append(_manifest_row(
            issue_id=f"ELIG-SEX-MULTI-{index:05d}",
            dq_test_name="eligibility__multiple_sexes_per_person", domain="eligibility",
            row=row, field="sex", original=original, injected=row["sex"], severity=3,
            expected_action="preserve source history and flag person-level demographic inconsistency",
            pattern="only the final monthly eligibility record differs",
        ))
    for index, member_rows in enumerate(
        members_for_demographic_drift[sex_drift_count:sex_drift_count + overlap_count], 1
    ):
        source = member_rows[len(member_rows) // 2]
        duplicate = copy.deepcopy(source)
        if payer in {"aetna", "priority_health"}:
            overlap_start = source["enrollment_month"] + timedelta(days=14)
            overlap_end = min(
                source["enrollment_end_date"],
                _month_end(_month_end(source["enrollment_month"]) + timedelta(days=1)),
            )
            if overlap_end <= overlap_start:
                continue
            duplicate["enrollment_start_date"] = overlap_start
            duplicate["enrollment_end_date"] = overlap_end
            dq_test_name = "eligibility__overlapping_enrollment_spans"
            field = "enrollment_start_date,enrollment_end_date"
            injected = f"{overlap_start.isoformat()}..{overlap_end.isoformat()}"
            severity: int | str = 2
            expected_action = (
                "preserve both same-plan finite spans and surface their overlap"
            )
            pattern = "a distinct same-plan finite span overlaps the member's existing coverage"
        else:
            dq_test_name = "connector__duplicate_eligibility_source_row"
            field = "source row"
            injected = "exact replay of one member-month"
            severity = "behavioral"
            expected_action = "deduplicate the replay without discarding other member-months"
            pattern = "one exact HCCI enrollment row is replayed in the source extract"
        enrollment.append(duplicate)
        manifest.append(_manifest_row(
            issue_id=f"ELIG-OVERLAP-{index:05d}",
            dq_test_name=dq_test_name, domain="eligibility",
            row=duplicate, field=field,
            original=(
                f"{source['enrollment_start_date'].isoformat()}.."
                f"{source['enrollment_end_date'].isoformat()}"
                if payer in {"aetna", "priority_health"}
                else source["enrollment_month"]
            ),
            injected=injected, severity=severity,
            expected_action=expected_action,
            pattern=pattern,
            evaluation_phase=(
                "post_connector_input_dq"
                if payer in {"aetna", "priority_health"}
                else "raw_source_deduplication"
            ),
        ))

    pharmacy_minority_source = _minority_source(pharmacy)
    _inject_scalar(
        selected=_choose((row for row in pharmacy if row["source_system"] == pharmacy_minority_source), rng, .0015, limit=55),
        manifest=manifest, issue_prefix="RX-NDC-INVALID",
        dq_test_name="pharmacy_claim__ndc_code_invalid", domain="pharmacy_claim",
        field="ndc_code", replacement=lambda row: str(row["ndc_code"])[:-1] + "O", severity=2,
        expected_action="retain and flag the invalid NDC rather than coercing it",
        pattern="letter O in an otherwise 11-character NDC",
    )
    _inject_scalar(
        selected=_choose((row for row in pharmacy if row["claim_status"] == "paid"), rng, .0007, limit=30),
        manifest=manifest, issue_prefix="RX-DAYS-SUPPLY",
        dq_test_name="pharmacy_claim__days_supply_not_positive", domain="pharmacy_claim",
        field="days_supply", replacement=0, severity=2,
        expected_action="surface impossible days supply",
        pattern="zero introduced on paid maintenance fills",
    )
    _inject_one_cent_paid_over_allowed(
        selected=_choose((row for row in pharmacy if row["allowed_amount"] > 0), rng, .0006, limit=25),
        manifest=manifest,
        issue_prefix="RX-PAID-GT-ALLOWED",
        dq_test_name="pharmacy_claim__paid_amount_gt_allowed_amount",
        domain="pharmacy_claim",
    )

    _add_adr_sequences(medical, rng, manifest, payer)
    dirty = CanonicalDataset(
        members=tuple(members), enrollment_months=tuple(enrollment),
        providers=tuple(providers), facilities=tuple(facilities),
        medical_claim_lines=tuple(medical), pharmacy_claims=tuple(pharmacy),
        start_date=dataset.start_date, end_date=dataset.end_date, seed=dataset.seed,
    )
    return dirty, tuple(manifest)
