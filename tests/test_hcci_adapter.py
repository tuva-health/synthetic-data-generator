from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from tuva_synthetic.adapters.hcci import adapt
from tuva_synthetic.model import CanonicalDataset


SCHEMA_ROOT = Path(__file__).parents[1] / "schemas"


def _schema_columns(*parts: object) -> list[str]:
    columns: list[str] = []
    for part in parts:
        if isinstance(part, str):
            columns.append(part)
        else:
            columns.extend(part)  # type: ignore[arg-type]
    return columns


EXPECTED_COLUMNS = {
    "member_enrollment": _schema_columns(
        "Z_PATID", "MNTH", "YR", "SEX", "AGE_BAND_CD", "MBR_ZIP_5_CD",
        "MBR_STATE", "MBR_CBSA", "HRR_CD", "PROD", "FI_FLG",
        "RX_CVG_IND", "MH_CVG_IND", "SIC", "OVER65_FLG", "ESI_FLG",
        "RURAL_FLG",
    ),
    "medical_claims_inpatient": _schema_columns(
        "Z_CLMID", "CLMSEQ", "YR", "MNTH", "CLM_FRM_TYP", "TOB",
        "FST_DT", "LST_DT", "FST_ADMTDT", "LST_DISCHDT", "Z_ADMIT_ID",
        "Z_PATID", "ADMIT_TYPE", "ADMIT_SRC", "MDC", "PAID_DT",
        "AMT_NET_PAID", "COINS", "COPAY", "DEDUCT", "CALC_ALLWD",
        "TOT_MEM_CS", "UNITS",
        [f"DIAG_ICD9_CM{i}" for i in range(1, 4)],
        [f"DIAG_ICD10_CM{i}" for i in range(1, 11)],
        [f"POA{i}" for i in range(1, 11)],
        "DRG", "DRG_DRVD", "DSTATUS", "PROC_CD",
        [f"PROC_ICD9_PCS{i}" for i in range(1, 4)],
        [f"PROC_ICD10_PCS{i}" for i in range(1, 11)],
        "PROCMOD", "RVNU_CD", "POS", "HNPI", "HNPI_BE",
        "PROV_ZIP_5_CD", "PROV_CBSA_CD", "PROV_STATE", "NTWRK_IND",
        "PRIMARY_CVG_IND", "OVER65_FLG", "HCCI_HL_CAT", "ESI_FLG",
    ),
    "medical_claims_outpatient": _schema_columns(
        "Z_CLMID", "CLMSEQ", "YR", "MNTH", "CLM_FRM_TYP", "TOB",
        "FST_DT", "LST_DT", "CLM_FST_DT", "Z_PATID", "Z_VISITID",
        "PAID_DT", "AMT_NET_PAID", "COINS", "COPAY", "DEDUCT",
        "CALC_ALLWD", "TOT_MEM_CS", "UNITS",
        [f"DIAG_ICD9_CM{i}" for i in range(1, 4)],
        [f"DIAG_ICD10_CM{i}" for i in range(1, 11)],
        "PROC_CD", "PROCMOD", "RVNU_CD", "POS", "HNPI", "HNPI_BE",
        "PROV_ZIP_5_CD", "PROV_CBSA_CD", "PROV_STATE", "NTWRK_IND",
        "PRIMARY_CVG_IND", "OVER65_FLG", "HCCI_HL_CAT", "ESI_FLG",
    ),
    "medical_claims_physician": _schema_columns(
        "Z_CLMID", "CLMSEQ", "YR", "MNTH", "CLM_FRM_TYP", "FST_DT",
        "LST_DT", "Z_PATID", "PAID_DT", "AMT_NET_PAID", "COINS",
        "COPAY", "DEDUCT", "CALC_ALLWD", "TOT_MEM_CS", "UNITS",
        [f"DIAG_ICD9_CM{i}" for i in range(1, 4)],
        [f"DIAG_ICD10_CM{i}" for i in range(1, 11)],
        "PROC_CD", "PROCMOD", "POS", "HNPI", "HNPI_BE",
        "PROV_ZIP_5_CD", "PROV_CBSA_CD", "PROV_STATE", "NTWRK_IND",
        "PRIMARY_CVG_IND", "OVER65_FLG", "HCCI_HL_CAT", "ESI_FLG",
    ),
    "pharmacy_claims": _schema_columns(
        "Z_PATID", "Z_CLMID", "YR", "MNTH", "YRMNTH_PD", "FILL_DT",
        "CHK_DT", "AMT_NET_PAID", "CALC_ALLWD", "TOT_MEM_CS", "DISPFEE",
        "QUANTITY", "HNPI", "HNPI_BE", "DAW", "DAYS_SUP", "NDC",
        "HCCI_HL_CAT", "OVER65_FLG", "ESI_FLG",
    ),
}


