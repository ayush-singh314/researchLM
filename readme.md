# ResearchLM

A signed-in research workspace that answers questions from **your** PDFs and URLs, streams grounded replies, and turns the thread into editable study notes.

FastAPI + LangGraph + Qdrant + Neon Postgres, with a Vite React UI and a separate DeepEval retrieval evaluation CLI.

---

## Project Overview

Reading papers is slow when answers are buried in PDFs, figures, and related web pages. Generic chatbots often invent citations or mix in knowledge that is not in the document you care about.

ResearchLM is a **per-session RAG workspace**: you upload papers or paste URLs, ask questions, and get answers produced from retrieved chunks (and optional Tavily web search when the researcher graph routes that way). Chat history is stored in LangGraph’s **Postgres checkpointer**, not a messages table. Study notes are generated from the discussion and saved in Postgres so you can edit and download them.

**Who it is for:** students and researchers who want Q&A and notes grounded in papers they actually ingested—and engineers who want a small, inspectable RAG + eval codebase.

Pipeline map: [docs/architecture.md](docs/architecture.md). Interview study guide: [interview/README.md](interview/README.md).

---

## Key Features

### Product

- Landing page for guests; Neon Auth sign-in / sign-up (`frontend/src/AuthGate.tsx`)
- Research sessions owned by JWT `sub` (`backend/api/models.py`, `backend/api/repos.py`)
- Ingest: PDF / `.txt` / `.md` upload and URL fetch (`POST /sessions/{id}/documents`, `POST /sessions/{id}/urls`)
- Streaming chat over SSE (`POST /sessions/{id}/chat`); markdown + KaTeX in the UI
- Study notes: generate from chat, autosave, preview, download `.md`
- Profile view of notes across sessions (`GET /notes`)

### RAG / AI

- Per-session Qdrant collections (`papeer_{session_id}`)
- LangGraph researcher: `router` → retrieve / claim-verify / direct answer → `generate_answer` (`backend/rag/graph.py`)
- Dense cosine search by default; optional hybrid BM25 + dense **unweighted RRF** (`RRF_K = 60`)
- PDF figure extraction + `gpt-4o` captions (`backend/rag/pdf_images.py`, `backend/rag/image_captioner.py`)
- Tavily tools on the retrieve path; claim path also searches `site:arxiv.org` (no arXiv-ID ingest API)
- Structured LLM outputs via Pydantic (`backend/llm_schemas.py`)

### Evaluation (CLI, not the HTTP chat graph)

- Datasets under `evaluation/datasets/` with cached `goldens.json`
- Strategies: `keyword`, `bm25`, `dense`, `hybrid`; `rag_fusion` is a stub that falls back to dense
- DeepEval generation metrics + custom retrieval metrics (`evaluation/metrics.py`)
- Run artifacts: `evaluation/runs/*.json`, aggregates in `evaluation/reports/summary.csv`

**Also in the API, unused by the current UI:** `POST /sessions/{id}/btw` streams a side-channel web answer (`backend/rag/btw_handler.py`). `frontend/src/api.ts` does not call it.

---

## Technology Stack

| Layer | Technology | Purpose in this repo |
| --- | --- | --- |
| Frontend | React 19, Vite, TypeScript | Landing, auth gate, chat, notes |
| Frontend data | TanStack Query, `fetch` + SSE | Sessions/notes CRUD; chat stream |
| Frontend rendering | react-markdown, remark-math, rehype-katex, KaTeX, Mermaid | Chat/notes markdown |
| Auth (client) | `@neondatabase/neon-js` | Neon Auth session + access token |
| Auth (API) | PyJWT + JWKS | Verify Bearer JWT; `user_id` = `sub` |
| API | FastAPI, Uvicorn | HTTP routers, CORS, SSE |
| App DB | Neon Postgres, SQLAlchemy, Alembic, Psycopg | `sessions`, `notes` |
| Agent memory | LangGraph `PostgresSaver` | Chat thread state (`thread_id` = session id) |
| Vectors | Qdrant, langchain-qdrant | Per-session embeddings index |
| Embeddings | OpenAI `text-embedding-3-small` (1536-d), `CacheBackedEmbeddings` | Index + query vectors |
| Captions | OpenAI `gpt-4o` | Image captions at ingest |
| LLM | Groq `ChatGroq` model `openai/gpt-oss-120b` | Router, researcher, notes, session titles |
| Web search | Tavily | Retrieve-path tool + claim verification |
| Retrieval extras | rank-bm25 | Hybrid path and eval BM25 |
| Ingest | PyMuPDF, BeautifulSoup / LangChain web loader | PDF pages and URLs |
| Orchestration | LangGraph, LangChain | Researcher + notes graphs |
| Evaluation | DeepEval, `scripts/evaluate.py` | Offline RAG experiments |

Listed in `pyproject.toml` but **not imported on live product paths:** `chromadb`, `streamlit`, `arxiv`, `langgraph-checkpoint-sqlite`. Do not treat those as the running stack.

---

## System Architecture

Two long-lived processes: the API (`uvicorn main:app`) and the Vite dev server. Evaluation is a third, offline path.

