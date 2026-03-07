import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    return psycopg2.connect(database_url)

def get_field_scraped_at(field_id):
    """
    Fetch the scraped_at timestamp for a given field_id.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT scraped_at FROM scheme_fields WHERE id = %s",
                (field_id,)
            )
            result = cur.fetchone()
            return result[0] if result else None
    finally:
        conn.close()