def _member() -> dict[str, object]:
    return {
        "person_id": "PHC00000001",
        "member_id": "HCM00000001",
        "sex": "F",
        "birth_date": date(1980, 5, 5),
        "age": 45,
        "age_band": "45-54",
        "state": "CO",
        "zip_code": "80202",
        "cbsa": "19740",
        "product": "PPO",
        "funding": "ASO",
        "rx_coverage": "Y",
        "mh_coverage": "Y",
        "source_system": "CONTRIBUTOR_A",
    }


def _medical_line(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "claim_id": "HCC0001",
        "original_claim_id": "HCC0001",
        "adjustment_sequence": 0,
        "final_action": True,
        "line_number": 1,
        "person_id": "PHC00000001",
        "member_id": "HCM00000001",
        "claim_type": "institutional",
        "setting": "inpatient",
        "claim_form_type": "U",
        "first_service_date": date(2025, 1, 5),
        "last_service_date": date(2025, 1, 8),
        "claim_first_date": date(2025, 1, 5),
        "admission_date": date(2025, 1, 5),
        "discharge_date": date(2025, 1, 8),
        "paid_date": date(2025, 1, 22),
        "admit_source": "1",
        "admit_type": "1",
        "discharge_status": "01",
        "bill_type": "111",
        "place_of_service": None,
        "revenue_code": "O250",
        "hcpcs_code": "BADHCPCS",
        "modifier_1": None,
        "diagnosis_codes": ["I10", "E11O"],
        "poa_codes": ["Y", "N"],
        "procedure_codes": ["0SRC0J9", "BADPROC"],
        "drg_code": "470",
        "rendering_npi": "9000000014",
        "billing_npi": "9000020006",
        "provider_state": "CO",
        "provider_zip_code": "80202",
        "units": 1,
        "network_flag": 1,
        "primary_coverage_indicator": "P",
        "claim_status": "paid",
        "denied_flag": 0,
        "allowed_amount": 100.00,
        "plan_paid_amount": 80.01,
        "member_paid_amount": 20.00,
        "coinsurance_amount": 10.00,
        "copay_amount": 5.00,
        "deductible_amount": 5.00,
        "source_system": "CONTRIBUTOR_A",
    }
    row.update(overrides)
    return row


def _dataset() -> CanonicalDataset:
    member = _member()
    enrollment = {
        **member,
        "enrollment_month": date(2025, 1, 1),
        "enrollment_year": 2025,
    }
    inpatient_original = _medical_line()
    inpatient_reversal = _medical_line(
        line_number=2,
        adjustment_sequence=1,
        final_action=False,
        claim_status="reversal",
        drg_code="471",
        allowed_amount=-75.25,
        plan_paid_amount=-60.25,
        member_paid_amount=-15.00,
        coinsurance_amount=-10.00,
        copay_amount=-5.00,
        deductible_amount=0.00,
    )
    outpatient = _medical_line(
        claim_id="HCC0002",
        original_claim_id="HCC0002",
        setting="emergency",
        admission_date=None,
        discharge_date=None,
        claim_first_date=date(2025, 2, 4),
        first_service_date=date(2025, 2, 4),
        last_service_date=date(2025, 2, 4),
        paid_date=date(2025, 2, 16),
        bill_type="13I",
        place_of_service="1O",
        drg_code=None,
    )
    physician = _medical_line(
        claim_id="HCC0003",
        original_claim_id="HCC0003",
        claim_type="professional",
        setting="professional",
        claim_form_type="P",
        admission_date=None,
        discharge_date=None,
        bill_type=None,
        revenue_code=None,
        place_of_service=None,
        drg_code=None,
    )
    pharmacy = {
        "claim_id": "HCR0001",
        "original_claim_id": "HCR0001",
        "adjustment_sequence": 1,
        "final_action": False,
        "person_id": member["person_id"],
        "member_id": member["member_id"],
        "fill_date": date(2025, 3, 1),
        "paid_date": date(2025, 3, 2),
        "ndc_code": "00093O1041",
        "quantity": 30,
        "days_supply": 30,
        "daw_code": "0",
        "prescriber_npi": "9000000014",
        "pharmacy_npi": "9000040002",
        "claim_status": "reversal",
        "allowed_amount": -22.50,
        "plan_paid_amount": -12.50,
        "member_paid_amount": -10.00,
        "dispensing_fee": -1.75,
        "source_system": "CONTRIBUTOR_A",
    }
    return CanonicalDataset(
        members=(member,),
        enrollment_months=(enrollment,),
        providers=(),
        facilities=(),
        medical_claim_lines=(
            inpatient_original, inpatient_reversal, outpatient, physician
        ),
        pharmacy_claims=(pharmacy,),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        seed=20260829,
    )


