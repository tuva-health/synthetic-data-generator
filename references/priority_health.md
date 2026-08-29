# Priority Health APCD projection

## Structural source

- **Source:** [Priority Health APCD Data Dictionaries](https://www.priorityhealth.com/-/media/priorityhealth/documents/provider-office/apcd-data-dictionary.pdf?hash=9F4D5C298FD9492F4BB1F91706FC7DE9&rev=6778e65a74834d2c8fce0d5acca9ba6d)
- **Source date:** February 23, 2021, from the PDF metadata and workbook title
- **Extracts:** medical claims (PDF pages 2–14), pharmacy claims (pages
  15–24), and eligibility (pages 25–31)

The schemas preserve all 350 reliably extractable published fields in source
order: 163 medical, 105 pharmacy, and 82 eligibility. Each JSON field records
the published name and size, its normalized and published types, the canonical
source key, default, and one generator-owned population class:

- `canonical`: copied from the shared longitudinal cohort
- `derived`: deterministically calculated from one or more canonical values
- `constant`: fixed by the Priority Health layout or synthetic scenario
- `intentionally_null`: documented as unused/unavailable, or unsupported by
  the canonical cohort without inventing an unstable meaning

## Projection decisions

- Medical output remains at claim-service-line and adjustment-transaction
  grain. Claim ID, line counter, version, prior claim control number, and
  frequency preserve original/replacement/reversal chains. A negative
  adjustment uses frequency `8`; the public dictionary describes original
  (`1`) and replacement (`7`) and names void/adjustment behavior but does not
  enumerate every value.
- Diagnosis arrays populate the principal diagnosis and up to 30 other
  diagnosis fields without validating or normalizing codes. POA arrays and up
  to six ICD procedure fields are likewise retained. DRG remains line-level,
  which deliberately permits multiple DRGs on one claim when the canonical
  scenario injects that defect.
- Medical paid, member-liability, COB, and allowed amounts are copied without
  rebalancing. `APCD_CHARGE_AMT` remains null because the source marks it
  unavailable; `PH_ALLOWED_AMT` carries the canonical allowed amount.
- Pharmacy output remains at one row per canonical transaction. NDC, fill,
  prescriber/pharmacy NPIs, quantity, days supply, adjustment lineage, and all
  available canonical financial values are retained.
- Eligibility remains one row per member-month. Plan, product, funding,
  subscriber/member relationship, coverage, PCP, and benefit-design fields are
  mapped or deterministically modeled.
- SSN-shaped values, addresses, phones, DEA numbers, licenses, pharmacy IDs,
  and other source-required identifiers are generated from salted hashes.
  `900`-prefixed SSN-shaped values are deliberately non-issued and are not PHI.

## Known limitations

- The public source is an APCD export specification, not a full operational
  claims-system schema, and its contents are dated even though the PDF remains
  publicly hosted.
- Some published definitions conflict with their types or examples. For
  example, employer subgroup ID is typed as an integer while its example is
  alphanumeric. The schema preserves the published type and emits a numeric
  deterministic subgroup ID.
- The source explicitly marks several fields unused. Those remain null unless
  the field is necessary to preserve the requested synthetic adjustment
  lineage (version and previous claim number).
- Canonical data do not carry real streets, phones, DEA numbers, formulary
  decisions, drug strengths, or benefit booklets. Modeled values are
  deterministic and plausible, but should not be interpreted as current
  Priority Health operational rules.
- Published size is retained as metadata; generated values are not silently
  truncated. Validation should surface any injected overlength value as a data
  quality defect.
