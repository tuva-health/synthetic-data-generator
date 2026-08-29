"""Project the canonical cohort into the public HCCI 2.0 SDDV2 layout."""

from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from tuva_synthetic.adapters.base import load_schema, project_rows
from tuva_synthetic.model import CanonicalDataset, OutputTable, Row


Transform = Callable[[Row], Any]

_SCHEMA_FILES = (
    "member_enrollment",
    "medical_claims_inpatient",
    "medical_claims_outpatient",
    "medical_claims_physician",
    "pharmacy_claims",
)

# The cohort generator draws member and provider ZIPs from these metros.  HCCI
# publishes CBSA rather than a free-text locality, so retain the geographic
# relationship instead of inventing a code from the ZIP digits.
_CBSA_BY_ZIP_PREFIX = {
    "016": "49340", "021": "14460", "071": "35620", "086": "45940",
    "100": "35620", "142": "15380", "152": "38300", "191": "37980",
    "222": "47900", "232": "40060", "276": "39580", "282": "16740",
    "303": "12060", "314": "42340", "328": "36740", "331": "33100",
    "336": "45300", "372": "34980", "381": "32820", "432": "18140",
    "441": "17460", "452": "17140", "462": "26900", "468": "23060",
    "481": "11460", "482": "19820", "489": "29620", "494": "26090",
    "495": "24340", "532": "33340", "537": "31540", "551": "33460",
    "554": "33460", "606": "16980", "627": "44100", "752": "19100",
    "770": "26420", "782": "41700", "787": "12420", "802": "19740",
    "809": "17820", "841": "41620", "850": "38060", "852": "38060",
    "900": "31080", "921": "41740", "941": "41860", "972": "38900",
    "974": "21660", "981": "42660", "992": "44060",
}

_AGE_BAND_CODES = {
    "0-17": "01",
    "18-24": "02",
    "25-34": "03",
    "35-44": "04",
    "45-54": "05",
    "55-64": "06",
    "65-74": "07",
    "75-84": "08",
    "85+": "09",
}

# MS-DRGs are organized by MDC in mostly contiguous ranges.  These boundaries
# cover the synthetic DRGs used by the generator and provide a realistic
# fallback without requiring a proprietary grouper.
_MDC_RANGES = (
    (1, 19, "00"), (20, 103, "01"), (113, 125, "02"),
    (129, 159, "03"), (163, 208, "04"), (215, 320, "05"),
    (326, 395, "06"), (405, 446, "07"), (453, 566, "08"),
    (570, 607, "09"), (614, 645, "10"), (652, 700, "11"),
    (707, 730, "12"), (734, 761, "13"), (765, 782, "14"),
    (789, 795, "15"), (799, 816, "16"), (820, 849, "17"),
    (853, 872, "18"), (876, 887, "19"), (894, 897, "20"),
    (901, 923, "21"), (927, 935, "22"), (939, 951, "23"),
    (955, 965, "24"), (969, 977, "25"),
)


def _schema_dir(schema_root: Path) -> Path:
    root = Path(schema_root)
    return root / "hcci" if (root / "hcci").is_dir() else root


def _decimal_hash(namespace: str, *values: Any, digits: int) -> int | None:
    if not values or any(value is None for value in values):
        return None
    raw = "|".join((namespace, *(str(value) for value in values)))
    digest = int.from_bytes(sha256(raw.encode()).digest(), "big")
    floor = 10 ** (digits - 1)
    return floor + digest % (9 * floor)


def _text_hash(namespace: str, *values: Any) -> str | None:
    if not values or any(value is None for value in values):
        return None
    raw = "|".join((namespace, *(str(value) for value in values)))
    return sha256(raw.encode()).hexdigest()[:32]


def _member_hash(row: Row) -> int | None:
    return _decimal_hash(
        "hcci-member",
        row.get("source_system") or "CONTRIBUTOR",
        row.get("person_id") or row.get("member_id"),
        digits=19,
    )


