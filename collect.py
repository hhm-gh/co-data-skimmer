"""
Collect data from any Socrata open-data portal into local cache.

Outputs:
  data/catalog.parquet   — catalog search results
  data/co_data.duckdb    — full datasets as tables (ds_<id>)
  data/co_data.sqlite    — SQLite mirror for Datasette (via --export)

Usage:
  uv run collect.py                                     # search default query
  uv run collect.py --search "traffic crashes"          # search catalog
  uv run collect.py --fetch 4ykn-tg5h                  # fetch + cache one dataset
  uv run collect.py --fetch 4ykn-tg5h --fetch j6g4-gayk  # fetch multiple
  uv run collect.py --domain data.cdc.gov --search "covid"  # any Socrata domain
  uv run collect.py --export                            # export DuckDB → SQLite
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from datasources.coloradogov import search_catalog, fetch_dataset
from datasources._http import make_session
import store

DATA_DIR = Path("data")
DEFAULT_DOMAIN = "data.colorado.gov"
DEFAULT_SEARCH = "colorado"


def cmd_search(query: str, domain: str, limit: int) -> None:
    session = make_session()
    print(f"Searching '{domain}' for '{query}' (limit {limit})...")
    df = search_catalog(query, session, limit=limit, domain=domain)
    if df.empty:
        print("No results.")
        return

    DATA_DIR.mkdir(exist_ok=True)
    # Tag with domain so the catalog can cover multiple portals
    df["domain"] = domain
    df.to_parquet(store.CATALOG_PATH, index=False)
    print(f"Saved {len(df)} entries → {store.CATALOG_PATH}\n")

    print(f"{'ID':<14} {'Rows':>8}  {'Category':<22} Name")
    print("─" * 80)
    for _, row in df.iterrows():
        rows_str = f"{int(row['rows']):,}" if pd.notna(row["rows"]) else "?"
        print(f"{row['dataset_id']:<14} {rows_str:>8}  {str(row['category']):<22} {row['name']}")


def cmd_fetch(dataset_ids: list[str], domain: str, rows: int | None) -> None:
    session = make_session()
    for dataset_id in dataset_ids:
        limit_note = f" (first {rows:,} rows)" if rows else " (all rows)"
        print(f"\nFetching {dataset_id} from {domain}{limit_note}...")
        if rows:
            # Use the SODA API directly with a row limit instead of full pagination
            import requests as _req
            url = f"https://{domain}/resource/{dataset_id}.json"
            resp = session.get(url, params={"$limit": rows}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            import pandas as _pd
            df = _pd.DataFrame(data) if data else _pd.DataFrame()
        else:
            df = fetch_dataset(dataset_id, session, domain=domain)
        if df.empty:
            print(f"  No data returned — skipping.")
            continue

        # Resolve a display name from the cached catalog if available
        name = dataset_id
        if store.catalog_available():
            catalog = pd.read_parquet(store.CATALOG_PATH)
            match = catalog[catalog["dataset_id"] == dataset_id]
            if not match.empty:
                name = match.iloc[0]["name"]

        store.save_dataset(dataset_id, name=name, domain=domain, df=df)
        print(f"  Saved {len(df):,} rows × {len(df.columns)} cols ('{name}')")


def cmd_export() -> None:
    print("Exporting DuckDB → SQLite for Datasette...")
    path = store.export_sqlite(verbose=True)
    print(f"\nDone → {path}")
    print("Run: datasette serve data/co_data.sqlite")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect Socrata open-data into local cache",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--search", metavar="QUERY", help="Search catalog and save results")
    parser.add_argument("--fetch", metavar="ID", action="append", dest="fetch_ids",
                        help="Fetch and cache a dataset by ID (repeatable)")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN,
                        help=f"Socrata domain (default: {DEFAULT_DOMAIN})")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max catalog results (default: 100)")
    parser.add_argument("--rows", type=int, default=50_000,
                        help="Max rows per dataset fetch (default: 50000; 0 = all rows)")
    parser.add_argument("--export", action="store_true",
                        help="Export DuckDB → SQLite for Datasette")
    args = parser.parse_args()

    ran_something = False

    if args.search:
        cmd_search(args.search, args.domain, args.limit)
        ran_something = True

    if args.fetch_ids:
        row_limit = args.rows if args.rows > 0 else None
        cmd_fetch(args.fetch_ids, args.domain, row_limit)
        ran_something = True

    if args.export:
        cmd_export()
        ran_something = True

    if not ran_something:
        # Default: search with the default query
        cmd_search(DEFAULT_SEARCH, args.domain, args.limit)


if __name__ == "__main__":
    main()
