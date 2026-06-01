# Efficient Data Connector Reuse

How to spin up a new data browser project that reuses the co-data-skimmer pattern.

## The three-step approach

1. **Add the data source connector to `~/code/data-sources`** alongside the existing connectors
   (`coloradogov.py`, `census.py`, `bls.py`, etc.). That package is already the abstraction layer —
   a new connector there means the new project's `collect.py` just imports it, and `store.py` copies
   over unchanged.

2. **Start the new project by copying co-data-skimmer**: `collect.py`, `store.py`,
   `app_streamlit.py`, `app_marimo.py`, `deploy.sh`, `Dockerfile`, `requirements.txt`.
   Note in the new project's `CLAUDE.md`:
   > *"Follows the pattern from `~/code/co-data-skimmer` — read that project's `CLAUDE.md` for
   > architecture context."*
   A future Claude session reads both and has full context instantly.

3. **Memory carries over**: the `project-co-data` memory file describes the collect → store →
   frontend pattern at a level that transfers to any new project. No extra setup needed.

---

## ACS / Census Bureau

`~/code/data-sources/src/datasources/census.py` already exists. It fetches ACS 1-year state-level
demographics (population, income, poverty, education, citizenship) for 2010–2024.

Key differences from the Socrata (co-data) connector:

| | Socrata / co-data | Census ACS |
|---|---|---|
| API key | Not required | Required — `CENSUS_API_KEY` env var |
| Discovery | `/api/catalog/v1` → browse all datasets | Variables defined in code; no catalog API |
| Geography | Dataset-specific | `for=state:*`, `for=county:*`, etc. |
| Vintage | Not applicable | Year parameter (ACS 1-year vs 5-year) |
| Data model | Flat tabular rows | Variables × geographies × years |

Because ACS has no catalog to browse, the new project's `collect.py` won't need a `--catalog`
command. Instead it will likely have `--fetch --year <year>` or `--fetch --years 2015-2024` style
commands to pull specific vintages into DuckDB.

`store.py`, the Streamlit app (with AgGrid), the Marimo notebook, and the GCP deploy pattern all
copy over verbatim.
