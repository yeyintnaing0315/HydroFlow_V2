# Architecture and limitations

## Data flow

1. The immutable Bago CSV in `data/raw/` is validated and transformed by
   `ml/hydroflow_ml/`.
2. Training creates scikit-learn pipelines and metadata in `artifacts/`.
   The flood-help pipeline estimates assistance demand from the same hydrologic
   features. Household and population counts are its targets, not its inputs.
3. FastAPI loads each saved pipeline once and performs inference only.
4. Risk scoring is a separate, documented academic heuristic.
5. Open-Meteo supplies forecast rainfall and GloFAS supplies modeled forecast
   discharge for the twelve-feature V2 model. NASA POWER supplies historical
   weather for retrospective charts only and is not a live model input.
   OpenTopography supplies
   Copernicus GLO-30 surface elevation for the selected point. That elevation
   is shown as terrain context and is not a model feature. Kardinal orders a
   caller-supplied delivery round. The dashboard sends township centroids, so
   that route is an illustration, not a site-level dispatch plan.
6. The React dashboard uses only backend responses and visibly labels demo
   inputs. The humanitarian view also reads `/census`, the 2024 Bago population,
   age-group, and household-situation reference. That reference is not a model
   feature.
7. PostgreSQL stores application locations, observation metadata, and alerts;
   source CSVs and model artifacts remain file based.

## Safety and scientific limits

- Test flood F1 is low because positive labels are rare and shift over time.
- Removing future-unavailable NASA fields reduced untouched-test flood F1 to
  about 0.029; serving validity takes priority over the stronger but unusable
  V1 score.
- Model scores are not independently calibrated operational probabilities.
- GloFAS discharge is not measured river height.
- Severity categories are retrospective impact rules, not forecast classes.
- Alerts are prototype in-app records, not official emergency notifications.
- Flood-help counts and planning ratios are academic illustrations, not operational caseload or logistics plans.
- No output is suitable for public-safety decisions without independent
  hydrological validation and local authority review.
