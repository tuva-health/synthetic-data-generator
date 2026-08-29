# Public source contracts

The generator uses public documentation to reproduce the shape of three raw
claims extracts. It does not contain, derive from, or attempt to recreate any
member-level data from Aetna, Priority Health, or the Health Care Cost
Institute (HCCI).

Links and availability were verified on August 29, 2026. The checked-in JSON
schemas are the version-pinned implementation contracts; upstream publishers
can revise or remove their documents without notice.

## Aetna Universal extracts

Aetna's [Data Science Universal files documentation index](https://www.aetna.com/info/aetinfo/)
describes the linked documents as the most current versions of its Universal
file references. The files are hosted in Aetna's 2018 document directory and
should not be interpreted as a representation of every current Aetna
operational feed.

| Synthetic raw table | Authoritative dictionary | Authoritative physical layout | Implemented fields |
| --- | --- | --- | ---: |
| `universal_medical_dental` | [Universal Medical/Dental data dictionary](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-universal-medical-dental-file-data-dictionary.doc) | [1480-byte record layout](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-universal-medical-dental-1480-record-layout.xlsx) | 178 |
| `universal_pharmacy` | [Universal Pharmacy data dictionary](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-universal-pharmacy-file-data-dictionary.doc) | [798-byte record layout](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna_universal-pharmacy-798-file-record-layout.xlsx) | 71 |
| `universal_medical_eligibility` | [Universal Medical Eligibility data dictionary](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-Universal_Medical_Eligibility_File_Data_Dictionary.doc) | [1000-byte record layout](https://www.aetna.com/info/aetinfo/uf_docs/2018/Aetna-Universal-Medical-Eligibility-1000-File-Layout.xls) | 63 |

The corresponding local schemas are under `schemas/aetna/`. They retain the
published ordinal, source name, type, length, fixed positions, and a concise
mapping decision. Published names that repeat, including reserved `FILLER`
fields, are disambiguated as tabular-safe output names while preserving the
original name in schema metadata.

## Priority Health APCD extracts

Priority Health publishes one [APCD Data Dictionaries PDF](https://www.priorityhealth.com/-/media/priorityhealth/documents/provider-office/apcd-data-dictionary.pdf?hash=9F4D5C298FD9492F4BB1F91706FC7DE9&rev=6778e65a74834d2c8fce0d5acca9ba6d).
The document is titled "APCD Data Dictionary (as of 2-23-21)" and contains
medical, pharmacy, and eligibility sections. It is a public APCD export
specification, not a representation of Priority Health's complete current
claims platform.

| Synthetic raw table | PDF section | Implemented fields |
| --- | --- | ---: |
| `medical_claims` | Medical claims, pages 1–14 | 163 |
| `pharmacy_claims` | Pharmacy claims, pages 15–24 | 105 |
| `eligibility` | Eligibility, pages 24–31 | 82 |

The local schemas under `schemas/priority_health/` preserve the source order,
published field name, type, size, and generator-owned mapping decision. Follow
the source link for Priority Health's descriptions. Fields that the document
marks unused are ordinarily null; synthetic adjustment lineage is populated
only where required for the connector evaluation.

## HCCI commercial claims

HCCI's current [HCCI 2.0 General Data Dictionary](https://healthcostinstitute.org/wp-content/uploads/2026/06/HCCI_2.0_General_Data_Dictionary_20260701.pdf)
is version 2.0, effective July 1, 2026, and labels the published view `SDDV2`.
The 12-page document defines enrollment and four claims file families.

| Synthetic raw table | Implemented fields |
| --- | ---: |
| `member_enrollment` | 17 |
| `medical_claims_inpatient` | 76 |
| `medical_claims_outpatient` | 46 |
| `medical_claims_physician` | 42 |
| `pharmacy_claims` | 20 |

HCCI's [Data Access Hub](https://healthcostinstitute.org/data-access-hub/)
describes the underlying commercial dataset as de-identified employer-
sponsored insurance data made available to approved researchers through a
secure enclave. This repository has no enclave access and redistributes no
HCCI data. The local schemas under `schemas/hcci/` use the public dictionary
only as a structural contract.

## Medication terminology provenance

The valid pharmacy baseline is checked against the National Library of
Medicine's official [RxNorm API](https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html),
using its [NDC status endpoint](https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxNorm.getNDCStatus.html).
On August 29, 2026, all 11 NDC11 values that can appear in clean generated
output—ten chronic therapies and one acute amoxicillin fill—returned active
RxNorm concepts. That public check establishes the terminology baseline for
the deliberately invalid NDCs in the evaluation profile.

The `00000000000` value associated in source code with "No drug therapy" has
zero treatment uptake and is never emitted. RxNorm contents can change over
time, so August 29, 2026 is the provenance date for the checked-in baseline
rather than a promise about future terminology releases.

## Interpretation boundaries

- Field presence and order are modeled from the cited documents. Synthetic
  CSV output is not a byte-for-byte reproduction of Aetna's fixed-width or
  tab-delimited transport files.
- A field being present does not imply that this generator reproduces a
  payer's confidential value sets, adjudication rules, masking algorithms,
  groupers, or production data distributions.
- Local schema classifications distinguish values copied from the canonical
  cohort, deterministic derivations, constants, and intentional nulls.
- All names, employers, plans, members, claims, pharmacies, facilities,
  providers, identifiers, and amounts are generated. No source record or PHI
  is used.
- Public documents are authoritative for their own published layouts. The
  generator and its mappings are an independent testing artifact and are not
  endorsed by any of the named organizations.
