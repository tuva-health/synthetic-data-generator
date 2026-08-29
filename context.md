# Repository context

## Purpose

This repository owns deterministic, payer-shaped synthetic claims corpora for
testing source-to-Tuva connector development and connector-building agents.

The generator creates a coherent synthetic healthcare population and then
projects it into public Aetna, Priority Health, and HCCI layouts. It is a
standalone testing utility: it does not change Tuva Core public contracts,
publish Tuva package data assets, or contain real payer records.

## Current dataset contract

- Default population: 10,000 members per payer profile.
- Default period: January 1, 2024 through December 31, 2025.
- Default seed: `20260829`, with stable payer-specific offsets.
- Default issue profile: `connector_eval`.
- Local format: deterministic gzip CSV plus ignored validation artifacts.

All raw layouts and column orders are versioned under `schemas/`. Public source
documents establish structure only. Synthetic value distributions and mapping
decisions are independent implementation choices documented under
`references/`.

## Evaluation integrity

The raw corpus includes low-density, nonuniform data problems aligned to Tuva
Input Data Quality and connector transaction behavior. The private issue
manifest is the evaluator's answer key. Never commit it, mix it with the raw
output files, or give it to the connector-building agent before a blind run is
complete.

Use `--issue-profile none` for a clean diagnostic control. Use a fresh seed if
ground truth from an evaluation run has leaked into the builder's context.

## Boundaries

- Entirely synthetic; no PHI, source extracts, enclave data, or production
  credentials belong here.
- Warehouse loading is deliberately outside this repository's scope.
- Payer names refer to modeled public schemas, not official datasets or
  endorsements.
- This corpus is for software evaluation, not clinical, actuarial, payment,
  network, or payer-performance analysis.
- Passing these fixtures does not prove production connector readiness.

Read `AGENTS.md` before making changes and `README.md` for operating commands.
