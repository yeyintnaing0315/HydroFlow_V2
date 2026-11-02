# HydroFlow V2 audit report

Audit date: 2026-10-15. Scope: repository, backend, database, ML, frontend,
providers, tests, deployment, geography, licensing, and documentation.

## Existing strengths

- FastAPI already exposed forecast, historical weather, census, flood-history,
  topography, routing, prediction, help, and prototype-alert APIs.
- React/Leaflet already provided a Bago township-centroid dashboard with strong
  non-operational disclaimers.
- The ML pipeline used chronological train/validation/test blocks, rebuilt
  trailing features causally, excluded impact leakage fields, persisted the
  complete sklearn pipeline, and did not retrain during test evaluation.
- Alert and location uniqueness constraints provided limited idempotency.
- Raw-data provenance was verifiable: SHA-256
  `c257da50c3bd912cae33e2d4255e82ed337ebbe9c67e07db47d20ac1a8f7b727`,
  40,172 rows.

## Material gaps found

- `db.create_tables()` performed startup schema mutation and deletion; no
  versioned migrations existed.
- Live weather/discharge was not persisted, despite an observation table and
  documentation suggesting otherwise. There were no provider, dataset,
  official-warning, inundation, model registry, result, or job-run tables.
- No scheduler, retry strategy, run lock, manual protected run, source
  monitoring, freshness, or coverage audit existed.
- APIs were unauthenticated; prediction requests could create records called
  alerts even though they were model/heuristic notices, not official warnings.
- Geography was hardcoded into six regrouped districts, mixed fallback IDs,
  an OSM fallback centroid, and an Open Admin Data response. The UI supported
  centroids only, and relief slugs did not reliably join to admin IDs.
- The same-day historical label task was used with future forecast inputs.
  Untouched-test flood F1 was 0.0293 with only 11 flood rows; scores were
  uncalibrated but displayed as percentages. The help model test F1 was 0.0196.
- Frontend/backend contracts included a mixed hourly-weather/daily-discharge
  list; several backend filters/endpoints were unused. No official-warning,
  observed-inundation, prediction, and heuristic layer separation existed.
- MIMU online embedding requires written permission. OCHA COD-AB is usable
  under CC BY 3.0 IGO but is based on MIMU v9.4, has documented uncorrected
  errors, and partial admin-4/5 coverage. No documented public DMH API was
  found.

## Baseline execution

- Raw hash and row count: passed.
- ML tests before implementation: 18 passed.
- Frontend tests before implementation: 4 passed.
- Frontend production build before implementation: passed.
- Docker Compose configuration before implementation: valid.
- Backend baseline run completed 32 tests and exposed one failure while the
  health endpoint was being upgraded during implementation; the final clean
  run is recorded in the verification handoff.

The detailed source/licence decisions are in `data-provenance.md`; model
evidence and limitations are in `ml-methodology.md`.
