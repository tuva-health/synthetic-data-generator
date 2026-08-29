from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from tuva_synthetic.adapters.aetna import adapt
from tuva_synthetic.model import CanonicalDataset


SCHEMA_ROOT = Path(__file__).parents[1] / "schemas"


def _dataset() -> CanonicalDataset:
    subscriber = {
        "person_id": "P0001",
        "member_id": "M0001",
        "subscriber_id": "S0001",
        "relation_code": "self",
        "sex": "F",
        "birth_date": date(1983, 4, 12),
        "state": "MI",
        "zip_code": "49503",
        "product": "PPO",
        "funding": "self-funded",
        "plan_id": "PL001",
        "plan_type": "employee",
        "group_id": "GRP00001",
        "group_name": "Synthetic Manufacturing",
        "rx_coverage": True,
        "mh_coverage": True,
        "first_name": "Mara",
        "last_name": "Quinn",
    }
    dependent = {
        **subscriber,
        "person_id": "P0002",
        "member_id": "M0002",
        "subscriber_id": "S0001",
        "relation_code": "child",
        "sex": "M",
        "birth_date": date(2012, 9, 3),
        "first_name": "Ilan",
        "last_name": "Quinn",
    }
    enrollment = {
        **dependent,
        "enrollment_month": date(2025, 1, 1),
        "enrollment_year": 2025,
        "enrollment_start_date": date(2024, 7, 1),
        "enrollment_end_date": None,
        "enrollment_status": "active",
        "pcp_npi": "1234567893",
    }
    base_medical = {
        "claim_id": "C000000000000001",
        "original_claim_id": "C000000000000001",
        "adjustment_sequence": 0,
        "final_action": "original",
        "person_id": "P0002",
        "member_id": "M0002",
        "claim_type": "institutional",
        "setting": "inpatient",
        "claim_form_type": "UB04",
        "first_service_date": date(2025, 1, 8),
        "last_service_date": date(2025, 1, 10),
        "claim_first_date": date(2025, 1, 8),
        "admission_date": date(2025, 1, 8),
        "discharge_date": date(2025, 1, 10),
        "paid_date": date(2025, 1, 28),
        "admit_source": "1",
        "admit_type": "3",
        "discharge_status": "01",
        "bill_type": "111",
        "place_of_service": None,
        "revenue_code": "ABCD",  # Deliberately invalid DQ case.
        "hcpcs_code": "?????",  # Deliberately invalid DQ case.
        "modifier_1": "25",
        "modifier_2": None,
        "modifier_3": None,
        "modifier_4": None,
        "diagnosis_codes": ["J189", "NOTACODE"],
        "poa_codes": ["Y", "N"],
        "procedure_codes": ["0WQF0ZZ", "BADPROC"],
        "procedure_dates": [date(2025, 1, 8)],
        "rendering_npi": "1234567893",
        "billing_npi": "1987654321",
        "facility_npi": "1098765432",
        "provider_category": "hospitalist",
        "provider_state": "MI",
        "provider_zip_code": "49503",
        "units": Decimal("1"),
        "network_flag": True,
        "primary_coverage_indicator": True,
        "claim_status": "paid",
        "denied_flag": False,
        "charge_amount": Decimal("150.00"),
        "allowed_amount": Decimal("100.00"),
        "plan_paid_amount": Decimal("60.00"),
        "member_paid_amount": Decimal("45.00"),  # Intentional $5 inconsistency.
        "coinsurance_amount": Decimal("20.00"),
        "copay_amount": Decimal("10.00"),
        "deductible_amount": Decimal("15.00"),
        "other_payer_amount": Decimal("0.00"),
        "service_category": "acute inpatient",
        "source_system": "aetna",
        "file_name": "aetna_medical_202501.dat",
        "file_date": date(2025, 2, 1),
    }
    medical_lines = (
        {**base_medical, "line_number": 1, "drg_code": "291"},
        {**base_medical, "line_number": 2, "drg_code": "470"},
        {
            **base_medical,
            "claim_id": "C000000000000001R",
            "line_number": 1,
            "adjustment_sequence": 1,
            "final_action": "reversal",
            "claim_status": "reversed",
            "charge_amount": Decimal("-150.00"),
            "allowed_amount": Decimal("-100.00"),
            "plan_paid_amount": Decimal("-60.00"),
            "member_paid_amount": Decimal("-45.00"),
            "coinsurance_amount": Decimal("-20.00"),
            "copay_amount": Decimal("-10.00"),
            "deductible_amount": Decimal("-15.00"),
            "drg_code": "291",
        },
    )
    pharmacy_claims = (
        {
            "claim_id": "RX00000000000001",
            "original_claim_id": "RX00000000000001",
            "adjustment_sequence": 0,
            "final_action": "original",
            "line_number": 1,
            "person_id": "P0002",
            "member_id": "M0002",
            "fill_date": date(2025, 1, 15),
            "paid_date": date(2025, 1, 16),
            "ndc_code": "BADNDC00000",  # Deliberately invalid DQ case.
            "drug_name": "Synthetic Drug",
            "therapeutic_class": "antibiotic",
            "quantity": Decimal("20.000"),
            "days_supply": 10,
            "refill_number": 0,
            "daw_code": "0",
            "prescriber_npi": "1234567893",
            "pharmacy_npi": "1555555555",
            "network_flag": True,
            "mail_order_flag": False,
            "generic_flag": True,
            "maintenance_flag": False,
            "claim_status": "denied",
            "denied_flag": True,
            "charge_amount": Decimal("34.50"),
            "allowed_amount": Decimal("0.00"),
            "plan_paid_amount": Decimal("0.00"),
            "member_paid_amount": Decimal("0.00"),
            "coinsurance_amount": Decimal("0.00"),
            "copay_amount": Decimal("0.00"),
            "deductible_amount": Decimal("0.00"),
            "ingredient_cost": Decimal("30.00"),
            "dispensing_fee": Decimal("4.50"),
            "source_system": "aetna",
            "file_name": "aetna_rx_202501.dat",
            "file_date": date(2025, 2, 1),
        },
    )
    return CanonicalDataset(
        members=(subscriber, dependent),
        enrollment_months=(enrollment,),
        providers=(
            {
                "provider_id": "PR0001",
                "npi": "1234567893",
                "first_name": "Jo",
                "last_name": "Rivera",
                "specialty": "pediatrics",
                "provider_category": "physician",
                "state": "MI",
                "zip_code": "49503",
                "network_id": "IN001",
                "tin": "381234567",
            },
        ),
        facilities=(
            {
                "facility_id": "PH0001",
                "npi": "1555555555",
                "name": "Synthetic Community Pharmacy",
                "facility_type": "pharmacy",
                "state": "MI",
                "zip_code": "49503",
                "tin": "389999999",
            },
        ),
        medical_claim_lines=medical_lines,
        pharmacy_claims=pharmacy_claims,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        seed=20250829,
    )


