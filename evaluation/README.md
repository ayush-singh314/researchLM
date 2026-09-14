# RAG Evaluation Framework

Benchmark multiple retrieval strategies (keyword, BM25, dense, hybrid, RAG-Fusion hook) across **text-only** and **multimodal** ingestion using cached synthetic golden QA datasets and DeepEval generation metrics.

## Folder structure

```
evaluation/
  __init__.py
  dataset_manager.py    # datasets, goldens cache, metadata
  strategies.py         # retrieval strategy registry + factory
  vector_index.py       # eval-scoped Qdrant index + retrievers
  metrics.py            # DeepEval builders + retrieval metrics
  experiment_runner.py  # end-to-end experiment execution
  report_writer.py      # JSON runs + CSV summary
  configs/              # example experiment configs
  datasets/             # one folder per dataset
    <name>/
      metadata.json
      goldens.json      # generated once, reused
      source.pdf        # optional (or source_files in metadata)
  runs/                 # per-run JSON artifacts
  reports/
    summary.csv         # aggregated comparison across runs
```

## Create a dataset

1. Create `evaluation/datasets/<name>/metadata.json`:

```json
{
  "dataset_name": "my_paper",
  "description": "Short description",
  "modality": "multimodal",
  "default_category": "general",
  "categories": ["text", "figure", "table", "cross_modal", "general"],
  "source_files": ["documents/my_paper.pdf"]
}
```

2. Optionally copy the PDF to `evaluation/datasets/<name>/source.pdf`.

3. Generate goldens once (cached to `goldens.json`):

```bash
python scripts/evaluate.py --dataset my_paper --strategy dense --regenerate-goldens
```

4. Optionally add per-question categories in `goldens.json`:

```json
{
  "input": "What does Figure 2 show?",
  "expected_output": "...",
  "category": "figure"
}
```

## Run experiments

```bash
# Dense retrieval, text-only ingestion
python scripts/evaluate.py --dataset openclaw --strategy dense --modality text_only

# Hybrid retrieval, multimodal ingestion (text + image captions)
python scripts/evaluate.py --dataset openclaw --strategy hybrid --modality multimodal

# BM25 baseline, different embedding model for dense/hybrid components
python scripts/evaluate.py --dataset openclaw --strategy bm25 --modality text_only --embedding-model text-embedding-3-small
```

### Useful flags

| Flag | Description |
|------|-------------|
| `--regenerate-goldens` | Rebuild `goldens.json` from source PDF(s) |
| `--embedding-model` | OpenAI embedding model for dense/hybrid (CLI default `text-embedding-3-small`) |
| `--metric-threshold` | DeepEval pass cutoff per metric (default **0.4**) |
| `--rrf-dense-weight` / `--rrf-bm25-weight` | Hybrid RRF mix (default **0.9 / 0.1**, same as chat) |
| `--output-dir` | Override JSON run output directory |
| `--top-k` | Retrieval depth per question |
| `--no-rerank` | Skip dedupe + cross-encoder rerank (`ms-marco-MiniLM-L-6-v2`) |
| `--list-datasets` | Show available datasets |

## Compare strategies

- **Per-run detail:** `evaluation/runs/<timestamp>_<dataset>_<strategy>.json`
- **Cross-run summary:** `evaluation/reports/summary.csv`

Each run JSON includes:

- timestamp, dataset, strategy, modality, embedding model
- DeepEval metric averages and pass rate
- Retrieval metrics (top-k hit, context count, modality hit rate)
- Per-question results grouped by category

## Cached goldens

Goldens follow the **generate once, reuse many times** pattern:

1. On first run, if `evaluation/datasets/<name>/goldens.json` is missing, DeepEval `Synthesizer` builds QA pairs from the source PDF.
2. Subsequent runs load the cached file instantly.
3. Use `--regenerate-goldens` only when the source document changes.

The legacy root `goldens.json` is bootstrapped into `evaluation/datasets/openclaw/` on first run if present.

## Strategies

| Strategy | Status |
|----------|--------|
| `keyword` | Token overlap over indexed chunks |
| `bm25` | BM25 lexical retrieval |
| `dense` | Qdrant dense vectors (default production behavior) |
| `hybrid` | RRF fusion of BM25 + dense |
| `rag_fusion` | Stub — dense fallback until multi-query expansion is added |

## Embedding cache benchmark

Measures `CacheBackedEmbeddings` (`blake2b` keys) on an isolated **temp** `LocalFileStore`. Production chat uses Redis Cloud (`REDIS_URL`); this script does not write to Redis or `./embedding_cache/`.

```bash
# from repo root; needs OPENAI_API_KEY
python evaluation/embedding_cache_benchmark.py --requests 50
```

`--queries` is an alias of `--requests`. Results and method: `evaluation/reports.md`. Reports **embedding** latency only, not full RAG.

## Environment

Requires the same keys as the main app:

- `OPENAI_API_KEY` (embeddings + DeepEval judge)
- `GROQ_API_KEY` (answer generation during eval)
- `QDRANT_URL`, `QDRANT_API_KEY`
- Optional `CROSS_ENCODER_MODEL` (default `cross-encoder/ms-marco-MiniLM-L-6-v2`) for eval rerank; first run downloads weights. Chat retrieval does not use this.

## Resume bullet

Built an evaluation framework for benchmarking multiple RAG strategies (BM25, dense, hybrid, RAG-Fusion) across text-only and multimodal retrieval using synthetic golden QA datasets and DeepEval-based answer faithfulness/relevancy metrics.
