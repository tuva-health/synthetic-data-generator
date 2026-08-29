# Aetna Universal extract reference

The Aetna adapter is shaped from Aetna's publicly hosted Universal extract
documentation. The source documents are referenced in place and are not
redistributed by this repository.

## Public sources

- [Aetna plan sponsor reporting documentation](https://www.aetna.com/info/aetinfo/)
- [Universal Medical / Dental data dictionary](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-universal-medical-dental-file-data-dictionary.doc)
- [Universal Medical / Dental 1480-byte physical layout](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-universal-medical-dental-1480-record-layout.xlsx)
- [Universal Pharmacy data dictionary](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-universal-pharmacy-file-data-dictionary.doc)
- [Universal Pharmacy 798-byte physical layout](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna_universal-pharmacy-798-file-record-layout.xlsx)
- [Universal Medical Eligibility data dictionary](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-Universal_Medical_Eligibility_File_Data_Dictionary.doc)
- [Universal Medical Eligibility 1000-byte physical layout](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-Universal-Medical-Eligibility-1000-File-Layout.xls)

The source layouts identify updates in April 2018 for pharmacy, June 2018 for
eligibility, and November 2018 for medical/dental. Aetna's public index still
described the linked files as the most current versions when reviewed on
2026-08-29.

## Implemented coverage

| Output table | Published fields | Published record length | Synthetic grain |
| --- | ---: | ---: | --- |
| `universal_medical_dental` | 178 | 1480 bytes | Claim service line or adjustment transaction |
| `universal_pharmacy` | 71 | 798 bytes | Pharmacy claim transaction |
| `universal_medical_eligibility` | 63 | 1000 bytes | Member enrollment month |

Every numbered physical-layout field is represented in exact ordinal order.
Each schema column records the published technical name, type, length, fixed
positions, canonical source/default, and a generator-owned population
classification of `modeled`, `derived`, `constant`, or `intentional_null`.

Some Aetna technical names repeat—for example, member and subscriber name
fields both use `last_nm`, and many reserved fields use `FILLER`. Output names
are therefore disambiguated for a valid tabular output. `source_name` always
retains the published technical name, and `ordinal` retains the unambiguous
physical identity.

## Mapping approach

- Eligibility supplies the member-month grain and plan, funding, household,
  demographic, coverage, and PCP fields.
- Medical/dental expands diagnosis codes to ten positions, present-on-admission
  codes to ten positions, inpatient procedures to six positions, and procedure
  modifiers to the positions available in the public layout.
- Pharmacy maps NDC, fill and paid dates, quantity, days supply, refill, DAW,
  prescriber, pharmacy, channel, generic/maintenance indicators, and available
  financial components.
- Aetna hierarchy fields use stable synthetic group and plan identifiers.
  Product, funding, coverage, network, status, and adjustment values are
  deterministically converted to compact Aetna-shaped codes.
- No SSNs, phone numbers, street addresses, or other unnecessary direct
  identifiers are generated. Those fields are intentionally null even though
  they exist in the published layouts.
- End-of-record markers and explicitly documented defaults are constants.
  Reserved, obsolete, unsupported Aetna Health Fund, and unavailable
  organization-specific fields are null or zero according to their schema
  classification.

## Fidelity and data-quality behavior

The generator writes typed raw tables in published field order; it does not
attempt to reproduce Aetna's tab-delimited fixed-width byte encoding. This is
intentional because the target is a raw analytical table rather than a plan
sponsor transport file.

The adapter is a projection, not a data cleaner. It preserves deliberately
injected missing or invalid place-of-service, diagnosis, procedure, and revenue
codes; claim-level DRG conflicts; denial and reversal status; negative
adjustments; and financial inconsistencies. That makes the result suitable for
testing connector behavior and Tuva Core Data Quality checks.

All people, organizations, identifiers, and utilization records emitted by the
generator are synthetic. Public documentation is used only to model structure.
