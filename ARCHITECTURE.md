---

# SBI MF FAQ Assistant — Architecture v1.2
# This file is the single source of truth.
# All phases must follow this exactly.

---

## STACK
- Scraper     : Python + Playwright (phase1-scraper/)
- Database    : PostgreSQL + pgvector on Neon.tech
- Embeddings  : Gemini gemini-embedding-001
- LLM         : Groq llama-3.1-8b-instant
- Backend API : FastAPI on Render.com (phase2-api/)
- Frontend    : Next.js on Vercel (phase3-frontend/)
- Scheduler   : Render Cron Job (monthly)
- Total cost  : $0 (all free tiers)

---

## FOLDER STRUCTURE
sbi-mf-faq/
├── ARCHITECTURE.md         ← this file
├── README.md
├── phase1-scraper/
│   ├── scraper.py          ← Playwright visits all URLs
│   ├── pdf_extractor.py    ← PyMuPDF extracts PDF text
│   ├── embedder.py         ← Gemini embeds fields → pgvector
│   ├── db.py               ← PostgreSQL connection + queries
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.toml
├── phase2-api/
│   ├── main.py             ← FastAPI app + /ask + /health
│   ├── rag.py              ← pgvector search + Gemini answer
│   ├── guardrails.py       ← PII blocking + advice refusal
│   ├── db.py               ← PostgreSQL connection
│   ├── requirements.txt
│   └── Dockerfile
└── phase3-frontend/
    ├── app/
    │   ├── page.tsx
    │   ├── api/ask/route.ts ← proxy to Railway (server-side)
    │   └── components/
    │       ├── ChatBox.tsx
    │       ├── ExampleChips.tsx
    │       └── AnswerCard.tsx
    ├── package.json
    └── .env.local

---

## DATABASE SCHEMA

-- Run once on Railway PostgreSQL before Phase 1

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE scheme_fields (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scheme_name TEXT NOT NULL,
  field_name  TEXT NOT NULL,
  field_value TEXT NOT NULL,
  source_url  TEXT NOT NULL,
  is_pdf      BOOLEAN DEFAULT false,
  scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  status      TEXT DEFAULT 'active'
);

CREATE TABLE chunks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  field_id    UUID REFERENCES scheme_fields(id),
  chunk_text  TEXT NOT NULL,
  embedding   vector(3072),
  source_url  TEXT NOT NULL,
  scheme_name TEXT NOT NULL,
  embedded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON scheme_fields(scheme_name);
CREATE INDEX ON scheme_fields(field_name);

---

## NEON PGVECTOR (VECTOR STORAGE)
Primary store for all production embeddings. 
Gemini gemini-embedding-001 vectors (3072 dims) are stored in the 'chunks' table.
Similarity search uses Cosine distance (vector_cosine_ops).
Threshold: 1 - (embedding <=> %s::vector) > 0.6 (Similarity).

---

## FIELDS TO EXTRACT PER SCHEME
Each scheme must produce rows for ALL these field_names:
- expense_ratio_direct
- expense_ratio_regular
- exit_load
- exit_load_period
- minimum_sip
- minimum_lumpsum
- lock_in_period       (ELSS only — value: "3 years")
- riskometer_level
- benchmark_index
- fund_manager
- aum
- scheme_category

chunk_text format for embedder.py:
"{scheme_name} {field_name}: {field_value}"
Example: "SBI Bluechip Fund expense_ratio_direct: 0.85%"

---

## API CONTRACT

POST /ask
Request  : { "question": string }
Response : {
  "answer"        : string,
  "source_url"    : string | null,
  "last_updated"  : string | null,
  "response_type" : "answer" | "refusal" | "pii_block"
}

GET /health
Response : { "status": "ok" }
-- Required by Railway to confirm service is alive

---

## GUARDRAILS (guardrails.py)

PII patterns to block BEFORE calling Gemini:
- PAN     : r"[A-Z]{5}[0-9]{4}[A-Z]{1}"
- Aadhaar : r"\d{12}"
- Phone   : r"[6-9]\d{9}"
- Email   : r"[^@]+@[^@]+\.[^@]+"
If match found → return response_type: "pii_block"
Do NOT log the query. Do NOT call Gemini.

