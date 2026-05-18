"""Run controlled RAG evaluation experiments across strategies and modalities."""

from __future__ import annotations

import json
import logging
import os
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# DeepEval timeout defaults (set before deepeval import; do not override existing values).
os.environ.setdefault("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE", "120")
os.environ.setdefault("DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE", "300")
os.environ.setdefault("DEEPEVAL_TASK_GATHER_BUFFER_SECONDS_OVERRIDE", "30")
os.environ.setdefault("DEEPEVAL_RETRY_MAX_ATTEMPTS", "2")

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from deepeval import evaluate
from deepeval.evaluate import AsyncConfig
from deepeval.test_case import LLMTestCase

from backend.paper_loader import load_document
from backend.retrieval_format import format_retrieved_context
from evaluation.dataset_manager import (
    DatasetInfo,
    GoldenItem,
    bootstrap_openclaw_dataset,
    ensure_goldens,
    load_dataset,
)
from evaluation.metrics import build_deepeval_metrics, compute_retrieval_metrics
from evaluation.report_writer import append_summary_csv, write_run_json
from evaluation.strategies import create_retriever, get_strategy_config
from evaluation.vector_index import EvalVectorIndex

load_dotenv()
logger = logging.getLogger(__name__)

MODALITY_TEXT_ONLY = "text_only"
MODALITY_MULTIMODAL = "multimodal"
SUPPORTED_MODALITIES = {MODALITY_TEXT_ONLY, MODALITY_MULTIMODAL}


@dataclass
class ExperimentConfig:
    dataset: str
    strategy: str = "dense"
    modality_mode: str = MODALITY_MULTIMODAL
    embedding_model: str = "text-embedding-3-small"
    output_dir: Path = Path("evaluation/runs")
    regenerate_goldens: bool = False
    metric_threshold: float = 0.7
    deepeval_model: str = "gpt-5.4-mini"
    top_k: int = 4
    max_contexts: int = 5
    goldens_per_context: int = 2


@dataclass
class QuestionResult:
    input: str
    expected_output: str
    actual_output: str
    category: str
    retrieval_context: list[str]
    retrieval_metrics: dict
    success: bool
    metrics: list[dict] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _limit_goldens(goldens: list[GoldenItem]) -> list[GoldenItem]:
    """Optionally limit goldens for debugging via EVAL_MAX_TEST_CASES."""
    raw = os.environ.get("EVAL_MAX_TEST_CASES")
    if raw is None or raw.strip() == "":
        return goldens
    limit = int(raw)
    return goldens[:limit]


def _async_config() -> AsyncConfig:
    return AsyncConfig(
        max_concurrent=_env_int("EVAL_MAX_CONCURRENT", 1),
        throttle_value=_env_int("EVAL_THROTTLE_VALUE", 5),
    )


def _print_pre_eval_diagnostics(
    *,
    goldens_loaded: int,
    test_cases_count: int,
    async_config: AsyncConfig,
) -> None:
    print("\n=== Pre-evaluation diagnostics ===")
    print(f"Goldens loaded:        {goldens_loaded}")
    print(f"Test cases to evaluate:{test_cases_count}")
    print(f"max_concurrent:        {async_config.max_concurrent}")
    print(f"throttle_value:        {async_config.throttle_value}")
    for key in (
        "DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE",
        "DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE",
        "DEEPEVAL_TASK_GATHER_BUFFER_SECONDS_OVERRIDE",
        "DEEPEVAL_RETRY_MAX_ATTEMPTS",
    ):
        print(f"{key}={os.environ.get(key)}")


def _save_eval_error_debug(
    exc: BaseException,
    *,
    test_cases: list[LLMTestCase],
    goldens_loaded: int,
) -> Path:
    error_path = Path("eval_results_error.json")
    payload = {
        "error": str(exc),
        "traceback": traceback.format_exc(),
        "goldens_loaded": goldens_loaded,
        "prepared_test_cases": len(test_cases),
        "test_case_inputs": [tc.input for tc in test_cases],
    }
    error_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.error("DeepEval failed; debug info saved to %s", error_path.resolve())
    return error_path


def _write_eval_results_json(question_results: list[QuestionResult]) -> Path:
    """Write legacy eval_results.json for successful runs."""
    results_path = Path("eval_results.json")
    summary = [
        {
            "input": row.input,
            "actual_output": row.actual_output,
            "success": row.success,
            "metrics": row.metrics,
        }
        for row in question_results
    ]
    results_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return results_path


