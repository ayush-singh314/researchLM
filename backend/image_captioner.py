"""Remote Qwen2.5-VL image captioning via configurable API endpoints."""

import base64
import logging
import mimetypes
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"

CAPTION_PROMPT = (
    "Describe this research-paper figure for semantic search and question answering. "
    "Focus on the main objects, chart/table structure, labels, trends, entities, "
    "and scientific meaning that are clearly visible. If text is unreadable, say so "
    "rather than guessing. Return one dense paragraph."
)


def _get_config() -> tuple[str, str, str]:
    api_key = os.environ.get("QWEN_VL_API_KEY", "").strip()
    base_url = os.environ.get("QWEN_VL_BASE_URL", "").strip().rstrip("/")
    model = os.environ.get("QWEN_VL_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if not api_key:
        raise ValueError("QWEN_VL_API_KEY is not set")
    if not base_url:
        raise ValueError("QWEN_VL_BASE_URL is not set")
    return api_key, base_url, model


def _provider_style(base_url: str) -> str:
    """Classify endpoint style for request formatting."""
    lower = base_url.lower()
    if "huggingface" in lower and "/v1" not in lower and "router." not in lower:
        return "huggingface"
    return "openai"


def _resolve_chat_completions_url(base_url: str) -> str:
    """Normalize base URL to an OpenAI-style chat completions endpoint."""
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _image_data_url(image_path: str) -> str:
    path = Path(image_path)
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "image/png"
    encoded = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _build_user_prompt(page_number: int | None, context_text: str | None) -> str:
    parts = [CAPTION_PROMPT]
    if page_number is not None:
        parts.append(f"This figure appears on page {page_number} of a research PDF.")
    if context_text and context_text.strip():
        parts.append(
            "Nearby page text (context only; do not repeat verbatim unless it clarifies the figure):\n"
            f"{context_text.strip()[:800]}"
        )
    return "\n\n".join(parts)


def _parse_openai_response(data: dict) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected caption API response: {data}") from exc
    if isinstance(content, list):
        text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        content = "\n".join(text_parts)
    return str(content).strip()


def _call_openai_compatible(
    api_key: str,
    base_url: str,
    model: str,
    image_path: str,
    prompt: str,
) -> str:
    url = _resolve_chat_completions_url(base_url)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                ],
            }
        ],
        "max_tokens": 512,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return _parse_openai_response(response.json())


def _call_huggingface_legacy(
    api_key: str,
    base_url: str,
    model: str,
    image_path: str,
    prompt: str,
) -> str:
    """
    Hugging Face Inference API (legacy). Prefer router OpenAI-compatible URLs when possible.
    """
    if base_url.startswith("http"):
        url = base_url if "/models/" in base_url else f"{base_url.rstrip('/')}/models/{model}"
    else:
        url = f"https://api-inference.huggingface.co/models/{model}"

    headers = {"Authorization": f"Bearer {api_key}"}
    with Path(image_path).open("rb") as image_file:
        files = {"file": (Path(image_path).name, image_file, "application/octet-stream")}
        data = {"inputs": prompt}
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, headers=headers, data=data, files=files)
            response.raise_for_status()
            body = response.json()

    if isinstance(body, list) and body:
        first = body[0]
        if isinstance(first, dict):
            return str(first.get("generated_text") or first.get("caption") or first).strip()
    if isinstance(body, dict):
        return str(body.get("generated_text") or body.get("caption") or body).strip()
    return str(body).strip()


def generate_image_caption(
    image_path: str,
    page_number: int | None = None,
    context_text: str | None = None,
) -> str:
    """
    Caption a research-paper figure via remote Qwen2.5-VL API.

    Endpoint style is inferred from QWEN_VL_BASE_URL (OpenAI-compatible vs Hugging Face).
    """
    api_key, base_url, model = _get_config()
    prompt = _build_user_prompt(page_number, context_text)
    style = _provider_style(base_url)

    if style == "huggingface":
        caption = _call_huggingface_legacy(api_key, base_url, model, image_path, prompt)
    else:
        caption = _call_openai_compatible(api_key, base_url, model, image_path, prompt)

    if not caption:
        raise ValueError("Caption API returned empty text")
    return caption
