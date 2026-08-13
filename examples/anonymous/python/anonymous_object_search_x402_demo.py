#!/usr/bin/env python3
"""
Minimal buyer-side x402 demo for the public Object Search API.

Flow:
1. Read a local image and prompt
2. POST /v1/public/object-search
3. The x402 client handles HTTP 402, signs payment, and retries
4. Print the object-search result JSON

Edit the config block below before running:
  EVM_PRIVATE_KEY  required, payer wallet private key, 0x-prefixed
  BASE_URL         API base URL
  IMAGE_PATH       local image file
  PROMPT           text prompt for targets in the image
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import requests
from eth_account import Account
from x402 import x402ClientSync
from x402.http.clients import x402_requests
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client


# Fill in the payer wallet private key. The x402 client uses it only to sign the
# payment challenge returned by the API; it is not sent as plain text.
EVM_PRIVATE_KEY = ""

# Public API base URL. Keep /api at the end when using the official website.
BASE_URL = "https://www.w-agent.cn/api"

# Local image to search in, and natural-language target description.
IMAGE_PATH = Path("example.jpg")
PROMPT = "person"

# Network timeout in seconds for the paid API call.
TIMEOUT = 120


def main() -> int:
    private_key = EVM_PRIVATE_KEY.strip()
    if not private_key:
        print("edit EVM_PRIVATE_KEY in anonymous_object_search_x402_demo.py before running this demo", file=sys.stderr)
        return 2
    if not IMAGE_PATH.is_file():
        print(f"image file not found: {IMAGE_PATH}", file=sys.stderr)
        return 2

    # Register an EVM signer with the official x402 Python client. The wrapped
    # requests session below will automatically handle the 402 challenge flow:
    # first request -> receive payment challenge -> sign -> retry with payment.
    signer = EthAccountSigner(Account.from_key(private_key))
    client = x402ClientSync()
    register_exact_evm_client(client, signer)

    # The HTTP API accepts raw base64 without a data:image/... prefix.
    payload = {
        "image_base64": base64.b64encode(IMAGE_PATH.read_bytes()).decode("ascii"),
        "prompt": PROMPT,
        "idempotency_key": f"{IMAGE_PATH.resolve()}:{PROMPT}",
    }
    url = f"{BASE_URL.rstrip('/')}/v1/public/object-search"

    print(f"base_url={BASE_URL}")
    print(f"image_path={IMAGE_PATH}")
    print(f"prompt={PROMPT}")
    print("starting paid object search...")
    # x402_requests behaves like requests.Session, but it retries paid endpoints
    # after signing the PAYMENT-SIGNATURE header.
    with x402_requests(client) as session:
        response = session.post(url, json=payload, timeout=TIMEOUT)

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
