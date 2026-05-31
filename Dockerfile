# GCP Cloud Run deployment for the Streamlit app.
#
# Build and run locally:
#   docker build -t co-data .
#   docker run -p 8080:8080 co-data
#
# Deploy to Cloud Run:
#   gcloud run deploy co-data --source . --region us-central1 --allow-unauthenticated
#
# Note: data/ is copied into the image at build time. Re-build after running
# collect.py to update the bundled dataset cache.

FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (layer-cached)
COPY pyproject.toml .
# Streamlit-only deps for the production image (no marimo/datasette/jupyter)
RUN uv pip install --system streamlit pandas pyarrow duckdb requests

# Copy app code and data
COPY store.py app_streamlit.py ./
# Bundle the local data cache into the image
COPY data/ data/

EXPOSE 8080

CMD ["streamlit", "run", "app_streamlit.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
