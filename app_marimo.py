import marimo

__generated_with = "0.23.8"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import store
    from datasources.coloradogov import search_catalog
    from datasources._http import make_session

    session = make_session()
    return mo, pd, search_catalog, session, store


@app.cell
def _(mo):
    mo.md("""
    # Colorado Information Marketplace
    Browse datasets from **[data.colorado.gov](https://data.colorado.gov)**.
    Catalog searches hit the live API; datasets load from local cache when available,
    otherwise fetched from the API and cached for future runs.

    > Pre-populate cache: `uv run collect.py --search "your query"`
    > Pre-fetch a dataset: `uv run collect.py --fetch <dataset_id>`
    """)
    return


@app.cell
def _(mo):
    search = mo.ui.text(
        placeholder="e.g. traffic, health, education, budget, water...",
        value="colorado",
        label="Search datasets",
    )
    return (search,)


@app.cell
def _(search):
    search
    return


@app.cell
def _(mo, pd, search, search_catalog, session, store):
    _q = search.value.strip() or "colorado"

    # Use local catalog for the default query if available, else hit the API
    _local = store.get_catalog()
    if not _local.empty and _q.lower() in ("colorado", ""):
        _raw = _local
    else:
        try:
            _raw = search_catalog(_q, session, limit=50)
            if not _raw.empty:
                _cached = set(store.list_cached_ids())
                _raw["cached"] = _raw["dataset_id"].isin(_cached)
        except Exception as _e:
            _raw = pd.DataFrame()

    catalog = _raw
    return (catalog,)


@app.cell
def _(catalog, mo):
    if catalog.empty:
        catalog_table = mo.md("_No datasets found. Try a different search term._")
    else:
        import pandas as _pd
        _cols = ["name", "category", "rows", "updated", "dataset_id", "description"]
        _display = catalog[[c for c in _cols if c in catalog.columns]].copy()
        if "rows" in _display.columns:
            _display["rows"] = _display["rows"].apply(
                lambda v: f"{int(v):,}" if _pd.notna(v) else "?"
            )
        if "cached" in catalog.columns:
            _display.insert(0, "cached", catalog["cached"].map({True: "✓", False: ""}))
        catalog_table = mo.ui.table(_display, selection="single")
    return (catalog_table,)


@app.cell
def _(catalog_table):
    catalog_table
    return


@app.cell
def _(catalog_table, mo):
    _sel = getattr(catalog_table, "value", None)
    mo.stop(
        _sel is None or len(_sel) == 0,
        mo.md("_Check a row above to load its data. ✓ = already cached locally._"),
    )
    selected_id = _sel.iloc[0]["dataset_id"]
    selected_name = _sel.iloc[0].get("name", selected_id)
    return selected_id, selected_name


@app.cell
def _(mo, pd, selected_id, selected_name, session, store):
    if store.dataset_cached(selected_id):
        dataset = store.get_dataset(selected_id, limit=1000)
        source = "local cache"
        load_error = None
    else:
        try:
            _url = f"https://data.colorado.gov/resource/{selected_id}.json"
            _resp = session.get(_url, params={"$limit": 1000}, timeout=30)
            _resp.raise_for_status()
            _rows = _resp.json()
            dataset = pd.DataFrame(_rows) if _rows else pd.DataFrame()
            source = "live API (now cached)"
            load_error = None
            if not dataset.empty:
                store.save_dataset(selected_id, selected_name, "data.colorado.gov", dataset)
        except Exception as _e:
            dataset = pd.DataFrame()
            source = ""
            load_error = str(_e)

    return dataset, load_error, source


@app.cell
def _(dataset, load_error, mo, selected_id, selected_name, source):
    if load_error:
        _out = mo.md(f"**Error loading `{selected_id}`:** {load_error}")
    elif dataset.empty:
        _out = mo.md(f"_No data returned for `{selected_id}`._")
    else:
        _out = mo.vstack([
            mo.md(
                f"### {selected_name}  \n"
                f"`{selected_id}` &nbsp;·&nbsp; "
                f"{len(dataset):,} rows &nbsp;×&nbsp; {len(dataset.columns)} columns"
                f"&nbsp; _(source: {source})_"
            ),
            mo.ui.table(dataset),
        ])
    _out
    return


if __name__ == "__main__":
    app.run()
