# ResearchLM architecture

Two processes: a FastAPI API (`uvicorn main:app` from the repo root) and a Vite React app (`frontend/`). Evaluation is a separate CLI that reuses ingestion and retrieval helpers, not the HTTP chat graph.

```text
PDF / URL  →  paper_loader (chunk + captions)
           →  OpenAI embeddings (CacheBackedEmbeddings → Redis Cloud)
           →  Qdrant (per-session collection)
           →  hybrid retrieve (0.9 dense / 0.1 BM25 RRF) → MiniLM cross-encoder → top-k
           →  LangGraph researcher (retrieve / Tavily / generate)
           →  SSE chat

Chat turns →  notes graph (supervisor → planner → writers)
           →  Postgres notes

evaluate CLI →  evaluation/datasets goldens
             →  eval-scoped Qdrant index
             →  DeepEval + retrieval metrics
             →  evaluation/runs + reports/summary.csv
```

## Layout

| Path | Responsibility |
|---|---|
| `frontend/` | Landing page, auth, chat, notes UI |
| `backend/api/` | FastAPI, JWT, Postgres sessions/notes, ingest HTTP |
| `backend/rag/` | Ingest, retrieval, researcher graph, BTW |
| `backend/notes/` | Study-note LangGraph |
| `backend/llm_schemas.py` | Pydantic schemas for structured LLM output |
| `evaluation/` | Metrics, strategies, datasets, experiment runner |
| `scripts/evaluate.py` | Eval CLI |
| `backend/api/models.py` | Postgres `sessions` / `notes` schema |

## Start

```bash
# repo root
uvicorn main:app --reload
cd frontend && npm run dev
python scripts/evaluate.py --list-datasets
```

Config: copy `.env.example` and `frontend/.env.example`. Never commit `.env`.
