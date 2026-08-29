# Evaluator-only Data Quality profile

This document describes the intentional problems in the `connector_eval`
profile. It is for test owners after generation and must be withheld from a
Connector Builder during a blind run. It identifies issue classes and design
patterns, but not affected row keys. Exact synthetic keys and before/after
values live only in the ignored
`reports/generated/<payer>/issue_manifest.csv` file.

## Design principles

Defects are added after a clean canonical dataset passes validation and before
the payer adapter projects it. This guarantees that the same underlying
problem is expressed through each source's native-looking columns.

Injection is deterministic, sparse, and nonuniform. Candidate rows are often
restricted to a minority source system, a quarter, a provider context, a
member's final month, or the last line of a claim. Many invalid values have the
right length and resemble valid codes. Several errors are at claim or person
grain and cannot be found by profiling one column independently.

Rates below are percentages of the eligible candidate pool, not percentages
of every raw row. Caps prevent a 10,000-member run from being dominated by one
failure class. At least one row is selected when an eligible pool exists.
Numeric severities mirror the pinned Tuva Core DQ contract: every Core-aligned
injection is severity `2` except `eligibility__multiple_sexes_per_person`,
which is severity `3`. Connector-only cases use `behavioral` because they do
not have a Core logical-test severity. These are test priorities, not clinical
severity.

## Medical claim issues

| Manifest test name | Candidate pattern | Nominal selection | Why it is nuanced | Expected connector behavior |
| --- | --- | ---: | --- | --- |
| `medical_claim__place_of_service_code_null_for_professional_claim` | Professional claims in the busiest quarter of the minority source system | 5.5%, cap 180 | The cluster period is data-driven; most professional claims and all other quarters remain populated | Preserve null and expose the failure |
| `medical_claim__place_of_service_code_invalid` | Populated claims from that same busiest-quarter cluster | 1.8%, cap 60 | `1O` uses a letter O in place of zero | Do not coerce; expose terminology failure |
| `medical_claim__diagnosis_code_2_to_25_invalid` | Single-line professional claims with a secondary diagnosis in the minority feed | 0.6%, cap 90 | `E11O` resembles a common ICD-10-CM code and the principal diagnosis stays valid | Preserve slot order and flag the secondary code |
| `medical_claim__revenue_center_code_invalid` | Institutional lines with revenue codes in the minority feed | 0.4%, cap 70 | Only the leading digit is replaced with `O` | Preserve the source value and flag it |
| `medical_claim__bill_type_code_invalid` | Institutional lines with type of bill in the minority feed | 0.2%, cap 35 | `13I` has the expected width and a letter in the final position | Preserve and flag rather than normalizing silently |
| `medical_claim__drg_code_count_ne_one_for_acute_inpatient_claim` | Multiline inpatient claims | 2.8% of eligible claims | Only the last ancillary line receives a neighboring, valid-looking DRG | Evaluate all lines at claim grain; do not pick one silently |
| `medical_claim__billing_npi_has_multiple_values_per_claim` | Priority Health multiline claims only | 0.4% of eligible claims | The last line receives a different checksum-valid NPI | Retain line detail and surface the claim-level conflict |
| `medical_claim__paid_date_before_claim_end_date` | Single-line minority-feed medical claims | 0.12%, cap 65 | The payment date is only one day early | Preserve and expose the temporal inconsistency |
| `medical_claim__paid_amount_gt_allowed_amount` | Paid lines with positive allowed amounts | 0.08%, cap 45 | Member and other-payer responsibility are zero, while plan paid is exactly one cent above allowed | Do not round or rebalance the isolated error away |
| `medical_claim__no_matching_eligibility_span` | Aetna/Priority members with a genuine mid-period coverage start | Up to 0.2% of members | A single-line professional claim is shifted to one day before otherwise plausible coverage | Surface the mismatch; do not invent enrollment |

There is no facility-NPI-null or checksum-invalid-NPI injection. All generated
NPIs are structurally checksum-valid but intentionally do not match NPPES or
Tuva `provider_data`; provider-reference invalid checks are excluded from
scoring rather than treated as injected connector findings.

## Eligibility issues

