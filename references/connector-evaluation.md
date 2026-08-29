# Connector Builder evaluation guide

These datasets are designed as a controlled source-to-Tuva evaluation corpus
for connector-building agents and workflows. The primary question is
not whether a connector can rename obvious fields. It is whether the connector
can infer grains and transaction lineage, preserve source meaning, produce the
Tuva Input Layer contract, and expose nuanced source-data problems without
silently repairing them.

## Evaluation targets

Give the Connector Builder one payer output at a time:

| Profile | Output directory | Files |
| --- | --- | --- |
| Aetna | `data/generated/aetna/` | `universal_medical_dental.csv.gz`, `universal_pharmacy.csv.gz`, `universal_medical_eligibility.csv.gz` |
| Priority Health | `data/generated/priority_health/` | `medical_claims.csv.gz`, `pharmacy_claims.csv.gz`, `eligibility.csv.gz` |
| HCCI | `data/generated/hcci/` | `medical_claims_inpatient.csv.gz`, `medical_claims_outpatient.csv.gz`, `medical_claims_physician.csv.gz`, `pharmacy_claims.csv.gz`, `member_enrollment.csv.gz` |

The public documents in [sources.md](sources.md) are appropriate inputs to a
connector-building exercise. They define the apparent source contract without
revealing which specific records were modified for evaluation.

## Blinded-run policy

Publishing the generator makes its issue classes and injection algorithms
inspectable. A blind run is therefore a procedural control, not a security
boundary: isolate the evaluated agent from this repository, evaluator-only
documentation, and prior run artifacts. A fresh undisclosed seed changes the
affected rows but does not conceal the published issue classes.

For a fair evaluation, the agent building the connector should have access to
the payer-shaped files—or raw relations loaded from only those files—and the
public source dictionaries, but not to:

- `reports/generated/<payer>/issue_manifest.csv`;
- the manifest path and issue counts recorded in `run_report.json`;
- `src/tuva_synthetic/issues.py`;
- the evaluator-only [data-quality profile](../docs/data-quality-profile.md);
- a previously completed connector for the same synthetic source.

Generated CSVs and report artifacts are ignored by Git. The issue manifest
must remain separate from the payer-shaped files and must never be placed in
an externally loaded raw schema. Treat it as test-answer material.

The manifest may be disclosed after the connector run to explain misses or
verify intended edge cases. It contains synthetic row keys, original and
injected values, the aligned Tuva Data Quality test name, expected connector
behavior, evaluation phase, expected final presence, exact source table/key
locator, and the exact Tuva Core DQ contract commit used to define the result.

## Suggested workflow

1. Generate a `connector_eval` dataset and archive its run report and manifest
   outside the connector's working context.
2. Provide the agent the source files or externally loaded raw relations,
   source dictionaries, Tuva Input Layer contracts, and ordinary Connector
   Builder instructions.
3. Have the agent profile source tables, infer claim and enrollment grains,
   implement mappings, and run Tuva Core with Input Data Quality enabled.
4. Capture the built relations, test results, and any agent-authored source
   assumptions before revealing ground truth.
5. Compare the final-action Tuva rows and Data Quality findings with the
   private manifest. Distinguish mapping failures from source defects.
6. Repeat on the other payer profiles. Do not reuse source-specific mapping
   code unless the field semantics actually match.

A clean `--issue-profile none` run can be used first for connector scaffolding
or to isolate a mapping defect. The scored or acceptance run should use a
fresh deterministic seed with `connector_eval` enabled so that hard-coded row
keys do not help.

## What successful behavior looks like

Structural mapping should preserve source identifiers as strings where
leading zeroes matter, expand repeated diagnosis and procedure slots in their
documented order, retain available source-file lineage, and produce the
documented Tuva claim-line and enrollment grains. Intentional source nulls
should not be invented merely to satisfy downstream tests.

Terminology handling should normalize valid codes according to the Tuva
contract while allowing invalid or unknown source values to remain observable.
A connector should not coerce a letter to a digit, select one of two conflicting
DRGs, manufacture coverage for a pre-enrollment claim, or rebalance a one-cent
financial discrepancy unless an explicit source rule requires it.

Provider-reference checks need a synthetic-data exception. Generated NPIs are
checksum-valid but intentionally do not match NPPES-derived Tuva
`provider_data`; rendering, billing, facility, prescribing, and pharmacy NPI
reference failures must therefore be excluded from connector scoring. There
is no deliberate checksum-invalid-NPI injection in the corpus.

Adjustment/denial/reversal (ADR) behavior is evaluated separately from field
mapping for Aetna and Priority Health only. Those two corpora include:

- an original medical transaction followed by a reversal and replacement,
  where the replacement is the final action;
- a paid medical claim followed by a complete void with no replacement, which
  must not survive as an active final claim;

This logic must operate at the source's claim-line transaction grain. Summing
every transaction, taking the highest amount, or selecting the newest file
without respecting sequence/status can each produce plausible but incorrect
results. Claims selected for static Data Quality injections are excluded from
ADR targets, so a row-level Core failure and a final-action history do not
compete for the same claim during scoring. There is no rejected-to-paid
pharmacy ADR scenario.

HCCI has no confidently resolvable native ADR expectation because its public
SDDV2 fields do not expose sufficient adjustment status and lineage. Its
behavioral source challenge is instead an exact replay of one enrollment row;
the connector should remove the replay without discarding other months. HCCI
also omits the exact Core `medical_claim__no_matching_eligibility_span`
injection because monthly enrollment fields cannot express the intended
day-level boundary faithfully.

Aetna and Priority Health receive overlapping enrollment records as distinct,
same-plan finite spans. Priority Health alone receives the claim-level
multiple-billing-NPI injection because only that projection confidently
preserves the intended inconsistency.

## Evaluation dimensions

Record results in four independent dimensions rather than reducing the run to
one pass/fail result:

- **Contract conformance:** required Tuva fields, types, flags, grains, keys,
  and source lineage are correct.
- **Semantic fidelity:** source fields are interpreted from the published
  layout and intentional nulls or invalid values are not silently fabricated
  or repaired.
- **Transaction fidelity:** Aetna/Priority replacements and voids resolve to
  the intended final action, and HCCI's exact eligibility replay is removed,
  without losing legitimate lines or member-months.
- **Data Quality observability:** the expected structural and logical failures
  surface with useful keys, while ordinary clean records do not generate a
  large volume of false positives.

The manifest supports issue-level recall analysis after the run, but it is not
a substitute for reviewing whether a connector's output grain and semantics
are sound. Some injected rows can legitimately trigger more than one Tuva
check; score the intended condition and record secondary findings separately.
Use each manifest row's `evaluation_phase` to compare like with like:
`post_connector_input_dq`, `post_connector_final_action`, or
`raw_source_deduplication`. The manifest's source table, source key column, and
source key value identify the exact raw record without relying on canonical
IDs.

## Reset and leakage controls

- Use a new root seed for a second blind run if any ground-truth files were
  exposed during development.
- Replace any externally loaded raw relations only from a complete generator
  output; do not patch individual source rows during an evaluation.
- Keep generated data and manifests out of pull requests and skill context.
- Do not present payer names, products, or code layouts as evidence that the
  synthetic records represent real payer performance or production quality.