def _claim_hash(row: Row) -> int | None:
    return _decimal_hash(
        "hcci-claim",
        row.get("source_system") or "CONTRIBUTOR",
        row.get("claim_id"),
        digits=32,
    )


def _group_hash(row: Row, kind: str) -> str | None:
    return _text_hash(
        f"hcci-{kind}",
        row.get("source_system") or "CONTRIBUTOR",
        row.get("original_claim_id") or row.get("claim_id"),
    )


def _npi_hash(value: Any) -> str | None:
    # HCCI's provider hash is stable across contributors, unlike Z_PATID.
    return _text_hash("hcci-npi", value)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _date_value(row: Row, *keys: str) -> date | None:
    for key in keys:
        result = _as_date(row.get(key))
        if result is not None:
            return result
    return None


def _date_part(row: Row, keys: tuple[str, ...], part: str) -> str | None:
    value = _date_value(row, *keys)
    return value.strftime(part) if value else None


def _indexed(row: Row, key: str, index: int) -> Any:
    values = row.get(key) or []
    return values[index] if index < len(values) else None


def _flag(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "in", "covered"}:
        return "1"
    if normalized in {"0", "false", "f", "no", "n", "out", "not covered"}:
        return "0"
    # Preserve deliberate malformed values for downstream Data Quality tests.
    return str(value)


