"""
Local data access layer — shared by all co-data frontends.

Populate with: uv run collect.py [--search QUERY] [--fetch DATASET_ID]

Works for any Socrata domain; the domain is stored alongside each dataset
so frontends can display it, but storage is domain-agnostic.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
CATALOG_PATH = DATA_DIR / "catalog.parquet"
CATALOG_MD_PATH = DATA_DIR / "catalog.md"
DB_PATH = DATA_DIR / "co_data.duckdb"
SQLITE_PATH = DATA_DIR / "co_data.sqlite"


# ── helpers ───────────────────────────────────────────────────────────────────

def _tbl(dataset_id: str) -> str:
    return "ds_" + dataset_id.replace("-", "_")


def _open(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def _ensure_index(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS _index (
            dataset_id  TEXT PRIMARY KEY,
            name        TEXT,
            domain      TEXT,
            table_name  TEXT,
            row_count   BIGINT,
            total_rows  BIGINT,
            col_count   INTEGER,
            fetched_at  TIMESTAMP DEFAULT now()
        )
    """)
    existing = con.execute("PRAGMA table_info(_index)").fetchdf()["name"].tolist()
    if "total_rows" not in existing:
        con.execute("ALTER TABLE _index ADD COLUMN total_rows BIGINT")


# ── catalog ───────────────────────────────────────────────────────────────────

def _catalog_in_db() -> bool:
    if not DB_PATH.exists():
        return False
    try:
        con = _open()
        tables = con.execute("SHOW TABLES").fetchdf()["name"].tolist()
        con.close()
        return "catalog" in tables
    except Exception:
        return False


def catalog_available() -> bool:
    return _catalog_in_db() or CATALOG_PATH.exists()


def _read_catalog_raw() -> pd.DataFrame:
    """Read catalog from DuckDB catalog table if available, else parquet."""
    if _catalog_in_db():
        try:
            con = _open()
            df = con.execute("SELECT * FROM catalog").df()
            con.close()
            return df
        except Exception:
            pass
    if CATALOG_PATH.exists():
        return pd.read_parquet(CATALOG_PATH)
    return pd.DataFrame()


def get_catalog() -> pd.DataFrame:
    """Return cached catalog with a `cached` boolean column added."""
    df = _read_catalog_raw()
    if df.empty:
        return df
    cached = set(list_cached_ids())
    df["cached"] = df["dataset_id"].isin(cached)
    return df


def save_catalog(df: pd.DataFrame) -> None:
    """Persist the full catalog DataFrame to the DuckDB 'catalog' table."""
    DATA_DIR.mkdir(exist_ok=True)
    con = _open(read_only=False)
    con.execute("DROP TABLE IF EXISTS catalog")
    con.execute("CREATE TABLE catalog AS SELECT * FROM df")
    con.close()


# ── datasets ──────────────────────────────────────────────────────────────────

def list_cached_ids() -> list[str]:
    if not DB_PATH.exists():
        return []
    try:
        con = _open()
        ids = con.execute(
            "SELECT dataset_id FROM _index ORDER BY fetched_at DESC"
        ).fetchdf()["dataset_id"].tolist()
        con.close()
        return ids
    except Exception:
        return []


def get_index() -> pd.DataFrame:
    """Return metadata about all cached datasets."""
    if not DB_PATH.exists():
        return pd.DataFrame()
    try:
        con = _open()
        df = con.execute("SELECT * FROM _index ORDER BY fetched_at DESC").df()
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


def dataset_cached(dataset_id: str) -> bool:
    return dataset_id in list_cached_ids()


def get_dataset(dataset_id: str, limit: int | None = 1000) -> pd.DataFrame:
    """Read a cached dataset from DuckDB. Returns empty DataFrame if not found."""
    if not DB_PATH.exists():
        return pd.DataFrame()
    tbl = _tbl(dataset_id)
    try:
        con = _open()
        tables = con.execute("SHOW TABLES").fetchdf()["name"].tolist()
        if tbl not in tables:
            con.close()
            return pd.DataFrame()
        q = f'SELECT * FROM "{tbl}"' + (f" LIMIT {limit}" if limit else "")
        df = con.execute(q).df()
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


def save_dataset(
    dataset_id: str,
    name: str,
    domain: str,
    df: pd.DataFrame,
    total_rows: int | None = None,
) -> None:
    """Persist a dataset to DuckDB and update the index."""
    DATA_DIR.mkdir(exist_ok=True)
    tbl = _tbl(dataset_id)
    con = _open(read_only=False)
    _ensure_index(con)
    con.execute(f'DROP TABLE IF EXISTS "{tbl}"')
    con.execute(f'CREATE TABLE "{tbl}" AS SELECT * FROM df')
    count = con.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
    con.execute("""
        INSERT INTO _index (dataset_id, name, domain, table_name, row_count, total_rows, col_count, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, now())
        ON CONFLICT (dataset_id) DO UPDATE SET
            name       = excluded.name,
            domain     = excluded.domain,
            table_name = excluded.table_name,
            row_count  = excluded.row_count,
            total_rows = excluded.total_rows,
            col_count  = excluded.col_count,
            fetched_at = excluded.fetched_at
    """, [dataset_id, name, domain, tbl, count, total_rows, len(df.columns)])
    con.close()


# ── sqlite export (for datasette) ─────────────────────────────────────────────

def export_sqlite(verbose: bool = True) -> Path:
    """Export DuckDB contents to SQLite for use with Datasette."""
    import sqlite3

    if not DB_PATH.exists():
        raise FileNotFoundError(f"No DuckDB at {DB_PATH}. Run collect.py first.")

    SQLITE_PATH.unlink(missing_ok=True)
    sqlite_con = sqlite3.connect(str(SQLITE_PATH))

    duck_con = _open()
    tables = duck_con.execute("SHOW TABLES").fetchdf()["name"].tolist()

    for tbl in tables:
        df = duck_con.execute(f'SELECT * FROM "{tbl}"').df()
        df.to_sql(tbl, sqlite_con, if_exists="replace", index=False)
        if verbose:
            print(f"  exported {tbl} ({len(df):,} rows)")

    duck_con.close()
    sqlite_con.close()
    return SQLITE_PATH
