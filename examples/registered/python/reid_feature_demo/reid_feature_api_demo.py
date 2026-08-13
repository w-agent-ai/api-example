#!/usr/bin/env python3
"""
Registered-user ReID feature demo.

Edit API_KEY and IMAGE_PATH before running.
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

# The ReID API expects one cropped person image. If the original image contains
# multiple people, detect the target person locally and crop it first.
IMAGE_PATH = Path("example.jpg")

# Network timeout in seconds for the API call.
TIMEOUT = 120


def main() -> int:
    api_key = API_KEY.strip()
    if not api_key or api_key == "gak_your_api_key":
        print("edit API_KEY in reid_feature_api_demo.py before running this demo", file=sys.stderr)
        return 2
    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else IMAGE_PATH
    if not image_path.is_file():
        print(f"image file not found: {image_path}", file=sys.stderr)
        return 2

    # The HTTP API accepts raw base64 without a data:image/... prefix.
    payload = {
        "image_base64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
        "idempotency_key": str(image_path.resolve()),
    }
    response = requests.post(
        f"{BASE_URL.rstrip('/')}/v1/features/reid",
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