def test_schemas_match_all_published_fields_in_order() -> None:
    total = 0
    for table, expected in EXPECTED_COLUMNS.items():
        schema = json.loads((SCHEMA_ROOT / "hcci" / f"{table}.json").read_text())
        assert [column["name"] for column in schema["columns"]] == expected
        assert [column["ordinal"] for column in schema["columns"]] == list(
            range(1, len(expected) + 1)
        )
        for column in schema["columns"]:
            assert column["data_type"]
            assert column["normalized_data_type"]
            assert column["length"] > 0
            assert column["classification"] in {
                "modeled", "derived", "constant", "intentionally_null"
            }
            assert "canonical" in column
            assert "default" in column
        total += len(expected)
    assert total == 201

    pharmacy = json.loads(
        (SCHEMA_ROOT / "hcci" / "pharmacy_claims.json").read_text()
    )
    billing_npi = next(
        column for column in pharmacy["columns"] if column["name"] == "HNPI_BE"
    )
    assert billing_npi["data_type"] == "Vachar"
    assert billing_npi["normalized_data_type"] == "Varchar"


def test_adapter_routes_rows_and_preserves_dq_problems() -> None:
    tables = adapt(_dataset(), SCHEMA_ROOT)

    assert list(tables) == list(EXPECTED_COLUMNS)
    assert len(tables["member_enrollment"].rows) == 1
    assert len(tables["medical_claims_inpatient"].rows) == 2
    assert len(tables["medical_claims_outpatient"].rows) == 1
    assert len(tables["medical_claims_physician"].rows) == 1
    assert len(tables["pharmacy_claims"].rows) == 1

    for table_name, table in tables.items():
        assert list(table.columns) == EXPECTED_COLUMNS[table_name]
        assert all(tuple(row) == table.columns for row in table.rows)

    enrollment = tables["member_enrollment"].rows[0]
    inpatient = tables["medical_claims_inpatient"].rows
    outpatient = tables["medical_claims_outpatient"].rows[0]
    physician = tables["medical_claims_physician"].rows[0]
    pharmacy = tables["pharmacy_claims"].rows[0]

    # Member linkage is stable across every file and respects the 19-digit
    # enrollment limit even though claim schemas publish a wider field.
    assert len(str(enrollment["Z_PATID"])) == 19
    assert {enrollment["Z_PATID"], *(row["Z_PATID"] for row in inpatient),
            outpatient["Z_PATID"], physician["Z_PATID"], pharmacy["Z_PATID"]} == {
        enrollment["Z_PATID"]
    }
    assert len(str(inpatient[0]["Z_CLMID"])) == 32
    assert inpatient[0]["Z_CLMID"] == inpatient[1]["Z_CLMID"]
    assert inpatient[0]["Z_ADMIT_ID"] == inpatient[1]["Z_ADMIT_ID"]

    # The adapter must not cleanse the nuanced connector-evaluation defects.
    assert inpatient[0]["DIAG_ICD10_CM2"] == "E11O"
    assert inpatient[0]["PROC_ICD10_PCS2"] == "BADPROC"
    assert inpatient[0]["RVNU_CD"] == "O250"
    assert [row["DRG"] for row in inpatient] == ["470", "471"]
    assert inpatient[0]["AMT_NET_PAID"] == 80.01
    assert inpatient[0]["CALC_ALLWD"] == 100.00
    assert inpatient[1]["AMT_NET_PAID"] == -60.25
    assert inpatient[1]["CALC_ALLWD"] == -75.25
    assert outpatient["TOB"] == "13I"
    assert outpatient["POS"] == "1O"
    assert physician["POS"] is None
    assert pharmacy["NDC"] == "00093O1041"
    assert pharmacy["CALC_ALLWD"] == -22.50

    assert enrollment["AGE_BAND_CD"] == "05"
    assert enrollment["MBR_CBSA"] == "19740"
    assert enrollment["RURAL_FLG"] == "0"
    assert inpatient[0]["MDC"] == "08"
    assert outpatient["HCCI_HL_CAT"] == "OP"
    assert physician["HCCI_HL_CAT"] == "PP"
    assert pharmacy["HCCI_HL_CAT"] == "RX"


def test_adapter_is_deterministic() -> None:
    first = adapt(_dataset(), SCHEMA_ROOT)
    second = adapt(_dataset(), SCHEMA_ROOT / "hcci")
    assert first == second
