from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from tuva_synthetic.adapters.priority_health import adapt
from tuva_synthetic.generation import GenerationConfig, generate_canonical
from tuva_synthetic.issues import inject_connector_eval_issues
from tuva_synthetic.model import CanonicalDataset
from tuva_synthetic.validation import failures, validate_output_tables


SCHEMA_ROOT = Path(__file__).parents[1] / "schemas"


def _dataset() -> CanonicalDataset:
    members = (
        {
            "person_id": "P001",
            "member_id": "M001",
            "subscriber_id": "M001",
            "relation_code": "self",
            "sex": "female",
            "birth_date": date(1982, 4, 12),
            "state": "MI",
            "zip_code": "49503",
            "product": "Commercial",
            "funding": "Fully Funded",
            "plan_id": "PLAN-PPO",
            "plan_name": "Priority PPO HSA",
            "plan_type": "PPO",
            "group_id": "123456",
            "group_name": "Synthetic Manufacturing",
            "rx_coverage": True,
            "risk_score": 1.3,
            "first_name": "Avery",
            "last_name": "Example",
        },
        {
            "person_id": "P002",
            "member_id": "M002",
            "subscriber_id": "M001",
            "relation_code": "child",
            "sex": "male",
            "birth_date": date(2012, 9, 3),
            "state": "MI",
            "zip_code": "49503",
            "product": "Commercial",
            "funding": "Fully Funded",
            "plan_id": "PLAN-PPO",
            "plan_name": "Priority PPO HSA",
            "plan_type": "PPO",
            "group_id": "123456",
            "group_name": "Synthetic Manufacturing",
            "rx_coverage": True,
            "risk_score": 0.4,
            "first_name": "Casey",
            "last_name": "Example",
        },
    )
    enrollment_months = (
        {
            **members[0],
            "enrollment_month": date(2025, 1, 1),
            "enrollment_year": 2025,
            "enrollment_start_date": date(2025, 1, 1),
            "enrollment_end_date": date(2025, 12, 31),
            "enrollment_status": "active",
            "pcp_npi": "1111111111",
        },
        {
            **members[1],
            "enrollment_month": date(2025, 1, 1),
            "enrollment_year": 2025,
            "enrollment_start_date": date(2025, 1, 1),
            "enrollment_end_date": date(2025, 12, 31),
            "enrollment_status": "active",
            "pcp_npi": "1111111111",
        },
    )
    providers = (
        {
            "provider_id": "PRV-PCP",
            "npi": "1111111111",
            "first_name": "Morgan",
            "last_name": "Clinician",
            "specialty": "Family Medicine",
            "provider_category": "primary care",
            "state": "MI",
            "zip_code": "49503",
            "network_id": "West Michigan Physicians",
            "tin": "900000001",
        },
        {
            "provider_id": "PRV-RENDER",
            "npi": "2222222222",
            "first_name": "Riley",
            "last_name": "Specialist",
            "specialty": "Cardiology",
            "provider_category": "specialist",
            "state": "MI",
            "zip_code": "49503",
            "network_id": "West Michigan Physicians",
            "tin": "900000002",
        },
        {
            "provider_id": "PRV-RX",
            "npi": "3333333333",
            "first_name": "Jordan",
            "last_name": "Prescriber",
            "specialty": "Internal Medicine",
            "provider_category": "primary care",
            "state": "MI",
            "zip_code": "49503",
            "network_id": "West Michigan Physicians",
            "tin": "900000003",
        },
    )
    facilities = (
        {
            "facility_id": "FAC001",
            "npi": "4444444444",
            "name": "Synthetic Regional Hospital",
            "facility_type": "acute care hospital",
            "state": "MI",
            "zip_code": "49503",
            "tin": "900000004",
        },
        {
            "facility_id": "RX001",
            "npi": "5555555555",
            "name": "Synthetic Community Pharmacy",
            "facility_type": "retail pharmacy",
            "state": "MI",
            "zip_code": "49503",
            "tin": "900000005",
        },
    )

    common_medical = {
        "original_claim_id": "CLM100",
        "adjustment_sequence": 0,
        "final_action": False,
        "person_id": "P001",
        "member_id": "M001",
        "claim_type": "institutional",
        "setting": "inpatient",
        "claim_form_type": "UB04",
        "first_service_date": date(2025, 1, 10),
        "last_service_date": date(2025, 1, 12),
        "claim_first_date": date(2025, 1, 10),
        "admission_date": date(2025, 1, 10),
        "discharge_date": date(2025, 1, 12),
        "paid_date": date(2025, 1, 25),
        "admit_source": "7",
        "admit_type": "1",
        "discharge_status": "1",
        "bill_type": "111",
        "place_of_service": "ZZ",
        "revenue_code": "BAD!",
        "hcpcs_code": "INVALID",
        "modifier_1": "25",
        "modifier_2": None,
        "modifier_3": "XX",
        "modifier_4": None,
        "diagnosis_codes": ["NOTACODE", "E119"],
        "poa_codes": ["Y", "N"],
        "procedure_codes": ["BADPROC"],
        "procedure_dates": [date(2025, 1, 10)],
        "rendering_npi": "2222222222",
        "billing_npi": "4444444444",
        "facility_npi": "4444444444",
        "provider_category": "specialist",
        "provider_state": "MI",
        "provider_zip_code": "49503",
        "units": 1.0,
        "claim_status": "paid",
        "denied_flag": False,
        "charge_amount": 175.0,
        "allowed_amount": 100.0,
        "plan_paid_amount": 80.0,
        "member_paid_amount": 30.0,
        "coinsurance_amount": 10.0,
        "copay_amount": 10.0,
        "deductible_amount": 10.0,
        "other_payer_amount": 0.0,
        "service_category": "inpatient facility",
    }
    medical_claim_lines = (
        {**common_medical, "claim_id": "CLM100", "line_number": 1, "drg_code": "001"},
        {
            **common_medical,
            "claim_id": "CLM100",
            "line_number": 2,
            "drg_code": "999",
            "revenue_code": "0250",
            "hcpcs_code": None,
        },
        {
            **common_medical,
            "claim_id": "CLM100R",
            "line_number": 1,
            "adjustment_sequence": 1,
            "drg_code": "001",
            "claim_status": "reversal",
            "plan_paid_amount": -80.0,
            "allowed_amount": -100.0,
            "member_paid_amount": -30.0,
            "coinsurance_amount": -10.0,
            "copay_amount": -10.0,
            "deductible_amount": -10.0,
        },
        {
            **common_medical,
            "claim_id": "CLMDENIED",
            "original_claim_id": "CLMDENIED",
            "line_number": 1,
            "final_action": True,
            "drg_code": None,
            "claim_status": "denied",
            "denied_flag": True,
            "allowed_amount": 0.0,
            "plan_paid_amount": 0.0,
            "member_paid_amount": 0.0,
            "coinsurance_amount": 0.0,
            "copay_amount": 0.0,
            "deductible_amount": 0.0,
        },
    )
    pharmacy_claims = (
        {
            "claim_id": "RX100",
            "original_claim_id": "RX100",
            "adjustment_sequence": 0,
            "final_action": True,
            "line_number": 1,
            "person_id": "P001",
            "member_id": "M001",
            "fill_date": date(2025, 1, 15),
            "paid_date": date(2025, 1, 16),
            "ndc_code": "00093010405",
            "drug_name": "Metformin 500 MG tablet",
            "therapeutic_class": "Endocrine and Metabolic Drugs",
            "quantity": 60.0,
            "days_supply": 30,
            "refill_number": 1,
            "daw_code": 0,
            "prescriber_npi": "3333333333",
            "pharmacy_npi": "5555555555",
            "mail_order_flag": False,
            "generic_flag": True,
            "claim_status": "paid",
            "denied_flag": False,
            "charge_amount": 24.0,
            "allowed_amount": 18.0,
            "plan_paid_amount": 8.0,
            "member_paid_amount": 10.0,
            "coinsurance_amount": 0.0,
            "copay_amount": 10.0,
            "deductible_amount": 0.0,
            "ingredient_cost": 16.5,
            "dispensing_fee": 1.5,
        },
    )
    return CanonicalDataset(
        members=members,
        enrollment_months=enrollment_months,
        providers=providers,
        facilities=facilities,
        medical_claim_lines=medical_claim_lines,
        pharmacy_claims=pharmacy_claims,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        seed=17,
    )


