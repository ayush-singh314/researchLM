"""Check that Qdrant credentials in .env can reach the cluster.

Run from the repository root:

    python scripts/qdrant_ping.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
load_dotenv(ROOT / ".env")

url = os.environ.get("QDRANT_URL", "").strip()
api_key = os.environ.get("QDRANT_API_KEY", "").strip()

if not url:
    print("QDRANT_URL is not set")
    sys.exit(1)
if not api_key:
    print("QDRANT_API_KEY is not set")
    sys.exit(1)

print(f"Connecting to {url} ...")
client = QdrantClient(url=url, api_key=api_key, timeout=30, check_compatibility=False)

try:
    info = client.get_collections()
    print("Qdrant credentials are active.")
    print(f"Collections: {len(info.collections)}")
    for col in info.collections:
        print(f"  - {col.name}")
except Exception as exc:
    print(f"Qdrant credentials failed: {type(exc).__name__}: {exc}")
    sys.exit(1)
