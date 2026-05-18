"""DeepEval metric builders and lightweight retrieval metrics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from langchain_core.documents import Document

from evaluation.dataset_manager import GoldenItem

_TOKEN_RE = re.compile(r"\w+")


def build_deepeval_metrics(*, threshold: float = 0.7, model: str = "gpt-5.4-mini"):
    return [
        ContextualPrecisionMetric(threshold=threshold, model=model),
        ContextualRecallMetric(threshold=threshold, model=model),
        ContextualRelevancyMetric(threshold=threshold, model=model),
        AnswerRelevancyMetric(threshold=threshold, model=model),
        FaithfulnessMetric(threshold=threshold, model=model),
    ]


def _normalize_tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def _overlap_ratio(expected: str, context: str) -> float:
    expected_tokens = _normalize_tokens(expected)
    if not expected_tokens:
        return 0.0
    context_tokens = _normalize_tokens(context)
    return len(expected_tokens & context_tokens) / len(expected_tokens)


@dataclass
class RetrievalMetrics:
    retrieved_context_count: int = 0
    top_k_hit: bool = False
    average_context_length: float = 0.0
    modality_hit_rate: float | None = None
    retrieved_modalities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "retrieved_context_count": self.retrieved_context_count,
            "top_k_hit": self.top_k_hit,
            "average_context_length": self.average_context_length,
            "modality_hit_rate": self.modality_hit_rate,
            "retrieved_modalities": self.retrieved_modalities,
        }


def compute_retrieval_metrics(
    golden: GoldenItem,
    retrieved_docs: list[Document],
    *,
    top_k: int = 4,
) -> RetrievalMetrics:
    """Compute lightweight retrieval metrics from retrieved documents."""
    contexts = [doc.page_content for doc in retrieved_docs]
    count = len(contexts)
    avg_len = sum(len(c) for c in contexts) / count if count else 0.0

    expected = golden.expected_output
    hit = any(_overlap_ratio(expected, ctx) >= 0.08 for ctx in contexts[:top_k])

    modalities = [doc.metadata.get("modality", "text") for doc in retrieved_docs]
    modality_hit_rate = None
    if golden.category in ("figure", "table", "cross_modal"):
        image_hits = sum(1 for m in modalities if m == "image")
        modality_hit_rate = image_hits / count if count else 0.0

    return RetrievalMetrics(
        retrieved_context_count=count,
        top_k_hit=hit,
        average_context_length=avg_len,
        modality_hit_rate=modality_hit_rate,
        retrieved_modalities=modalities,
    )
