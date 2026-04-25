from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from agent.core.config import settings

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PostgresConfig:
    dsn: str
    schema: str = "public"


_POOL: ConnectionPool | None = None


def postgres_enabled() -> bool:
    return bool(settings.conversation_db_enabled and settings.postgres_dsn)


def _get_config() -> PostgresConfig:
    return PostgresConfig(dsn=settings.postgres_dsn, schema=settings.conversation_db_schema)


def get_pool() -> ConnectionPool:
    global _POOL
    if _POOL is None:
        cfg = _get_config()
        _POOL = ConnectionPool(
            conninfo=cfg.dsn, min_size=1, max_size=8, kwargs={"row_factory": dict_row}
        )
    return _POOL


@contextlib.contextmanager
def get_conn() -> Iterator[Connection]:
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def ensure_schema(conn: Connection) -> None:
    cfg = _get_config()
    schema = (cfg.schema or "public").strip()
    if not schema:
        schema = "public"
    with conn.cursor() as cur:
        cur.execute(f'create schema if not exists "{schema}"')
        cur.execute(f'set search_path to "{schema}"')


def run_migrations(*, migrations_dir: str | Path | None = None) -> None:
    """Apply SQL migrations in lexicographic order with a simple schema_migrations table."""
    if not postgres_enabled():
        return

    migrations_path = (
        Path(migrations_dir) if migrations_dir else Path(__file__).parent / "migrations"
    )
    sql_files = sorted(p for p in migrations_path.glob("*.sql") if p.is_file())
    if not sql_files:
        return

    with get_conn() as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists schema_migrations (
                  filename text primary key,
                  applied_at timestamptz not null default now()
                )
                """
            )
            cur.execute("select filename from schema_migrations")
            applied = {row["filename"] for row in cur.fetchall()}

            for path in sql_files:
                if path.name in applied:
                    continue
                sql = path.read_text(encoding="utf-8")
                _log.info("postgres.migrate", extra={"pg_migration": path.name})
                cur.execute(sql)
                cur.execute("insert into schema_migrations (filename) values (%s)", (path.name,))
        conn.commit()
