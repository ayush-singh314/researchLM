import os
import base64
import json
import mimetypes
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = "https://api.openai.com/v1"
MODEL = "gpt-4o"

# Change this to your extracted figure path
IMAGE_PATH = r"C:\Development\genai_projects\researchlm\documents\extracted_images\1706_03762v7\page_0003_img_01.png"


def image_to_data_url(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image path does not exist: {path.resolve()}")

    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type is None:
        mime_type = "application/octet-stream"

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def caption_image():
    if not OPENAI_API_KEY:
        raise ValueError("Missing OPENAI_API_KEY in .env")

    image_data_url = image_to_data_url(IMAGE_PATH)

    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You describe research-paper figures for retrieval and question answering."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe this research-paper figure for semantic search and QA. "
                            "Focus on architecture, blocks, arrows, labels, modules, flow, and key relationships. "
                            "If some text is unreadable, say so instead of guessing. "
                            "Return one dense paragraph."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        },
                    },
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }

    print("=== REQUEST URL ===")
    print(url)
    print("\n=== MODEL ===")
    print(MODEL)
    print("\n=== IMAGE EXISTS ===")
    print(Path(IMAGE_PATH).resolve(), Path(IMAGE_PATH).exists())

    response = requests.post(url, headers=headers, json=payload, timeout=120)

    print("\n=== STATUS CODE ===")
    print(response.status_code)

    print("\n=== RESPONSE TEXT ===")
    print(response.text[:5000])

    try:
        data = response.json()
        print("\n=== PARSED JSON ===")
        print(json.dumps(data, indent=2)[:5000])

        if "choices" in data:
            print("\n=== CAPTION ===")
            print(data["choices"][0]["message"]["content"])
    except Exception as e:
        print("\nJSON parse failed:", e)


if __name__ == "__main__":
    caption_image()