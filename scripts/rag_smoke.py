#!/usr/bin/env python
"""
End-to-end validation script for the ResearchLM RAG pipeline.

Usage (from repository root):
    python scripts/rag_smoke.py
    python scripts/rag_smoke.py --query "What optimizer does the model use?"
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_groq import ChatGroq

from backend.rag.chunking import chunk_research_paper_pages
from backend.rag.format import format_retrieved_context
from backend.rag.vector_store import add_paper, get_collection_name, qdrant_client, search

load_dotenv()

logger = logging.getLogger("rag_e2e_test")

PAPER_TITLE = "Synthetic Neural Architecture Survey (E2E Test)"
DEFAULT_QUERY = "What learning rate schedule does the synthetic model use during training?"
MIN_WORDS = 1000
MIN_CHUNKS = 2
RETRIEVAL_K = 4


def _build_dummy_document() -> tuple[Document, int]:
    """Build a research-paper-like document with 1000+ words across multiple sections."""
    sections = [
        (
            "Abstract",
            "We present a comprehensive survey of synthetic neural architectures designed for "
            "long-context language modeling under constrained compute budgets. Our study evaluates "
            "stacked transformer blocks with grouped-query attention, rotary positional embeddings, "
            "and mixture-of-experts routing across pretraining and fine-tuning regimes. Experiments "
            "on synthetic benchmarks demonstrate that careful normalization placement, depth scaling, "
            "and learning-rate warmup jointly determine convergence stability. We report perplexity, "
            "downstream accuracy, and retrieval-augmented generation quality when models are paired "
            "with dense and hybrid retrievers. The results suggest that mid-sized models with "
            "efficient attention kernels remain competitive when paired with high-quality document "
            "chunking and section-aware indexing strategies.",
        ),
        (
            "1 Introduction",
            "Retrieval-augmented generation has become a standard approach for grounding large "
            "language models in domain-specific corpora. However, production systems must validate "
            "each pipeline stage independently: ingestion, chunking, embedding, indexing, retrieval, "
            "and answer synthesis. Failures often appear late in the workflow even when earlier "
            "components appear healthy. This synthetic paper describes a fictional architecture "
            "named SynArch-7B so that automated tests can assert end-to-end behavior without "
            "depending on external PDF files. SynArch-7B uses 32 transformer layers, 4096 hidden "
            "units, and 32 attention heads with grouped-query attention reducing key-value head count "
            "to eight. The model is pretrained on 1.2 trillion tokens drawn from books, code, "
            "scientific articles, and curated web snapshots filtered for quality and deduplication.",
        ),
        (
            "2 Model Architecture",
            "The SynArch-7B backbone follows a Pre-LN transformer layout. Each block contains "
            "multi-head self-attention, a gated feed-forward network with SwiGLU activations, and "
            "residual connections wrapped by root-mean-square normalization. Rotary positional "
            "embeddings are applied to queries and keys with base frequency 10,000 and scaling "
            "enabled for contexts up to 32,768 tokens. A sparse mixture-of-experts layer appears "
            "every fourth block, routing each token to two of sixteen experts via a learned gate "
            "with load-balancing auxiliary loss. Token embeddings are tied to the output projection "
            "matrix to reduce parameter count. For inference, key-value caches are stored in bfloat16 "
            "while attention accumulators remain in float32 to limit drift on long sequences.",
        ),
        (
            "3 Training Procedure",
            "Pretraining uses the AdamW optimizer with beta1=0.9, beta2=0.95, and weight decay 0.1 "
            "applied only to matrix parameters excluding biases and normalization scales. The peak "
            "learning rate is 3e-4 with linear warmup over the first 2,000 steps followed by cosine "
            "decay to 3e-5 at 500,000 steps. Global batch size is 4 million tokens with gradient "
            "accumulation across 256 accelerators. Mixed-precision training employs dynamic loss "
            "scaling when float16 is selected; bfloat16 runs without scaling. Checkpoints are saved "
            "every 1,000 steps with exponential moving averages maintained for evaluation-only "
            "weights. Data pipelines perform sequence packing to minimize padding overhead and "
            "shuffle shards with deterministic seeds for reproducibility.",
        ),
        (
            "4 Retrieval Integration",
            "For retrieval-augmented question answering, documents are split using section-aware "
            "chunking that preserves headings such as Abstract, Introduction, and Experiments. "
            "Each chunk receives metadata including title, page number, and modality. Text chunks "
            "and optional figure captions are embedded with text-embedding-3-small and stored in "
            "Qdrant collections scoped per session. At query time the system supports dense vector "
            "search, BM25 lexical retrieval, and reciprocal rank fusion hybrid ranking. Retrieved "
            "passages are formatted with modality labels before being passed to a Groq-hosted "
            "GPT-OSS 120B model instructed to answer only from supplied evidence. When chunks are "
            "irrelevant, the generator must abstain rather than hallucinate unsupported claims.",
        ),
        (
            "5 Experiments",
            "We evaluate SynArch-7B on synthetic reading comprehension, multi-hop reasoning, and "
            "table-to-text generation tasks. Baselines include dense-only retrieval, BM25-only "
            "retrieval, and hybrid fusion with k equal to four by default. Metrics cover contextual "
            "precision, recall, answer relevancy, and faithfulness using LLM-as-judge scoring. "
            "Hybrid retrieval improves recall on keyword-heavy queries by 8.4 points while dense "
            "retrieval remains superior on paraphrased questions. Section-aware chunking reduces "
            "fragmented answers compared to fixed-size splitting with 200-token overlap. Latency "
            "measurements show embedding cache hits decrease end-to-end response time by roughly "
            "35 percent on repeated evaluation runs over the same corpus.",
        ),
        (
            "6 Conclusion",
            "This synthetic survey highlights practical requirements for reliable RAG deployments: "
            "validate chunk counts, confirm vector store connectivity, inspect retrieved evidence, "
            "and only then trust generated answers. SynArch-7B serves as a stand-in corpus for "
            "automated regression tests that exercise ingestion through generation without manual "
            "PDF uploads. Future work will extend the pipeline with reranking models, multimodal "
            "figure indexing, and automated claim verification against live literature search. "
            "Teams should run this script after infrastructure changes to Qdrant, embedding "
            "providers, or LLM endpoints to catch regressions early.",
        ),
    ]

    paragraphs: list[str] = []
    for heading, body in sections:
        paragraphs.append(heading)
        paragraphs.append(body)
        # Pad with an extra explanatory paragraph to guarantee length > 1000 words.
        paragraphs.append(
            f"Additional notes for {heading}: The SynArch-7B evaluation harness logs each "
            "pipeline stage with structured severity levels so operators can distinguish ingestion "
            "failures from retrieval misconfiguration. Instrumentation includes chunk counts, "
            "embedding dimension checks, collection names, retrieved snippet previews, and final "
            "answer length. When any stage fails, downstream stages are skipped to surface the "
            "root cause quickly rather than masking errors inside generic LLM responses."
        )

    full_text = "\n\n".join(paragraphs)
    word_count = len(full_text.split())
    if word_count < MIN_WORDS:
        raise RuntimeError(f"Dummy document too short: {word_count} words (need {MIN_WORDS}+)")

    doc = Document(
        page_content=full_text,
        metadata={
            "title": PAPER_TITLE,
            "source_type": "synthetic_test",
            "page": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return doc, word_count


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _check_prerequisites() -> None:
    import os

    missing = [key for key in ("OPENAI_API_KEY", "GROQ_API_KEY", "QDRANT_URL") if not os.environ.get(key)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        raise SystemExit(1)

    logger.info("Checking Qdrant connectivity at %s", os.environ["QDRANT_URL"])
    try:
        collections = qdrant_client.get_collections()
        logger.info(
            "Qdrant reachable — %d existing collection(s)",
            len(collections.collections),
        )
    except Exception as exc:
        logger.error("Qdrant connectivity check failed: %s", exc)
        logger.warning(
            "Verify QDRANT_URL includes the correct host/port and that QDRANT_API_KEY is valid."
        )
        raise SystemExit(1) from exc


def _stage_document_creation() -> tuple[Document, int]:
    logger.info("=== Stage 1: Document creation ===")
    doc, word_count = _build_dummy_document()
    logger.info("Created synthetic document '%s'", PAPER_TITLE)
    logger.info("Document length: %d words, %d characters", word_count, len(doc.page_content))
    return doc, word_count


def _stage_chunking(source_doc: Document) -> list[Document]:
    logger.info("=== Stage 2: Chunking ===")
    page_docs = [Document(page_content=source_doc.page_content, metadata=dict(source_doc.metadata))]
    chunks = chunk_research_paper_pages(page_docs)
    for doc in chunks:
        doc.metadata["title"] = PAPER_TITLE
        doc.metadata.setdefault("modality", "text")

    logger.info("Produced %d chunk(s) from research chunking profile", len(chunks))
    if len(chunks) < MIN_CHUNKS:
        logger.error("Expected at least %d chunks, got %d", MIN_CHUNKS, len(chunks))
        raise RuntimeError("Chunking produced too few chunks")

    for idx, chunk in enumerate(chunks[:3]):
        preview = chunk.page_content[:120].replace("\n", " ")
        logger.info("Chunk %d preview: %s…", idx + 1, preview)
    if len(chunks) > 3:
        logger.info("… and %d more chunk(s)", len(chunks) - 3)
    return chunks


def _stage_embedding(chunks: list[Document]) -> None:
    logger.info("=== Stage 3: Embedding generation ===")
    from backend.rag.vector_store import embeddings

    sample = chunks[0].page_content[:500]
    logger.info("Embedding sample text (%d chars) with text-embedding-3-small", len(sample))
    vector = embeddings.embed_query(sample)
    logger.info("Generated query embedding — dimension=%d", len(vector))
    if len(vector) != 1536:
        logger.warning("Unexpected embedding dimension: %d (expected 1536)", len(vector))


def _stage_vector_store_insert(chunks: list[Document], session_id: str) -> str:
    logger.info("=== Stage 4: Vector store insertion ===")
    collection = get_collection_name(session_id)
    logger.info("Target collection: %s", collection)
    add_paper(chunks, session_id)
    logger.info("Indexed %d chunk(s) into Qdrant", len(chunks))
    return collection


def _stage_retrieval(session_id: str, query: str) -> list[Document]:
    logger.info("=== Stage 5: Retrieval ===")
    logger.info("Query: %s", query)
    docs = search(query=query, session_id=session_id, k=RETRIEVAL_K, strategy="dense")
    logger.info("Retrieved %d chunk(s)", len(docs))
    if not docs:
        logger.error("Retrieval returned no documents")
        raise RuntimeError("Retrieval returned empty results")

    for idx, doc in enumerate(docs):
        preview = doc.page_content[:100].replace("\n", " ")
        title = doc.metadata.get("title", "unknown")
        logger.info("Hit %d | title=%s | preview=%s…", idx + 1, title, preview)
    return docs


def _stage_llm_response(query: str, retrieved: list[Document]) -> str:
    logger.info("=== Stage 6: LLM response generation ===")
    context = format_retrieved_context(retrieved)
    prompt = (
        "Answer the question using ONLY the evidence below from uploaded research papers.\n"
        "If the evidence is insufficient, say you do not know.\n\n"
        f"{context}\n\nQuestion: {query}"
    )
    llm = ChatGroq(model="openai/gpt-oss-120b")
    logger.info("Invoking Groq LLM (openai/gpt-oss-120b)")
    answer = llm.invoke([{"role": "user", "content": prompt}]).content.strip()
    if not answer:
        logger.error("LLM returned an empty answer")
        raise RuntimeError("LLM returned empty response")

    logger.info("Generated answer (%d chars)", len(answer))
    logger.info("Answer preview: %s", answer[:300] + ("…" if len(answer) > 300 else ""))
    return answer


def _cleanup_collection(collection_name: str, *, keep: bool) -> None:
    if keep:
        logger.info("Skipping cleanup — collection '%s' retained for inspection", collection_name)
        return
    try:
        if qdrant_client.collection_exists(collection_name):
            qdrant_client.delete_collection(collection_name)
            logger.info("Deleted test collection '%s'", collection_name)
    except Exception as exc:
        logger.warning("Could not delete test collection '%s': %s", collection_name, exc)


def run_pipeline(query: str, *, keep_collection: bool, verbose: bool) -> int:
    _configure_logging(verbose)
    logger.info("Starting RAG end-to-end validation")
    _check_prerequisites()

    session_id = f"e2e-test-{uuid.uuid4()}"
    collection_name = get_collection_name(session_id)
    logger.info("Using isolated test session_id=%s", session_id)

    try:
        source_doc, word_count = _stage_document_creation()
        chunks = _stage_chunking(source_doc)
        _stage_embedding(chunks)
        _stage_vector_store_insert(chunks, session_id)
        retrieved = _stage_retrieval(session_id, query)
        answer = _stage_llm_response(query, retrieved)

        logger.info("=== Pipeline summary ===")
        logger.info("Document words : %d", word_count)
        logger.info("Chunks indexed : %d", len(chunks))
        logger.info("Chunks retrieved: %d", len(retrieved))
        logger.info("Answer length  : %d chars", len(answer))
        logger.info("RAG pipeline validation PASSED")
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        logger.error("RAG pipeline validation FAILED: %s", exc, exc_info=verbose)
        return 1
    finally:
        _cleanup_collection(collection_name, keep=keep_collection)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the ResearchLM RAG pipeline end-to-end.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Test question for retrieval + LLM")
    parser.add_argument(
        "--keep-collection",
        action="store_true",
        help="Retain the Qdrant test collection after the run",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")
    args = parser.parse_args()
    sys.exit(run_pipeline(args.query, keep_collection=args.keep_collection, verbose=args.verbose))


if __name__ == "__main__":
    main()
