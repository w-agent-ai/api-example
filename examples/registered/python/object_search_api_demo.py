#!/usr/bin/env python3
"""
Minimal registered-user demo for Object Search.

Edit API_KEY, IMAGE_PATH, and PROMPT below before running.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import requests


# Fill in your registered W-Agent API Key. It is sent as:
# Authorization: Bearer <api_key>
API_KEY = "gak_your_api_key"

# Public API base URL. Keep /api at the end when using the official website.
BASE_URL = "https://www.w-agent.cn/api"

# Local image and text prompt. The server returns boxes that match the prompt.
IMAGE_PATH = Path("example.jpg")
PROMPT = "person"

# Network timeout in seconds for the API call.
TIMEOUT = 120


def main() -> int:
    api_key = API_KEY.strip()
    if not api_key or api_key == "gak_your_api_key":
        print("edit API_KEY in object_search_api_demo.py before running this demo", file=sys.stderr)
        return 2
    if not IMAGE_PATH.is_file():
        print(f"image file not found: {IMAGE_PATH}", file=sys.stderr)
        return 2

    # The HTTP API accepts raw base64 without a data:image/... prefix.
    # idempotency_key prevents accidental duplicate billing for the same local
    # image/prompt pair if the client retries after a network interruption.
    payload = {
        "image_base64": base64.b64encode(IMAGE_PATH.read_bytes()).decode("ascii"),
        "prompt": PROMPT,
        "idempotency_key": f"{IMAGE_PATH.resolve()}:{PROMPT}",
    }
    # Registered users are billed from their account balance through the API Key.
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
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    response.raise_for_status()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as exc:
        response = exc.response
        if response is not None:
            print(f"http_error={response.status_code}", file=sys.stderr)
            print(response.text, file=sys.stderr)
        raise
    except Exception as exc:  # pragma: no cover - demo script
        print(f"fatal_error={exc}", file=sys.stderr)
        raise
