#!/usr/bin/env python3
"""
Registered-user demo for gait recognition from an existing image sequence.

Edit API_KEY and SEQ_DIR below before running.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


# Fill in your registered W-Agent API Key. It is sent as:
# Authorization: Bearer <api_key>
API_KEY = "gak_your_api_key"

# Public API base URL. Keep /api at the end when using the official website.
BASE_URL = "https://www.w-agent.cn/api"

# One tracked person sequence. Put image frames directly under ./images.
# Filenames can be arbitrary; this demo sorts them by name before upload.
SEQ_DIR = Path("./images")

# Optional local output directory if this file is imported by batch demos.
RESULT_DIR = Path("./result")

# Network timeout in seconds. Feature extraction may take longer for long sequences.
TIMEOUT = 120

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main() -> int:
    api_key = load_api_key()
    frames = collect_frames(SEQ_DIR)
    if not frames:
        print(f"no image files found in {SEQ_DIR}", file=sys.stderr)
        return 2

    check_api_health()
    with requests.Session() as session:
        result = run_registered_gait_sequence(session, {"Authorization": f"Bearer {api_key}"}, SEQ_DIR)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def load_api_key() -> str:
    api_key = API_KEY.strip()
    if not api_key or api_key == "gak_your_api_key":
        print("edit API_KEY in gait_sequence_api_demo.py before running this demo", file=sys.stderr)
        raise SystemExit(2)
    return api_key


def run_registered_gait_sequence(session: requests.Session, headers: dict[str, str], seq_dir: Path) -> dict:
    frames = collect_frames(seq_dir)
    # Create a sequence task first. The server returns one upload slot per frame.
    created = request_json(session, "POST", "/v1/sequences", headers=headers, json_payload={"frame_count": len(frames)})
    task_id = created["task_id"]
    uploads = created["uploads"]
    if len(uploads) != len(frames):
        raise RuntimeError(f"upload count mismatch: api={len(uploads)} local={len(frames)}")

    parse_frames: list[dict] = []
    # Upload all frames in one multipart/form-data request. This is faster than
    # sending one HTTP request per frame and keeps the frame order from uploads.
    upload_frames_batch(session, headers, task_id, upload_token_from_uploads(uploads), frames)
    for upload in uploads:
        parse_frames.append({"index": upload["index"], "object_key": upload["object_key"]})

    # /parse runs the gait SDK and bills the registered account by actual result.
    return request_json(
        session,
        "POST",
        f"/v1/sequences/{task_id}/parse",
        headers=headers,
        json_payload={"frames": parse_frames},
    )


def collect_leaf_sequence_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        if collect_frames(path):
            child_dirs = [item for item in path.iterdir() if item.is_dir()]
            if not any(collect_frames(child) for child in child_dirs):
                out.append(path)
    return out


def collect_frames(seq_dir: Path) -> list[Path]:
    files = [item for item in seq_dir.iterdir() if item.is_file() and item.suffix.lower() in ALLOWED_SUFFIXES]
    return sorted(files, key=lambda item: item.name)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def check_api_health() -> None:
    response = requests.get(f"{BASE_URL.rstrip('/')}/healthz", timeout=TIMEOUT)
    response.raise_for_status()


def upload_frames_batch(session: requests.Session, headers: dict[str, str], task_id: str, upload_token: str, frames: list[Path]) -> None:
    files = []
    handles = []
    try:
        for index, frame in enumerate(frames):
            handle = frame.open("rb")
            handles.append(handle)
            # The server uses the multipart order, not the original filename, to
            # map files to upload slots. Zero-padded names make logs easier to read.
            files.append(("frames", (f"{index:06d}{frame.suffix.lower()}", handle, detect_content_type(frame))))
        response = session.post(
            f"{BASE_URL.rstrip('/')}/v1/sequences/{task_id}/uploads/batch",
            headers=headers,
            data={"upload_token": upload_token},
            files=files,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    finally:
        for handle in handles:
            handle.close()


def upload_token_from_uploads(uploads: list[dict]) -> str:
    if not uploads:
        raise RuntimeError("create sequence response has no upload slots")
    token = parse_qs(urlparse(str(uploads[0]["upload_url"])).query).get("token", [""])[0]
    if not token:
        raise RuntimeError("upload_url has no token")
    return token


def request_json(session: requests.Session, method: str, path: str, headers: dict[str, str], json_payload: dict | None = None) -> dict:
    response = session.request(
        method,
        f"{BASE_URL.rstrip('/')}{path}",
        headers={**headers, "Content-Type": "application/json"},
        json=json_payload,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as exc:
        response = exc.response
        if response is not None:
            print(f"http_error={response.status_code}", file=sys.stderr)
            print(response.text, file=sys.stderr)
        raise
