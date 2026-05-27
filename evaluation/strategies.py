"""Retrieval strategy definitions and factory."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from langchain_core.documents import Document

from evaluation.retrieval_pipeline import postprocess_retrieved
from evaluation.vector_index import EvalVectorIndex


class StrategyName(str, Enum):
    KEYWORD = "keyword"
    BM25 = "bm25"
    DENSE = "dense"
    HYBRID = "hybrid"
    RAG_FUSION = "rag_fusion"


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration for a named retrieval strategy."""

    name: StrategyName
    top_k: int = 4
    description: str = ""

    @property
    def is_implemented(self) -> bool:
        return self.name != StrategyName.RAG_FUSION


STRATEGY_REGISTRY: dict[str, StrategyConfig] = {
    StrategyName.KEYWORD.value: StrategyConfig(
        name=StrategyName.KEYWORD,
        description="Token overlap keyword search over indexed chunks.",
    ),
    StrategyName.BM25.value: StrategyConfig(
        name=StrategyName.BM25,
        description="BM25 lexical retrieval over indexed chunks.",
    ),
    StrategyName.DENSE.value: StrategyConfig(
        name=StrategyName.DENSE,
        description="Dense vector similarity via Qdrant (production default).",
    ),
    StrategyName.HYBRID.value: StrategyConfig(
        name=StrategyName.HYBRID,
        description="Reciprocal-rank fusion of BM25 and dense retrieval.",
    ),
    StrategyName.RAG_FUSION.value: StrategyConfig(
        name=StrategyName.RAG_FUSION,
        description="Multi-query RAG-Fusion hook (stub — falls back to dense).",
    ),
}


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int | None = None) -> list[Document]:
        ...


class StrategyRetriever:
    """Dispatch retrieval to the configured strategy implementation."""

    def __init__(
        self,
        index: EvalVectorIndex,
        strategy: StrategyName,
        top_k: int = 4,
        use_rerank: bool = True,
    ):
        self.index = index
        self.strategy = strategy
        self.top_k = top_k
        self.use_rerank = use_rerank

    def retrieve(self, query: str, top_k: int | None = None) -> list[Document]:
        k = top_k or self.top_k
        fetch_k = max(k * 3, k + 10) if self.use_rerank else k
        if self.strategy == StrategyName.KEYWORD:
            docs = self.index.keyword_search(query, k=fetch_k)
        elif self.strategy == StrategyName.BM25:
            docs = self.index.bm25_search(query, k=fetch_k)
        elif self.strategy == StrategyName.DENSE:
            docs = self.index.dense_search(query, k=fetch_k)
        elif self.strategy == StrategyName.HYBRID:
            docs = self.index.hybrid_search(query, k=fetch_k)
        elif self.strategy == StrategyName.RAG_FUSION:
            docs = self.index.dense_search(query, k=fetch_k)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

        if self.use_rerank:
            return postprocess_retrieved(query, docs, top_k=k)
        return docs[:k]


def get_strategy_config(name: str) -> StrategyConfig:
    key = name.lower().strip()
    if key not in STRATEGY_REGISTRY:
        supported = ", ".join(STRATEGY_REGISTRY)
        raise ValueError(f"Unknown strategy '{name}'. Supported: {supported}")
    return STRATEGY_REGISTRY[key]


def create_retriever(
    index: EvalVectorIndex,
    strategy_name: str,
    top_k: int = 4,
    *,
    use_rerank: bool = True,
) -> StrategyRetriever:
    config = get_strategy_config(strategy_name)
    return StrategyRetriever(
        index=index,
        strategy=config.name,
        top_k=top_k,
        use_rerank=use_rerank,
    )
