"""Persist experiment runs as JSON and append summary CSV rows."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNS_DIR = Path("evaluation/runs")
REPORTS_DIR = Path("evaluation/reports")
SUMMARY_CSV = REPORTS_DIR / "summary.csv"

SUMMARY_COLUMNS = [
    "timestamp",
    "run_id",
    "dataset",
    "strategy",
    "modality_mode",
    "embedding_model",
    "num_questions",
    "pass_rate",
    "avg_contextual_precision",
    "avg_contextual_recall",
    "avg_contextual_relevancy",
    "avg_answer_relevancy",
    "avg_faithfulness",
    "avg_top_k_hit",
    "avg_retrieved_context_count",
    "text_category_pass_rate",
    "figure_category_pass_rate",
]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_run_json(run_payload: dict[str, Any], output_dir: Path | None = None) -> Path:
    runs_dir = output_dir or RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_payload.get("run_id") or _utc_timestamp()
    dataset = run_payload.get("dataset", "unknown")
    strategy = run_payload.get("strategy", "unknown")
    filename = f"{run_id}_{dataset}_{strategy}.json"
    path = runs_dir / filename
    path.write_text(json.dumps(run_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def append_summary_csv(run_payload: dict[str, Any], summary_path: Path | None = None) -> Path:
    path = summary_path or SUMMARY_CSV
    path.parent.mkdir(parents=True, exist_ok=True)

    summary = run_payload.get("summary", {})
    row = {
        "timestamp": run_payload.get("timestamp", ""),
        "run_id": run_payload.get("run_id", ""),
        "dataset": run_payload.get("dataset", ""),
        "strategy": run_payload.get("strategy", ""),
        "modality_mode": run_payload.get("modality_mode", ""),
        "embedding_model": run_payload.get("embedding_model", ""),
        "num_questions": summary.get("num_questions", 0),
        "pass_rate": summary.get("pass_rate", 0.0),
        "avg_contextual_precision": summary.get("avg_contextual_precision"),
        "avg_contextual_recall": summary.get("avg_contextual_recall"),
        "avg_contextual_relevancy": summary.get("avg_contextual_relevancy"),
        "avg_answer_relevancy": summary.get("avg_answer_relevancy"),
        "avg_faithfulness": summary.get("avg_faithfulness"),
        "avg_top_k_hit": summary.get("avg_top_k_hit"),
        "avg_retrieved_context_count": summary.get("avg_retrieved_context_count"),
        "text_category_pass_rate": summary.get("by_category", {}).get("text", {}).get("pass_rate"),
        "figure_category_pass_rate": summary.get("by_category", {}).get("figure", {}).get("pass_rate"),
    }

    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return path
