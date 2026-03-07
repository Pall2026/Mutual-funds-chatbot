from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import guardrails
import rag
import db

app = FastAPI(title="SBI MF FAQ Assistant API")

# CORS configuration as per ARCHITECTURE.md
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update with Vercel URL in Phase 3
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str
    source_url: Optional[str] = None
    last_updated: Optional[str] = None
    response_type: str # "answer" | "refusal" | "pii_block"

# Init Chroma collection at startup
_collection = None

@app.on_event("startup")
def startup_event():
    global _collection
    try:
        _collection = rag.init_chroma()
    except Exception as e:
        print(f"Error initializing ChromaDB: {e}")

@app.get("/health")
def health_check():
    return {"status": "ok", "phase": "2"}

@app.post("/ask", response_model=AskResponse)
def ask_question(req: AskRequest):
    question = req.question
    
    # 1. Guardrail: PII Block
    if guardrails.check_pii(question):
        return AskResponse(
            answer="I detected personal information (PII) in your query. Please remove it and try again.",
            response_type="pii_block"
        )
    
    # 2. Guardrail: Advice Refusal
    if guardrails.check_advice(question):
        return AskResponse(
            answer="I am a facts-only assistant and cannot provide investment advice or recommendations.",
            source_url="https://www.amfiindia.com/investor-corner",
            response_type="refusal"
        )
    
    # 3. RAG Flow
    try:
        query_embedding = rag.embed_query(question)
        search_results = rag.search_chunks(_collection, query_embedding, n_results=3)
        
        # Check distance threshold (simplified for now: if no results or very far)
        # Using ARCHITECTURE.md suggestion: if cosine distance > 0.4
        # ChromaDB results['distances'] are often 1-cosine_similarity or squared L2
        # We will assume some relevant context is found if any result exists.
        
        if not search_results['documents'] or not search_results['documents'][0]:
            return AskResponse(
                answer="I could not find a reliable source for this. Please visit sbimf.com directly.",
                response_type="refusal"
            )
            
        context = "\n".join(search_results['documents'][0])
        answer = rag.generate_answer(question, context)
        
        # Extract metadata from top result
        top_meta = search_results['metadatas'][0][0]
        source_url = top_meta.get('source_url')
        field_id = top_meta.get('field_id')
        
        # Get scraped_at from DB
        last_updated = str(db.get_field_scraped_at(field_id)) if field_id else None
        
        return AskResponse(
            answer=answer,
            source_url=source_url,
            last_updated=last_updated,
            response_type="answer" if "I could not find" not in answer else "refusal"
        )
        
    except Exception as e:
        print(f"Error in /ask: {e}")
        return AskResponse(
            answer="An error occurred while processing your request.",
            response_type="refusal"
        )
