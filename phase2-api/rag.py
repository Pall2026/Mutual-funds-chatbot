import os
import time
from typing import List, Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Configuration from env/ARCHITECTURE.md
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# ChromaDB path removed. Using Neon pgvector.
EMBEDDING_MODEL = "models/text-embedding-004"
LLM_MODEL = "gemini-1.5-flash-latest"
print(f"INFO: Using LLM model: {LLM_MODEL}")

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

def init_chroma():
    """
    (ChromaDB initialization removed)
    """
    return None

def embed_query(text: str) -> List[float]:
    """
    Embed the user query using Gemini.
    """
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    return result.embeddings[0].values

import db

def check_statement_question(question: str) -> bool:
    keywords = [
        "download", "statement", "capital gains",
        "cas", "account statement", "consolidated"
    ]
    q = question.lower()
    return any(k in q for k in keywords)

def search_chunks(collection, embedding: List[float], n_results: int = 3, question: str = None):
    """
    Search Neon pgvector for relevant chunks.
    """
    if question and check_statement_question(question):
        print(f"DEBUG: Statement intercept triggered")
        return {
            'ids': [['hardcoded-statement']],
            'distances': [[0.0]],
            'metadatas': [[{
                'source_url': "https://online.sbimf.com/statement,https://www.amfiindia.com/online-center/download-cas",
                'field_id': None,
                'scheme_name': "GENERAL"
            }]],
            'documents': [[
                "To download your SBI Mutual Fund account statement or capital gains statement, visit online.sbimf.com/statement and enter your folio number to receive the statement on your registered email. You can also download a Consolidated Account Statement (CAS) covering all mutual funds by visiting amfiindia.com/online-center/download-cas and entering your PAN and email."
            ]]
        }

    print(f"DEBUG: Querying Neon pgvector...")
    conn = db.get_connection()
    if not conn:
        print("ERROR: Could not connect to database for search.")
        return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}

    try:
        with conn.cursor() as cur:
            # ORDER BY embedding <=> %s::vector (Cosine distance)
            # Threshold 0.4 distance = 0.6 similarity
            cur.execute(
                """
                SELECT chunk_text, source_url, scheme_name, field_id,
                       1 - (embedding <=> %s::vector) as similarity
                FROM chunks
                WHERE 1 - (embedding <=> %s::vector) > 0.6
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (embedding, embedding, embedding, n_results),
            )
            rows = cur.fetchall()

        documents = [row[0] for row in rows]
        metadatas = [{'source_url': row[1], 'scheme_name': row[2], 'field_id': row[3]} for row in rows]
        similarities = [row[4] for row in rows]

        # Deduplicate source URLs
        source_urls = set()
        for meta in metadatas:
            if meta and 'source_url' in meta:
                urls = meta['source_url'].split(',')
                for u in urls:
                    source_urls.add(u.strip())

        return {
            'documents': [documents],
            'metadatas': [metadatas],
            'similarities': [similarities],
            'source_url': ",".join(sorted(list(source_urls)))
        }
    finally:
        conn.close()

def generate_answer(question: str, context: str) -> str:
    """
    Generate a facts-only answer using Gemini 2.0 Flash.
    """
    prompt = f"""
You are a facts-only assistant for SBI Mutual Fund 
schemes. Answer in maximum 3 sentences using ONLY 
the context provided below. Do not add any 
information not present in the context. Do not give 
investment advice or performance predictions. If the 
context is insufficient, say exactly: I could not 
find a reliable source for this. Please visit 
sbimf.com directly.

CONTEXT:
{context}

QUESTION:
{question}
"""
    
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=LLM_MODEL,
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            if '429' in str(e) and attempt < 2:
                print(f"Quota hit, waiting 5s (attempt {attempt+1}/3)")
                time.sleep(5)
                continue
            raise e
