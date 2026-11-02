# HydroFlow V2 machine learning

This directory contains a deterministic, leakage-aware academic flood-risk
baseline and a separate flood-help model. The baseline predicts the observed
binary `flood` label with a class-weighted logistic regression. The flood-help
model estimates whether assistance is needed and the expected households and
affected people. `households` and `affected_people` are targets of that second
model and are never inputs to either model.

## Setup and commands

Run from the repository root:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r backend/requirements.txt -r ml/requirements.txt
.venv/Scripts/python.exe ml/run.py validate
.venv/Scripts/python.exe ml/run.py process
.venv/Scripts/python.exe ml/run.py eda
.venv/Scripts/python.exe ml/run.py train
.venv/Scripts/python.exe ml/run.py evaluate
.venv/Scripts/python.exe ml/run.py train-help
.venv/Scripts/python.exe ml/run.py evaluate-help
```

`ml/run.py eda` validates the raw file first and summarizes that cleaned dataset.
`ml/run.py run-all` runs all phases in order. Tests run with:

```powershell
.venv/Scripts/python.exe -m pytest -c ml/pytest.ini ml/tests
```

Inference accepts a CSV containing the engineered columns listed in
`hydroflow_ml.config.MODEL_FEATURES`:

```powershell
.venv/Scripts/python.exe ml/run.py predict data/processed/model_features.csv --output artifacts/predictions.csv
```

The feature input must include enough correctly ordered history for trailing
features to have been computed by `process`; inference itself does not read
labels or impact fields.

V2 uses twelve forecast-available rainfall, discharge, calendar, and location
features. NASA POWER soil wetness and humidity remain available for offline
historical comparison but are not model inputs.

## Outputs

- `data/processed/validated_daily.csv`: validated, canonical source copy
- `data/processed/model_features.csv`: deterministic same-day/trailing features
- `data/processed/split_assignments.csv`: auditable date-block assignments
- `artifacts/eda_summary.json`: dataset and label-distribution summary
- `artifacts/flood_logistic_pipeline.joblib`: preprocessing and classifier
- `artifacts/model_metadata.json`: threshold, splits, exclusions, coefficients
- `artifacts/evaluation_metrics.json`: validation and untouched-test metrics, threshold behavior, township and event summaries, and naive plus published Hydroflow comparisons
- `artifacts/evaluation_predictions.csv`: row-level validation/test predictions
- `artifacts/flood_help_pipeline.joblib`: help classifier and two Ridge magnitude models
- `artifacts/help_model_metadata.json`: help threshold, exclusions, planning ratios, and coefficients
- `artifacts/help_evaluation_metrics.json`: untouched validation and test help metrics
- `artifacts/help_evaluation_predictions.csv`: row-level help predictions

The threshold maximizes F1 on the chronological validation block. The test block
is not used for fitting, threshold selection, or calibration. Probability
calibration is intentionally omitted because there is no additional independent
chronological calibration block; reported scores are model scores and should not
be interpreted as operationally calibrated probabilities.

Any severity derived by `severity.py` is a retrospective, rule-based academic
impact category. It uses observed impact fields, is not trained ML, and must
never be presented as a forecast.
