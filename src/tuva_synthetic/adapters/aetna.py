"""Project the canonical cohort into Aetna Universal file layouts.

The public layouts are fixed-width extracts, but the generator emits typed raw
tables with the same physical field order.  Repeated technical names in the
published layouts are disambiguated in schema metadata while ``source_name``
retains Aetna's published name.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from tuva_synthetic.adapters.base import load_schema, project_rows
from tuva_synthetic.model import CanonicalDataset, OutputTable, Row


Transform = Callable[[Row], Any]


def _schema_dir(schema_root: Path) -> Path:
    root = Path(schema_root)
    return root / "aetna" if (root / "aetna").is_dir() else root


def _member_enriched(
    row: Row, members: dict[str, Row], subscribers: dict[str, Row]
) -> Row:
    member = members.get(str(row.get("member_id")), {})
    subscriber = subscribers.get(str(member.get("subscriber_id")), {})
    return {**member, **row, "_member": member, "_subscriber": subscriber}


def _provider_enriched(
    row: Row,
    providers: dict[str, Row],
    facilities: dict[str, Row],
    npi_field: str,
) -> Row:
    npi = row.get(npi_field)
    provider = providers.get(str(npi), {})
    facility = facilities.get(str(npi), {})
    return {**row, "_provider": provider, "_facility": facility}


def _nested(row: Row, container: str, key: str) -> Any:
    value = row.get(container) or {}
    return value.get(key)


def _indexed(row: Row, field: str, index: int) -> Any:
    values = row.get(field) or []
    return values[index] if index < len(values) else None


def _digits(value: Any, width: int) -> str | None:
    if value is None:
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    if digits:
        return digits[-width:].zfill(width)
    digest = int(sha256(str(value).encode()).hexdigest()[:16], 16)
    return str(digest % (10**width)).zfill(width)


def _stable_number(*values: Any, width: int) -> int:
    raw = "|".join("" if value is None else str(value) for value in values)
    return int(sha256(raw.encode()).hexdigest()[:16], 16) % (10**width)


def _short_code(value: Any, width: int) -> str | None:
    if value is None:
        return None
    cleaned = "".join(c for c in str(value).upper() if c.isalnum())
    return cleaned[:width] or None


def _product_code(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("_", "-")
    mapping = {
        "ppo": "PP",
        "hmo": "HM",
        "epo": "EP",
        "pos": "PO",
        "hdhp": "HD",
        "commercial": "CM",
        "medicare": "MA",
        "medicaid": "MD",
    }
    return mapping.get(normalized, _short_code(value, 2))


def _funding_code(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("_", "-")
    if normalized in {"self", "self-funded", "aso"}:
        return "S"
    if normalized in {"fully-insured", "fully insured", "insured"}:
        return "F"
    return _short_code(value, 1)


def _relationship_code(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return {
        "self": "1",
        "subscriber": "1",
        "18": "1",
        "spouse": "2",
        "01": "2",
        "child": "3",
        "19": "3",
        "other": "4",
    }.get(normalized, _short_code(value, 1))


def _coverage_code(row: Row) -> str | None:
    relationship = _relationship_code(row.get("relation_code"))
    return {"1": "E", "2": "S", "3": "C", "4": "F"}.get(relationship)


def _flag(value: Any, true_code: str = "Y", false_code: str = "N") -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return true_code if value else false_code
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "in", "generic", "mail"}:
        return true_code
    if normalized in {"0", "false", "f", "no", "n", "out", "brand", "retail"}:
        return false_code
    # Preserve deliberately malformed canonical values for downstream DQ tests.
    return str(value)


def _network_code(value: Any, in_code: str = "P", out_code: str = "N") -> str | None:
    return _flag(value, in_code, out_code)


def _claim_status(row: Row) -> str | None:
    value = row.get("claim_status")
    if value is None and row.get("denied_flag") is not None:
        value = "denied" if row.get("denied_flag") else "paid"
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return {
        "paid": "P",
        "final": "P",
        "denied": "D",
        "reversed": "R",
        "reversal": "R",
        "void": "R",
        "adjusted": "A",
        "replacement": "P",
        "paid_after_reject": "P",
    }.get(normalized, str(value))


def _adjustment_code(row: Row) -> str:
    action = str(row.get("final_action") or "").strip().lower()
    status = str(row.get("claim_status") or "").strip().lower()
    sequence = int(row.get("adjustment_sequence") or 0)
    if action in {"reversal", "reversed", "void"} or status in {
        "reversal",
        "reversed",
        "void",
    }:
        return "R"
    if sequence > 0 or action in {"adjustment", "adjusted", "replacement"}:
        return "A"
    return "O"


def _reversal_code(row: Row) -> str | None:
    action = str(row.get("final_action") or "").strip().lower()
    status = str(row.get("claim_status") or "").strip().lower()
    return (
        "RV"
        if action in {"reversal", "reversed", "void"}
        or status in {"reversal", "reversed", "void"}
        else None
    )


def _file_id(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return {
        "aetna": "03",
        "aetna_core": "03",
        "aetna_legacy": "01",
    }.get(normalized, _short_code(value, 2))


def _subtract(left: Any, right: Any) -> Any:
    if left is None or right is None:
        return None
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        return Decimal(str(left)) - Decimal(str(right))
    return left - right


def _received_date(row: Row) -> date | None:
    paid = row.get("paid_date")
    return paid - timedelta(days=7) if isinstance(paid, date) else None


def _service_code(value: Any) -> str | None:
    mapping = {
        "inpatient": "30",
        "outpatient": "20",
        "emergency": "23",
        "professional": "01",
    }
    return mapping.get(str(value).lower(), _short_code(value, 2)) if value else None


def _reason_code(row: Row) -> str | None:
    if bool(row.get("denied_flag")):
        return "D001"
    if _adjustment_code(row) == "A":
        return "A001"
    if _adjustment_code(row) == "R":
        return "R001"
    return None


def _provider_name(row: Row) -> str | None:
    provider = row.get("_provider") or {}
    if provider:
        name = " ".join(
            str(value).strip()
            for value in (provider.get("last_name"), provider.get("first_name"))
            if value
        )
        if name:
            return name
    return _nested(row, "_facility", "name")


def _medical_transforms() -> dict[str, Transform]:
    transforms: dict[str, Transform] = {
        "file_id": lambda r: _file_id(r.get("source_system")),
        "clm_ln_type_cd": _adjustment_code,
        "non_prfrrd_srv_cd": lambda r: _network_code(r.get("network_flag")),
        "plsp_prod_cd": lambda r: _product_code(r.get("product")),
        "product_ln_cd": lambda r: _product_code(r.get("product")),
        "benefit_tier": _coverage_code,
        "fund_ctg_cd": lambda r: _funding_code(r.get("funding")),
        "subscriber_last_nm": lambda r: _nested(r, "_subscriber", "last_name"),
        "subscriber_first_nm": lambda r: _nested(r, "_subscriber", "first_name"),
        "subscriber_gender_cd": lambda r: _nested(r, "_subscriber", "sex"),
        "subscriber_brth_dt": lambda r: _nested(r, "_subscriber", "birth_date"),
        "subs_zip_cd": lambda r: _nested(r, "_subscriber", "zip_code"),
        "subs_st_postal_cd": lambda r: _nested(r, "_subscriber", "state"),
        "coverage_type_cd": _coverage_code,
        "member_number": lambda r: _digits(r.get("member_id"), 2),
        "member_last_nm": lambda r: _nested(r, "_member", "last_name"),
        "member_first_nm": lambda r: _nested(r, "_member", "first_name"),
        "mbr_gender_cd": lambda r: _nested(r, "_member", "sex"),
        "mbr_rtp_type_cd": lambda r: _relationship_code(_nested(r, "_member", "relation_code")),
        "birth_dt": lambda r: _nested(r, "_member", "birth_date"),
        "acas_gen_seq_nbr": lambda r: str(int(r.get("adjustment_sequence") or 0)).zfill(2),
        "prev_clm_seg_id": lambda r: str(max(0, int(r.get("adjustment_sequence") or 0) - 1)).zfill(2),
        "claim_line_id": lambda r: _stable_number(r.get("claim_id"), r.get("adjustment_sequence"), r.get("line_number"), width=12),
        "ntwk_srv_area_id": lambda r: _short_code(r.get("plan_id"), 5),
        "paid_prvdr_nsa_id": lambda r: "IN001" if _flag(r.get("network_flag")) == "Y" else "OUT01",
        "servicing_provider_tax_id_format_cd": lambda r: "1" if _nested(r, "_provider", "tin") else None,
        "servicing_provider_tax_id_nbr": lambda r: _nested(r, "_provider", "tin") or _nested(r, "_facility", "tin"),
        "srv_prvdr_id": lambda r: _digits(r.get("rendering_npi"), 7),
        "servicing_provider_print_nm": _provider_name,
        "specialty_cd": lambda r: _short_code(_nested(r, "_provider", "specialty"), 5),
        "paid_prvdr_par_cd": lambda r: _network_code(r.get("network_flag"), "Y", "N"),
        "received_dt": _received_date,
        "prcdr_type_cd": lambda r: "C" if r.get("hcpcs_code") else None,
        "type_srv_cd": lambda r: _service_code(r.get("setting")),
        "benefit_cd": lambda r: _short_code(r.get("service_category"), 3),
        "not_covered_amt_1": lambda r: _subtract(r.get("charge_amount"), r.get("allowed_amount")),
        "clm_ln_msg_cd_1": _reason_code,
        "negot_savings_amt": lambda r: _subtract(r.get("charge_amount"), r.get("allowed_amount")),
        "pri_payer_cvg_cd": lambda r: _flag(r.get("primary_coverage_indicator"), "P", "S"),
        "cob_type_cd": lambda r: "O" if r.get("other_payer_amount") not in {None, 0, Decimal("0")} else None,
        "cob_cd": lambda r: "Y" if r.get("other_payer_amount") not in {None, 0, Decimal("0")} else "N",
        "src_member_id": lambda r: _nested(r, "_member", "subscriber_id"),
        "clm_ln_status_cd": _claim_status,
        "reversal_cd": _reversal_code,
        "admit_cnt": lambda r: "01" if r.get("admission_date") else None,
        "type_class_cd": lambda r: _short_code(r.get("provider_category"), 1),
        "specialty_ctg_cd": lambda r: _short_code(_nested(r, "_provider", "specialty") or r.get("provider_category"), 4),
        "icd_10_ind": lambda r: "Y" if r.get("diagnosis_codes") else None,
    }
    for index, name in enumerate(("poa_cd_1", "poa_cd_2", "poa_cd_3")):
        transforms[name] = lambda row, index=index: _indexed(row, "poa_codes", index)
    for index in range(3, 10):
        transforms[f"poa_cd_{index + 1}"] = lambda row, index=index: _indexed(row, "poa_codes", index)
    diagnosis_names = ["pri_icd9_dx_cd", *[f"icd9_dx_cd_{index}" for index in range(2, 11)]]
    for index, name in enumerate(diagnosis_names):
        transforms[name] = lambda row, index=index: _indexed(row, "diagnosis_codes", index)
    for index in range(6):
        transforms[f"icd9_prcdr_cd_{index + 1}"] = lambda row, index=index: _indexed(row, "procedure_codes", index)
    return transforms


def _eligibility_transforms(providers: dict[str, Row]) -> dict[str, Transform]:
    return {
        "eff_dt": lambda r: r.get("enrollment_month").strftime("%Y%m") if isinstance(r.get("enrollment_month"), date) else r.get("enrollment_month"),
        "mbr_rtp_type_cd": lambda r: _relationship_code(r.get("relation_code")),
        "subscriber_last_nm": lambda r: _nested(r, "_subscriber", "last_name"),
        "subscriber_first_nm": lambda r: _nested(r, "_subscriber", "first_name"),
        "gender_cd": lambda r: _nested(r, "_subscriber", "sex"),
        "subscriber_brth_dt": lambda r: _nested(r, "_subscriber", "birth_date"),
        "subs_zip_cd": lambda r: _nested(r, "_subscriber", "zip_code"),
        "subs_st_postal_cd": lambda r: _nested(r, "_subscriber", "state"),
        "file_id": lambda r: _file_id(r.get("source_system")),
        "plsp_prod_cd": lambda r: _product_code(r.get("product")),
        "product_ln_cd": lambda r: _product_code(r.get("product")),
        "business_ln_cd": lambda r: _product_code(r.get("product")),
        "fund_ctg_cd": lambda r: _funding_code(r.get("funding")),
        "coverage_type_cd": _coverage_code,
        "ntwk_srv_area_id": lambda r: _short_code(r.get("plan_id"), 5),
        "drug_ind": lambda r: _flag(r.get("rx_coverage")),
        "sbstnc_abuse_ind": lambda r: _flag(r.get("mh_coverage")),
        "mental_health_ind": lambda r: _flag(r.get("mh_coverage")),
        "pcp_tax_id_nbr": lambda r: providers.get(str(r.get("pcp_npi")), {}).get("tin"),
        "pcp_prvdr_id": lambda r: _digits(r.get("pcp_npi"), 7),
        "pcp_print_nm": lambda r: " ".join(
            str(value).strip()
            for value in (
                providers.get(str(r.get("pcp_npi")), {}).get("last_name"),
                providers.get(str(r.get("pcp_npi")), {}).get("first_name"),
            )
            if value
        ) or None,
        "pcp_state_postal_cd": lambda r: providers.get(str(r.get("pcp_npi")), {}).get("state"),
        "pcp_zip_cd": lambda r: providers.get(str(r.get("pcp_npi")), {}).get("zip_code"),
        "specialty_ctg_cd": lambda r: _short_code(providers.get(str(r.get("pcp_npi")), {}).get("specialty"), 5),
    }


def _pharmacy_transforms() -> dict[str, Transform]:
    return {
        "product_ln_cd": lambda r: _product_code(r.get("product")),
        "rx_product_cd": lambda r: _short_code(r.get("product") or "RX", 5),
        "fund_ctg_cd": lambda r: _funding_code(r.get("funding")),
        "option_cd": _coverage_code,
        "subscriber_last_name": lambda r: _nested(r, "_subscriber", "last_name"),
        "subscriber_first_name": lambda r: _nested(r, "_subscriber", "first_name"),
        "subs_zip_cd": lambda r: _nested(r, "_subscriber", "zip_code"),
        "src_rx_member_id": lambda r: r.get("member_id"),
        "member_last_name": lambda r: _nested(r, "_member", "last_name"),
        "member_first_name": lambda r: _nested(r, "_member", "first_name"),
        "src_mbr_gender_cd": lambda r: _nested(r, "_member", "sex"),
        "mbr_rpt_type_cd": lambda r: _relationship_code(_nested(r, "_member", "relation_code")),
        "src_mbr_birth_dt": lambda r: _nested(r, "_member", "birth_date"),
        "clm_status": _claim_status,
        "ee_ntwk_srv_area_id": lambda r: _short_code(r.get("plan_id"), 5),
        "office_id": lambda r: _stable_number(r.get("group_id"), width=12),
        "sort_name": lambda r: r.get("group_name"),
        "specialty_ctg_cd": lambda r: _short_code(_nested(r, "_provider", "specialty"), 4),
        "nabp_nbr": lambda r: _digits(r.get("pharmacy_npi"), 7),
        "phm_zip_cd": lambda r: _nested(r, "_facility", "zip_code") or _nested(r, "_member", "zip_code"),
        "generic_cd": lambda r: _flag(r.get("generic_flag"), "G", "B"),
        "source_type_cd": lambda r: _flag(r.get("generic_flag"), "M", "S"),
        "retail_mod_cd": lambda r: _flag(r.get("mail_order_flag"), "M", "R"),
        "maint_drug_cd": lambda r: _flag(r.get("maintenance_flag")),
        "prescription_nbr": lambda r: _digits(r.get("original_claim_id") or r.get("claim_id"), 12),
    }


def adapt(dataset: CanonicalDataset, schema_root: Path) -> dict[str, OutputTable]:
    """Return all three Aetna Universal tables in published field order."""

    root = _schema_dir(Path(schema_root))
    medical_schema = load_schema(root / "universal_medical_dental.json")
    pharmacy_schema = load_schema(root / "universal_pharmacy.json")
    eligibility_schema = load_schema(root / "universal_medical_eligibility.json")

    members = {str(row["member_id"]): row for row in dataset.members}
    subscribers = {
        str(row["subscriber_id"]): row
        for row in dataset.members
        if str(row.get("relation_code", "")).lower() in {"18", "self", "subscriber"}
    }
    providers = {str(row["npi"]): row for row in dataset.providers if row.get("npi")}
    facilities = {str(row["npi"]): row for row in dataset.facilities if row.get("npi")}

    medical_rows = tuple(
        _provider_enriched(
            _member_enriched(row, members, subscribers),
            providers,
            facilities,
            "rendering_npi",
        )
        for row in dataset.medical_claim_lines
    )
    pharmacy_rows = tuple(
        _provider_enriched(
            _member_enriched(row, members, subscribers),
            providers,
            facilities,
            "prescriber_npi",
        )
        for row in dataset.pharmacy_claims
    )
    eligibility_rows = tuple(
        _member_enriched(row, members, subscribers)
        for row in dataset.enrollment_months
    )

    return {
        medical_schema["table"]: project_rows(
            table_name=medical_schema["table"],
            schema=medical_schema,
            source_rows=medical_rows,
            transforms=_medical_transforms(),
        ),
        pharmacy_schema["table"]: project_rows(
            table_name=pharmacy_schema["table"],
            schema=pharmacy_schema,
            source_rows=pharmacy_rows,
            transforms=_pharmacy_transforms(),
        ),
        eligibility_schema["table"]: project_rows(
            table_name=eligibility_schema["table"],
            schema=eligibility_schema,
            source_rows=eligibility_rows,
            transforms=_eligibility_transforms(providers),
        ),
    }
