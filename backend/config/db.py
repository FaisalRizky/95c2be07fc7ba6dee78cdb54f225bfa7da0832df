import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Protocol

from config.app import config

# ---------------------------------------------------------------------------
# Protocol — the contract every engine must satisfy.
# All SQL written in the service layer uses "?" as the canonical placeholder.
# Each engine translates it internally via _normalize_sql(), so switching
# drivers (SQLite → PostgreSQL) requires ZERO changes to any query string.
# ---------------------------------------------------------------------------

class DatabaseEngine(Protocol):
    def fetch_all(self, query: str, params: list = None) -> list[dict]: ...
    def fetch_one(self, query: str, params: list = None) -> dict | None: ...
    def fetch_many_generator(
        self, query: str, params: list = None, chunk_size: int = 100
    ) -> Generator[dict, None, None]: ...
    def check_health(self) -> bool: ...


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------

class SQLiteEngine:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _normalize_sql(self, sql: str) -> str:
        # SQLite uses "?" natively — no translation needed.
        return sql

    def _get_connection(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise RuntimeError(f"Database not found at: {self.db_path}")
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def fetch_all(self, query: str, params: list = None) -> list[dict]:
        conn = self._get_connection()
        try:
            rows = conn.execute(self._normalize_sql(query), params or []).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            raise RuntimeError(f"Database error: {exc}") from exc
        finally:
            conn.close()

    def fetch_one(self, query: str, params: list = None) -> dict | None:
        conn = self._get_connection()
        try:
            row = conn.execute(self._normalize_sql(query), params or []).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as exc:
            raise RuntimeError(f"Database error: {exc}") from exc
        finally:
            conn.close()

    def fetch_many_generator(
        self, query: str, params: list = None, chunk_size: int = 100
    ) -> Generator[dict, None, None]:
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(self._normalize_sql(query), params or [])
            while True:
                rows = cursor.fetchmany(chunk_size)
                if not rows:
                    break
                for row in rows:
                    yield dict(row)
        except sqlite3.Error as exc:
            # Once streaming has started we cannot raise an HTTP error, so log it.
            print(f"Database stream error: {exc}")
        finally:
            if conn:
                conn.close()

    def check_health(self) -> bool:
        try:
            self.fetch_one("SELECT 1 FROM projects LIMIT 1")
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# PostgreSQL stub (psycopg2 / psycopg3)
#
# To activate: set DB_ENGINE=postgres and POSTGRES_DSN in environment.
# The only change from SQLiteEngine is _normalize_sql — every other method
# is structurally identical; only the driver import and connection call differ.
#
# Placeholder translation:
#   SQLite / canonical  →  "?"
#   psycopg2 / psycopg3 →  "%s"   (replace ? with %s)
#   asyncpg             →  "$1, $2, ..."  (replace each ? with $N)
# ---------------------------------------------------------------------------

# class PostgresEngine:
#     def __init__(self, dsn: str):
#         import psycopg2
#         import psycopg2.extras
#         self._dsn = dsn
#         self._psycopg2 = psycopg2
#         self._extras = psycopg2.extras
#
#     def _normalize_sql(self, sql: str) -> str:
#         # Convert canonical "?" placeholders to psycopg2's "%s" style.
#         return sql.replace("?", "%s")
#
#     def _get_connection(self):
#         conn = self._psycopg2.connect(self._dsn)
#         conn.autocommit = True
#         return conn
#
#     def fetch_all(self, query: str, params: list = None) -> list[dict]:
#         with self._get_connection() as conn:
#             with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
#                 cur.execute(self._normalize_sql(query), params or [])
#                 return [dict(r) for r in cur.fetchall()]
#
#     def fetch_one(self, query: str, params: list = None) -> dict | None:
#         with self._get_connection() as conn:
#             with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
#                 cur.execute(self._normalize_sql(query), params or [])
#                 row = cur.fetchone()
#                 return dict(row) if row else None
#
#     def fetch_many_generator(
#         self, query: str, params: list = None, chunk_size: int = 100
#     ) -> Generator[dict, None, None]:
#         with self._get_connection() as conn:
#             with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
#                 cur.execute(self._normalize_sql(query), params or [])
#                 while True:
#                     rows = cur.fetchmany(chunk_size)
#                     if not rows:
#                         break
#                     for row in rows:
#                         yield dict(row)
#
#     def check_health(self) -> bool:
#         try:
#             self.fetch_one("SELECT 1")
#             return True
#         except Exception:
#             return False


def _initialize_db() -> DatabaseEngine:
    engine_type = config.DB_ENGINE
    if engine_type == "sqlite":
        print("[startup] Using SQLiteEngine")
        # SQLITE_DB_PATH env var overrides the default; useful in Docker where the
        # file is mounted at a custom location (e.g. /glenigan.sql).
        db_path = (
            Path(config.SQLITE_DB_PATH)
            if config.SQLITE_DB_PATH
            else Path(__file__).parent.parent.parent / "glenigan.sql"
        )
        return SQLiteEngine(db_path)
    # Uncomment and set DB_ENGINE=postgres to switch:
    # if engine_type == "postgres":
    #     print("[startup] Using PostgresEngine")
    #     return PostgresEngine(config.POSTGRES_DSN)
    raise NotImplementedError(f"Database engine '{engine_type}' is not implemented. See config/db.py.")


# Singleton — injected into every request via FastAPI Depends(get_db).
_active_engine = _initialize_db()


def get_db() -> DatabaseEngine:
    return _active_engine
