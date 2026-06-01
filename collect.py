"""
Collect data from any Socrata open-data portal into local cache.

Outputs:
  data/catalog.parquet   — full catalog (all datasets for the domain)
  data/catalog.md        — full catalog as a markdown table
  data/co_data.duckdb    — catalog table + fetched datasets as ds_<id> tables
  data/co_data.sqlite    — SQLite mirror for Datasette (via --export)

Usage:
  uv run collect.py                                        # full catalog (default)
  uv run collect.py --catalog                             # full catalog (explicit)
  uv run collect.py --search "traffic crashes"            # ad-hoc catalog search
  uv run collect.py --fetch 4ykn-tg5h                    # fetch + cache one dataset
  uv run collect.py --fetch 4ykn-tg5h --fetch j6g4-gayk  # fetch multiple
  uv run collect.py --domain data.cdc.gov --catalog       # any Socrata domain
  uv run collect.py --export                              # export DuckDB → SQLite
"""

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from datasources.coloradogov import search_catalog, fetch_dataset
from datasources._http import make_session
import store

DATA_DIR = Path("data")
DEFAULT_DOMAIN = "data.colorado.gov"
DEFAULT_SEARCH = "colorado"
DISCOVERY_URL = "https://api.us.socrata.com/api/catalog/v1"


def _parse_entry(entry: dict, domain: str) -> dict:
    resource = entry.get("resource", {})
    classific = entry.get("classification", {})
    return {
        "dataset_id":  resource.get("id", ""),
        "name":        resource.get("name", ""),
        "description": (resource.get("description") or "")[:200],
        "type":        resource.get("type", ""),
        "updated":     resource.get("updatedAt", ""),
        "rows":        resource.get("row_count"),
        "category":    classific.get("domain_category", ""),
        "tags":        ", ".join(classific.get("domain_tags", [])[:5]),
        "soda_url":    f"https://{domain}/resource/{resource.get('id', '')}.json",
    }


def _write_catalog_md(df: pd.DataFrame, domain: str, ts: datetime) -> None:
    sorted_df = df.sort_values(["category", "name"], na_position="last")
    lines = [
        f"# {domain} — Full Dataset Catalog",
        "",
        f"Downloaded: {ts.strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"Domain: {domain}  ",
        f"Total datasets: {len(df):,}",
        "",
        "| Name | Category | Rows | Dataset ID | Description |",
        "|------|----------|------|------------|-------------|",
    ]
    for _, row in sorted_df.iterrows():
        name = str(row["name"]).replace("|", "\\|")
        category = str(row.get("category") or "").replace("|", "\\|")
        rows_str = f"{int(row['rows']):,}" if pd.notna(row.get("rows")) else ""
        dataset_id = str(row["dataset_id"])
        desc = str(row.get("description") or "")[:120].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {name} | {category} | {rows_str} | {dataset_id} | {desc} |")
    store.CATALOG_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_catalog(domain: str) -> None:
    session = make_session()
    print(f"Fetching complete catalog from '{domain}'...")

    BATCH = 100
    offset = 0
    records: list[dict] = []
    total: int | str = "?"

    while True:
        params = {
            "domains": domain,
            "search_context": domain,
            "limit": BATCH,
            "offset": offset,
        }
        resp = session.get(DISCOVERY_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if offset == 0:
            total = data.get("resultSetSize", "?")
            print(f"  Total datasets reported: {total}")

        results = data.get("results", [])
        if not results:
            break

        for entry in results:
            records.append(_parse_entry(entry, domain))

        print(f"  fetched {len(records):,} ...", end="\r")

        if len(results) < BATCH:
            break
        offset += BATCH
        time.sleep(0.1)

    ts = datetime.now(timezone.utc)
    print(f"\n  Done — {len(records):,} datasets")

    df = pd.DataFrame(records)
    df["domain"] = domain
    DATA_DIR.mkdir(exist_ok=True)

    df.to_parquet(store.CATALOG_PATH, index=False)
    print(f"  → {store.CATALOG_PATH}")

    store.save_catalog(df)
    print(f"  → {store.DB_PATH} (catalog table)")

    _write_catalog_md(df, domain, ts)
    print(f"  → {store.CATALOG_MD_PATH}")


def cmd_search(query: str, domain: str, limit: int) -> None:
    session = make_session()
    print(f"Searching '{domain}' for '{query}' (limit {limit})...")
    df = search_catalog(query, session, limit=limit, domain=domain)
    if df.empty:
        print("No results.")
        return

    print(f"\n{len(df)} results:\n")
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
            url = f"https://{domain}/resource/{dataset_id}.json"
            resp = session.get(url, params={"$limit": rows}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            df = pd.DataFrame(data) if data else pd.DataFrame()
        else:
            df = fetch_dataset(dataset_id, session, domain=domain)
        if df.empty:
            print(f"  No data returned — skipping.")
            continue

        name = dataset_id
        if store.catalog_available():
            catalog = store._read_catalog_raw()
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
    parser.add_argument("--catalog", action="store_true",
                        help="Download complete catalog (parquet + DuckDB + markdown)")
    parser.add_argument("--search", metavar="QUERY", help="Ad-hoc catalog search (display only)")
    parser.add_argument("--fetch", metavar="ID", action="append", dest="fetch_ids",
                        help="Fetch and cache a dataset by ID (repeatable)")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN,
                        help=f"Socrata domain (default: {DEFAULT_DOMAIN})")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max results for --search (default: 100)")
    parser.add_argument("--rows", type=int, default=50_000,
                        help="Max rows per dataset fetch (default: 50000; 0 = all rows)")
    parser.add_argument("--export", action="store_true",
                        help="Export DuckDB → SQLite for Datasette")
    args = parser.parse_args()

    ran_something = False

    if args.catalog:
        cmd_catalog(args.domain)
        ran_something = True

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
        cmd_catalog(args.domain)


if __name__ == "__main__":
    main()