def test_published_schemas_are_complete_ordered_physical_layouts() -> None:
    expectations = {
        "universal_medical_dental.json": (178, 1480),
        "universal_pharmacy.json": (71, 798),
        "universal_medical_eligibility.json": (63, 1000),
    }
    required = {
        "ordinal",
        "name",
        "source_name",
        "type",
        "length",
        "start",
        "end",
        "canonical",
        "default",
        "population",
    }
    for filename, (field_count, record_length) in expectations.items():
        with (SCHEMA_ROOT / "aetna" / filename).open(encoding="utf-8") as handle:
            schema = json.load(handle)
        assert len(schema["columns"]) == field_count
        assert schema["record_length"] == record_length
        assert [column["ordinal"] for column in schema["columns"]] == list(
            range(1, field_count + 1)
        )
        assert len({column["name"] for column in schema["columns"]}) == field_count
        assert all(required == set(column) for column in schema["columns"])
        assert all(
            column["population"]
            in {"modeled", "derived", "constant", "intentional_null"}
            for column in schema["columns"]
        )
        assert all(
            current["end"] < following["start"]
            for current, following in zip(schema["columns"], schema["columns"][1:])
        )
        assert schema["columns"][-1]["end"] == record_length


def test_adapter_projects_identity_relationships_and_aetna_codes() -> None:
    tables = adapt(_dataset(), SCHEMA_ROOT)
    assert set(tables) == {
        "universal_medical_dental",
        "universal_pharmacy",
        "universal_medical_eligibility",
    }

    eligibility = tables["universal_medical_eligibility"].rows[0]
    assert eligibility["eff_dt"] == "202501"
    assert eligibility["member_id"] == "M0002"
    assert eligibility["emp_src_member_id"] == "S0001"
    assert eligibility["subscriber_last_nm"] == "Quinn"
    assert eligibility["mbr_rtp_type_cd"] == "3"
    assert eligibility["plsp_prod_cd"] == "PP"
    assert eligibility["fund_ctg_cd"] == "S"
    assert eligibility["pcp_tax_id_nbr"] == "381234567"
    assert eligibility["npi_no"] == "1234567893"
    assert eligibility["ssn_nbr"] is None
    assert eligibility["subscriber_ssn_nbr"] is None
    assert eligibility["eor_marker"] == "X"

    medical = tables["universal_medical_dental"].rows[0]
    assert medical["file_id"] == "03"
    assert medical["subscriber_first_nm"] == "Mara"
    assert medical["member_first_nm"] == "Ilan"
    assert medical["servicing_provider_tax_id_nbr"] == "381234567"
    assert medical["servicing_provider_print_nm"] == "Rivera Jo"
    assert medical["not_covered_amt_1"] == Decimal("50.00")
    assert medical["negot_savings_amt"] == Decimal("50.00")
    assert medical["clm_ln_status_cd"] == "P"
    assert medical["src_subscriber_id"] is None
    assert medical["ssn_nbr"] is None
    assert medical["eor_marker"] == "X"

    pharmacy = tables["universal_pharmacy"].rows[0]
    assert pharmacy["member_id"] == "M0002"
    assert pharmacy["subscriber_first_name"] == "Mara"
    assert pharmacy["prescriber_id"] == "1234567893"
    assert pharmacy["nabp_nbr"] == "5555555"
    assert pharmacy["phm_zip_cd"] == "49503"
    assert pharmacy["generic_cd"] == "G"
    assert pharmacy["retail_mod_cd"] == "R"
    assert pharmacy["clm_status"] == "D"
    assert pharmacy["ssn_nbr"] is None
    assert pharmacy["eor_marker"] == "X"


