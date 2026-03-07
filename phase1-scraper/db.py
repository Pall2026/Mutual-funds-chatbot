"""
db.py — PostgreSQL connection + schema initialization
Uses DATABASE_URL from environment (never hardcoded).

NOTE (local testing): pgvector/chunks table removed.
Embedding storage is handled by ChromaDB (embedder.py).
Switch back to pgvector for Railway deployment.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Return a new psycopg2 connection using DATABASE_URL from env."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set.")
    return psycopg2.connect(database_url)


def init_db():
    """
    Initialize the database schema on first run.
    Creates extension, tables, and indexes if they don't exist.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # NOTE: pgvector extension omitted — not available locally.
            # Restore for Railway: cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Main table: one row per scraped field per scheme
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheme_fields (
                    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    scheme_name TEXT NOT NULL,
                    field_name  TEXT NOT NULL,
                    field_value TEXT NOT NULL,
                    source_url  TEXT NOT NULL,
                    is_pdf      BOOLEAN DEFAULT false,
                    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    status      TEXT DEFAULT 'active'
                );
            """)

            # NOTE: chunks table omitted — embeddings stored in ChromaDB locally.
            # Restore for Railway: CREATE TABLE chunks (...) with vector(768) column.

            cur.execute("""
                CREATE INDEX IF NOT EXISTS scheme_fields_scheme_idx
                    ON scheme_fields(scheme_name);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS scheme_fields_field_idx
                    ON scheme_fields(field_name);
            """)

            # Unique constraint for deduplication
            try:
                cur.execute("ALTER TABLE scheme_fields ADD CONSTRAINT unique_scheme_field UNIQUE (scheme_name, field_name);")
            except psycopg2.errors.DuplicateTable:
                pass # Constraint already exists
            except Exception:
                conn.rollback() # Specific error handling often needed for constraints in code
                # Re-check existence or ignore if it fails due to existing constraint
                pass

            conn.commit()
            print("Database schema initialized successfully.")
    finally:
        conn.close()


def insert_field(scheme_name, field_name, field_value, source_url, is_pdf=False):
    """
    Insert a single extracted field row into scheme_fields.
    Returns the newly created row's UUID.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scheme_fields 
                (scheme_name, field_name, field_value, source_url, is_pdf, scraped_at, status)
                VALUES (%s, %s, %s, %s, %s, NOW(), 'active')
                ON CONFLICT (scheme_name, field_name) 
                DO UPDATE SET 
                  field_value = EXCLUDED.field_value,
                  source_url = EXCLUDED.source_url,
                  scraped_at = NOW(),
                  status = 'active'
                RETURNING id;
                """,
                (scheme_name, field_name, field_value, source_url, is_pdf),
            )
            row_id = cur.fetchone()[0]
            conn.commit()
            return row_id
    finally:
        conn.close()


def get_active_fields():
    """
    Return all rows from scheme_fields where status = 'active'.
    Used by embedder.py to generate embeddings.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, scheme_name, field_name, field_value, source_url
                FROM scheme_fields
                WHERE status = 'active'
                ORDER BY scraped_at;
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


# insert_chunk() removed — embeddings are stored in ChromaDB for local testing.
# Restore this function when deploying to Railway with pgvector.


if __name__ == "__main__":
    init_db()