def _sex(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return {"MALE": "M", "FEMALE": "F"}.get(normalized, normalized or None)


def _age_band(row: Row) -> str | None:
    value = row.get("age_band")
    if value in _AGE_BAND_CODES:
        return _AGE_BAND_CODES[str(value)]
    if value is not None and len(str(value)) <= 2:
        return str(value)
    age = row.get("age")
    if isinstance(age, int):
        if age <= 17: return "01"
        if age <= 24: return "02"
        if age <= 34: return "03"
        if age <= 44: return "04"
        if age <= 54: return "05"
        if age <= 64: return "06"
        if age <= 74: return "07"
        if age <= 84: return "08"
        return "09"
    return None


def _product(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return {"HDHP": "HDP"}.get(normalized, normalized[:3] or None)


def _funding(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("_", "-")
    if normalized in {"aso", "self", "self-funded"}:
        return "A"
    if normalized in {"fi", "fully-insured", "fully insured", "insured"}:
        return "F"
    return str(value)


def _age_on(row: Row, as_of: date | None = None) -> int | None:
    birth_date = _as_date(row.get("birth_date"))
    if birth_date and as_of:
        return as_of.year - birth_date.year - (
            (as_of.month, as_of.day) < (birth_date.month, birth_date.day)
        )
    value = row.get("age")
    return value if isinstance(value, int) else None


def _over65(row: Row, *date_keys: str) -> str | None:
    age = _age_on(row, _date_value(row, *date_keys))
    return None if age is None else ("1" if age >= 65 else "0")


def _esi(row: Row, *date_keys: str) -> str:
    age = _age_on(row, _date_value(row, *date_keys))
    product = _product(row.get("product"))
    valid_sex = _sex(row.get("sex")) in {"M", "F"}
    return "1" if age is not None and age < 65 and valid_sex and product in {
        "EPO", "HMO", "POS", "PPO"
    } else "0"


def _cbsa_from_zip(value: Any) -> str | None:
    if value is None:
        return None
    return _CBSA_BY_ZIP_PREFIX.get(str(value).zfill(5)[:3])


def _member_cbsa(row: Row) -> str | None:
    if not row.get("zip_code"):
        return None
    return _cbsa_from_zip(row.get("zip_code")) or row.get("cbsa")


def _hrr(row: Row) -> int | None:
    cbsa = _member_cbsa(row)
    if cbsa is None:
        return None
    # Public HCCI materials do not publish their CBSA-to-HRR crosswalk.  Keep
    # the result in the valid three-digit HRR domain and deterministic.
    return 1 + int(sha256(f"hrr|{cbsa}".encode()).hexdigest()[:8], 16) % 306


def _rural(row: Row) -> str | None:
    zip_code = row.get("zip_code")
    if not zip_code:
        return None
    # Every ZIP in the current generator profile belongs to a mapped metro.
    return "0" if _cbsa_from_zip(zip_code) else None


def _mdc(value: Any) -> str | None:
    if value is None:
        return None
    try:
        drg = int(str(value))
    except ValueError:
        # Keep the invalid DRG visible in DRG; MDC cannot be derived from it.
        return None
    for lower, upper, mdc in _MDC_RANGES:
        if lower <= drg <= upper:
            return mdc
    return None


def _line_sequence(row: Row) -> str | None:
    value = row.get("line_number")
    return None if value is None else str(value)


def _enrich(row: Row, by_person: dict[str, Row], by_member: dict[str, Row]) -> Row:
    member = by_person.get(str(row.get("person_id"))) or by_member.get(
        str(row.get("member_id")), {}
    )
    return {**member, **row}


def _enrollment_transforms() -> dict[str, Transform]:
    return {
        "Z_PATID": _member_hash,
        "MNTH": lambda r: _date_part(r, ("enrollment_month",), "%m"),
        "YR": lambda r: _date_part(r, ("enrollment_month",), "%Y")
        or (str(r.get("enrollment_year")) if r.get("enrollment_year") else None),
        "SEX": lambda r: _sex(r.get("sex")),
        "AGE_BAND_CD": _age_band,
        "MBR_CBSA": _member_cbsa,
        "HRR_CD": _hrr,
        "PROD": lambda r: _product(r.get("product")),
        "FI_FLG": lambda r: _funding(r.get("funding")),
        "RX_CVG_IND": lambda r: _flag(r.get("rx_coverage")),
        "MH_CVG_IND": lambda r: _flag(r.get("mh_coverage")),
        "OVER65_FLG": lambda r: _over65(r, "enrollment_month"),
        "ESI_FLG": lambda r: _esi(r, "enrollment_month"),
        "RURAL_FLG": _rural,
    }


def _medical_transforms(kind: str) -> dict[str, Transform]:
    date_keys = {
        "inpatient": ("admission_date", "first_service_date"),
        "outpatient": ("claim_first_date", "first_service_date"),
        "physician": ("first_service_date",),
    }[kind]
    transforms: dict[str, Transform] = {
        "Z_CLMID": _claim_hash,
        "CLMSEQ": _line_sequence,
        "YR": lambda r: _date_part(r, date_keys, "%Y"),
        "MNTH": lambda r: _date_part(r, date_keys, "%m"),
        "Z_PATID": _member_hash,
        "PAID_DT": lambda r: _as_date(r.get("paid_date")),
        "HNPI": lambda r: _npi_hash(r.get("rendering_npi")),
        "HNPI_BE": lambda r: _npi_hash(r.get("billing_npi")),
        "PROV_CBSA_CD": lambda r: _cbsa_from_zip(r.get("provider_zip_code")),
        "NTWRK_IND": lambda r: _flag(r.get("network_flag")),
        "OVER65_FLG": lambda r: _over65(r, *date_keys),
        "ESI_FLG": lambda r: _esi(r, *date_keys),
    }
    for index in range(3):
        transforms[f"DIAG_ICD9_CM{index + 1}"] = lambda _row: None
    for index in range(10):
        transforms[f"DIAG_ICD10_CM{index + 1}"] = (
            lambda row, index=index: _indexed(row, "diagnosis_codes", index)
        )
    if kind == "inpatient":
        transforms.update({
            "Z_ADMIT_ID": lambda r: _group_hash(r, "admit"),
            "MDC": lambda r: _mdc(r.get("drg_code")),
            "DRG_DRVD": lambda r: r.get("drg_code"),
        })
        for index in range(10):
            transforms[f"POA{index + 1}"] = (
                lambda row, index=index: _indexed(row, "poa_codes", index)
            )
            transforms[f"PROC_ICD10_PCS{index + 1}"] = (
                lambda row, index=index: _indexed(row, "procedure_codes", index)
            )
        for index in range(3):
            transforms[f"PROC_ICD9_PCS{index + 1}"] = lambda _row: None
    elif kind == "outpatient":
        transforms["Z_VISITID"] = lambda r: _group_hash(r, "visit")
    return transforms


def _pharmacy_transforms() -> dict[str, Transform]:
    return {
        "Z_PATID": _member_hash,
        "Z_CLMID": _claim_hash,
        "YR": lambda r: _date_part(r, ("fill_date",), "%Y"),
        "MNTH": lambda r: _date_part(r, ("fill_date",), "%m"),
        "YRMNTH_PD": lambda r: _date_part(r, ("paid_date",), "%Y%m"),
        "FILL_DT": lambda r: _as_date(r.get("fill_date")),
        "CHK_DT": lambda r: _as_date(r.get("paid_date")),
        "HNPI": lambda r: _npi_hash(r.get("prescriber_npi")),
        "HNPI_BE": lambda r: _npi_hash(r.get("pharmacy_npi")),
        "OVER65_FLG": lambda r: _over65(r, "fill_date"),
        "ESI_FLG": lambda r: _esi(r, "fill_date"),
    }


def adapt(dataset: CanonicalDataset, schema_root: Path) -> dict[str, OutputTable]:
    """Return all five HCCI SDDV2 tables in published field order.

    All input claim rows are retained.  Institutional rows are routed to
    inpatient only when explicitly marked inpatient; other institutional
    rows (including emergency) go to outpatient.  Professional rows go to
    physician.  This preserves denials, negative reversals, adjustments, and
    deliberately malformed clinical and financial values for DQ evaluation.
    """

    root = _schema_dir(Path(schema_root))
    schemas = {name: load_schema(root / f"{name}.json") for name in _SCHEMA_FILES}

    by_person = {
        str(row["person_id"]): row for row in dataset.members if row.get("person_id")
    }
    by_member = {
        str(row["member_id"]): row for row in dataset.members if row.get("member_id")
    }
    medical_rows = tuple(
        _enrich(row, by_person, by_member) for row in dataset.medical_claim_lines
    )
    pharmacy_rows = tuple(
        _enrich(row, by_person, by_member) for row in dataset.pharmacy_claims
    )

    inpatient = tuple(row for row in medical_rows if row.get("setting") == "inpatient")
    physician = tuple(
        row for row in medical_rows
        if row.get("claim_type") == "professional" or row.get("setting") == "professional"
    )
    outpatient = tuple(
        row
        for row in medical_rows
        if row.get("setting") != "inpatient"
        and row.get("claim_type") != "professional"
        and row.get("setting") != "professional"
    )

    return {
        "member_enrollment": project_rows(
            table_name="member_enrollment",
            schema=schemas["member_enrollment"],
            source_rows=dataset.enrollment_months,
            transforms=_enrollment_transforms(),
        ),
        "medical_claims_inpatient": project_rows(
            table_name="medical_claims_inpatient",
            schema=schemas["medical_claims_inpatient"],
            source_rows=inpatient,
            transforms=_medical_transforms("inpatient"),
        ),
        "medical_claims_outpatient": project_rows(
            table_name="medical_claims_outpatient",
            schema=schemas["medical_claims_outpatient"],
            source_rows=outpatient,
            transforms=_medical_transforms("outpatient"),
        ),
        "medical_claims_physician": project_rows(
            table_name="medical_claims_physician",
            schema=schemas["medical_claims_physician"],
            source_rows=physician,
            transforms=_medical_transforms("physician"),
        ),
        "pharmacy_claims": project_rows(
            table_name="pharmacy_claims",
            schema=schemas["pharmacy_claims"],
            source_rows=pharmacy_rows,
            transforms=_pharmacy_transforms(),
        ),
    }
