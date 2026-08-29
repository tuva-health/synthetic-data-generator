# Canonical generation model

Adapters consume `CanonicalDataset` row dictionaries with these stable keys.
Dates are `datetime.date`; lists remain lists until an adapter expands them.

## members

`person_id`, `member_id`, `subscriber_id`, `relation_code`, `sex`,
`birth_date`, `death_date`, `age`, `age_band`, `state`, `zip_code`, `cbsa`,
`product`, `funding`, `plan_id`, `plan_name`, `plan_type`, `group_id`,
`group_name`, `rx_coverage`, `mh_coverage`, `risk_score`, `conditions`,
`first_name`, `last_name`, `race`, `ethnicity`, `source_system`.

## enrollment_months

All identity and coverage attributes needed from `members`, plus
`enrollment_month`, `enrollment_year`, `enrollment_start_date`,
`enrollment_end_date`, `enrollment_status`, `pcp_npi`, `source_system`,
`file_name`, `file_date`.

## providers

`provider_id`, `npi`, `first_name`, `last_name`, `specialty`,
`provider_category`, `state`, `zip_code`, `network_id`, `tin`.

## facilities

`facility_id`, `npi`, `name`, `facility_type`, `state`, `zip_code`, `tin`.

## medical_claim_lines

`claim_id`, `original_claim_id`, `adjustment_sequence`, `final_action`,
`line_number`, `person_id`, `member_id`, `claim_type` (`institutional` or
`professional`), `setting` (`inpatient`, `outpatient`, `emergency`, or
`professional`), `claim_form_type`, `first_service_date`, `last_service_date`,
`claim_first_date`, `admission_date`, `discharge_date`, `paid_date`,
`claim_line_start_date`, `claim_line_end_date`, `payer`, `plan`,
`admit_source`, `admit_type`, `discharge_status`, `bill_type`,
`place_of_service`, `revenue_code`, `hcpcs_code`, `modifier_1`, `modifier_2`,
`modifier_3`, `modifier_4`, `diagnosis_codes`, `poa_codes`, `procedure_codes`,
`procedure_dates`, `diagnosis_code_type`, `procedure_code_type`,
`drg_code_type`, `drg_code`, `rendering_npi`, `billing_npi`, `facility_npi`,
`provider_category`, `provider_state`, `provider_zip_code`, `units`,
`network_flag`, `primary_coverage_indicator`, `claim_status`, `denied_flag`,
`charge_amount`, `allowed_amount`, `plan_paid_amount`, `member_paid_amount`,
`coinsurance_amount`, `copay_amount`, `deductible_amount`, `other_payer_amount`,
`service_category`, `source_system`, `file_name`, `file_date`.

Financial identity for non-denied final-action rows is:
`allowed_amount = plan_paid_amount + member_paid_amount + other_payer_amount`
and `member_paid_amount = coinsurance_amount + copay_amount + deductible_amount`.
Adjustment rows may be negative and reverse an earlier transaction.

## pharmacy_claims

`claim_id`, `original_claim_id`, `adjustment_sequence`, `final_action`,
`line_number`, `person_id`, `member_id`, `fill_date`, `paid_date`, `ndc_code`,
`payer`, `plan`,
`drug_name`, `therapeutic_class`, `quantity`, `days_supply`, `refill_number`,
`daw_code`, `prescriber_npi`, `pharmacy_npi`, `network_flag`, `mail_order_flag`,
`generic_flag`, `maintenance_flag`, `claim_status`, `denied_flag`,
`charge_amount`, `allowed_amount`, `plan_paid_amount`, `member_paid_amount`,
`coinsurance_amount`, `copay_amount`, `deductible_amount`, `ingredient_cost`,
`dispensing_fee`, `source_system`, `file_name`, `file_date`.