def test_adapter_preserves_injected_data_quality_problems() -> None:
    tables = adapt(_dataset(), SCHEMA_ROOT)
    medical = tables["universal_medical_dental"].rows

    # Missing/invalid codes are not repaired by the payer projection.
    assert medical[0]["plc_srv_cd"] is None
    assert medical[0]["hcfa_plc_srv_cd"] is None
    assert medical[0]["revenue_cd"] == "ABCD"
    assert medical[0]["prcdr_cd"] == "?????"
    assert medical[0]["icd9_dx_cd_2"] == "NOTACODE"
    assert medical[0]["icd9_prcdr_cd_2"] == "BADPROC"

    # Multiple DRGs on the same source claim remain visible.
    assert {medical[0]["drg_cd"], medical[1]["drg_cd"]} == {"291", "470"}
    assert medical[0]["src_clm_id"] == medical[1]["src_clm_id"]

    # The intentionally inconsistent financial identity is preserved exactly.
    assert medical[0]["allowed_amt"] == Decimal("100.00")
    assert medical[0]["paid_amt"] == Decimal("60.00")
    assert medical[0]["srv_copay_amt"] == Decimal("10.00")
    assert medical[0]["deductible_amt"] == Decimal("15.00")
    assert medical[0]["coinsurance_amt"] == Decimal("20.00")

    reversal = medical[2]
    assert reversal["clm_ln_type_cd"] == "R"
    assert reversal["reversal_cd"] == "RV"
    assert reversal["clm_ln_status_cd"] == "R"
    assert reversal["billed_amt"] == Decimal("-150.00")
    assert reversal["allowed_amt"] == Decimal("-100.00")
    assert reversal["paid_amt"] == Decimal("-60.00")

    pharmacy = tables["universal_pharmacy"].rows[0]
    assert pharmacy["ndc_cd"] == "BADNDC00000"
    assert pharmacy["clm_status"] == "D"


def test_adapter_is_deterministic_and_uses_schema_column_order() -> None:
    first = adapt(_dataset(), SCHEMA_ROOT)
    second = adapt(_dataset(), SCHEMA_ROOT)
    assert first == second
    for table in first.values():
        assert all(tuple(row) == table.columns for row in table.rows)
