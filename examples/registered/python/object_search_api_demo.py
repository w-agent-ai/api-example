#!/usr/bin/env python3
"""
Minimal registered-user demo for 图搜万物 / Object Search.

Flow:
1. Read one local image file and base64-encode it.
2. POST /v1/object-search with Authorization: Bearer <API_KEY>.
3. Print returned boxes and billing info.

Run:
  export GAIT_REGISTERED_API_KEY='gak_your_api_key'
  python3 examples/registered/python/object_search_api_demo.py examples/sample_sequences/ID_0001/001811.jpg 'person'
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[3]
BASE_URL = os.environ.get("GAIT_API_BASE_URL", "https://www.w-agent.cn/api")
API_KEY = os.environ.get("GAIT_REGISTERED_API_KEY", "")
DEFAULT_IMAGE = ROOT / "examples" / "sample_sequences" / "ID_0001" / "001811.jpg"
DEFAULT_PROMPT = "person"
TIMEOUT = 120


def main() -> int:
    api_key = API_KEY.strip()
    if not api_key:
        print("export GAIT_REGISTERED_API_KEY before running this demo", file=sys.stderr)
        return 2

    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE
    prompt = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROMPT
    if not image_path.is_file():
        print(f"image file not found: {image_path}", file=sys.stderr)
        return 2

    payload = {
        "image_base64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
        "prompt": prompt,
    }
    response = requests.post(
        f"{BASE_URL.rstrip('/')}/v1/object-search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    print(f"status={response.status_code}")
    print(response.text)
    response.raise_for_status()

    body = response.json()
    print("---summary---")
    print(f"image={image_path}")
    print(f"prompt={prompt}")
    print(f"box_count={len(body.get('boxes') or [])}")
    print(f"billing={json.dumps(body.get('billing') or {}, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
