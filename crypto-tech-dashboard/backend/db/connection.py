"""Postgres connection management via DATABASE_URL environment variable.

Provides a simple get_conn() helper that returns a psycopg2 connection.
Connection is opened fresh per call — appropriate for Vercel serverless where
we cannot hold long-lived connections. Neon's PgBouncer pooler handles
connection reuse transparently on the server side.
"""

from __future__ import annotations

import os
import psycopg2
import psycopg2.extras


def get_conn():
    """Open and return a psycopg2 connection from DATABASE_URL."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it to a Neon/Postgres connection string."
        )
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def execute_schema(conn) -> None:
    """Create all tables if they don't exist. Safe to call repeatedly."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        ddl = f.read()
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
