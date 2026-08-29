"""Project the canonical cohort into Priority Health's public APCD layouts."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Callable

from tuva_synthetic.adapters.base import load_schema, project_rows
from tuva_synthetic.model import CanonicalDataset, OutputTable, Row


Transform = Callable[[Row], Any]


def _stable_number(value: Any, *, digits: int, salt: str = "") -> str:
    digest = sha256(f"priority-health|{salt}|{value}".encode()).hexdigest()
    modulus = 10**digits
    return f"{int(digest[:16], 16) % modulus:0{digits}d}"


def _synthetic_ssn(value: Any) -> str:
    """Return a deterministic, visibly non-issued SSN-shaped identifier."""

    return "900" + _stable_number(value, digits=6, salt="ssn")


def _synthetic_address(value: Any) -> str:
    number = 100 + int(_stable_number(value, digits=4, salt="address")) % 9800
    return f"{number} Synthetic Health Ave"


def _synthetic_phone(value: Any) -> str:
    # 555-01xx is reserved for fictional use in North America.
    suffix = 100 + int(_stable_number(value, digits=2, salt="phone"))
    return f"616555{suffix:04d}"


def _yn(value: Any) -> str:
    if isinstance(value, str):
        return "Y" if value.strip().lower() in {"1", "true", "t", "yes", "y"} else "N"
    return "Y" if bool(value) else "N"


def _relationship(value: Any) -> str:
    normalized = str(value or "0").strip().lower()
    return {
        "18": "1",
        "01": "2",
        "19": "3",
        "self": "1",
        "subscriber": "1",
        "spouse": "2",
        "child": "3",
        "dependent": "3",
        "adopted child": "10",
        "foster child": "11",
        "stepchild": "17",
        "life partner": "28",
    }.get(normalized, str(value or "0"))


def _gender(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"f", "female"}:
        return "F"
    if normalized in {"m", "male"}:
        return "M"
    return None if not normalized else str(value)[:1].upper()


def _city(state: Any, zip_code: Any = None) -> str:
    state_code = str(state or "MI").upper()
    if state_code == "MI":
        prefix = str(zip_code or "")[:3]
        if prefix in {"480", "481", "482", "483"}:
            return "Detroit"
        if prefix in {"488", "489"}:
            return "Lansing"
        if prefix in {"490", "491"}:
            return "Kalamazoo"
        if prefix in {"496", "497"}:
            return "Traverse City"
        return "Grand Rapids"
    return {
        "IL": "Chicago",
        "IN": "Indianapolis",
        "OH": "Columbus",
        "WI": "Milwaukee",
    }.get(state_code, "Grand Rapids")


def _county(state: Any, zip_code: Any = None) -> str:
    if str(state or "MI").upper() != "MI":
        return "Out of State"
    prefix = str(zip_code or "")[:3]
    return {
        "480": "Macomb",
        "481": "Wayne",
        "482": "Wayne",
        "483": "Oakland",
        "488": "Ingham",
        "489": "Ingham",
        "490": "Kalamazoo",
        "491": "Berrien",
        "496": "Grand Traverse",
        "497": "Emmet",
    }.get(prefix, "Kent")


def _insurance_code(row: Row) -> str:
    product = str(row.get("product") or "").lower()
    plan_type = str(row.get("plan_type") or "").lower()
    funding = str(row.get("funding") or "").lower()
    if "medicaid" in product or "michild" in product:
        return "CAID"
    if "medicare" in product:
        return "CARE"
    self_funded = "self" in funding or funding == "aso"
    coverage = f"{product} {plan_type}"
    if "epo" in coverage:
        return "SEPO" if self_funded else "FEPO"
    if "pos" in coverage:
        return "SPOS" if self_funded else "FPOS"
    if "hmo" in coverage:
        return "SHMO" if self_funded else "FHMO"
    if "ppo" in coverage or "hdhp" in coverage:
        return "SPPO" if self_funded else "FPPO"
    if "individual" in product:
        return "SIND"
    return "0"


def _market_category(row: Row) -> str:
    product = str(row.get("product") or "").lower()
    if "medicare" in product or "medicaid" in product or "michild" in product:
        return "PUB"
    if "individual" in product:
        return "IND"
    return "GRP"


def _claim_status(row: Row) -> str:
    status = str(row.get("claim_status") or "").lower()
    return "2" if row.get("denied_flag") or "denied" in status else "1"


def _frequency(row: Row) -> str:
    sequence = int(row.get("adjustment_sequence") or 0)
    status = str(row.get("claim_status") or "").lower()
    paid = row.get("plan_paid_amount")
    if "revers" in status or (sequence > 0 and paid is not None and float(paid) < 0):
        return "8"
    return "7" if sequence > 0 else "1"


def _previous_claim(row: Row) -> Any:
    if int(row.get("adjustment_sequence") or 0) <= 0:
        return None
    return row.get("original_claim_id")


def _member_suffix(row: Row) -> str:
    if _relationship(row.get("relation_code")) == "1":
        return "00"
    return _stable_number(row.get("member_id"), digits=2, salt="suffix")


def _hour(row: Row, date_field: str, salt: str) -> str | None:
    if row.get(date_field) is None:
        return None
    hour = int(_stable_number(row.get("claim_id"), digits=2, salt=salt)) % 24
    return f"{hour:02d}"


def _at(values: Any, index: int) -> Any:
    if not isinstance(values, (list, tuple)) or index >= len(values):
        return None
    return values[index]


def _provider_value(row: Row, role: str, field: str) -> Any:
    provider = row.get(role) or {}
    return provider.get(field)


def _provider_name(provider: Row | None) -> str | None:
    if not provider:
        return None
    values = [provider.get("first_name"), provider.get("last_name")]
    value = " ".join(str(part) for part in values if part)
    return value or provider.get("name")


def _risk_group(row: Row) -> str:
    risk = float((row.get("_member") or {}).get("risk_score") or 0)
    if risk >= 2.0:
        return "High Risk"
    if risk >= 1.0:
        return "Moderate Risk"
    return "Standard Risk"


def _service_code(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return cleaned[:20] or None


def _drug_route(row: Row) -> str:
    text = f"{row.get('drug_name', '')} {row.get('therapeutic_class', '')}".lower()
    if any(word in text for word in ("insulin", "inject", "semaglutide")):
        return "SC"
    if any(word in text for word in ("inhal", "albuterol", "fluticasone")):
        return "IN"
    if any(word in text for word in ("ophthalm", "eye drop")):
        return "OP"
    if any(word in text for word in ("cream", "ointment", "topical")):
        return "EX"
    return "OR"


def _drug_unit(row: Row) -> str:
    text = str(row.get("drug_name") or "").lower()
    if "insulin" in text:
        return "UNIT"
    if any(word in text for word in ("solution", "suspension", "inhal")):
        return "ML"
    return "MG"


def _drug_strength(row: Row) -> float | None:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:MG|MCG|G|ML|UNIT)", str(row.get("drug_name") or ""), re.I)
    return float(match.group(1)) if match else None


def _controlled_schedule(row: Row) -> int:
    text = f"{row.get('drug_name', '')} {row.get('therapeutic_class', '')}".lower()
    if any(word in text for word in ("oxycodone", "hydrocodone", "morphine", "fentanyl")):
        return 2
    if any(word in text for word in ("amphetamine", "methylphenidate")):
        return 2
    if any(word in text for word in ("alprazolam", "lorazepam", "clonazepam")):
        return 4
    return 0


def _drug_supergroup(row: Row) -> tuple[int, str]:
    text = str(row.get("therapeutic_class") or "").lower()
    groups = [
        (1, "Anti-Infective Agents", ("antibi", "antiviral", "anti-infect")),
        (2, "Biologicals", ("biologic", "vaccine")),
        (3, "Antineoplastic Agents", ("oncolog", "antineoplastic")),
        (4, "Endocrine and Metabolic Drugs", ("diabet", "endocr", "thyroid")),
        (5, "Cardiovascular Agents", ("cardio", "statin", "hypertension")),
        (6, "Respiratory Agents", ("respirat", "asthma", "copd")),
        (7, "Gastrointestinal Agents", ("gastro", "acid")),
        (9, "Central Nervous System Drugs", ("neuro", "depress", "anxiety")),
        (12, "Analgesics and Anesthetics", ("analges", "opioid", "pain")),
    ]
    for identifier, description, terms in groups:
        if any(term in text for term in terms):
            return identifier, description
    return 17, "Miscellaneous Products"


def _benefit(row: Row, benefit: str) -> float:
    public = _market_category(row) == "PUB"
    high_deductible = any(
        marker in f"{row.get('plan_name', '')} {row.get('product', '')}".lower()
        for marker in ("hsa", "hdhp")
    )
    values = {
        "office": 10.0 if public else 25.0,
        "er": 50.0 if public else 250.0,
        "specialist": 20.0 if public else 50.0,
        "coinsurance": 0.1 if public else 0.2,
        "individual_deductible": 250.0 if public else (3000.0 if high_deductible else 1000.0),
        "family_deductible": 500.0 if public else (6000.0 if high_deductible else 2000.0),
        "rx_brand": 15.0 if public else 45.0,
        "rx_generic": 4.0 if public else 10.0,
        "htr": 50.0 if public else 150.0,
        "urgent": 20.0 if public else 75.0,
    }
    return values[benefit]


def _schema_directory(schema_root: str | Path) -> Path:
    root = Path(schema_root)
    candidate = root / "priority_health"
    return candidate if candidate.is_dir() else root


def _lookups(dataset: CanonicalDataset) -> dict[str, Any]:
    members = {str(row["member_id"]): row for row in dataset.members}
    subscribers: dict[str, Row] = {}
    for row in dataset.members:
        contract = str(row.get("subscriber_id") or row["member_id"])
        if _relationship(row.get("relation_code")) == "1" or contract not in subscribers:
            subscribers[contract] = row
    providers = {str(row.get("npi")): row for row in dataset.providers if row.get("npi")}
    facilities = {str(row.get("npi")): row for row in dataset.facilities if row.get("npi")}
    enrollment: dict[tuple[str, int, int], Row] = {}
    latest: dict[str, Row] = {}
    for row in dataset.enrollment_months:
        month = row.get("enrollment_month")
        if isinstance(month, date):
            enrollment[(str(row["member_id"]), month.year, month.month)] = row
        latest[str(row["member_id"])] = row
    return {
        "members": members,
        "subscribers": subscribers,
        "providers": providers,
        "facilities": facilities,
        "enrollment": enrollment,
        "latest_enrollment": latest,
    }


def _enrollment_for(lookups: dict[str, Any], member_id: Any, on_date: Any) -> Row:
    if isinstance(on_date, date):
        exact = lookups["enrollment"].get((str(member_id), on_date.year, on_date.month))
        if exact:
            return exact
    return lookups["latest_enrollment"].get(str(member_id), {})


def _enrich_claim(row: Row, lookups: dict[str, Any], *, pharmacy: bool) -> Row:
    member = lookups["members"].get(str(row.get("member_id")), {})
    subscriber_key = str(member.get("subscriber_id") or row.get("member_id"))
    subscriber = lookups["subscribers"].get(subscriber_key, member)
    date_key = row.get("fill_date") if pharmacy else row.get("first_service_date")
    enrollment = _enrollment_for(lookups, row.get("member_id"), date_key)
    pcp = lookups["providers"].get(str(enrollment.get("pcp_npi")), {})
    enriched: Row = {**member, **row}
    enriched.update(
        {
            "_member": member,
            "_subscriber": subscriber,
            "_enrollment": enrollment,
            "_pcp": pcp,
        }
    )
    if pharmacy:
        npi = str(row.get("pharmacy_npi") or "")
        pharmacy_row = lookups["facilities"].get(npi) or lookups["providers"].get(npi) or {}
        enriched["_pharmacy"] = pharmacy_row
        enriched["_prescriber"] = lookups["providers"].get(str(row.get("prescriber_npi")), {})
    else:
        service_npi = str(row.get("rendering_npi") or row.get("facility_npi") or row.get("billing_npi") or "")
        billing_npi = str(row.get("billing_npi") or row.get("facility_npi") or "")
        enriched["_service_provider"] = lookups["providers"].get(service_npi) or lookups["facilities"].get(service_npi) or {}
        enriched["_billing_provider"] = lookups["providers"].get(billing_npi) or lookups["facilities"].get(billing_npi) or {}
        enriched["_facility"] = lookups["facilities"].get(str(row.get("facility_npi") or ""), {})
    return enriched


def _enrich_eligibility(row: Row, lookups: dict[str, Any]) -> Row:
    member = lookups["members"].get(str(row.get("member_id")), {})
    subscriber_key = str(row.get("subscriber_id") or member.get("subscriber_id") or row.get("member_id"))
    subscriber = lookups["subscribers"].get(subscriber_key, member)
    pcp = lookups["providers"].get(str(row.get("pcp_npi")), {})
    return {**member, **row, "_member": member, "_subscriber": subscriber, "_pcp": pcp}


def _medical_transforms() -> dict[str, Transform]:
    transforms: dict[str, Transform] = {
        "APCD_INSURANCE_TYPE_CD": _insurance_code,
        "APCD_VERSION_NUM": lambda r: int(r.get("adjustment_sequence") or 0),
        "APCD_SUBSCRIBER_SSN": lambda r: _synthetic_ssn(r.get("subscriber_id")),
        "APCD_MEMBER_SUFFIX": _member_suffix,
        "APCD_RELATIONSHIP_CD": lambda r: _relationship(r.get("relation_code")),
        "APCD_MEMBER_GENDER": lambda r: _gender(r.get("sex")),
        "APCD_MEMBER_CITY": lambda r: _city(r.get("state"), r.get("zip_code")),
        "APCD_ADMIT_HOUR": lambda r: _hour(r, "admission_date", "admit-hour"),
        "APCD_DISCHARGE_HR": lambda r: _hour(r, "discharge_date", "discharge-hour"),
        "APCD_SERV_PROV_NUM": lambda r: _provider_value(r, "_service_provider", "provider_id") or r.get("rendering_npi"),
        "APCD_SERV_PROV_TIN": lambda r: _provider_value(r, "_service_provider", "tin"),
        "APCD_SERV_PROV_FIRST_NAME": lambda r: _provider_value(r, "_service_provider", "first_name"),
        "APCD_SERV_PROV_MID_NAME": lambda r: _provider_value(r, "_service_provider", "middle_name"),
        "APCD_SERV_PROV_LAST_NAME": lambda r: _provider_value(r, "_service_provider", "last_name") or _provider_value(r, "_service_provider", "name"),
        "APCD_SERV_PROV_SUFFIX": lambda r: _provider_value(r, "_service_provider", "suffix"),
        "APCD_SERV_PROV_SPECIALTY": lambda r: _provider_value(r, "_service_provider", "specialty") or r.get("provider_category"),
        "APCD_SERV_PROV_CITY": lambda r: _city(r.get("provider_state"), r.get("provider_zip_code")),
        "APCD_CLAIM_STATUS": _claim_status,
        "APCD_ADMITTING_DIAGNOSIS": lambda r: _at(r.get("diagnosis_codes"), 0) if r.get("admission_date") else None,
        "APCD_PRINCIPAL_DIAGNOSIS": lambda r: _at(r.get("diagnosis_codes"), 0),
        "APCD_ICD_PROC_CD": lambda r: _at(r.get("procedure_codes"), 0),
        "APCD_PAT_ACCT_CNTRL_NUM": lambda r: "PA" + _stable_number(r.get("claim_id"), digits=12, salt="patient-account"),
        "APCD_APR_DRG": lambda r: r.get("drg_code") if "medicaid" in str(r.get("product") or "").lower() else None,
        "APCD_BILLING_PROV_NUM": lambda r: _provider_value(r, "_billing_provider", "tin") or r.get("billing_npi"),
        "APCD_BILLING_PROV_LAST_NAME": lambda r: _provider_value(r, "_billing_provider", "last_name") or _provider_value(r, "_billing_provider", "name"),
        "APCD_SUBSCR_LAST_NAME": lambda r: _provider_value(r, "_subscriber", "last_name"),
        "APCD_SUBSCR_FIRST_NAME": lambda r: _provider_value(r, "_subscriber", "first_name"),
        "APCD_SUBSCR_MIDDLE_INIT": lambda r: str(_provider_value(r, "_subscriber", "middle_name") or "")[:1] or None,
        "APCD_MEMBER_LAST_NAME": lambda r: _provider_value(r, "_member", "last_name"),
        "APCD_MEMBER_FIRST_NAME": lambda r: _provider_value(r, "_member", "first_name"),
        "APCD_MEMBER_MIDDLE_INIT": lambda r: str(_provider_value(r, "_member", "middle_name") or "")[:1] or None,
        "MDC_PAYER_CLM_CNTRL_NUM_PREV": _previous_claim,
        "MDC_MEMBER_SSN": lambda r: _synthetic_ssn(r.get("member_id")),
        "MDC_PROC_MOD_3": lambda r: r.get("modifier_3"),
        "MDC_PROC_MOD_4": lambda r: r.get("modifier_4"),
        "MDC_PROF_FAC_FLG": lambda r: "F" if r.get("claim_type") == "institutional" else "P",
        "MDC_FREQUENCY": _frequency,
        "MDC_ICD_VERS_IND": lambda r: "10" if r.get("diagnosis_codes") else None,
        "PH_CAPITATED_SERV_IND": lambda r: "Y" if "capitat" in str(r.get("service_category") or "").lower() else "N",
        "PH_PROV_GROUP_PCP": lambda r: _provider_value(r, "_pcp", "network_id") or "Priority Health Provider Group",
        "PH_PCP_NAME": lambda r: _provider_name(r.get("_pcp")),
        "PH_RISK_GROUP": _risk_group,
        "PH_PCP_NPI": lambda r: int(_provider_value(r, "_pcp", "npi")) if str(_provider_value(r, "_pcp", "npi") or "").isdigit() else None,
        "PH_APPROVED_AMOUNT": lambda r: r.get("plan_paid_amount"),
        "PH_BILLING_FAC_NAME": lambda r: _provider_value(r, "_facility", "name") or _provider_name(r.get("_billing_provider")),
        "PH_REPORT_CAT_CODE": lambda r: _service_code(r.get("service_category")),
        "PH_REPORT_CAT_DESC": lambda r: r.get("service_category"),
        "APCD_BUS_SUBCAT_CD": _insurance_code,
    }
    for index in range(1, 13):
        transforms[f"APCD_OTHER_DIAGNOSIS_{index}"] = lambda r, i=index: _at(r.get("diagnosis_codes"), i)
    for index in range(13, 31):
        transforms[f"MDC_OTHER_DIAGNOSIS_{index}"] = lambda r, i=index: _at(r.get("diagnosis_codes"), i)
    for index in range(1, 6):
        transforms[f"MDC_OTHR_ICD_PROC_CD_{index}"] = lambda r, i=index: _at(r.get("procedure_codes"), i)
    transforms["MDC_POA_ADMIT_DIAGNOSIS"] = lambda r: _at(r.get("poa_codes"), 0) if r.get("admission_date") else None
    transforms["MDC_POA_PRIMARY_DIAGNOSIS"] = lambda r: _at(r.get("poa_codes"), 0)
    for index in range(1, 7):
        transforms[f"MDC_POA_OTHER_DIAGNOSIS_{index:02d}"] = lambda r, i=index: _at(r.get("poa_codes"), i)
    return transforms


def _pharmacy_transforms() -> dict[str, Transform]:
    def pharmacy_value(row: Row, field: str) -> Any:
        return _provider_value(row, "_pharmacy", field)

    def prescriber_value(row: Row, field: str) -> Any:
        return _provider_value(row, "_prescriber", field)

    return {
        "APCD_Insurance_Type_Code": _insurance_code,
        "APCD_Version_Number": lambda r: int(r.get("adjustment_sequence") or 0),
        "APCD_Subscriber_SSN": lambda r: _synthetic_ssn(r.get("subscriber_id")),
        "APCD_Member_Suffix": _member_suffix,
        "APCD_Relationship_Code": lambda r: _relationship(r.get("relation_code")),
        "APCD_Member_Gender": lambda r: _gender(r.get("sex")),
        "APCD_Member_City": lambda r: _city(r.get("state"), r.get("zip_code")),
        "APCD_Pharmacy_Number": lambda r: int(_stable_number(r.get("pharmacy_npi"), digits=7, salt="pharmacy-number")),
        "APCD_Pharmacy_Tax_ID_Number": lambda r: pharmacy_value(r, "tin") or _stable_number(r.get("pharmacy_npi"), digits=9, salt="pharmacy-tin"),
        "APCD_Pharmacy_Name": lambda r: pharmacy_value(r, "name") or f"Synthetic Pharmacy {_stable_number(r.get('pharmacy_npi'), digits=4)}",
        "APCD_Pharmacy_Location_City": lambda r: pharmacy_value(r, "city") or _city(pharmacy_value(r, "state") or r.get("state"), pharmacy_value(r, "zip_code")),
        "APCD_Pharmacy_Location_State": lambda r: pharmacy_value(r, "state") or r.get("state"),
        "APCD_Pharmacy_ZIP_Code": lambda r: pharmacy_value(r, "zip_code") or r.get("zip_code"),
        "APCD_Claim_Status": _claim_status,
        "APCD_Generic_Drug_Indicator": lambda r: _yn(r.get("generic_flag")),
        "APCD_Mail_Order_pharmacy": lambda r: _yn(r.get("mail_order_flag")),
        "APCD_Prescribing_Physician_First_Name": lambda r: prescriber_value(r, "first_name"),
        "APCD_Prescribing_Physician_Middle_Name": lambda r: prescriber_value(r, "middle_name"),
        "APCD_Prescribing_Physician_Last_Name": lambda r: prescriber_value(r, "last_name"),
        "APCD_Prescribing_Physician_DEA_Number": lambda r: "AP" + _stable_number(r.get("prescriber_npi"), digits=7, salt="dea"),
        "APCD_Prescribing_Physician_License_Number": lambda r: _stable_number(r.get("prescriber_npi"), digits=10, salt="license"),
        "APCD_Prescribing_Physician_Street_Address": lambda r: _synthetic_address(r.get("prescriber_npi")),
        "APCD_Prescribing_Physician_Street_Address_2": lambda r: None,
        "APCD_Prescribing_Physician_City": lambda r: _city(prescriber_value(r, "state"), prescriber_value(r, "zip_code")),
        "APCD_Prescribing_Physician_State": lambda r: prescriber_value(r, "state"),
        "APCD_Prescribing_Physician_Zip": lambda r: prescriber_value(r, "zip_code"),
        "APCD_Script_number": lambda r: int(_stable_number(r.get("claim_id"), digits=7, salt="script")),
        "APCD_Single_Or_Multiple_Source_Indicator": lambda r: "Y" if _yn(r.get("generic_flag")) == "Y" else "N",
        "APCD_Subscriber_Last_Name": lambda r: _provider_value(r, "_subscriber", "last_name"),
        "APCD_Subscriber_First_Name": lambda r: _provider_value(r, "_subscriber", "first_name"),
        "APCD_Subscriber_Middle_Initial": lambda r: str(_provider_value(r, "_subscriber", "middle_name") or "")[:1] or None,
        "APCD_Member_Last_Name": lambda r: _provider_value(r, "_member", "last_name"),
        "APCD_Member_First_Name": lambda r: _provider_value(r, "_member", "first_name"),
        "APCD_Member_Middle_Initial": lambda r: str(_provider_value(r, "_member", "middle_name") or "")[:1] or None,
        "APCD_Member_Street_Address": lambda r: _synthetic_address(r.get("member_id")),
        "APCD_Billing_Provider_Tax_ID_Number": lambda r: pharmacy_value(r, "tin") or _stable_number(r.get("pharmacy_npi"), digits=9, salt="pharmacy-tin"),
        "MDC_Frequency": _frequency,
        "MDC_Member_SSN": lambda r: _synthetic_ssn(r.get("member_id")),
        "MDC_Payer_Claim_Control_Number_Previous": _previous_claim,
        "MDC_Primary_or_Secondary_Indicator": lambda r: "SECONDARY" if str(r.get("primary_coverage_indicator") or "").lower().startswith("s") else "PRIMARY",
        "PH_Formulary_Code": lambda r: "N" if int(_stable_number(r.get("claim_id"), digits=2, salt="formulary")) < 10 else "Y",
        "PH_Route_of_Administration": _drug_route,
        "PH_Drug_Unit_of_Measure": _drug_unit,
        "PH_Amount_Sales_tax": lambda r: 0.0,
        "PH_Labeler_Code": lambda r: str(r.get("ndc_code") or "")[:5] or None,
        "PH Drug Strength": _drug_strength,
        "PH_Drug_Subclass": lambda r: _stable_number(r.get("therapeutic_class"), digits=6, salt="subclass"),
        "PH_Controlled_Drug_Code": _controlled_schedule,
        "PH_PCP_Name": lambda r: _provider_name(r.get("_pcp")),
        "PH_Risk_Group": _risk_group,
        "PH_PCP_NPI": lambda r: _provider_value(r, "_pcp", "npi"),
        "PH_Average_Wholesale_Price_Amount": lambda r: round(float(r.get("charge_amount") or 0) * 1.15, 2),
        "PH_Medicare_Primary_Coverage_Flag": lambda r: "Y" if "medicare" in str(r.get("product") or "").lower() else "N",
        "PH_Drug_Class_code": lambda r: _stable_number(r.get("therapeutic_class"), digits=4, salt="drug-class"),
        "PH_Drug_Group_code": lambda r: _stable_number(r.get("therapeutic_class"), digits=2, salt="drug-group"),
        "PH_Drug_supergroup_id": lambda r: _drug_supergroup(r)[0],
        "PH_Drug_supergroup_description": lambda r: _drug_supergroup(r)[1],
        "PH_Generic_Code": lambda r: _stable_number(r.get("ndc_code"), digits=14, salt="generic-code"),
        "PH_Prescription_Origin": lambda r: "3",
        "APCD_BUS_SUBCAT_CD": _insurance_code,
    }


def _eligibility_transforms() -> dict[str, Transform]:
    return {
        "APCD_INSURANCE_TYPE_CD": _insurance_code,
        "APCD_MONTH": lambda r: r.get("enrollment_month").month if isinstance(r.get("enrollment_month"), date) else r.get("enrollment_month"),
        "APCD_SUBSCRIBER_SSN": lambda r: _synthetic_ssn(r.get("subscriber_id")),
        "APCD_MBR_SUFFIX": _member_suffix,
        "APCD_RELATIONSHIP_CD": lambda r: _relationship(r.get("relation_code")),
        "APCD_MBR_GENDER": lambda r: _gender(r.get("sex")),
        "APCD_MBR_CITY": lambda r: _city(r.get("state"), r.get("zip_code")),
        "APCD_MED_COV": lambda r: "N" if str(r.get("enrollment_status") or "active").lower() in {"inactive", "terminated"} else "Y",
        "APCD_RX_DRUG_COV": lambda r: _yn(r.get("rx_coverage")),
        "APCD_DENTAL_COV": lambda r: "Y" if int(_stable_number(r.get("member_id"), digits=2, salt="dental")) < 60 else "N",
        "APCD_COV_TYPE": lambda r: "Y" if str(r.get("funding") or "").lower() in {"aso", "self funded", "self-funded"} else "N",
        "APCD_MARKET_CAT_CD": _market_category,
        "APCD_SUBSCRIBER_LAST_NAME": lambda r: _provider_value(r, "_subscriber", "last_name"),
        "APCD_SUBSCRIBER_FIRST_NAME": lambda r: _provider_value(r, "_subscriber", "first_name"),
        "APCD_SUBSCRIBER_MID_INITIAL": lambda r: str(_provider_value(r, "_subscriber", "middle_name") or "")[:1] or None,
        "APCD_MBR_LAST_NAME": lambda r: _provider_value(r, "_member", "last_name"),
        "APCD_MBR_FIRST_NAME": lambda r: _provider_value(r, "_member", "first_name"),
        "APCD_MBR_MIDDLE_INITIAL": lambda r: str(_provider_value(r, "_member", "middle_name") or "")[:1] or None,
        "MDC_MBR_SSN": lambda r: _synthetic_ssn(r.get("member_id")),
        "MDC_MBR_STREET_ADDRESS": lambda r: _synthetic_address(r.get("member_id")),
        "MDC_MBR_ADDRESS_2": lambda r: None,
        "MDC_MBR_PHONE_NUM": lambda r: _synthetic_phone(r.get("member_id")),
        "MDC_OFFICE_VISIT_COPAY": lambda r: _benefit(r, "office"),
        "MDC_ER_COPAY": lambda r: _benefit(r, "er"),
        "MDC_SPECIALIST_COPAY": lambda r: _benefit(r, "specialist"),
        "MDC_COINSURANCE_AMT": lambda r: _benefit(r, "coinsurance"),
        "MBR_COUNTY": lambda r: _county(r.get("state"), r.get("zip_code")),
        "PH_HOSPITAL_NETWORK": lambda r: _provider_value(r, "_pcp", "network_id") or "Priority Health Network",
        "PH_PROV_GROUP_PCP": lambda r: _provider_value(r, "_pcp", "network_id") or "Priority Health Provider Group",
        "PH_PCP_NAME": lambda r: _provider_name(r.get("_pcp")),
        "PH_PROV_GROUP_NPI": lambda r: _provider_value(r, "_pcp", "npi"),
        "PH_EMP_SUBGROUP_ID": lambda r: int(_stable_number(r.get("group_id"), digits=4, salt="subgroup")),
        "PH_EMP_SUBGROUP_NAME": lambda r: f"{r.get('group_name') or 'Synthetic Group'} - Main",
        "PH_MEDICARE_PRIM_COV_FLAG": lambda r: "Y" if "medicare" in str(r.get("product") or "").lower() else "N",
        "PH_MAIL_POST_EXT": lambda r: _stable_number(r.get("member_id"), digits=4, salt="zip4"),
        "PH_INDIVIDUAL_DEDUCT": lambda r: _benefit(r, "individual_deductible"),
        "PH_FAMILY_DEDUCT": lambda r: _benefit(r, "family_deductible"),
        "PH_RX_BRAND_COPAY": lambda r: _benefit(r, "rx_brand"),
        "PH_RX_GENERIC_COPAY": lambda r: _benefit(r, "rx_generic"),
        "PH_HTR_COPAY": lambda r: _benefit(r, "htr"),
        "PH_UC_COPAY": lambda r: _benefit(r, "urgent"),
        "PH_HBC_FLAG": lambda r: "N",
        "PH_HBCI_CD": lambda r: "N",
        "PH_HRA_FLAG": lambda r: "Y" if "hra" in str(r.get("plan_name") or "").lower() else "N",
        "PH_HSA_FLAG": lambda r: "Y" if any(marker in f"{r.get('plan_name', '')} {r.get('product', '')}".lower() for marker in ("hsa", "hdhp")) else "N",
        "PH_PCP_ATTRB_FLAG": lambda r: "Y" if r.get("pcp_npi") else "N",
        "PH_STATUS": lambda r: _eligibility_status(r),
        "APCD_BUS_SUBCAT_CD": _insurance_code,
    }


def _eligibility_status(row: Row) -> str:
    start = row.get("enrollment_start_date")
    month = row.get("enrollment_month")
    if isinstance(start, date) and isinstance(month, date):
        delta = (month - start.replace(day=1)).days
        if 0 <= delta <= 30:
            return "New"
    return "Existing"


def adapt(dataset: CanonicalDataset, schema_root: str | Path) -> dict[str, OutputTable]:
    """Return all three Priority Health APCD-style raw tables.

    The adapter keeps every canonical claim transaction and service line. It
    deliberately does not sanitize codes or rebalance financial values, so
    injected structural and logical data-quality defects remain observable.
    """

    schema_dir = _schema_directory(schema_root)
    lookups = _lookups(dataset)
    medical_schema = load_schema(schema_dir / "medical_claims.json")
    pharmacy_schema = load_schema(schema_dir / "pharmacy_claims.json")
    eligibility_schema = load_schema(schema_dir / "eligibility.json")

    medical_rows = tuple(
        _enrich_claim(row, lookups, pharmacy=False) for row in dataset.medical_claim_lines
    )
    pharmacy_rows = tuple(
        _enrich_claim(row, lookups, pharmacy=True) for row in dataset.pharmacy_claims
    )
    eligibility_rows = tuple(
        _enrich_eligibility(row, lookups) for row in dataset.enrollment_months
    )

    return {
        "medical_claims": project_rows(
            table_name="medical_claims",
            schema=medical_schema,
            source_rows=medical_rows,
            transforms=_medical_transforms(),
        ),
        "pharmacy_claims": project_rows(
            table_name="pharmacy_claims",
            schema=pharmacy_schema,
            source_rows=pharmacy_rows,
            transforms=_pharmacy_transforms(),
        ),
        "eligibility": project_rows(
            table_name="eligibility",
            schema=eligibility_schema,
            source_rows=eligibility_rows,
            transforms=_eligibility_transforms(),
        ),
    }
