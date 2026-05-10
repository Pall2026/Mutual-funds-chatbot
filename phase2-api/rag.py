import os
import time
from typing import List, Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# Configuration from env/ARCHITECTURE.md
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

EMBEDDING_MODEL = "models/gemini-embedding-001"
GROQ_MODEL = "llama-3.1-8b-instant"
print(f"INFO: Using Groq model: {GROQ_MODEL}")

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

groq_client = None
if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)

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


def normalize_question(question: str) -> str:
    """Map common scheme name aliases to canonical names."""
    aliases = {
        "sbi large cap": "SBI Bluechip Fund",
        "sbi largecap": "SBI Bluechip Fund",
        "sbi bluechip": "SBI Bluechip Fund",
        "sbi elss": "SBI ELSS Tax Saver Fund",
        "sbi tax saver": "SBI ELSS Tax Saver Fund",
        "sbi long term equity": "SBI ELSS Tax Saver Fund",
        "sbi flexi cap": "SBI Flexicap Fund",
        "sbi flexicap": "SBI Flexicap Fund",
        "sbi small cap": "SBI Small Cap Fund",
        "sbi smallcap": "SBI Small Cap Fund",
    }
    import re
    q_lower = question.lower()
    for alias, canonical in aliases.items():
        if alias in q_lower:
            # Replace alias with canonical name, preserving case of the rest of the question
            result = re.sub(re.escape(alias), canonical, question, flags=re.IGNORECASE)
            # Remove trailing duplicate " fund" after canonical name
            result = re.sub(re.escape(canonical) + r"(?i:\s+fund)", canonical, result, flags=re.IGNORECASE)
            return result
    return question

def detect_scheme(question: str) -> Optional[str]:
    schemes = [
        'SBI Bluechip Fund',
        'SBI Flexicap Fund', 
        'SBI ELSS Tax Saver Fund',
        'SBI Small Cap Fund'
    ]
    q_lower = question.lower()
    for scheme in schemes:
        if scheme.lower() in q_lower:
            return scheme
    return None

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
            target_scheme = None
            if question:
                target_scheme = detect_scheme(question)

            if target_scheme:
                cur.execute(
                    """
                    SELECT chunk_text, source_url, scheme_name, field_id,
                           1 - (embedding <=> %s::vector) as similarity
                    FROM chunks
                    WHERE scheme_name = %s AND 1 - (embedding <=> %s::vector) > 0.6
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (embedding, target_scheme, embedding, embedding, n_results),
                )
            else:
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
    Generate a facts-only answer using Groq Llama-3.1.
    """
    if not context or "I could not find a reliable source" in context:
        return "I could not find a reliable source for this. Please visit sbimf.com directly."

    try:
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a facts-only assistant for SBI Mutual Fund schemes. Follow these rules strictly:\n1. Answer in 1-2 sentences maximum\n2. Use ONLY information from the context provided\n3. Do not repeat the same fact twice\n4. Do not add related fields not asked about\n5. Do not give investment advice\n6. Be concise and direct\n7. Answer ONLY what was specifically asked"
                },
                {
                    "role": "user", 
                    "content": f"Context:\n{context}\n\nQuestion: {question}"
                }
            ],
            max_tokens=200
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Groq API error: {e}")
        return "Something went wrong with the answer generation. Please try again."
