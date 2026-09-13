"""Post-retrieval dedupe + cross-encoder (eval CLI). Implementation lives in `backend.rag.rerank`."""

from backend.rag.rerank import (  # noqa: F401
    DEFAULT_CROSS_ENCODER,
    deduplicate_documents,
    postprocess_retrieved,
    rerank_documents,
)