def _run_deepeval_with_guard(
    test_cases: list[LLMTestCase],
    metrics: list,
    async_config: AsyncConfig,
    *,
    goldens_loaded: int,
):
    try:
        return evaluate(test_cases, metrics, async_config=async_config)
    except Exception as exc:
        _save_eval_error_debug(exc, test_cases=test_cases, goldens_loaded=goldens_loaded)
        raise RuntimeError(
            f"DeepEval evaluation failed after preparing {len(test_cases)} test case(s). "
            f"See eval_results_error.json for details."
        ) from exc


def _load_corpus(dataset: DatasetInfo, modality_mode: str) -> list[Document]:
    include_images = modality_mode == MODALITY_MULTIMODAL
    all_docs: list[Document] = []
    for source_path in dataset.source_paths:
        docs = load_document(
            str(source_path),
            paper_title=source_path.stem,
            include_images=include_images,
        )
        if modality_mode == MODALITY_TEXT_ONLY:
            docs = [d for d in docs if d.metadata.get("modality", "text") == "text"]
        all_docs.extend(docs)
    return all_docs


def _generate_answer(query: str, retrieved_docs: list[Document]) -> str:
    if not retrieved_docs:
        return "I don't know the answer."
    context = format_retrieved_context(retrieved_docs)
    prompt = (
        "Answer the question using ONLY the evidence below from uploaded research papers.\n"
        "Evidence may include text excerpts and figure captions. "
        "Do not invent details beyond the evidence.\n\n"
        f"{context}\n\nQuestion: {query}"
    )
    llm = ChatGroq(model="llama-3.3-70b-versatile")
    return llm.invoke([{"role": "user", "content": prompt}]).content


def _aggregate_deepeval_results(test_results: list, retrieval_rows: list[dict]) -> dict:
    metric_scores: dict[str, list[float]] = {}
    passed = 0
    for test_result, retrieval_row in zip(test_results, retrieval_rows, strict=False):
        if test_result.success:
            passed += 1
        for metric in test_result.metrics_data:
            if metric.score is not None:
                metric_scores.setdefault(metric.name, []).append(metric.score)

    def avg(name: str) -> float | None:
        values = metric_scores.get(name, [])
        return sum(values) / len(values) if values else None

    total = len(test_results)
    return {
        "num_questions": total,
        "pass_rate": passed / total if total else 0.0,
        "avg_contextual_precision": avg("Contextual Precision"),
        "avg_contextual_recall": avg("Contextual Recall"),
        "avg_contextual_relevancy": avg("Contextual Relevancy"),
        "avg_answer_relevancy": avg("Answer Relevancy"),
        "avg_faithfulness": avg("Faithfulness"),
        "avg_top_k_hit": (
            sum(1 for r in retrieval_rows if r.get("top_k_hit")) / len(retrieval_rows)
            if retrieval_rows
            else 0.0
        ),
        "avg_retrieved_context_count": (
            sum(r.get("retrieved_context_count", 0) for r in retrieval_rows) / len(retrieval_rows)
            if retrieval_rows
            else 0.0
        ),
    }


def _aggregate_by_category(question_results: list[QuestionResult]) -> dict:
    buckets: dict[str, list[QuestionResult]] = {}
    for result in question_results:
        buckets.setdefault(result.category, []).append(result)

    by_category = {}
    for category, rows in buckets.items():
        passed = sum(1 for r in rows if r.success)
        by_category[category] = {
            "count": len(rows),
            "pass_rate": passed / len(rows) if rows else 0.0,
        }
    return by_category


