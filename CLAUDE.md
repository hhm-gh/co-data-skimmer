# co-data

Colorado Information Marketplace data browser — multiple frontend implementations
over a shared local cache backed by DuckDB.

## Architecture

```
collect.py        CLI: search Socrata catalog + fetch datasets → local cache
store.py          Shared read layer used by all frontends
app_marimo.py     Marimo notebook (exploration, live API + cache fallback)
app_streamlit.py  Streamlit app (local + GCP Cloud Run deployment)
datasette.yml     Datasette config (reads data/co_data.sqlite)
Dockerfile        GCP Cloud Run image for Streamlit
data/             .gitignored local cache
  catalog.parquet       Catalog search results
  co_data.duckdb        Datasets as tables (ds_<id>) + _index table
  co_data.sqlite        SQLite mirror for Datasette (via collect.py --export)
```

## Data source

Colorado Information Marketplace — `data.colorado.gov` — Socrata SODA API, no key required.
`collect.py` works with any Socrata domain via `--domain`.

## Workflow

```bash
# 1. Populate catalog
uv run collect.py --search "colorado"

# 2. Fetch datasets into local cache (default 50k rows; --rows 0 = all)
uv run collect.py --fetch <dataset_id>
uv run collect.py --fetch <id1> --fetch <id2>

# 3. Export to SQLite for Datasette
uv run collect.py --export

# 4. Run frontends
uv run marimo edit app_marimo.py --port 2718
uv run streamlit run app_streamlit.py
uv run datasette serve data/co_data.sqlite --metadata datasette.yml

# Other Socrata portals
uv run collect.py --domain data.cdc.gov --search "covid"
```

## Frontend behaviour

| Frontend   | Catalog source     | Dataset source              | GCP-deployable |
|------------|--------------------|-----------------------------|----------------|
| Marimo     | Live API + local   | DuckDB cache, API fallback  | No (edit mode) |
| Streamlit  | Local only         | DuckDB cache only           | Yes            |
| Datasette  | —                  | SQLite export               | Yes            |

## GCP deployment

`deploy.sh` matches the pattern from `~/code/rental/deploy.sh`: builds via `gcloud builds submit`
(in GCP, not locally) and deploys to Cloud Run via Artifact Registry.

```bash
./deploy.sh          # build + deploy (run after collect.py to publish fresh data)
./deploy.sh stop     # set 0% traffic — prevents invocations without deleting
./deploy.sh start    # restore 100% traffic
./deploy.sh delete   # remove the service entirely
```

**Scale-to-zero is the primary start/stop mechanism.** Cloud Run automatically scales to zero
when idle (no cost, no requests served). Manual stop/start is only needed to explicitly prevent
cold-start invocations.

Reads project from `gcloud config get-value project`. Artifact Registry repo is created
automatically on first deploy. Requires these APIs enabled:
`run.googleapis.com`, `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com`.

Dockerfile uses `requirements.txt` (not uv) to keep the image simple. Data is bundled at build
time — re-run `collect.py` then `./deploy.sh` to publish updated datasets.

## Key design decisions

- **Cache-on-read in Marimo**: first fetch from API saves to DuckDB automatically; subsequent
  loads are instant from local cache. The `✓` column in the catalog table marks cached datasets.
- **`cached` column staleness**: the `cached` column in catalog tables (both Marimo and Streamlit)
  reflects which datasets were in DuckDB at the time `collect.py --search` last ran. If you fetch
  new datasets after searching, re-run `collect.py --search` to refresh the column.
- **`--rows 50000` default** in `collect.py --fetch`: prevents accidentally pulling multi-million-
  row datasets. Pass `--rows 0` to fetch all rows.
- **DuckDB table naming**: `ds_<dataset_id_with_dashes_replaced_by_underscores>`. The `_index`
  table in DuckDB maps dataset IDs to table names, row counts, and fetch timestamps.
- **SQLite export**: `collect.py --export` uses pandas `.to_sql()` to mirror DuckDB → SQLite.
  Re-run after each new `--fetch` to keep Datasette in sync.
- **Datasette** is purely read-only over the SQLite export; it does not talk to the API.
- **Streamlit GCP**: data is bundled into the Docker image at build time. Re-build after
  running `collect.py` to publish updated data.

## Dependencies

- `datasources` package from `../data-sources` (local editable install via uv.sources)
- Python ≥ 3.14 (matches data-sources)
- marimo ≥ 0.23.8, streamlit ≥ 1.35, datasette ≥ 0.65, duckdb ≥ 1.5.3

## Related projects

- `~/code/data-sources` — source of `datasources` package (Socrata connector, HTTP helpers)
- `~/code/housing` — same parquet + DuckDB caching pattern; marimo explore.py for analysis
