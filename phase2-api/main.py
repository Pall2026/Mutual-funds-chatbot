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

# ChromaDB collection removed. pgvector search handled inside rag.py.

@app.on_event("startup")
def startup_event():
    pass # init_chroma no longer needed

@app.get("/health")
def health_check():
    return {"status": "ok", "phase": "2"}

@app.post("/ask", response_model=AskResponse)
def ask_question(req: AskRequest):
    question = req.question
    
    # 1. Guardrail: PII Block
    if guardrails.check_pii(question):
        ans = "I detected personal information (PII) in your query. Please remove it and try again."
        rtype = "pii_block"
        print(f"DEBUG returning: {rtype} - {ans[:50]}")
        return AskResponse(
            answer=ans,
            response_type=rtype
        )
    
    # 2. Guardrail: Advice Refusal
    if guardrails.check_advice(question):
        ans = "I am a facts-only assistant and cannot provide investment advice or recommendations."
        rtype = "refusal"
        print(f"DEBUG returning: {rtype} - {ans[:50]}")
        return AskResponse(
            answer=ans,
            source_url="https://www.sbimf.com",
            response_type=rtype
        )
    
    # 3. RAG Flow
    try:
        print(f"DEBUG: Question received: {question}")
        try:
            print(f"DEBUG original: {question}")
            question = rag.normalize_question(question)
            print(f"DEBUG normalized: {question}")
            
            query_embedding = rag.embed_query(question)
            search_results = rag.search_chunks(None, query_embedding, n_results=3, question=question)
            
            if not search_results['documents'] or not search_results['documents'][0]:
                ans = "I could not find a reliable source for this. Please visit sbimf.com directly."
                rtype = "refusal"
                print(f"DEBUG returning: {rtype} - {ans[:50]}")
                return AskResponse(
                    answer=ans,
                    response_type=rtype
                )
                
            context = "\n".join(search_results['documents'][0])
            answer = rag.generate_answer(question, context)
        except Exception as e:
            import traceback
            print(f"RAG ERROR: {type(e).__name__}: {e}")
            print(traceback.format_exc())
            ans = "Something went wrong. Please try again."
            rtype = "error"
            print(f"DEBUG returning: {rtype} - {ans[:50]}")
            return AskResponse(
                answer=ans,
                source_url=None,
                last_updated=None,
                response_type=rtype
            )
        
        # Extract metadata from top result
        top_meta = search_results['metadatas'][0][0]
        source_url = top_meta.get('source_url')
        field_id = top_meta.get('field_id')
        
        # Get scraped_at from DB
        last_updated = str(db.get_field_scraped_at(field_id)) if field_id else None
        
        response_type = "answer" if "I could not find" not in answer else "refusal"
        print(f"DEBUG returning: {response_type} - {answer[:50]}")

        return AskResponse(
            answer=answer,
            source_url=source_url,
            last_updated=last_updated,
            response_type=response_type
        )
        
    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR in /ask: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        ans = "Something went wrong. Please try again."
        rtype = "error"
        print(f"DEBUG returning: {rtype} - {ans[:50]}")
        return AskResponse(
            answer=ans,
            source_url=None,
            last_updated=None,
            response_type=rtype
        )
