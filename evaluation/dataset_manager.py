"""Dataset discovery, golden QA management, and metadata loading."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from deepeval.synthesizer import Synthesizer
from deepeval.synthesizer.config import ContextConstructionConfig

DATASETS_ROOT = Path("evaluation/datasets")
DEFAULT_CATEGORY = "general"

GOLDEN_GENERATION_DEFAULTS = {
    "max_contexts_per_document": 5,
    "max_goldens_per_context": 2,
}


@dataclass
class DatasetInfo:
    name: str
    root: Path
    metadata: dict
    source_paths: list[Path]
    goldens_path: Path

    @property
    def description(self) -> str:
        return self.metadata.get("description", "")

    @property
    def categories(self) -> list[str]:
        return self.metadata.get(
            "categories",
            ["text", "figure", "table", "cross_modal", "general"],
        )


@dataclass
class GoldenItem:
    input: str
    expected_output: str
    category: str = DEFAULT_CATEGORY

    def to_dict(self) -> dict:
        return {
            "input": self.input,
            "expected_output": self.expected_output,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GoldenItem:
        return cls(
            input=data["input"],
            expected_output=data["expected_output"],
            category=data.get("category", DEFAULT_CATEGORY),
        )


def list_datasets() -> list[str]:
    if not DATASETS_ROOT.exists():
        return []
    return sorted(
        p.name for p in DATASETS_ROOT.iterdir() if p.is_dir() and (p / "metadata.json").exists()
    )


def _resolve_source_paths(dataset_dir: Path, metadata: dict) -> list[Path]:
    local_pdf = dataset_dir / "source.pdf"
    if local_pdf.exists():
        return [local_pdf.resolve()]

    repo_root = Path.cwd()
    paths: list[Path] = []
    for rel in metadata.get("source_files", []):
        candidate = (repo_root / rel).resolve()
        if candidate.exists():
            paths.append(candidate)
    if not paths:
        raise FileNotFoundError(
            f"No source PDF found for dataset '{dataset_dir.name}'. "
            f"Add {local_pdf} or set source_files in metadata.json."
        )
    return paths


def load_dataset(name: str) -> DatasetInfo:
    dataset_dir = DATASETS_ROOT / name
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"Dataset not found: {dataset_dir}")

    metadata_path = dataset_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing metadata.json in {dataset_dir}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.setdefault("dataset_name", name)

    return DatasetInfo(
        name=name,
        root=dataset_dir,
        metadata=metadata,
        source_paths=_resolve_source_paths(dataset_dir, metadata),
        goldens_path=dataset_dir / "goldens.json",
    )


def load_goldens(dataset: DatasetInfo) -> list[GoldenItem]:
    if not dataset.goldens_path.exists():
        raise FileNotFoundError(
            f"Goldens not found at {dataset.goldens_path}. "
            "Run with --regenerate-goldens or call ensure_goldens()."
        )
    raw = json.loads(dataset.goldens_path.read_text(encoding="utf-8"))
    return [GoldenItem.from_dict(item) for item in raw]


def generate_goldens(
    dataset: DatasetInfo,
    *,
    max_contexts: int | None = None,
    goldens_per_context: int | None = None,
) -> list[GoldenItem]:
    """Generate synthetic QA pairs from dataset source PDFs and cache to goldens.json."""
    max_contexts = max_contexts or GOLDEN_GENERATION_DEFAULTS["max_contexts_per_document"]
    goldens_per_context = goldens_per_context or GOLDEN_GENERATION_DEFAULTS["max_goldens_per_context"]

    synthesizer = Synthesizer()
    document_paths = [str(p) for p in dataset.source_paths]
    goldens = synthesizer.generate_goldens_from_docs(
        document_paths=document_paths,
        include_expected_output=True,
        max_goldens_per_context=goldens_per_context,
        context_construction_config=ContextConstructionConfig(
            max_contexts_per_document=max_contexts,
        ),
    )

    items: list[GoldenItem] = []
    default_category = dataset.metadata.get("default_category", DEFAULT_CATEGORY)
    for golden in goldens:
        if golden.input and golden.expected_output:
            items.append(
                GoldenItem(
                    input=golden.input,
                    expected_output=golden.expected_output,
                    category=default_category,
                )
            )

    dataset.goldens_path.write_text(
        json.dumps([item.to_dict() for item in items], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return items


def ensure_goldens(
    dataset: DatasetInfo,
    *,
    regenerate: bool = False,
    max_contexts: int | None = None,
    goldens_per_context: int | None = None,
) -> list[GoldenItem]:
    """Load cached goldens or generate once and reuse."""
    if regenerate or not dataset.goldens_path.exists():
        return generate_goldens(
            dataset,
            max_contexts=max_contexts,
            goldens_per_context=goldens_per_context,
        )
    return load_goldens(dataset)


def bootstrap_openclaw_dataset(repo_root: Path | None = None) -> None:
    """Copy legacy project goldens/PDF into evaluation/datasets/openclaw if missing."""
    root = repo_root or Path.cwd()
    dataset_dir = root / "evaluation" / "datasets" / "openclaw"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    legacy_goldens = root / "goldens.json"
    legacy_pdf = root / "documents" / "Openclaw_Research_Report.pdf"
    target_goldens = dataset_dir / "goldens.json"
    target_pdf = dataset_dir / "source.pdf"

    if legacy_goldens.exists() and not target_goldens.exists():
        shutil.copy2(legacy_goldens, target_goldens)

    if legacy_pdf.exists() and not target_pdf.exists():
        shutil.copy2(legacy_pdf, target_pdf)
