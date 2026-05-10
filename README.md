# SBI Mutual Fund FAQ Assistant

A facts only RAG chatbot for SBI Mutual Fund schemes.
Answers factual questions about expense ratios, exit loads,
minimum SIP, lock-in periods, riskometer, and more.

## Live Demo
Frontend: https://mutual-funds-chatbot.vercel.app/
Backend API: https://sbi-mf-api-us.onrender.com/health

## What It Does
- Answers factual questions about 4 SBI Mutual Fund schemes
- Blocks investment advice requests (SEBI compliant)
- Blocks PII (PAN, Aadhaar, phone, email)
- Cites official SBI MF sources for every answer
- Auto-updates data monthly via scraper

## Schemes Covered
- SBI Bluechip Fund (Large Cap)
- SBI Flexicap Fund
- SBI ELSS Tax Saver Fund
- SBI Small Cap Fund

## Tech Stack
| Layer | Technology |
|-------|------------|
| Scraper | Python + Playwright |
| Database | PostgreSQL + pgvector (Neon.tech) |
| Embeddings | Gemini gemini-embedding-001 |
| LLM | Groq llama-3.1-8b-instant |
| Backend | FastAPI (Render.com) |
| Frontend | Next.js (Vercel) |

## Project Structure
- phase1-scraper/ → Web scraper + PDF extractor + embedder
- phase2-api/     → FastAPI RAG backend
- phase3-frontend/ → Next.js chat interface

## Setup
See ARCHITECTURE.md for full technical details.

Vercel live demo - https://mutual-funds-chatbot.vercel.app/



https://github.com/user-attachments/assets/98d3f6f2-f33f-492a-a7b4-8964968d1d3f

