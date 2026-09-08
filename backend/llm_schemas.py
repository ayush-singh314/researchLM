from typing import Literal

from pydantic import BaseModel


class ExtractedImage(BaseModel):
    """Metadata for a figure extracted from a PDF."""

    paper_id: str
    page_number: int
    image_index: int
    image_path: str
    source_pdf: str
    xref: int
    modality: Literal["image"] = "image"


class BtwRouteDecision(BaseModel):
    needs_web_search: bool


class RouterDecision(BaseModel):
    route: Literal["retrieve", "verify_claim", "direct_answer"]


class RelevancyDecision(BaseModel):
    is_relevant: bool
    reason: str


class SupersedingPaper(BaseModel):
    title: str
    url: str
    summary: str


class ClaimVerificationResult(BaseModel):
    is_superseded: bool
    verdict_summary: str
    superseding_papers: list[SupersedingPaper]
