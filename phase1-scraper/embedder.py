"""
embedder.py — Generate Gemini embeddings for all active scheme_fields rows.
Reads GEMINI_API_KEY from environment (never hardcoded).
Processes in batches of 20. Waits 1 second between batches.
On 429 rate limit: waits 30 seconds, retries once.
On retry failure: logs error, skips row, continues.

NOTE: Embeddings are now stored in Neon pgvector (PostgreSQL).
ChromaDB dependency has been removed.
"""

import os
import sys
import time
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types
from db import get_active_fields, insert_chunk

# ---------------------------------------------------------------------------
# ChromaDB setup removed.
# Using Neon pgvector via db.insert_chunk().
# ---------------------------------------------------------------------------

# Dimension for gemini-embedding-001 is 3072
EMBEDDING_DIM = 3072

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable is not set.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

EMBEDDING_MODEL = "models/text-embedding-004"
BATCH_SIZE = 20
BATCH_DELAY_SECONDS = 1       # wait between batches
RATE_LIMIT_WAIT_SECONDS = 30  # wait on 429 before retry


def test_gemini_connection():
    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents="test"
        )
        print(f"Gemini test OK: vector length = {len(result.embeddings[0].values)}")
        return True
    except Exception as e:
        print(f"Gemini test FAILED: {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def embed_text(text: str) -> Optional[List[float]]:
    """
    Call Gemini gemini-embedding-001 to get a 3072-dim vector.
    On 429 rate limit: wait 30 seconds and retry once.
    On any failure: return None (caller will skip this row).
    """
    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
        )
        return result.embeddings[0].values
    except Exception as e:
        error_str = str(e).lower()
        if "429" in error_str or "rate" in error_str or "quota" in error_str:
            print(f"  429 Rate limit hit. Waiting {RATE_LIMIT_WAIT_SECONDS}s before retry...")
            time.sleep(RATE_LIMIT_WAIT_SECONDS)
            # Retry once
            try:
                result = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=text,
                )
                return result.embeddings[0].values
            except Exception as retry_e:
                print(f"  ERROR on retry: {retry_e}. Skipping this row.")
                return None
        else:
            print(f"  ERROR embedding text: {e}. Skipping this row.")
            return None


def format_chunk_text(scheme_name: str, field_name: str, field_value: str) -> str:
    """
    Build the chunk_text string in the exact format required by ARCHITECTURE.md.
    Example: "SBI Bluechip Fund expense_ratio_direct: 0.85%"
    """
    return f"{scheme_name} {field_name}: {field_value}"


# ---------------------------------------------------------------------------
# Main embedding loop
# ---------------------------------------------------------------------------

def main():
    if not test_gemini_connection():
        print("Aborting: Gemini connection test failed.")
        sys.exit(1)

    print("Fetching active fields from scheme_fields table...")
    rows = get_active_fields()

    if not rows:
        print("No active rows found in scheme_fields. Run scraper.py first.")
        sys.exit(0)

    total_rows = len(rows)
    total_batches = (total_rows + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Found {total_rows} rows to embed. Processing in {total_batches} batches of {BATCH_SIZE}.")

    skipped = 0
    embedded = 0

    for batch_num in range(total_batches):
        batch_start = batch_num * BATCH_SIZE
        batch_end = batch_start + BATCH_SIZE
        batch = rows[batch_start:batch_end]

        print(f"Embedding batch {batch_num + 1}/{total_batches}...")

        for row in batch:
            # row = (id, scheme_name, field_name, field_value, source_url)
            field_id, scheme_name, field_name, field_value, source_url = row

            chunk_text = format_chunk_text(scheme_name, field_name, field_value)

            try:
                embedding = embed_text(chunk_text)
                if embedding is None:
                    # This case is handled inside embed_text but we add context here
                    print(f"  Skipping row {field_id} due to None result from embed_text.")
                    skipped += 1
                    continue
            except Exception as e:
                print(f"Gemini API error on row {field_id}: {type(e).__name__}: {e}")
                skipped += 1
                continue

            # Validate embedding dimension
            if len(embedding) != EMBEDDING_DIM:
                print(
                    f"  WARNING: Expected {EMBEDDING_DIM}-dim embedding, got {len(embedding)} for row {field_id}. Skipping."
                )
                skipped += 1
                continue

            try:
                # Neon pgvector insert (plain insert)
                insert_chunk(
                    field_id=field_id,
                    chunk_text=chunk_text,
                    embedding=embedding,
                    source_url=source_url,
                    scheme_name=scheme_name
                )
                embedded += 1
            except Exception as e:
                print(f"  ERROR inserting chunk into Neon for row {field_id}: {e}. Skipping.")
                skipped += 1

        # Wait between batches (except after the last batch)
        if batch_num < total_batches - 1:
            print(f"  Batch {batch_num + 1} done. Waiting {BATCH_DELAY_SECONDS}s before next batch...")
            time.sleep(BATCH_DELAY_SECONDS)

    print(f"\n{'='*60}")
    print(f"Embedding complete. Embedded: {embedded}, Skipped: {skipped}")
    print(f"{'='*60}")

    if embedded == 0:
        print("ERROR: No embeddings were saved. Check GEMINI_API_KEY and DB connection.")
        sys.exit(1)


if __name__ == "__main__":
    main()
