import os
import time
from typing import List, Optional
import chromadb
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Configuration from env/ARCHITECTURE.md
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHROMA_PATH = os.getenv("CHROMA_PATH", "../phase1-scraper/chroma_data")
EMBEDDING_MODEL = "models/gemini-embedding-001"
LLM_MODEL = "gemini-flash-latest"

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

def init_chroma():
    """
    Initialize ChromaDB client and collection.
    """
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(name="sbi_mf_chunks")
    return collection

def embed_query(text: str) -> List[float]:
    """
    Embed the user query using Gemini.
    """
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    return result.embeddings[0].values

def search_chunks(collection, embedding: List[float], n_results: int = 3):
    """
    Search ChromaDB for relevant chunks.
    """
    results = collection.query(
        query_embeddings=[embedding],
        n_results=n_results
    )
    return results

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
    
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=prompt
    )
    return response.text.strip()
