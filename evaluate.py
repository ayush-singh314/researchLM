#!/usr/bin/env python
"""CLI entry point for the RAG evaluation framework."""

from __future__ import annotations

import os

# DeepEval timeout defaults — only set when not already provided externally.
os.environ.setdefault("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE", "120")
os.environ.setdefault("DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE", "300")
os.environ.setdefault("DEEPEVAL_TASK_GATHER_BUFFER_SECONDS_OVERRIDE", "30")
os.environ.setdefault("DEEPEVAL_RETRY_MAX_ATTEMPTS", "2")

import argparse
import logging
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

from evaluation.dataset_manager import list_datasets
from evaluation.experiment_runner import (
    MODALITY_MULTIMODAL,
    MODALITY_TEXT_ONLY,
    ExperimentConfig,
    run_experiment,
)
from evaluation.strategies import STRATEGY_REGISTRY

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

DEEPEVAL_TIMEOUT_ENV_KEYS = [
    "DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE",
    "DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE",
    "DEEPEVAL_TASK_GATHER_BUFFER_SECONDS_OVERRIDE",
    "DEEPEVAL_RETRY_MAX_ATTEMPTS",
]


def _print_runtime_config() -> None:
    max_concurrent = os.environ.get("EVAL_MAX_CONCURRENT", "1")
    throttle = os.environ.get("EVAL_THROTTLE_VALUE", "5")
    max_cases = os.environ.get("EVAL_MAX_TEST_CASES", "(all)")
    print("\n=== Evaluation runtime config ===")
    print(f"EVAL_MAX_CONCURRENT={max_concurrent}")
    print(f"EVAL_THROTTLE_VALUE={throttle}")
    print(f"EVAL_MAX_TEST_CASES={max_cases}")
    print(f"RETRIEVAL_STRATEGY={os.environ.get('RETRIEVAL_STRATEGY', 'dense')} (app only)")
    for key in DEEPEVAL_TIMEOUT_ENV_KEYS:
        print(f"{key}={os.environ.get(key)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark RAG retrieval strategies on golden QA datasets.",
    )
    parser.add_argument(
        "--dataset",
        help="Dataset name under evaluation/datasets/<name>/",
    )
    parser.add_argument(
        "--strategy",
        default="dense",
        choices=list(STRATEGY_REGISTRY.keys()),
        help="Retrieval strategy to evaluate",
    )
    parser.add_argument(
        "--modality",
        default=MODALITY_MULTIMODAL,
        choices=[MODALITY_TEXT_ONLY, MODALITY_MULTIMODAL],
        help="Ingestion/retrieval modality mode",
    )
    parser.add_argument(
        "--embedding-model",
        default="text-embedding-3-small",
        help="OpenAI embedding model for dense/hybrid indexing",
    )
    parser.add_argument(
        "--output-dir",
        default="evaluation/runs",
        type=Path,
        help="Directory for per-run JSON artifacts",
    )
    parser.add_argument(
        "--regenerate-goldens",
        action="store_true",
        help="Regenerate synthetic goldens even if cached",
    )
    parser.add_argument(
        "--metric-threshold",
        type=float,
        default=0.7,
        help="DeepEval pass threshold",
    )
    parser.add_argument(
        "--deepeval-model",
        default="gpt-5.4-mini",
        help="Judge model for DeepEval metrics",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Number of chunks to retrieve per question",
    )
    parser.add_argument(
        "--list-datasets",
        action="store_true",
        help="List available datasets and exit",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_datasets:
        datasets = list_datasets()
        if not datasets:
            print("No datasets found under evaluation/datasets/")
        else:
            print("Available datasets:")
            for name in datasets:
                print(f"  - {name}")
        return

    if not args.dataset:
        parser.error("--dataset is required unless --list-datasets is used")

    _print_runtime_config()

    config = ExperimentConfig(
        dataset=args.dataset,
        strategy=args.strategy,
        modality_mode=args.modality,
        embedding_model=args.embedding_model,
        output_dir=args.output_dir,
        regenerate_goldens=args.regenerate_goldens,
        metric_threshold=args.metric_threshold,
        deepeval_model=args.deepeval_model,
        top_k=args.top_k,
    )

    try:
        result = run_experiment(config)
    except Exception as exc:
        print(f"\nEvaluation failed: {exc}")
        error_path = Path("eval_results_error.json")
        if error_path.exists():
            print(f"Partial debug details saved to {error_path.resolve()}")
        raise SystemExit(1) from exc

    summary = result["summary"]
    print("\n=== Experiment complete ===")
    print(f"Dataset:   {result['dataset']}")
    print(f"Strategy:  {result['strategy']}")
    print(f"Modality:  {result['modality_mode']}")
    print(f"Embedding: {result['embedding_model']}")
    print(f"Pass rate: {summary.get('pass_rate', 0.0):.2%}")
    print(f"JSON:      {result['artifacts']['json']}")
    print(f"CSV:       {result['artifacts']['summary_csv']}")
    if result.get("eval_results_path"):
        print(f"Results:   {result['eval_results_path']}")


if __name__ == "__main__":
    main()