| Manifest test name | Candidate pattern | Nominal selection | Why it is nuanced | Expected connector behavior |
| --- | --- | ---: | --- | --- |
| `eligibility__multiple_sexes_per_person` | One final monthly row for selected subscribers | 0.18% of members | Every earlier month agrees; this is the sole Core severity-3 injection | Preserve source history and expose person-level drift |
| `eligibility__overlapping_enrollment_spans` | Aetna/Priority only: a distinct finite span overlaps existing coverage under the same plan | 0.12% of members | Both spans are finite and plan identity does not provide an easy deduplication rule | Preserve both and expose the genuine overlap |
| `connector__duplicate_eligibility_source_row` | HCCI only: one member-month is replayed exactly | 0.12% of members | Every field and source key matches, while adjacent legitimate months must remain | Deduplicate the replay without discarding other months |

## Pharmacy claim issues

| Manifest test name | Candidate pattern | Nominal selection | Why it is nuanced | Expected connector behavior |
| --- | --- | ---: | --- | --- |
| `pharmacy_claim__ndc_code_invalid` | Fills from the minority source system | 0.15%, cap 55 | The last NDC character is `O`, preserving the expected width | Preserve and flag rather than coercing |
| `pharmacy_claim__days_supply_not_positive` | Paid fills | 0.07%, cap 30 | Zero appears on otherwise plausible maintenance fills | Surface the impossible days supply |
| `pharmacy_claim__paid_amount_gt_allowed_amount` | Positive-allowed fills | 0.06%, cap 25 | Member and other-payer responsibility are zero, while plan paid is exactly one cent above allowed | Retain currency precision and flag the isolated error |

## ADR transaction histories

ADR means adjustment, denial, and reversal behavior in this evaluation—not a
single payer-standard field or code set. Native medical ADR is injected only
for Aetna and Priority Health, whose public layouts expose enough lineage and
status information for a defensible final-action expectation.

| Manifest test name | History | Nominal selection | Required final-action interpretation |
| --- | --- | ---: | --- |
| `connector__select_final_action_replacement` | Paid original, exact negative reversal, then a slightly lower replacement | 3.5% of eligible paid medical claims from the minority feed | Retain replacement lines as final; original and reversal are lineage, not active duplicates |
| `connector__remove_voided_claim` | Paid original followed by a complete negative void and no replacement | 1.0% of remaining eligible medical claims | Exclude the claim from final active medical claims |

Adjustment logic is intentionally difficult to infer from amounts alone.
Original, reversal, void, and replacement rows share claim lineage and line
identity while sequence, status, dates, and sign distinguish their meaning.
An adapter that deduplicates before interpreting the transaction chain can
produce a clean-looking but incorrect final claim set.

Claims already selected for a static claim-level issue are reserved and
excluded from the ADR candidate pool. This prevents a Core logical failure
from disappearing when final-action logic removes or replaces its claim. No
rejected-to-paid pharmacy ADR is injected.

HCCI has no scored native ADR history: the public SDDV2 layout does not expose
enough adjustment status/lineage to define one confidently. HCCI uses the
exact enrollment replay above as its behavioral deduplication challenge. Its
monthly enrollment layout also cannot preserve the intended day-level
boundary for `medical_claim__no_matching_eligibility_span`, so that exact Core
flag is omitted from HCCI.

## Ground-truth handling

The manifest has one row per injected condition or ADR history and includes:

- `issue_id` and aligned `dq_test_name`;
- domain, payer, setting, canonical member/claim/line/source keys;
- `evaluation_phase`, `expected_final_presence`, expected count, and known
  collateral tests;
- exact raw `source_table`, source key column, and source key value resolved
  after payer projection;
- affected field plus original and injected values;
- numeric Core severity or behavioral classification, expected connector
  action, and clustering pattern;
- `tuva_core_dq_contract`, currently pinned to
  `tuva-core 1.0.0@22bb5766c8890d9b4d66fdefb21dc532e3da785e`.

Do not mix this file into the payer-shaped raw files or any externally loaded
raw schema. Do not copy it into a connector repository, prompt, generated
documentation, or debug artifact that the evaluated agent can read. If a run
is contaminated, regenerate with a new seed and retain the replacement
manifest outside the agent's context.

The manifest records intended defects, not every downstream symptom. A single
row can trigger additional Tuva checks, and a faulty connector can introduce
new failures that have no manifest entry. Evaluation therefore combines
manifest reconciliation with review of the final Tuva grain, source lineage,
and full Data Quality output.
