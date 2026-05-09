"""
db.py — PostgreSQL connection + schema initialization
Uses DATABASE_URL from environment (never hardcoded).

Uses pgvector for vector storage in chunks table.
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
    
    if '?' not in database_url:
        database_url += '?sslmode=require'
    elif 'sslmode' not in database_url:
        database_url += '&sslmode=require'
        
    return psycopg2.connect(database_url)


def init_db():
    """
    Initialize the database schema on first run.
    Creates extension, tables, and indexes if they don't exist.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Enable pgvector
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

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

            # Chunks table for embeddings
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    field_id    UUID REFERENCES scheme_fields(id),
                    chunk_text  TEXT NOT NULL,
                    embedding   vector(3072),
                    source_url  TEXT NOT NULL,
                    scheme_name TEXT NOT NULL,
                    embedded_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)

            # HNSW index for vector search (Commented out: 2000 dim limit exceeded by 3072 dim Gemini embeddings)
            # cur.execute("CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);")

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
    Returns the newly created row's UUID, or None if skipped.
    """
    if not field_value:  # FIX 1: skip None or empty values silently
        return None
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
                  source_url = CASE
                    WHEN scheme_fields.source_url LIKE '%%/kim-%%' THEN scheme_fields.source_url
                    WHEN scheme_fields.source_url LIKE '%%/sid-%%' THEN scheme_fields.source_url
                    WHEN scheme_fields.source_url LIKE '%%factsheet%%' THEN scheme_fields.source_url
                    ELSE EXCLUDED.source_url
                  END,
                  is_pdf = CASE
                    WHEN scheme_fields.is_pdf = TRUE THEN TRUE
                    ELSE EXCLUDED.is_pdf
                  END,
                  scraped_at = NOW(),
                  status = 'active'
                RETURNING id;
                """,
                (scheme_name, field_name, field_value, source_url, is_pdf),
            )
            row = cur.fetchone()  # FIX: may be None if WHERE blocked the upsert
            conn.commit()
            return row[0] if row else None
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


def insert_chunk(field_id, chunk_text, embedding, source_url, scheme_name):
    """
    Insert an embedding chunk into the chunks table.
    Uses pgvector (embedding::vector) for storage.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chunks 
                (field_id, chunk_text, embedding, source_url, scheme_name)
                VALUES (%s, %s, %s::vector, %s, %s)
                ON CONFLICT (field_id) 
                DO UPDATE SET
                  chunk_text = EXCLUDED.chunk_text,
                  embedding = EXCLUDED.embedding,
                  source_url = EXCLUDED.source_url,
                  scheme_name = EXCLUDED.scheme_name,
                  embedded_at = NOW();
                """,
                (field_id, chunk_text, embedding, source_url, scheme_name),
            )
            conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
