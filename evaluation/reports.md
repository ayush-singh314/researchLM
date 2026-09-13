# Embedding cache benchmark report

This documents how the cache benchmark was measured and the numbers from the first real OpenAI run (`--requests 50`).

## What was measured

ResearchLM already wraps OpenAI `text-embedding-3-small` with LangChain `CacheBackedEmbeddings` (`blake2b` keys, `LocalFileStore`, `query_embedding_cache=True`) in `backend/rag/vector_store.py`. The script `evaluation/embedding_cache_benchmark.py` exercises **that same cache class**, not a toy cache.

Scope is **embedding `embed_query` only**. It does not time LangGraph, Qdrant, BM25, cross-encoder rerank, or Groq generation.

## How the two modes work

The same input sequence is used twice (fixed seed `42`, default repeat fraction `0.4`).

1. **No cache** — raw `OpenAIEmbeddings`. Every request is expected to hit the API.
2. **With cache** — production `CacheBackedEmbeddings.from_bytes_store` on a **temporary** directory. After the run the temp cache is deleted so `./embedding_cache/` is not written.

API calls are counted by wrapping `OpenAIEmbeddings.client.create` (the sync embedding HTTP call). A **cache hit** is an `embed_query` where `client.create` did not run. A **miss** is an `embed_query` where it did.

Latency is `time.perf_counter()` around each `embed_query`. Percentiles: P50 always; P95 if ≥5 samples; P99 if ≥20 samples.

Inputs: OpenClaw golden questions plus short paper-like strings, with repeats so the cache can hit after the first unique texts.

## Command

```bash
python evaluation/embedding_cache_benchmark.py --requests 50
```

Requires `OPENAI_API_KEY`.

## Results (50 requests)

========================================================
Embedding Cache Benchmark
========================================================

Total requests:             50
Scope:                      OpenAI embedding embed_query only
                            (not LangGraph / Qdrant / Groq RAG)

                               No Cache       With Cache
--------------------------------------------------------
API calls                            50               18
Cache hits                            0               32
Cache misses                          0               18
Cache hit rate                    0.00%           64.00%
Total latency               24407.92 ms       8388.89 ms
Average latency               487.98 ms        167.68 ms
P50                           398.77 ms         14.60 ms
P95                           615.80 ms        541.73 ms
P99                          2200.20 ms        693.70 ms
--------------------------------------------------------
API calls avoided:       32
API call reduction:      64.00%
Embedding latency reduction (wall): 65.63%

Measured API calls wrap OpenAIEmbeddings.client.create (lowest-level sync call).
Cache hits/misses: with-cache only; a hit is embed_query with zero client.create.

[No Cache] embedding latency only (not full RAG / LangGraph)
  HIT  n=   0  avg=n/a  P50=n/a  P95=n/a  P99=n/a
  MISS n=  50  avg=487.98 ms  P50=398.77 ms  P95=615.80 ms  P99=2200.20 ms

[With Cache] embedding latency only (not full RAG / LangGraph)
  HIT  n=  32  avg=9.18 ms  P50=2.10 ms  P95=36.89 ms  P99=40.98 ms
  MISS n=  18  avg=449.46 ms  P50=407.37 ms  P95=632.51 ms  P99=n/a

How to read (from this run, not examples):
  Cache hit rate = 32 / 50 = 64.00%
  API calls avoided = 50 - 18 = 32
  API call reduction = 32 / 50 = 64.00%

With-cache P99 for misses is `n/a` because there were only 18 miss samples (P99 needs 20).

## Limitations

- Network jitter affects miss latency; P99 on the no-cache run (2200 ms) shows one slow API call.
- Hit rate depends on how many strings in the 50-request sequence were repeats, not on live user traffic.
- This is not an overall RAG latency improvement.
