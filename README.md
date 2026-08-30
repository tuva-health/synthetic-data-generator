# Tuva Synthetic Data Generator

[![CI](https://github.com/tuva-health/synthetic-data-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/tuva-health/synthetic-data-generator/actions/workflows/ci.yml)

Deterministic, wholly synthetic longitudinal claims data shaped like public
Aetna, Priority Health, and HCCI data dictionaries. The primary use case is a
controlled evaluation corpus for source-to-Tuva connector-building workflows.

This repository contains no real patient data and no source claims extracts.
The payer names describe the public raw-file layouts being modeled; these are
not official payer datasets and are not endorsed by the source organizations.

## What it generates

Each payer gets an independent 10,000-member, two-year cohort by default. The
canonical model creates correlated enrollment, demographics, chronic
conditions, provider and facility attribution, professional and institutional
utilization, multi-line claims, plan design, network status, adjudicated
amounts, and prescription fills. Payer adapters then project that reality into
the exact published field order.

| Dataset | Raw tables | Published fields |
| --- | --- | ---: |
| Aetna | `universal_medical_dental`, `universal_pharmacy`, `universal_medical_eligibility` | 178 + 71 + 63 |
| Priority Health | `medical_claims`, `pharmacy_claims`, `eligibility` | 163 + 105 + 82 |
| HCCI 2.0 | `member_enrollment`, `medical_claims_inpatient`, `medical_claims_outpatient`, `medical_claims_physician`, `pharmacy_claims` | 17 + 76 + 46 + 42 + 20 |

The default `connector_eval` profile also introduces sparse, patterned source
problems. Examples include source- and period-clustered missing place of
service, plausible-looking invalid terminology, multiple valid DRGs on one
inpatient claim, inconsistent claim-level NPIs, temporal and penny-level
financial anomalies, claims just outside enrollment, overlapping coverage,
demographic drift, and original/reversal/replacement or void histories.
The raw values are not cleaned by the payer adapters.

Row-level issue truth is written only to the ignored local
`reports/generated/` directory, separate from the payer-shaped files. Keep
that directory outside a connector-building agent's context during a blind
evaluation. Because the generator source is public and necessarily describes
the issue classes, blindness is procedural: isolate the evaluated agent from
this repository and keep the chosen seed and row-level manifest undisclosed.

## Setup

Python 3.11 or newer is required.

```bash
git clone https://github.com/tuva-health/synthetic-data-generator.git
cd synthetic-data-generator
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest
```

## Generate locally

Generate all three default 10,000-member cohorts:

```bash
scripts/generate
```

The platform-neutral equivalent is:

```bash
.venv/bin/python -m tuva_synthetic
```

Generate one smaller fixture or a clean comparison dataset:

```bash
scripts/generate --payer aetna --members 1000
scripts/generate --payer hcci --members 1000 --issue-profile none
```

Important options are `--payer`, `--members`, `--start-date`, `--end-date`,
`--seed`, `--issue-profile`, `--output-dir`, and `--reports-dir`. CSV outputs
are gzip-compressed and byte-reproducible for the same arguments, including
across Python hash seeds.

See every option without generating data:

```bash
scripts/generate --help
```

Generated files go to:

- `data/generated/<payer>/*.csv.gz`
- `reports/generated/<payer>/validation_report.json`
- `reports/generated/<payer>/issue_manifest.csv` (private evaluation truth)
- `reports/generated/run_report.json`

Both generated directories are excluded from Git.

## Reproducibility

The default arguments are part of the dataset contract:

| Argument | Default |
| --- | --- |
| Members | 10,000 per payer profile |
| Period | 2024-01-01 through 2025-12-31 |
| Root seed | `20260829` |
| Issue profile | `connector_eval` |

The same repository revision and arguments produce the same members, claims,
amounts, injected issue locations, reports, and gzip bytes. Stable
payer-specific seed offsets keep the three cohorts independent without making
reruns drift. To create a different but repeatable corpus, provide a new seed:

```bash
scripts/generate --seed 314159
```

Rerunning that command with the same code and arguments reproduces the same
files. Changing the seed, member count, date range, issue profile, or generator
revision intentionally changes the corpus.

## Using the files

Each gzip file is an ordinary UTF-8 CSV with a header row. The corresponding
JSON file under `schemas/<payer>/` defines exact column order, source type and
length metadata, and generator-owned modeling decisions. Follow its source
links for the publisher's field descriptions. Use those artifacts together
when profiling a source or building a connector.

Warehouse loading is intentionally outside this repository's scope. The
repository contains no warehouse client, loader, credential integration,
account identifier, role name, or environment-specific loading procedure. If
the files are loaded into a database for evaluation, use the organization's
normal governed ingestion tooling and expose only the resulting raw relations
and public dictionaries to the connector builder.

## Design and source context

- [Canonical model](references/canonical-model.md)
- [Source dictionaries](references/sources.md)
- [Generation methodology](references/methodology.md)
- [Connector evaluation](references/connector-evaluation.md)
- [Data-quality profile](docs/data-quality-profile.md)
- Payer-specific notes: [Aetna](references/aetna.md), [Priority Health](references/priority_health.md), [HCCI](references/hcci.md)

The schemas under `schemas/` are structural metadata transcribed from public
documentation. They record field order, type/length metadata, canonical
mapping, and whether each field is modeled, derived, constant, or
intentionally null. See the methodology for known limitations; in particular,
synthetic HCCI identifiers are deterministic stand-ins rather than HCCI's
proprietary encryption output.

## License

Apache License 2.0. See [LICENSE](LICENSE).
