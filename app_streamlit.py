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

_display_cols = ["name", "category", "dataset_id", "description"]
if "cached" in filtered.columns:
    _display_cols = ["cached"] + _display_cols

_display = filtered[_display_cols].copy()
if "cached" in _display.columns:
    _display["cached"] = _display["cached"].map({True: "✓", False: ""})

st.dataframe(_display, width="stretch", hide_index=True)

# ── dataset picker + preview ──────────────────────────────────────────────────

st.subheader("Preview a dataset")

_options = filtered[["name", "dataset_id"]].copy()
_options["label"] = _options["name"] + "  (" + _options["dataset_id"] + ")"

selected_label = st.selectbox(
    "Select dataset",
    options=_options["label"].tolist(),
    index=None,
    placeholder="Choose a dataset...",
)

if selected_label:
    selected_id = _options.loc[_options["label"] == selected_label, "dataset_id"].iloc[0]
    selected_name = _options.loc[_options["label"] == selected_label, "name"].iloc[0]

    if store.dataset_cached(selected_id):
        df = store.get_dataset(selected_id, limit=1000)
        st.caption(
            f"`{selected_id}` &nbsp;·&nbsp; "
            f"{len(df):,} rows × {len(df.columns)} columns _(local cache, first 1,000 rows)_"
        )
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info(
            f"**{selected_name}** is not cached locally.\n\n"
            f"Fetch it with:\n```\nuv run collect.py --fetch {selected_id}\n```"
        )
