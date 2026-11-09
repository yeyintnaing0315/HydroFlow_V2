FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# deb.debian.org on port 80 is refused from this network. The slim image
# already has CA certificates, so use the same mirror over HTTPS.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Keep the repo layout. The API resolves data and models from the project root,
# which is three levels above backend/app/services.
COPY backend/app backend/app
COPY ml/models ml/models
COPY ml/flood/static_prior.py ml/flood/static_prior.py
COPY data/external/bago_census_2024.json data/external/bago_census_2024.json
COPY data/external/bago_river_points.csv data/external/bago_river_points.csv
COPY data/external/geography data/external/geography
COPY data/offline/flood_sources.sqlite data/offline/flood_sources.sqlite

ENV MODEL_PATH=/app/ml/models/bago_flood_model.joblib
ENV MODEL_METADATA_PATH=/app/ml/models/bago_flood_model_metadata.json
ENV SECONDARY_MODEL_PATH=/app/ml/models/bago_flood_model_logistic.joblib
ENV SECONDARY_MODEL_METADATA_PATH=/app/ml/models/bago_flood_model_logistic_metadata.json
ENV CENSUS_PATH=/app/data/external/bago_census_2024.json

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