```mermaid
flowchart LR
  User --> Frontend
  Frontend --> NeonAuth[Neon Auth]
  Frontend --> API[FastAPI]
  API --> JWKS[Neon Auth JWKS]
  API --> Postgres[(Neon Postgres)]
  API --> Checkpointer[PostgresSaver]
  API --> Qdrant[(Qdrant)]
  API --> Groq[Groq LLM]
  API --> OpenAI[OpenAI embeddings and captions]
  API --> Tavily[Tavily]
```

More detail: [docs/architecture.md](docs/architecture.md) and [interview/architecture/system-architecture.md](interview/architecture/system-architecture.md).

---

## How the System Works

```text
Sign in (Neon Auth JWT)
  → FastAPI verifies JWKS, sets user_id = sub
  → Create session (Postgres)
  → Upload PDF / URLs → chunk (+ optional captions) → Qdrant collection papeer_{session}
  → Chat SSE → LangGraph researcher (thread_id = session id)
       router → retrieve | verify_claim | direct_answer → generate_answer
  → GET messages reads checkpoint state (no messages table)
  → Notes generate: supervisor → planner → section writers → assemble → INSERT notes
```

**Evaluation (separate):** golden QA → eval-scoped Qdrant index → strategy retriever → Groq answer prompt in `evaluation/experiment_runner.py` → DeepEval → `evaluation/runs` + `evaluation/reports/summary.csv`. This path does **not** invoke `backend/rag/graph.py`.

---

## Evaluation & Metrics

**What was evaluated:** retrieval + a simple Groq answer on cached goldens (10 questions per reported run).

**How:** `python scripts/evaluate.py --dataset … --strategy … --modality …`  
Default DeepEval threshold is **0.7** (`--metric-threshold`). Default judge model in the CLI is `gpt-5.4-mini`.

**Pass rate:** fraction of questions where DeepEval marks the test case `success` (in the saved runs, that is all five generation metrics passing). Implemented in `evaluation/experiment_runner.py` (`_aggregate_deepeval_results`).

**Custom retrieval:** `top_k_hit` is token-overlap of expected answer vs a retrieved context at ratio **≥ 0.08** (`evaluation/metrics.py`).

Values below are copied from [`evaluation/reports/summary.csv`](evaluation/reports/summary.csv). Embedding model for all three rows: `text-embedding-3-small`. **Do not treat these as production chat-graph metrics.**

| Dataset | Strategy | Modality | n | pass_rate | Contextual Precision | Contextual Recall | Contextual Relevancy | Answer Relevancy | Faithfulness | avg_top_k_hit | avg_retrieved_context_count |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| openclaw | dense | text_only | 10 | 0.4 | 1.0 | 0.9333333333333333 | 0.6850178161847991 | 0.8890509828009827 | 0.9732142857142858 | 1.0 | 4.0 |
| openclaw | hybrid | text_only | 10 | 0.6 | 1.0 | 0.9547619047619047 | 0.7031652053321974 | 0.8983936651583709 | 0.9723076923076924 | 1.0 | 4.0 |
| attention_is_all_you_need | hybrid | multimodal | 10 | 0.0 | 0.7246503295438018 | 0.915 | 0.21370851723864673 | 0.9375 | 0.9357142857142857 | 1.0 | 20.0 |

**How to read this:** on the text-only OpenClaw set, hybrid’s pass_rate is higher than dense (0.6 vs 0.4) with similar faithfulness. On the multimodal Attention paper run, **every question failed the overall pass** (`pass_rate = 0.0`) while faithfulness and answer relevancy stayed high and `avg_top_k_hit` was still 1.0—contextual relevancy dropped to ~0.21 with 20 contexts per question. With n=10, pass_rate moves in 0.1 steps; it is brittle.

`evaluation/reports/eval_results.json` is per-question detail for the Attention hybrid run only, not a second summary of all three experiments.

---

## Technical Highlights

- **Tenancy without stuffing identity into the agent state:** `sessions.user_id` / `notes.user_id` equal JWT `sub`. `RAGState` has `session_id` but not `user_id` (`backend/rag/graph.py`). Ownership is enforced in the API (`require_owned_session`).
- **Conversation persistence:** one `PostgresSaver`; `GET /sessions/{id}/messages` reconstructs chat from checkpoint (`backend/api/serialize.py`).
- **Session-scoped vectors:** collection name `papeer_{session_id with '-' → '_'}` so uploads do not share an index across chats.
- **Researcher routing:** structured `RouterDecision` before retrieval; retrieve path can call vector search and Tavily, with a relevancy check and at most one query rewrite.
- **Streaming UX:** SSE events `token` | `done` | `error`; empty/failed answers use a shared fallback string in API and UI.
- **Eval isolation:** strategy comparison does not require standing up the chat graph or auth.

---

## Design / Engineering Decisions

**Postgres checkpointer for chat, not SQLite**  
Why: session metadata and notes already live on Neon; `thread_id` is the session UUID.  
In repo: live code uses `PostgresSaver` (`backend/api/checkpoint.py`). `langgraph-checkpoint-sqlite` remains in `pyproject.toml` but is unused on live import paths.  
Trade-off: checkpointer tables are created by `saver.setup()`, not Alembic.

