# Contributing

Thanks for helping improve Tuva's synthetic claims fixtures.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Run a small end-to-end generation check before opening a pull request:

```bash
scripts/generate --members 100 --output-dir data/generated-smoke \
  --reports-dir reports/generated-smoke
```

## Pull requests

- Explain the source-layout, realism, or evaluation behavior being changed.
- Add or update deterministic tests for behavioral changes.
- Keep generated CSVs, reports, caches, and environments out of Git.
- Never contribute PHI, payer extracts, credentials, warehouse loaders, or
  environment-specific authentication instructions.
- Cite authoritative public sources for structural metadata. Store only the
  minimum factual schema contract and original Tuva-authored mapping notes;
  link to publisher descriptions instead of copying them.
- Preserve byte reproducibility for the same revision and arguments.

By contributing, you agree that your contribution is licensed under the
Apache License 2.0.
