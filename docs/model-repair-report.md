# Model repair report

## Why the live feature schema changed

The V1 pipelines used NASA POWER root-zone soil wetness and relative humidity for
same-day scoring. NASA POWER daily data is retrospective, so those values are not
reliably available for future outlook dates. The V2 pipelines remove both fields
and use twelve features derived from Open-Meteo rainfall, GloFAS discharge,
calendar position, and location. Historical NASA POWER weather remains available
for retrospective dashboard charts only.

## Untouched chronological test comparison

Flood occurrence:

- V1 (14 features): precision 0.0612, recall 0.2727, F1 0.1000, PR-AUC 0.1885.
- V2 (12 forecast-available features): precision 0.0155, recall 0.2727, F1
  0.0293, PR-AUC 0.0238.

Flood-help classification:

- V1: precision 0.0408, recall 0.2000, F1 0.0678, expected-people MAE 353.2.
- V2: precision 0.0103, recall 0.2000, F1 0.0196, expected-people MAE 399.2.

The lower V2 scores are retained and reported because the V1 inputs were not
available for a genuine future outlook. The repair improves serving validity; it
does not claim improved predictive skill.

## Data audit

- The source has 40,172 township-days and 220 positive flood rows (0.55%).
- The chronological blocks contain 42 train, 167 validation, and 11 test flood
  rows. The untouched test block therefore has too few positives for stable
  township-level conclusions.
- Labels are temporally concentrated: 167 positives occur in 2024, 11 in 2025,
  and none in the available 2026 rows. This distribution shift requires a
  provenance and label-completeness review before further model tuning.
- Every one of the 22 townships has at least one positive across the full
  dataset, but none has five positives in the test block, so township test
  metrics are intentionally suppressed.
- Duplicate township/date rows, invalid dates, missing required model fields,
  non-binary labels, and invalid coordinates are rejected by validation.

## Required next data milestone

Add independently verified and consistently collected flood labels for later
years, preserving event dates and township provenance. Re-evaluate with a new
untouched time block only after label coverage is confirmed. Do not compensate
for missing real events by treating synthetic positives as evaluation evidence.
