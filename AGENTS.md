# Tuva Synthetic Data Generator

- All generated people, identifiers, providers, facilities, claims, and
  pharmacy fills must be wholly synthetic. Never ingest or reproduce PHI.
- Preserve deterministic generation from an explicit seed.
- Treat public payer data dictionaries as structural references, not as
  permission to redistribute their documents. Store source links and concise
  mapping notes rather than vendored source files.
- Keep generated datasets and credentials out of Git.
- A payer adapter must preserve the published table and field names where the
  public dictionary is sufficiently clear. Mark modeled, derived, constant,
  and intentionally-null fields in its schema metadata.
- Validate identifiers, grains, relationships, dates, financial arithmetic,
  claim adjustment behavior, and distributional targets before loading data.
- Keep warehouse loaders, account or role names, authentication integrations,
  and environment-specific loading instructions outside this public repository.
