# HCCI 2.0 synthetic projection

## Structural sources

- Health Care Cost Institute, [HCCI 2.0 General Data Dictionary](https://healthcostinstitute.org/wp-content/uploads/2026/06/HCCI_2.0_General_Data_Dictionary_20260701.pdf), version 2.0, effective July 1, 2026. The current PDF is 12 pages and identifies the published view as SDDV2.
- HCCI, [Data Access Hub](https://healthcostinstitute.org/data-access-hub/), retrieved August 29, 2026. The page describes the commercial dataset, licensing, and secure-enclave access model.

The public dictionary was used only as a structural reference. No HCCI claim,
member, provider, or pharmacy record was accessed or copied.

## Field coverage

The checked-in ordered schemas cover all 201 fields in the July 2026 PDF:

| Synthetic raw table | Published fields | Synthetic grain |
| --- | ---: | --- |
| `member_enrollment` | 17 | member × active month |
| `medical_claims_inpatient` | 76 | inpatient service or adjustment line |
| `medical_claims_outpatient` | 46 | outpatient/emergency facility service or adjustment line |
| `medical_claims_physician` | 42 | professional service or adjustment line |
| `pharmacy_claims` | 20 | pharmacy fill or adjustment transaction |

Each column records its ordinal, published name, published data type and
length, concise meaning, canonical source, default, and whether it is modeled,
derived, constant, or intentionally null. The schemas preserve the PDF's
`Vachar` spelling for pharmacy `HNPI_BE` and separately identify `Varchar` as
the normalized type for DDL.

## Projection decisions

- `Z_PATID` is a deterministic 19-digit hash of contributor and synthetic
  person. This fits the enrollment limit and is reused in every claim table,
  whose published limit is 32. Contributor is included because HCCI says the
  identifier is not stable across data contributors.
- `Z_CLMID` is a contributor-scoped 32-digit deterministic claim hash.
  Admission and visit identifiers are separate 32-character hashes based on
  the original claim, so adjustment lines remain grouped.
- Provider and billing-entity NPIs use a contributor-independent,
  32-character SHA-256 prefix. This models HCCI's cross-contributor stability,
  but does not claim to reproduce HCCI's or Humana's encryption algorithm.
- Enrollment and claim months are emitted as two digits even though the PDF
  gives `MNTH` a length of 8. This follows the field description rather than
  padding the value.
- The public dictionary names the age ranges but does not publish their code
  lookup. The projection uses deterministic codes `01` through `09` in the
  published age-range order.
- Member and provider CBSAs are derived from the generator's finite metro ZIP
  list. HRR is a stable three-digit modeled value because the HCCI-specific
  CBSA-to-HRR crosswalk is not public. All configured ZIPs are metropolitan,
  so their rural flag is `0`; missing or unmapped ZIPs yield null geography
  derivatives.
- HCCI high-level categories are constant by file family: `IP`, `OP`, `PP`,
  and `RX`. `MDC` is derived from public MS-DRG range structure, while
  `DRG_DRVD` retains the modeled DRG as the result of that synthetic grouping.
- The generated period begins after the ICD-10 transition, so ICD-9 diagnosis
  and procedure fields are intentionally null. The synthetic employer SIC
  category is also null because the canonical cohort does not model employer
  industry.
- Allowed amount, net plan payment, total member cost share, coinsurance,
  copay, and deductible are projected independently. This intentionally
  preserves injected arithmetic errors, negative reversals, denied claims,
  and adjustments for downstream Tuva Data Quality evaluation.
- Invalid or missing POS, diagnosis, CPT/HCPCS, ICD-10-PCS, DRG, and revenue
  codes are not sanitized. Multiple DRGs on lines of one claim are preserved.

## Limitations

The public document defines fields but does not provide all value-set lookups,
data-contributor transformations, suppression implementation, or the actual
HCCI grouper. Synthetic age bands, HRRs, high-level categories, and hashes are
therefore representative implementations rather than replicas. The HCCI data
itself is licensed for secure-enclave research and is not redistributed here.
