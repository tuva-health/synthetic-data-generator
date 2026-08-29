# Generation methodology

The generator creates a coherent longitudinal commercial population first and
then projects that population into payer-shaped raw tables. This separation is
important: utilization, diagnoses, enrollment, providers, and financials are
correlated before any adapter applies source-specific names or encodings.

## Default run

The default invocation produces an independent 10,000-member cohort for each
payer profile over January 1, 2024 through December 31, 2025. The root seed is
`20260829`; stable payer offsets keep the three cohorts deterministic without
making their rows identical. A run can reduce member count or change the date
range and seed for faster development.

The build path is:

1. Generate a clean canonical cohort.
2. Validate keys, relationships, financial identities, dates, and broad
   utilization ranges.
3. Apply the selected issue profile. The default `connector_eval` profile
   introduces sparse, clustered defects plus only the transaction histories
   that the selected source layout can support confidently.
4. Project the canonical rows through an Aetna, Priority Health, or HCCI
   adapter in exact checked-in schema order.
5. Validate table presence, exact column sets, and unique column names.
6. Write deterministic gzip-compressed CSV files and private validation
   artifacts. Warehouse ingestion remains outside this repository.

Use `--issue-profile none` to produce the clean baseline. Use
`--issue-profile connector_eval` for a connector evaluation corpus.

## Population and enrollment

Members are generated in households with subscribers, spouses, and dependent
children. Household members share subscriber, surname, geography, employer
group, product, funding arrangement, source system, and plan context while
retaining individual member and person identifiers.

Subscriber ages use a bounded adult distribution. Dependent ages and
relationships are conditioned on the subscriber. Geographic and product
mixtures differ by profile: Priority Health is Michigan-centered, Aetna spans
multiple large commercial markets, and HCCI spans a broader contributor mix.
Member-month enrollment includes realistic mid-period starts, terminations,
and occasional one- or two-month gaps. Pharmacy and mental-health coverage,
PCP assignment, ASO versus fully insured funding, and product type persist
coherently across each enrollment history.

## Morbidity and utilization

Chronic conditions are sampled with age- and, where relevant, sex-dependent
probabilities. Selected comorbidities are correlated—for example, diabetes can
increase the likelihood of hyperlipidemia, and coronary disease can increase
the likelihood of hypertension. A member risk score combines age and
condition burden.

Medical event counts are Poisson draws conditioned on age and condition
count. Professional, outpatient, emergency, and inpatient encounters have
different base rates, denial rates, line counts, provider specialties, sites
of service, and financial scales. Diagnoses are tied to chronic or acute
events; inpatient templates tie diagnoses, MS-DRGs, procedures, length of
stay, and revenue-center lines together. Claims occur only during active
enrollment before deliberate issue injection.

Pharmacy utilization is conditioned on chronic disease, prescription
coverage, treatment uptake, and member-level adherence. Thirty- and 90-day
fills, refill sequences, mail order, maintenance status, generic status,
prescriber and pharmacy identifiers, and occasional acute antibiotic fills
are modeled together. The 11 NDCs that can appear in the clean output were
verified as active through the official NLM RxNorm API on August 29, 2026; see
[sources.md](sources.md).

## Providers and financials

The shared provider pool contains 800 checksum-valid synthetic NPIs across ten
specialties. The facility pool contains 80 hospitals, ambulatory surgery
centers, diagnostic centers, and urgent-care organizations. Identifiers use
reserved-looking synthetic prefixes and deterministic checksums; they do not
come from NPPES or a payer and intentionally do not match NPPES-derived Tuva
`provider_data`. Provider-reference invalid tests are consequently background
artifacts of synthetic identity and are excluded from evaluation scoring.

Charges use right-skewed log-normal variation around setting-specific costs.
Allowed amounts depend on network status. Copay, deductible, and coinsurance
depend on product and setting, with deductible exposure declining through the
year. Clean final-action rows satisfy both of these identities within currency
rounding:

```text
allowed = plan paid + member paid + other payer paid
member paid = coinsurance + copay + deductible
```

Denied rows retain charges but carry zero allowed and paid amounts. A targeted
paid-greater-than-allowed defect sets member responsibility and other payer
amounts to zero, then sets plan paid to exactly one cent above allowed. This
isolates the intended Core failure from unrelated cost-share arithmetic.
Aetna and Priority Health adjustment transactions can contain negative values
that reverse prior activity; no native medical ADR history is asserted for
HCCI because its public layout does not expose enough status/lineage semantics
to resolve final action confidently.

## Raw projections

File names are normalized to lowercase. Columns retain the adapter's published
or disambiguated source names in exact schema order.

| Output directory | File | Grain |
| --- | --- | --- |
| `aetna` | `universal_medical_dental.csv.gz` | Claim service line or adjustment transaction |
| `aetna` | `universal_pharmacy.csv.gz` | Pharmacy transaction |
| `aetna` | `universal_medical_eligibility.csv.gz` | Member × active enrollment month |
| `priority_health` | `medical_claims.csv.gz` | Claim service line or adjustment transaction |
| `priority_health` | `pharmacy_claims.csv.gz` | Pharmacy transaction |
| `priority_health` | `eligibility.csv.gz` | Member × eligibility reporting month |
| `hcci` | `medical_claims_inpatient.csv.gz` | Inpatient service line |
| `hcci` | `medical_claims_outpatient.csv.gz` | Outpatient or emergency facility service line |
| `hcci` | `medical_claims_physician.csv.gz` | Professional service line |
| `hcci` | `pharmacy_claims.csv.gz` | Pharmacy transaction |
| `hcci` | `member_enrollment.csv.gz` | Member × active enrollment month |

## Validation and reproducibility

Clean canonical validation checks uniqueness and referential integrity,
transaction-line grain, financial identities, positive line numbers, service
date order, exposure, and broad commercial utilization bounds. The evaluation
profile permits only its documented exceptions and also requires the core
issue classes to be present at a low overall density. Projection validation
requires every output row to have exactly the checked-in schema columns. The
private manifest is enriched after projection with an exact raw table/key
locator and is validated against the emitted tables.

The Python random generator is locally seeded and source iteration order is
stable. Dates, booleans, arrays, and decimals have explicit serialization, and
gzip timestamps are fixed. Given the same revision and arguments, generated
files are byte reproducible.

## Privacy and limitations

- The corpus is entirely synthetic and is not intended for clinical care,
  actuarial pricing, network analysis, payment policy, or payer benchmarking.
- Names are sampled from small synthetic lists. Where a source layout requires
  addresses, phone numbers, SSN-shaped values, or other identifier-shaped
  fields, populated values are visibly fictional and deterministic. No value
  comes from a real person, and none should be joined to external identity
  data.
- Checksum-valid synthetic NPIs deliberately have no NPPES/Tuva provider-data
  identity. Provider-reference failures are not evidence of connector defects.
- Real claims contain more coding, benefit, provider, and adjustment diversity
  than a tractable test corpus. Passing against these datasets is evidence of
  connector behavior, not proof of production readiness.
- Public data dictionaries omit proprietary value sets and transformations.
  Representative encodings are documented in each payer reference and should
  not be treated as current payer business rules.
- The three payer profiles use the same modeling framework. They are useful
  for testing structural adaptation, but they are not statistically
  independent estimates of real payer populations.