**Dense retrieval as app default; hybrid is opt-in**  
Why: `RETRIEVAL_STRATEGY` defaults to `dense` in `backend/rag/vector_store.py`. Hybrid fetches `k*2` dense and BM25 lists, then RRF.  
Trade-off: hybrid needs a full collection scroll for BM25 (cached in-process). Eval additionally has a lexical rerank step the **chat path does not use**.

**Eval pipeline separate from LangGraph chat**  
Why: cheap strategy A/B on goldens without agent routing, tools, or SSE.  
Trade-off: reported metrics are **not** a measure of the production researcher graph.

**JWKS verification with `verify_aud: False`**  
Why: Neon Auth JWTs are verified for signature, algorithm, and issuer (`backend/api/auth.py`). Audience is not checked.  
Trade-off: simpler local setup; weaker audience binding than a locked `aud` check.

---

## Project Structure

```text
researchlm/
├── frontend/                 # Vite React UI
├── backend/
│   ├── api/                  # FastAPI, JWT, Postgres sessions/notes, HTTP
│   ├── rag/                  # Ingest, Qdrant, researcher graph, BTW
│   ├── notes/                # Notes LangGraph
│   └── llm_schemas.py        # Structured LLM models (not SQLAlchemy)
├── evaluation/               # CLI metrics, datasets, runs, reports
├── scripts/                  # evaluate.py, rag_smoke.py, qdrant_ping.py
├── alembic/                  # sessions/notes migrations
├── docs/architecture.md
├── documents/                # eval-referenced PDFs (e.g. OpenClaw report)
├── main.py                   # uvicorn main:app
├── .env.example
├── frontend/.env.example
└── interview/                # Interview study guide
```

---

## Getting Started

### Prerequisites

- Python **3.12+** (`pyproject.toml` `requires-python`)
- Node.js (Vite frontend; no `engines` field in `frontend/package.json`)
- Qdrant (`QDRANT_URL`)
- Neon (or other) Postgres (`DATABASE_URL`)
- Neon Auth base URL
- API keys: OpenAI, Groq, Tavily (as used by embeddings, captions, ChatGroq, web search)

### Install

```bash
# clone your copy of the repo, then:
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate

pip install -r requirements.txt
# or: uv sync

copy .env.example .env          # Windows
# cp .env.example .env          # Unix
# fill DATABASE_URL, NEON_AUTH_URL, QDRANT_*, OPENAI_API_KEY, GROQ_API_KEY, TAVILY_API_KEY

cd frontend
copy .env.example .env          # set VITE_NEON_AUTH_URL and VITE_API_BASE_URL
npm install
```

Optional migrations (API startup also runs `Base.metadata.create_all` and a user_id column check in `backend/api/db.py`):

```bash
alembic upgrade head
```

### Run

```bash
# repo root — API (docs at http://localhost:8000/docs, health GET /health)
uvicorn main:app --reload

# frontend
cd frontend
npm run dev
```

UI default: `http://localhost:5173`. CORS default: `http://localhost:5173`.

### Evaluate

```bash
python scripts/evaluate.py --list-datasets
python scripts/evaluate.py --dataset openclaw --strategy dense --modality text_only
python scripts/evaluate.py --dataset openclaw --strategy hybrid --modality text_only
```

Do not use `--dataset bert` unless you add `evaluation/datasets/bert/metadata.json`; the PDF alone is not listable.

### Environment (placeholders only)

Root `.env.example`: `DATABASE_URL`, optional `CHECKPOINT_DATABASE_URL`, `NEON_AUTH_URL`, `CORS_ORIGINS`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `TAVILY_API_KEY`, `RETRIEVAL_STRATEGY`.

Frontend: `VITE_API_BASE_URL=http://localhost:8000`, `VITE_NEON_AUTH_URL=<neon-auth-base-url>`.

Never commit `.env`.

---

## Usage

1. Open the landing page and sign in (or sign up) with Neon Auth.
2. Create a session.
3. Upload a PDF (or `.txt` / `.md`) and/or add URLs.
4. Ask questions in chat; tokens stream in. History reloads from the checkpointer.
5. Generate study notes from the thread; edit and download markdown. Profile lists notes across sessions.

---

## Future Improvements

These are gaps relative to the current code, not unfinished items described as done:

- Wire or remove `POST /sessions/{id}/btw` in the UI
- Implement eval `rag_fusion` (currently a stub → dense)
- Investigate the multimodal Attention run (`pass_rate = 0.0`, low contextual relevancy)
- API rate limiting (auth exists; throttling does not)
- Drop unused Python dependencies (`chromadb`, `streamlit`, `arxiv`, sqlite checkpointer package)
- Audience (`aud`) verification on JWTs if Neon Auth issues a stable audience
- Container / hosting manifests are not in this repo

---

## Acknowledgments

LangChain / LangGraph, Qdrant, DeepEval, OpenAI embeddings, Groq, Tavily, and Neon (Postgres + Auth).
