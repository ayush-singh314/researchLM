"""Research-paper figure captioning via direct OpenAI GPT-4o vision API."""

import base64
import logging
import mimetypes
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENAI_BASE_URL = "https://api.openai.com/v1"
CAPTION_MODEL = "gpt-4o"

CAPTION_SYSTEM_PROMPT = (
    "You describe research-paper figures for retrieval and question answering."
)

CAPTION_USER_PROMPT = (
    "Describe this research-paper figure for semantic search and QA. "
    "Focus on architecture, blocks, arrows, labels, modules, flow, charts, tables, "
    "trends, entities, and key relationships that are clearly visible. "
    "If some text is unreadable, say so instead of guessing. "
    "Return one dense paragraph."
)


def _get_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set")
    return api_key


def _image_data_url(image_path: str) -> str:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image path does not exist: {path.resolve()}")

    mime_type, _ = mimetypes.guess_type(path.name)
    mime_type = mime_type or "application/octet-stream"
    encoded = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _build_user_prompt(page_number: int | None, context_text: str | None) -> str:
    parts = [CAPTION_USER_PROMPT]
    if page_number is not None:
        parts.append(f"This figure appears on page {page_number} of a research PDF.")
    if context_text and context_text.strip():
        parts.append(
            "Nearby page text (context only; do not repeat verbatim unless it clarifies the figure):\n"
            f"{context_text.strip()[:800]}"
        )
    return "\n\n".join(parts)


def _parse_response(data: dict) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected OpenAI caption response: {data}") from exc
    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        content = "\n".join(text_parts)
    caption = str(content).strip()
    if not caption:
        raise ValueError("OpenAI caption API returned empty text")
    return caption


def generate_image_caption(
    image_path: str,
    page_number: int | None = None,
    context_text: str | None = None,
) -> str:
    """
    Caption a research-paper figure using OpenAI GPT-4o vision.

    Uses OPENAI_API_KEY and POST https://api.openai.com/v1/chat/completions.
    """
    api_key = _get_api_key()
    prompt = _build_user_prompt(page_number, context_text)
    url = f"{OPENAI_BASE_URL}/chat/completions"

    payload = {
        "model": CAPTION_MODEL,
        "messages": [
            {"role": "system", "content": CAPTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_data_url(image_path)},
                    },
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.debug("Requesting caption for %s (page %s) via %s", image_path, page_number, CAPTION_MODEL)
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        caption = _parse_response(response.json())

    logger.info(
        "Caption success for %s (page %s, %d chars)",
        image_path,
        page_number,
        len(caption),
    )
    return caption
