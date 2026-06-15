#!/usr/bin/env python3
"""
No-registration trial demo for W-Agent.

Supported operations:
  - object-search: one image + text prompt
  - sequence-parse: a folder of ordered person images
  - gait-pose: a folder of ordered person images

Trial calls do not use an API key or x402 wallet. The server limits usage by
IP and optional fingerprint.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import socket
import sys
import uuid
from pathlib import Path
from typing import Any

import requests


BASE_URL = os.environ.get("GAIT_API_BASE_URL", "https://www.w-agent.cn")
TIMEOUT = 600
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main() -> int:
    parser = argparse.ArgumentParser(description="W-Agent no-registration trial demo")
    parser.add_argument(
        "operation",
        choices=["object-search", "locate-anything", "sequence-parse", "gait-pose"],
        help="trial operation to run",
    )
    parser.add_argument("input", help="image path for object-search, or sequence image folder")
    parser.add_argument("--prompt", default="person", help="text prompt for object-search")
    parser.add_argument("--base-url", default=BASE_URL, help="API base URL, default: %(default)s")
    parser.add_argument("--fingerprint", default=default_fingerprint(), help="trial fingerprint")
    parser.add_argument("--output", default="", help="optional JSON output path")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    if args.operation in {"object-search", "locate-anything"}:
        result = run_locate_anything(base_url, Path(args.input), args.prompt, args.fingerprint)
    else:
        frames = load_sequence_frames(Path(args.input))
        endpoint = "/v1/public/sequences/trial/parse"
        if args.operation == "gait-pose":
            endpoint = "/v1/public/sequences/trial/gait-pose"
        result = post_json(base_url + endpoint, {"frames": frames, "fingerprint": args.fingerprint})

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


def run_locate_anything(base_url: str, image_path: Path, prompt: str, fingerprint: str) -> dict[str, Any]:
    payload = {
        "image_base64": encode_file(image_path),
        "prompt": prompt,
        "fingerprint": fingerprint,
    }
    return post_json(base_url + "/v1/public/object-search/trial", payload)


def load_sequence_frames(seq_dir: Path) -> list[dict[str, Any]]:
    if not seq_dir.is_dir():
        raise SystemExit(f"sequence folder not found: {seq_dir}")
    images = sorted(p for p in seq_dir.iterdir() if p.suffix.lower() in ALLOWED_IMAGE_SUFFIXES)
    if not images:
        raise SystemExit(f"no image frames found in: {seq_dir}")
    return [{"index": index, "content_base64": encode_file(path)} for index, path in enumerate(images)]


def encode_file(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"file not found: {path}")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(url, json=payload, timeout=TIMEOUT)
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        raise SystemExit(json.dumps(data, ensure_ascii=False, indent=2) or f"HTTP {resp.status_code}")
    return data


def default_fingerprint() -> str:
    parts = [
        platform.node() or socket.gethostname(),
        platform.platform(),
        str(uuid.getnode()),
    ]
    return "python-" + base64.urlsafe_b64encode("|".join(parts).encode("utf-8")).decode("ascii")[:80]


if __name__ == "__main__":
    sys.exit(main())