Advice refusal keywords to block:
- "should i", "shall i", "recommend", "better fund",
  "which fund", "buy", "sell", "invest in", "returns",
  "performance", "best fund", "compare funds"
If match found → return response_type: "refusal"
source_url must be "https://www.amfiindia.com/investor-corner"

RAG threshold:
If pgvector cosine distance > 0.4 for all top 3 results:
Return "I could not find a reliable source for this.
Please visit sbimf.com directly."

---

## GEMINI SYSTEM PROMPT (used in rag.py)

"You are a facts-only assistant for SBI Mutual Fund 
schemes. Answer in maximum 3 sentences using ONLY 
the context provided below. Do not add any 
information not present in the context. Do not give 
investment advice or performance predictions. If the 
context is insufficient, say exactly: I could not 
find a reliable source for this. Please visit 
sbimf.com directly."

---

## CORS (main.py — CRITICAL)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
  CORSMiddleware,
  allow_origins=["https://mutual-funds-chatbot.vercel.app"],
  allow_methods=["POST", "GET"],
  allow_headers=["*"],
)
-- Replace with real Vercel URL in Phase 3

---

## RENDER CONFIG (phase1-scraper/Dockerfile)

[build]
builder = "dockerfile"

command = "python scraper.py && python embedder.py"
-- Note: Render Cron Jobs are configured in the Render Dashboard

-- IMPORTANT: scraper.py must sys.exit(1) on any error
-- && ensures embedder only runs if scraper succeeds

---

## ENVIRONMENT VARIABLES

Neon.tech (both phase1 and phase2 services):
- DATABASE_URL   → auto-provided by Neon.tech PostgreSQL

Render.com (phase2):
- GEMINI_API_KEY → from aistudio.google.com
- GROQ_API_KEY   → from console.groq.com

Vercel (phase3):
- API_URL → Render.com FastAPI service URL
-- NOTE: NO NEXT_PUBLIC_ prefix — keeps URL server-side only
-- Use in api/ask/route.ts proxy only, never client-side

---

## PHASE BOUNDARIES

PHASE 1 — /phase1-scraper only
  Build: scraper.py, pdf_extractor.py, embedder.py, 
         db.py, Dockerfile, railway.toml
  Done when: PostgreSQL has 60+ rows in scheme_fields,
             chunks table has embeddings for all rows
  Test: Raw SQL query confirms correct data
  DO NOT touch phase2-api or phase3-frontend

PHASE 2 — /phase2-api only
  Build: main.py, rag.py, guardrails.py, db.py,
         Dockerfile
  Done when: POST /ask returns correct JSON for
             factual, refusal, and pii_block queries
  Test: Manual API calls via browser or Postman
  DO NOT touch phase1-scraper or phase3-frontend

PHASE 3 — /phase3-frontend only
  Build: page.tsx, api/ask/route.ts, ChatBox.tsx,
         ExampleChips.tsx, AnswerCard.tsx
  Done when: Live Vercel URL working end to end
  Test: Use as real user, check all 3 chips work
  DO NOT touch phase1-scraper or phase2-api

---

## DEPLOYMENT URLS
Backend API: https://sbi-mf-api-us.onrender.com/health
Frontend:    https://mutual-funds-chatbot.vercel.app/
Database:    Neon.tech (Singapore region)

---

## MANUAL TEST CHECKLIST

Phase 1 SQL test (run in Neon SQL Editor):
SELECT scheme_name, field_name, field_value 
FROM scheme_fields 
WHERE scheme_name = 'SBI Bluechip Fund';
-- Must return 12 rows (one per field)

Phase 2 API tests (test all 3 types):
1. POST /ask {"question": "What is expense ratio of SBI Bluechip Fund?"}
   → response_type must be "answer"
2. POST /ask {"question": "Should I invest in SBI Bluechip?"}
   → response_type must be "refusal"
3. POST /ask {"question": "My PAN is ABCDE1234F"}
   → response_type must be "pii_block"

Phase 3 UI tests:
1. Click each example chip → answer appears
2. Every answer has a source link
3. Every answer has "Data last updated: Month Year"
4. Type PAN in input → warning appears, API not called

---
End of ARCHITECTURE.md
---