def test_priority_health_schemas_cover_every_published_field_in_order() -> None:
    expected = {
        "medical_claims": (163, "APCD_PAYER", "APCD_BUS_SUBCAT_CD"),
        "pharmacy_claims": (105, "APCD_Payer", "APCD_BUS_SUBCAT_CD"),
        "eligibility": (82, "APCD_PAYER", "APCD_BUS_SUBCAT_CD"),
    }
    required = {
        "position",
        "name",
        "type",
        "source_type",
        "size",
        "canonical",
        "default",
        "population",
    }

    for table, (count, first, last) in expected.items():
        schema = json.loads((SCHEMA_ROOT / "priority_health" / f"{table}.json").read_text())
        columns = schema["columns"]
        assert len(columns) == count
        assert [column["position"] for column in columns] == list(range(1, count + 1))
        assert columns[0]["name"] == first
        assert columns[-1]["name"] == last
        assert all(required <= column.keys() for column in columns)
        assert {column["population"] for column in columns} <= {
            "canonical",
            "derived",
            "constant",
            "intentionally_null",
            "modeled",
        }


def test_adapter_is_deterministic_and_preserves_source_grains() -> None:
    dataset = _dataset()
    first = adapt(dataset, SCHEMA_ROOT)
    second = adapt(dataset, SCHEMA_ROOT)

    assert first == second
    assert set(first) == {"medical_claims", "pharmacy_claims", "eligibility"}
    assert len(first["medical_claims"].rows) == len(dataset.medical_claim_lines)
    assert len(first["pharmacy_claims"].rows) == len(dataset.pharmacy_claims)
    assert len(first["eligibility"].rows) == len(dataset.enrollment_months)
    for table in first.values():
        assert all(tuple(row) == table.columns for row in table.rows)


