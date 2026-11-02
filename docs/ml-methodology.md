# HydroFlow V2 ML methodology

## Scope

This is an interpretable academic prototype, not an operational warning system.
The target is the source dataset's incomplete relief-derived flood indicator.
Rainfall is reanalysis data and discharge is modelled, not a measured gauge
height. Results therefore measure agreement with this dataset, not general flood
detection performance.

## Data and leakage controls

Ingestion and validation are separate from feature engineering. Validation
checks schema, binary labels, duplicate township/date keys, coordinates,
non-negative hydro-meteorological values, and required-field completeness.

The V2 feature schema uses rainfall, modelled discharge, coordinates,
seasonality, and trailing values computed within township. NASA POWER soil
wetness and humidity were removed because those retrospective fields are not
available for future outlook dates. Rolling windows are right-aligned and use
only the current or earlier row. Tests mutate future
weather values and verify that earlier features do not change.

The flood label is the same calendar day as rainfall and discharge. Same-day
weather is contemporaneous with the label, not a forecast lead. Exploratory
analysis reports consecutive flood-day runs, flood counts by township, and how
many positives fall in the chronological test block.

`households` and `affected_people` are post-event impact observations. They are
explicitly excluded from predictive features. The source file's precomputed
rolling columns are also rebuilt rather than trusted.

## Splitting, fitting, and evaluation

Complete dates are split chronologically: first 60% train, next 20% validation,
last 20% test. The class-weighted logistic regression and all preprocessing are
fit on train only. Numeric fields are median-imputed and standardized. The
persisted artifact contains both preprocessing and classifier.

The decision threshold is selected on validation by maximum flood-class F1.
The final test block remains untouched until evaluation, and evaluation only
loads the saved pipeline. Reported metrics are precision, recall, F1, average
precision (PR-AUC), ROC-AUC, confusion matrix, a threshold sweep, and secondary
accuracy. Per-township precision, recall, and F1 are reported only when a block
contains at least five flood days for that township. Event recall treats a
consecutive township flood run as detected when any day in the run is predicted
positive, and it is marked as a limited sample below five events.

The same untouched test labels are also scored with two naive rules: always no
flood, and always flood. Those scores sit beside the published Hydroflow
RandomForest test metrics (flood precision 0.005, recall 0.818, F1 0.01). That
earlier run used a different feature set and a test window starting one day
later, so it is context rather than a paired rescore. A new tree is not fit:
the train and test blocks are too sparse to justify a second, less interpretable
model. Coefficients are persisted for inspection.

Calibration is not applied: using the same validation data for both threshold
selection and calibration would not be independent, while subdividing the
already rare chronological positives would make calibration unstable.

## Severity

`academic_impact_severity` is an optional retrospective rule:

- score = households + affected_people / 5
- none: 0; low: greater than 0; moderate: at least 100
- high: at least 500; severe: at least 2,000

It uses impact fields available after an event. It is not a learned model, is not
a predictive feature, and must not be described as forecast severity.

## Current V2 results

The untouched chronological test block has only 11 flood rows. The V2 flood
model has precision 0.0155, recall 0.2727, F1 0.0293, and PR-AUC 0.0238. These
figures are too sparse for operational interpretation. The full V1/V2
comparison and label-distribution audit are in `model-repair-report.md`.

## Flood help model

A second artifact, `flood-help-v2`, estimates humanitarian assistance demand.
It does not replace the flood-occurrence baseline and it is not a tree model.

The classifier target is `help_needed`: 1 when recorded `households` or
`affected_people` is greater than zero. Two Ridge models then estimate
`log1p(affected_people)` and `log1p(households)`, and they are fit only on train
rows where help was needed. Features are the same hydrologic columns as the
flood model. Impact fields and the flood label are excluded from inputs.

The help-class threshold maximizes F1 on the chronological validation block.
Expected counts are the help probability times the magnitude estimate. Shelter
kits, 3-day food rations, and drinking water multiply those expected counts by
fixed planning ratios stored in the metadata. Assistance priority applies the
retrospective severity rule to the expected counts. The untouched test block is
used only in `evaluate-help`.

Its untouched-test help F1 is 0.0196 and expected-affected-people MAE is 399.2.
It is an academic planning illustration, not an operational caseload estimate.
