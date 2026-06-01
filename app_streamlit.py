"""
Colorado Information Marketplace — Streamlit app.

Reads from local cache (data/). Populate with:
  uv run collect.py --search "colorado"
  uv run collect.py --fetch <dataset_id>

Run locally:
  uv run streamlit run app_streamlit.py

Deploy to GCP Cloud Run:
  docker build -t co-data . && docker run -p 8080:8080 co-data
"""

import streamlit as st
import pandas as pd
import requests
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, ColumnsAutoSizeMode
import store

st.set_page_config(
    page_title="Colorado Information Marketplace",
    page_icon="🏔",
    layout="wide",
)

st.title("Colorado Information Marketplace")
st.caption(
    "Browse datasets from [data.colorado.gov](https://data.colorado.gov). "
    "Data loaded from local cache — run `collect.py` to refresh."
)

# ── catalog ───────────────────────────────────────────────────────────────────

if not store.catalog_available():
    st.error(
        "No catalog found. Run:\n"
        "```\nuv run collect.py --search 'colorado'\n```"
    )
    st.stop()

catalog = store.get_catalog()

with st.sidebar:
    st.header("Filter catalog")
    st.caption("_The AgGrid table below has per-column filters — sidebar filters are redundant and may be removed in a future refactor._")
    query = st.text_input("Search by name / description", placeholder="e.g. traffic, health")
    categories = ["All"] + sorted(catalog["category"].dropna().unique().tolist())
    category = st.selectbox("Category", categories)
    cached_only = st.checkbox("Cached datasets only")

    st.divider()
    st.caption(f"{len(catalog)} datasets in catalog")
    cached_count = catalog["cached"].sum() if "cached" in catalog.columns else 0
    st.caption(f"{cached_count} datasets cached locally")

# Apply filters
filtered = catalog.copy()
if query:
    _mask = (
        filtered["name"].str.contains(query, case=False, na=False)
        | filtered["description"].str.contains(query, case=False, na=False)
    )
    filtered = filtered[_mask]
if category != "All":
    filtered = filtered[filtered["category"] == category]
if cached_only and "cached" in filtered.columns:
    filtered = filtered[filtered["cached"]]

# ── catalog table ─────────────────────────────────────────────────────────────

st.subheader(f"Catalog — {len(filtered)} datasets")

_display_cols = ["name", "category", "rows", "dataset_id", "description"]
if "cached" in filtered.columns:
    _display_cols = ["cached"] + _display_cols

_display = filtered[_display_cols].copy()
if "cached" in _display.columns:
    _display["cached"] = _display["cached"].map({True: "✓", False: ""})

# Populate rows from _index total_rows (only known for fetched datasets)
_idx = store.get_index()
if not _idx.empty and "total_rows" in _idx.columns:
    _total_map = _idx.set_index("dataset_id")["total_rows"]
else:
    _total_map = pd.Series(dtype="Int64")
_display["rows"] = _display["dataset_id"].map(_total_map).apply(
    lambda v: f"{int(v):,}" if pd.notna(v) else ""
)

_gb = GridOptionsBuilder.from_dataframe(_display)
_gb.configure_default_column(filter=True, sortable=True, resizable=True)
_gb.configure_column("name", minWidth=200)
_gb.configure_column("description", minWidth=300)
_gb.configure_column("cached", maxWidth=80)
_gb.configure_column("rows", maxWidth=100)
_gb.configure_column("dataset_id", maxWidth=130)
_gb.configure_selection("single", use_checkbox=False)
_gb.configure_grid_options(domLayout="normal")

_grid = AgGrid(
    _display,
    gridOptions=_gb.build(),
    update_mode=GridUpdateMode.SELECTION_CHANGED,
    columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
    height=400,
    allow_unsafe_jscode=False,
)

# ── dataset preview ───────────────────────────────────────────────────────────

st.subheader("Preview a dataset")

_sel_rows = _grid.get("selected_rows")
if _sel_rows is not None and len(_sel_rows) > 0:
    selected_id = _sel_rows.iloc[0]["dataset_id"]
    selected_name = _sel_rows.iloc[0]["name"]

    try:
        domain = filtered.loc[filtered["dataset_id"] == selected_id, "domain"].iloc[0]
    except (KeyError, IndexError):
        domain = "data.colorado.gov"

    if store.dataset_cached(selected_id):
        df = store.get_dataset(selected_id, limit=1000)
        source = "local cache"
        # Read stored total from _index if available
        _idx = store.get_index()
        _match = _idx[_idx["dataset_id"] == selected_id]
        total_rows = int(_match.iloc[0]["total_rows"]) if not _match.empty and pd.notna(_match.iloc[0].get("total_rows")) else None
    else:
        with st.spinner(f"Fetching {selected_name} from API..."):
            try:
                # Fetch sample rows and total count in parallel-ish (sequential is fine)
                resp = requests.get(
                    f"https://{domain}/resource/{selected_id}.json",
                    params={"$limit": 1000},
                    timeout=30,
                )
                resp.raise_for_status()
                df = pd.DataFrame(resp.json())

                count_resp = requests.get(
                    f"https://{domain}/resource/{selected_id}.json",
                    params={"$select": "count(*)", "$limit": 1},
                    timeout=15,
                )
                try:
                    count_data = count_resp.json()
                    total_rows = int(next(iter(count_data[0].values()))) if count_resp.ok and count_data else None
                except Exception:
                    total_rows = None

                if not df.empty:
                    store.save_dataset(selected_id, selected_name, domain, df, total_rows=total_rows)
                    st.rerun()
                source = "live API (now cached)"
            except Exception as e:
                st.error(f"Failed to fetch `{selected_id}`: {e}")
                df = pd.DataFrame()
                source = ""
                total_rows = None

    if not df.empty:
        _total_note = f" of {total_rows:,} total" if total_rows else ""
        st.caption(
            f"`{selected_id}` &nbsp;·&nbsp; "
            f"showing {len(df):,} rows{_total_note} × {len(df.columns)} columns _(source: {source})_"
        )
        st.dataframe(df, width="stretch", hide_index=True)
else:
    st.caption("_Click a row in the catalog table above to preview its data._")