def test_medical_projection_preserves_adjustments_and_injected_dq_defects() -> None:
    medical = adapt(_dataset(), SCHEMA_ROOT)["medical_claims"].rows

    original = medical[0]
    second_line = medical[1]
    reversal = medical[2]
    denied = medical[3]

    assert (original["APCD_PYR_CLAIM_CNTRL_NUM"], original["APCD_LINE_CNTR"]) == ("CLM100", 1)
    assert (second_line["APCD_PYR_CLAIM_CNTRL_NUM"], second_line["APCD_LINE_CNTR"]) == ("CLM100", 2)
    assert {original["APCD_DRG"], second_line["APCD_DRG"]} == {"001", "999"}

    assert original["APCD_FACILITY_TYPE_PROF"] == "ZZ"
    assert original["APCD_REVENUE_CD"] == "BAD!"
    assert original["APCD_PRINCIPAL_DIAGNOSIS"] == "NOTACODE"
    assert original["APCD_PROCEDURE_CD"] == "INVALID"
    assert original["MDC_PROC_MOD_3"] == "XX"
    assert original["PH_ALLOWED_AMT"] == 100.0
    assert original["APCD_PAID_AMT"] == 80.0
    assert original["APCD_COPAY_AMT"] + original["APCD_COINS_AMT"] + original["APCD_DEDUCT_AMT"] == 30.0
    assert original["PH_ALLOWED_AMT"] != original["APCD_PAID_AMT"] + 30.0

    assert reversal["APCD_VERSION_NUM"] == 1
    assert reversal["MDC_FREQUENCY"] == "8"
    assert reversal["MDC_PAYER_CLM_CNTRL_NUM_PREV"] == "CLM100"
    assert reversal["APCD_PAID_AMT"] == -80.0
    assert denied["APCD_CLAIM_STATUS"] == "2"


def test_pharmacy_and_eligibility_projection_populate_core_relationships() -> None:
    output = adapt(_dataset(), SCHEMA_ROOT)
    pharmacy = output["pharmacy_claims"].rows[0]
    eligibility = output["eligibility"].rows[0]

    assert pharmacy["APCD_Drug_Code"] == "00093010405"
    assert pharmacy["APCD_National_Pharmacy_ID"] == "5555555555"
    assert pharmacy["APCD_Prescribing_Physician_NPI_Number"] == "3333333333"
    assert pharmacy["APCD_Generic_Drug_Indicator"] == "Y"
    assert pharmacy["PH Drug Strength"] == 500.0
    assert pharmacy["PH_Allowed_amount"] == 18.0

    assert eligibility["APCD_YEAR"] == 2025
    assert eligibility["APCD_MONTH"] == 1
    assert eligibility["APCD_MBR_PAT_ID"] == "M001"
    assert eligibility["APCD_RX_DRUG_COV"] == "Y"
    assert eligibility["MDC_MBR_PCP_ID_ATTR_PHYS_ID"] == "1111111111"
    assert eligibility["PH_PCP_NAME"] == "Morgan Clinician"
    assert eligibility["APCD_SUBSCRIBER_SSN"].startswith("900")
    assert eligibility["APCD_SUBSCRIBER_SSN"].isdigit()
    assert len(eligibility["APCD_SUBSCRIBER_SSN"]) == 9


def test_priority_profile_projects_with_injected_connector_evaluation_issues() -> None:
    clean = generate_canonical(
        GenerationConfig(
            payer="priority_health",
            member_count=40,
            start_date=date(2024, 1, 1),
            end_date=date(2025, 12, 31),
            seed=812,
        )
    )
    dirty, manifest = inject_connector_eval_issues(clean)
    output = adapt(dirty, SCHEMA_ROOT)

    assert manifest
    assert not failures(validate_output_tables(output.values()))
    assert len(output["medical_claims"].rows) == len(dirty.medical_claim_lines)
    assert len(output["pharmacy_claims"].rows) == len(dirty.pharmacy_claims)
    assert len(output["eligibility"].rows) == len(dirty.enrollment_months)
    assert {row["APCD_INSURANCE_TYPE_CD"] for row in output["medical_claims"].rows} <= {
        "FEPO",
        "FHMO",
        "FPOS",
        "FPPO",
        "SEPO",
        "SHMO",
        "SPOS",
        "SPPO",
    }
    assert {row["APCD_RELATIONSHIP_CD"] for row in output["eligibility"].rows} <= {
        "1",
        "2",
        "3",
    }
