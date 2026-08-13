#!/usr/bin/env python3
"""
Minimal buyer-side x402 demo for the public sequence API.

Flow:
1. Create a public sequence task
2. Upload local frames
3. Use the official x402 Python client to auto-pay on /parse
4. Print the parse result JSON

Edit the config block below before running:
  EVM_PRIVATE_KEY  required, payer wallet private key, 0x-prefixed
  BASE_URL         API base URL
  SEQ_DIR          local frame directory
  TIMEOUT          request timeout seconds
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

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

# Directory containing one tracked person's ordered crop images.
# The demo uploads every image under this directory as one sequence.
SEQ_DIR = Path("./images")

# Network timeout in seconds for upload and paid parse calls.
TIMEOUT = 120

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main() -> int:
    private_key = EVM_PRIVATE_KEY.strip()
    if not private_key:
        print("fill EVM_PRIVATE_KEY in examples/anonymous/python/anonymous_sequence_x402_demo.py", file=sys.stderr)
        return 2

    frames = collect_frames(SEQ_DIR)
    if not frames:
        print(f"no image files found in {SEQ_DIR}", file=sys.stderr)
        return 2

    print(f"base_url={BASE_URL}")
    print(f"seq_dir={SEQ_DIR}")
    print(f"frame_count={len(frames)}")

    # Public sequence APIs are task-based: create upload slots first, upload the
    # frames, then call the paid parse endpoint.
    task = create_public_task(len(frames))
    print(f"task_id={task['task_id']}")
    print(f"task_token={task['task_token']}")

    uploads = task["uploads"]
    if len(uploads) != len(frames):
        raise RuntimeError(f"upload count mismatch: {len(uploads)} != {len(frames)}")

    upload_frames(task["task_id"], task["task_token"], uploads, frames)

    # Register an EVM signer with the official x402 Python client. The wrapped
    # requests session below will automatically handle the 402 challenge flow:
    # first request -> receive payment challenge -> sign -> retry with payment.
    signer = EthAccountSigner(Account.from_key(private_key))
    client = x402ClientSync()
    register_exact_evm_client(client, signer)

    parse_url = f"{BASE_URL}/v1/public/sequences/{task['task_id']}/parse"
    parse_payload = {
        "frames": [
            {
                "index": upload["index"],
                "object_key": upload["object_key"],
            }
            for upload in uploads
        ]
    }

    # Optional: preview the 402 challenge before the paid call. This prints the
    # supported network/token choices and helps users check wallet readiness.
    preview_parse_challenge(task["task_id"], task["task_token"], parse_payload)

    print("starting paid parse...")
    # x402_requests behaves like requests.Session, but it retries paid endpoints
    # after signing the PAYMENT-SIGNATURE header.
    with x402_requests(client) as session:
        response = session.post(
            parse_url,
            headers={
                "Content-Type": "application/json",
                "X-Task-Token": task["task_token"],
            },
            json=parse_payload,
            timeout=TIMEOUT,
        )

    print(f"parse_status={response.status_code}")
    print(response.text)
    response.raise_for_status()

    body = response.json()
    sequences = body.get("sequences") or []
    sequence = sequences[0] if sequences else {}
    print("---summary---")
    print(f"status={body.get('status')}")
    print(f"sequence_count={body.get('sequence_count') or len(sequences)}")
    print(f"sequence_id={sequence.get('sequence_id')}")
    print(f"result_frame_count={sequence.get('frame_count')}")
    print(f"gait_image_url={nested_get(sequence, 'gait_image', 'url')}")
    print(f"face_image_url={nested_get(sequence, 'face_image', 'url')}")
    return 0


def collect_frames(seq_dir: Path) -> list[Path]:
    files = [item for item in seq_dir.iterdir() if item.is_file() and item.suffix.lower() in ALLOWED_SUFFIXES]
    return sorted(files, key=lambda item: item.name)


def create_public_task(frame_count: int) -> dict:
    # Only frame_count is sent here. Images are uploaded in the next step.
    response = requests.post(
        f"{BASE_URL}/v1/public/sequences",
        json={"frame_count": frame_count},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def upload_frames(task_id: str, task_token: str, uploads: Iterable[dict], frames: list[Path]) -> None:
    # Batch upload sends all sequence images in one multipart request. The API
    # maps frames by multipart order, so filenames are only for human readability.
    uploads = list(uploads)
    files = []
    handles = []
    try:
        for index, frame in enumerate(frames):
            handle = frame.open("rb")
            handles.append(handle)
            files.append(("frames", (f"{index:06d}{frame.suffix.lower()}", handle, detect_content_type(frame))))
        response = requests.post(
            f"{BASE_URL}/v1/public/sequences/{task_id}/uploads/batch",
            headers={"X-Task-Token": task_token},
            data={"upload_token": upload_token_from_uploads(uploads)},
            files=files,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    finally:
        for handle in handles:
            handle.close()
    print(f"uploaded_batch={len(frames)}")


def upload_token_from_uploads(uploads: list[dict]) -> str:
    if not uploads:
        raise RuntimeError("create sequence response has no upload slots")
    token = parse_qs(urlparse(str(uploads[0]["upload_url"])).query).get("token", [""])[0]
    if not token:
        raise RuntimeError("upload_url has no token")
    return token


def preview_parse_challenge(task_id: str, task_token: str, parse_payload: dict) -> None:
    response = requests.post(
        f"{BASE_URL}/v1/public/sequences/{task_id}/parse",
        headers={
            "Content-Type": "application/json",
            "X-Task-Token": task_token,
        },
        json=parse_payload,
        timeout=TIMEOUT,
    )
    if response.status_code != 402:
        print(f"preview_parse_status={response.status_code}")
        print(response.text)
        response.raise_for_status()
        return
    print("preview_parse_status=402")
    body = response.json()
    accepts = nested_get_value(body, "payment_context", "challenge", "accepts")
    if isinstance(accepts, list):
        print(f"accept_count={len(accepts)}")
        for idx, item in enumerate(accepts):
            if not isinstance(item, dict):
                continue
            extra = item.get("extra") or {}
            symbol = extra.get("assetSymbol") or ""
            transfer_method = extra.get("assetTransferMethod") or ""
            allowance_target = extra.get("allowanceTarget") or ""
            print(
                "accept[{idx}] network={network} asset={asset} symbol={symbol} method={method} pay_to={pay_to} allowance_target={allowance_target}".format(
                    idx=idx,
                    network=item.get("network", ""),
                    asset=item.get("asset", ""),
                    symbol=symbol,
                    method=transfer_method,
                    pay_to=item.get("payTo", ""),
                    allowance_target=allowance_target,
                )
            )
    else:
        print(response.text)


def detect_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".bmp":
        return "image/bmp"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


def nested_get(data: dict, *keys: str) -> str:
    current = nested_get_value(data, *keys)
    if current is None:
        return ""
    return str(current)


def nested_get_value(data: dict, *keys: str):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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
