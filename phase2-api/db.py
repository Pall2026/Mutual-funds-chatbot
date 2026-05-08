import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
        
    if '?' not in database_url:
        database_url += '?sslmode=require'
    elif 'sslmode' not in database_url:
        database_url += '&sslmode=require'
        
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

def get_general_fields():
    """
    Fetch general download guides from scheme_fields.
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT field_value, source_url 
                FROM scheme_fields 
                WHERE field_name IN ('cas_download_guide', 'statement_download_guide')
                AND status = 'active'
                LIMIT 2
                """
            )
            return cur.fetchall()
    finally:
        conn.close()
