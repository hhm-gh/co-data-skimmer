# Caching Strategy

## Overview

All data is fetched once from the Socrata API and stored locally. Frontends
read exclusively from local files — no frontend talks to the network directly.
`collect.py` is the only network-touching component.

```
Socrata API  →  collect.py  →  data/catalog.parquet
                            →  data/co_data.duckdb
                            →  data/co_data.sqlite   (via --export)
```

---

## Cache layers

### 1. Catalog — `data/catalog.parquet`

Populated by `collect.py --search <query>`. Contains the metadata returned by
the Socrata discovery API: dataset name, ID, category, description, row count,
last-updated timestamp.

- One file, replaced on each `--search` run.
- Loaded in full by Streamlit and Marimo at startup.
- A `cached` boolean column is added at read time (by `store.get_catalog()`)
  by cross-referencing the DuckDB `_index` table.
- **Staleness note:** the `cached` column reflects DuckDB state at the time
  `--search` last ran. Fetch new datasets → re-run `--search` to refresh it.

### 2. Datasets — `data/co_data.duckdb`

Populated by `collect.py --fetch <dataset_id>`. Each dataset is stored as a
table named `ds_<id>` (dashes replaced by underscores).

An `_index` table tracks metadata for every cached dataset:

| column | description |
|--------|-------------|
| `dataset_id` | Socrata 4×4 ID |
| `name` | Human-readable name |
| `domain` | Source Socrata domain |
| `table_name` | DuckDB table name (`ds_…`) |
| `row_count` | Rows stored |
| `col_count` | Columns stored |
| `fetched_at` | Timestamp of last fetch |

Default row limit is **50,000 rows** per dataset. Pass `--rows 0` to fetch all
rows (check `row_count` in the catalog first — some datasets exceed 2M rows).

### 3. SQLite mirror — `data/co_data.sqlite`

Populated by `collect.py --export`. A full copy of the DuckDB contents written
to SQLite using pandas `.to_sql()`. Used exclusively by Datasette.

Must be re-run after each new `--fetch` to keep Datasette in sync with DuckDB.

---

## Cache-on-read (Marimo only)

The Marimo app has one exception to the "frontends don't touch the network"
rule: if a selected dataset is **not** in DuckDB, it fetches the first 1,000
rows from the API and saves them to DuckDB automatically. This makes the
Marimo app self-populating during exploration — the first view of any dataset
is live, every subsequent view is instant from cache.

The Streamlit app does **not** do this; it shows a prompt to run
`collect.py --fetch` instead.

---

## Workflow summary

```bash
# Initial population
uv run collect.py --search "colorado"       # catalog
uv run collect.py --fetch <id1> --fetch <id2>  # datasets (50k rows each)
uv run collect.py --export                  # SQLite for Datasette

# After fetching new datasets — refresh cached markers
uv run collect.py --search "colorado"

# GCP: rebuild image to publish updated cache
./deploy.sh
```

---

## What is not cached

- **Live catalog searches in Marimo**: when the user types a search term other
  than the default, Marimo queries the Socrata discovery API directly and does
  not cache the results to `catalog.parquet`. Only `collect.py --search` writes
  the catalog file.
- **Full dataset rows beyond the fetch limit**: `collect.py --fetch` stores up
  to `--rows` rows (default 50k). The remainder is not fetched unless `--rows 0`
  is used.
