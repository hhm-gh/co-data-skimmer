# co-data-skimmer

Browse and preview datasets from the [Colorado Information Marketplace](https://data.colorado.gov) — three frontend implementations over a shared local cache.

## Frontends

| App | Command | Best for |
|-----|---------|----------|
| **Marimo** | `uv run marimo edit app_marimo.py` | Exploration — live catalog search, cache-on-read |
| **Streamlit** | `uv run streamlit run app_streamlit.py` | Presentation — local or GCP Cloud Run |
| **Datasette** | `uv run datasette serve data/co_data.sqlite --metadata datasette.yml` | Ad-hoc querying, filtering, CSV export |

## Screenshots

### Streamlit — catalog with sidebar filters
![Streamlit catalog](screenshots/streamlit-catalog.png)

### Streamlit — dataset preview
![Streamlit dataset preview](screenshots/streamlit-preview.png)

### Datasette — home
![Datasette home](screenshots/datasette-home.png)

### Datasette — browsing a dataset
![Datasette dataset](screenshots/datasette-dataset.png)

## Quickstart

```bash
git clone https://github.com/hhm-gh/co-data-skimmer
cd co-data-skimmer
uv sync

# Populate the local catalog
uv run collect.py --search "colorado"

# Fetch a couple of datasets
uv run collect.py --fetch 4e3w-qire   # Unemployment Estimates
uv run collect.py --fetch k4uv-yvnk   # Current Notaries

# Re-run search to refresh the cached (✓) markers in the catalog
uv run collect.py --search "colorado"

# Export to SQLite for Datasette
uv run collect.py --export

# Launch any frontend
uv run marimo edit app_marimo.py
```

> **Note:** The `cached` column (✓ markers) in the catalog table reflects which datasets were
> in DuckDB at the time `--search` last ran. If you fetch new datasets, re-run
> `collect.py --search` to refresh it.

## Data collection

`collect.py` is the only piece that talks to the network. Everything else reads from `data/`.

```bash
# Search the catalog (saves to data/catalog.parquet)
uv run collect.py --search "traffic crashes"

# Fetch a dataset (saves to data/co_data.duckdb, default 50k rows)
uv run collect.py --fetch <dataset_id>

# Fetch all rows (can be very large — check row count first)
uv run collect.py --fetch <dataset_id> --rows 0

# Fetch multiple datasets at once
uv run collect.py --fetch <id1> --fetch <id2>

# Export DuckDB → SQLite for Datasette (re-run after each new fetch)
uv run collect.py --export

# Works with any Socrata portal
uv run collect.py --domain data.cdc.gov --search "covid"
uv run collect.py --domain data.gov --search "census"
```

## Architecture

```
collect.py          CLI — Socrata API → local cache
store.py            Shared read layer (all frontends import this)
app_marimo.py       Marimo notebook — live search + DuckDB cache fallback
app_streamlit.py    Streamlit app — local-only, GCP-deployable
datasette.yml       Datasette metadata config
Dockerfile          Cloud Run image for Streamlit
data/               Local cache (git-ignored)
  catalog.parquet       Catalog search results
  co_data.duckdb        Datasets as tables + _index registry
  co_data.sqlite        SQLite mirror for Datasette
```

## GCP deployment (Streamlit)

The Streamlit app bundles `data/` into the Docker image at build time — no network calls at runtime.

```bash
# After populating data/ with collect.py:
docker build -t co-data-skimmer .
docker run -p 8080:8080 co-data-skimmer

# Deploy to Cloud Run
gcloud run deploy co-data-skimmer \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

Re-build the image after running `collect.py` to publish updated data.

## Dependencies

- Python ≥ 3.14, [uv](https://docs.astral.sh/uv/)
- [`data-sources`](https://github.com/hhm-gh/data-sources) package (sibling repo, provides the Socrata connector)

```bash
# data-sources must be checked out alongside this repo
git clone https://github.com/hhm-gh/data-sources ../data-sources
```