def run_experiment(config: ExperimentConfig) -> dict:
    """Execute one evaluation experiment and persist run artifacts."""
    if config.modality_mode not in SUPPORTED_MODALITIES:
        raise ValueError(f"modality_mode must be one of {SUPPORTED_MODALITIES}")

    strategy_cfg = get_strategy_config(config.strategy)
    if not strategy_cfg.is_implemented and config.strategy == "rag_fusion":
        logger.warning("rag_fusion is stubbed; using dense retrieval fallback.")

    bootstrap_openclaw_dataset()
    dataset = load_dataset(config.dataset)
    goldens = ensure_goldens(
        dataset,
        regenerate=config.regenerate_goldens,
        max_contexts=config.max_contexts,
        goldens_per_context=config.goldens_per_context,
    )
    goldens_loaded = len(goldens)
    goldens = _limit_goldens(goldens)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"eval_{config.dataset}_{config.strategy}_{uuid4().hex[:8]}"

    logger.info(
        "Starting experiment run_id=%s dataset=%s strategy=%s modality=%s embedding=%s",
        run_id,
        config.dataset,
        config.strategy,
        config.modality_mode,
        config.embedding_model,
    )

    corpus = _load_corpus(dataset, config.modality_mode)
    index = EvalVectorIndex(session_id=session_id, embedding_model=config.embedding_model)
    index.index_documents(corpus)
    retriever = create_retriever(index, config.strategy, top_k=config.top_k)

    test_cases: list[LLMTestCase] = []
    question_results: list[QuestionResult] = []
    retrieval_metric_rows: list[dict] = []

    for golden in goldens:
        query = golden.input + " as per the report in knowledge base"
        retrieved_docs = retriever.retrieve(query, top_k=config.top_k)
        retrieval_metrics = compute_retrieval_metrics(
            golden, retrieved_docs, top_k=config.top_k
        )
        retrieval_metric_rows.append(retrieval_metrics.to_dict())

        answer = _generate_answer(golden.input, retrieved_docs)
        retrieval_context = [doc.page_content for doc in retrieved_docs]

        test_cases.append(
            LLMTestCase(
                input=golden.input,
                actual_output=answer,
                expected_output=golden.expected_output,
                retrieval_context=retrieval_context,
            )
        )
        question_results.append(
            QuestionResult(
                input=golden.input,
                expected_output=golden.expected_output,
                actual_output=answer,
                category=golden.category,
                retrieval_context=retrieval_context,
                retrieval_metrics=retrieval_metrics.to_dict(),
                success=False,
            )
        )

    deepeval_metrics = build_deepeval_metrics(
        threshold=config.metric_threshold,
        model=config.deepeval_model,
    )
    async_config = _async_config()
    _print_pre_eval_diagnostics(
        goldens_loaded=goldens_loaded,
        test_cases_count=len(test_cases),
        async_config=async_config,
    )
    eval_results = _run_deepeval_with_guard(
        test_cases,
        deepeval_metrics,
        async_config,
        goldens_loaded=goldens_loaded,
    )

    for test_result, question_row in zip(eval_results.test_results, question_results, strict=False):
        question_row.success = test_result.success
        question_row.metrics = [
            {
                "name": m.name,
                "score": m.score,
                "passed": m.success,
                "reason": m.reason,
            }
            for m in test_result.metrics_data
        ]

    summary = _aggregate_deepeval_results(eval_results.test_results, retrieval_metric_rows)
    summary["by_category"] = _aggregate_by_category(question_results)

    run_payload = {
        "run_id": run_id,
        "timestamp": _utc_now(),
        "dataset": config.dataset,
        "strategy": config.strategy,
        "strategy_description": strategy_cfg.description,
        "modality_mode": config.modality_mode,
        "embedding_model": config.embedding_model,
        "metric_threshold": config.metric_threshold,
        "deepeval_model": config.deepeval_model,
        "top_k": config.top_k,
        "session_id": session_id,
        "summary": summary,
        "per_question": [
            {
                "input": q.input,
                "expected_output": q.expected_output,
                "actual_output": q.actual_output,
                "category": q.category,
                "success": q.success,
                "retrieval_metrics": q.retrieval_metrics,
                "metrics": q.metrics,
            }
            for q in question_results
        ],
    }

    json_path = write_run_json(run_payload, output_dir=config.output_dir)
    csv_path = append_summary_csv(run_payload)
    eval_results_path = _write_eval_results_json(question_results)
    logger.info("Run saved to %s and %s", json_path, csv_path)
    print(f"\nResults saved to {eval_results_path.resolve()}")
    print(f"Run artifact:  {json_path.resolve()}")
    print(f"Summary CSV:   {csv_path.resolve()}")

    run_payload["artifacts"] = {"json": str(json_path), "summary_csv": str(csv_path)}
    run_payload["eval_results_path"] = str(eval_results_path.resolve())
    return run_payload
