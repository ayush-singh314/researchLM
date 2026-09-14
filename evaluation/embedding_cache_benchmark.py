#!/usr/bin/env python
"""Benchmark CacheBackedEmbeddings (blake2b) without writing to Redis Cloud.

Uses a throwaway LocalFileStore so production Redis and ./embedding_cache/ are
not written. Eval indexing still uses ./embedding_cache/eval_<model>/.

Inspected production path (chat):
- Ingest: add_paper -> QdrantVectorStore.add_documents -> embeddings.embed_documents
- Query: similarity_search -> embeddings.embed_query (query_embedding_cache=True)
- Key: blake2b(utf-8 text) hex, prefixed with model namespace
- Production store: Redis Cloud RedisStore (REDIS_URL)
- Model: text-embedding-3-small
- API: OpenAIEmbeddings -> self.client.create (langchain_openai embeddings)

Run from repo root:
    python evaluation/embedding_cache_benchmark.py --requests 50
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# Same construction as backend/rag/vector_store.py
PROD_MODEL = "text-embedding-3-small"
PROD_KEY_ENCODER = "blake2b"

GOLDENS_PATH = ROOT / "evaluation" / "datasets" / "openclaw" / "goldens.json"


@dataclass
class LatencyBag:
    samples_ms: list[float] = field(default_factory=list)

    def add(self, seconds: float) -> None:
        self.samples_ms.append(seconds * 1000.0)

    def avg(self) -> float | None:
        return statistics.mean(self.samples_ms) if self.samples_ms else None

    def percentile(self, p: float, *, min_n: int) -> float | None:
        if len(self.samples_ms) < min_n:
            return None
        ordered = sorted(self.samples_ms)
        if not ordered:
            return None
        k = (len(ordered) - 1) * (p / 100.0)
        lo = int(k)
        hi = min(lo + 1, len(ordered) - 1)
        frac = k - lo
        return ordered[lo] * (1 - frac) + ordered[hi] * frac


@dataclass
class RunStats:
    label: str
    n_requests: int
    api_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    all_ms: LatencyBag = field(default_factory=LatencyBag)
    hit_ms: LatencyBag = field(default_factory=LatencyBag)
    miss_ms: LatencyBag = field(default_factory=LatencyBag)
    wall_s: float = 0.0


def _pct(num: float, den: float) -> float | None:
    if den <= 0:
        return None
    return 100.0 * num / den


def _fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f} ms"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _default_pool() -> list[str]:
    """Realistic query/chunk strings: OpenClaw goldens + short paper-like chunks."""
    pool: list[str] = []
    if GOLDENS_PATH.is_file():
        try:
            goldens = json.loads(GOLDENS_PATH.read_text(encoding="utf-8"))
            for item in goldens:
                inp = (item.get("input") or "").strip()
                if inp:
                    pool.append(inp)
        except (OSError, json.JSONDecodeError):
            pass
    pool.extend(
        [
            "Transformer self-attention with residual connections and layer normalization.",
            "Moltbot is a self-hosted agentic assistant with multi-channel messaging.",
            "Hybrid retrieval fuses dense cosine neighbors with BM25 via reciprocal rank fusion.",
            "Qdrant collections are isolated per research session using papeer_ plus the session id.",
            "Cross-encoder ms-marco-MiniLM reranks fused candidates before the final top-k context.",
            "PDF figures are extracted with PyMuPDF xrefs then captioned by GPT-4o vision.",
            "LangGraph PostgresSaver stores chat thread state keyed by session UUID.",
            "Neon Auth JWTs are verified with JWKS; user_id is the token subject claim.",
        ]
    )
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for text in pool:
        if text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def build_sequence(
    n: int,
    *,
    seed: int,
    repeat_fraction: float,
) -> list[str]:
    """Fixed sequence: unique texts plus repeats so the cache can hit."""
    rng = random.Random(seed)
    pool = _default_pool()
    if not pool:
        pool = [f"synthetic embedding benchmark text {i}" for i in range(max(8, n))]

    n_unique = max(1, min(len(pool), max(1, int(round(n * (1.0 - repeat_fraction))))))
    n_unique = min(n_unique, n)
    bases = pool[:n_unique]
    while len(bases) < n_unique:
        bases.append(f"synthetic unique chunk {len(bases)}")

    seq: list[str] = []
    # First pass: each unique once (cold misses)
    seq.extend(bases)
    # Remaining: sample from bases (hits after cache is warm)
    while len(seq) < n:
        seq.append(rng.choice(bases))
    return seq[:n]


class CountingOpenAIEmbeddings:
    """OpenAIEmbeddings with client.create wrapped so we count real HTTP embedding calls."""

    def __init__(self, model: str):
        from langchain_openai import OpenAIEmbeddings

        self.inner = OpenAIEmbeddings(model=model)
        self.api_calls = 0
        client = self.inner.client
        original = client.create

        def create_and_count(*args, **kwargs):
            self.api_calls += 1
            return original(*args, **kwargs)

        client.create = create_and_count  # type: ignore[method-assign]

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents(texts)


def _make_cached_embedder(underlying, cache_dir: Path):
    """Same CacheBackedEmbeddings settings as production, isolated temp directory."""
    from langchain_classic.embeddings import CacheBackedEmbeddings
    from langchain_classic.storage import LocalFileStore

    store = LocalFileStore(str(cache_dir))
    return CacheBackedEmbeddings.from_bytes_store(
        underlying.inner,
        store,
        namespace=underlying.inner.model,
        query_embedding_cache=True,
        key_encoder=PROD_KEY_ENCODER,
    )


def run_sequence(
    texts: list[str],
    *,
    use_cache: bool,
    model: str,
    cache_dir: Path | None,
) -> RunStats:
    label = "With Cache" if use_cache else "No Cache"
    stats = RunStats(label=label, n_requests=len(texts))
    underlying = CountingOpenAIEmbeddings(model)
    embedder = (
        _make_cached_embedder(underlying, cache_dir)
        if use_cache and cache_dir is not None
        else underlying
    )

    wall0 = time.perf_counter()
    for text in texts:
        api_before = underlying.api_calls
        t0 = time.perf_counter()
        # Production query path is embed_query; one string = one logical request.
        embedder.embed_query(text)
        dt = time.perf_counter() - t0
        stats.all_ms.add(dt)
        api_delta = underlying.api_calls - api_before
        if use_cache:
            if api_delta == 0:
                stats.cache_hits += 1
                stats.hit_ms.add(dt)
            else:
                stats.cache_misses += 1
                stats.miss_ms.add(dt)
        else:
            stats.miss_ms.add(dt)
    stats.wall_s = time.perf_counter() - wall0
    stats.api_calls = underlying.api_calls
    return stats


def _print_hit_breakdown(stats: RunStats) -> None:
    print(f"\n[{stats.label}] embedding latency only (not full RAG / LangGraph)")
    print(f"  HIT  n={len(stats.hit_ms.samples_ms):4d}  "
          f"avg={_fmt_ms(stats.hit_ms.avg())}  "
          f"P50={_fmt_ms(stats.hit_ms.percentile(50, min_n=1))}  "
          f"P95={_fmt_ms(stats.hit_ms.percentile(95, min_n=5))}  "
          f"P99={_fmt_ms(stats.hit_ms.percentile(99, min_n=20))}")
    print(f"  MISS n={len(stats.miss_ms.samples_ms):4d}  "
          f"avg={_fmt_ms(stats.miss_ms.avg())}  "
          f"P50={_fmt_ms(stats.miss_ms.percentile(50, min_n=1))}  "
          f"P95={_fmt_ms(stats.miss_ms.percentile(95, min_n=5))}  "
          f"P99={_fmt_ms(stats.miss_ms.percentile(99, min_n=20))}")


def print_report(
    no_cache: RunStats,
    with_cache: RunStats,
) -> None:
    n = no_cache.n_requests
    avoided = no_cache.api_calls - with_cache.api_calls
    api_reduction = _pct(avoided, no_cache.api_calls)
    wall_reduction = _pct(no_cache.wall_s - with_cache.wall_s, no_cache.wall_s)
    hit_rate = _pct(with_cache.cache_hits, with_cache.n_requests)

    def row(name: str, a, b) -> None:
        print(f"{name:<22} {a:>16} {b:>16}")

    print()
    print("=" * 56)
    print("Embedding Cache Benchmark")
    print("=" * 56)
    print()
    print(f"Total requests:             {n}")
    print("Scope:                      OpenAI embedding embed_query only")
    print("                            (not LangGraph / Qdrant / Groq RAG)")
    print()
    print(f"{'':22} {'No Cache':>16} {'With Cache':>16}")
    print("-" * 56)
    row("API calls", no_cache.api_calls, with_cache.api_calls)
    row("Cache hits", no_cache.cache_hits, with_cache.cache_hits)
    row("Cache misses", no_cache.cache_misses, with_cache.cache_misses)
    row("Cache hit rate", _fmt_pct(_pct(no_cache.cache_hits, n)), _fmt_pct(hit_rate))
    row("Total latency", f"{no_cache.wall_s * 1000:.2f} ms", f"{with_cache.wall_s * 1000:.2f} ms")
    row("Average latency", _fmt_ms(no_cache.all_ms.avg()), _fmt_ms(with_cache.all_ms.avg()))
    row("P50", _fmt_ms(no_cache.all_ms.percentile(50, min_n=1)), _fmt_ms(with_cache.all_ms.percentile(50, min_n=1)))
    row("P95", _fmt_ms(no_cache.all_ms.percentile(95, min_n=5)), _fmt_ms(with_cache.all_ms.percentile(95, min_n=5)))
    row("P99", _fmt_ms(no_cache.all_ms.percentile(99, min_n=20)), _fmt_ms(with_cache.all_ms.percentile(99, min_n=20)))
    print("-" * 56)
    print(f"API calls avoided:       {avoided}")
    print(f"API call reduction:      {_fmt_pct(api_reduction)}")
    print(f"Embedding latency reduction (wall): {_fmt_pct(wall_reduction)}")
    print()
    print("Measured API calls wrap OpenAIEmbeddings.client.create (lowest-level sync call).")
    print("Cache hits/misses: with-cache only; a hit is embed_query with zero client.create.")
    _print_hit_breakdown(no_cache)
    _print_hit_breakdown(with_cache)
    print()
    if n:
        print("How to read (from this run, not examples):")
        print(
            f"  Cache hit rate = {with_cache.cache_hits} / {n} = {_fmt_pct(hit_rate)}"
        )
        print(
            f"  API calls avoided = {no_cache.api_calls} - {with_cache.api_calls} = {avoided}"
        )
        print(
            f"  API call reduction = {avoided} / {no_cache.api_calls} = {_fmt_pct(api_reduction)}"
            if no_cache.api_calls
            else "  API call reduction = n/a"
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--requests",
        "--queries",
        dest="n_requests",
        type=int,
        default=50,
        help="Total embedding requests (same sequence for both modes)",
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--repeat-fraction", type=float, default=0.4, help="Share of requests that are repeats")
    p.add_argument("--model", default=PROD_MODEL, help="Must match production unless you intend otherwise")
    return p


def main() -> None:
    args = build_parser().parse_args()
    seq = build_sequence(
        args.n_requests,
        seed=args.seed,
        repeat_fraction=args.repeat_fraction,
    )
    unique_n = len(set(seq))
    print(f"Model: {args.model}  requests: {len(seq)}  unique texts: {unique_n}  seed: {args.seed}")
    print("Cache: CacheBackedEmbeddings + temp LocalFileStore + blake2b (isolated; production uses Redis)")

    import os

    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise SystemExit("OPENAI_API_KEY is not set")

    print("\nRunning NO CACHE (raw OpenAIEmbeddings, every request hits the API)...")
    no_cache = run_sequence(seq, use_cache=False, model=args.model, cache_dir=None)

    print("Running WITH CACHE (isolated temp LocalFileStore, same CacheBackedEmbeddings API)...")
    with tempfile.TemporaryDirectory(prefix="researchlm_embed_cache_bench_") as tmp:
        with_cache = run_sequence(
            seq,
            use_cache=True,
            model=args.model,
            cache_dir=Path(tmp),
        )

    print_report(no_cache, with_cache)


if __name__ == "__main__":
    main()
