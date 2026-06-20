#!/usr/bin/env python3
"""
Parse local sequence folders and output a pairwise similarity CSV.

This is the shortest end-to-end registered-user flow for agents:

1. POST /v1/sequences with {"frame_count": N}
2. PUT each local image to uploads[].upload_url
3. POST /v1/sequences/{task_id}/parse with frames[].object_key
4. Read features from response.sequences[]
5. Dot-product same feature types and write a similarity matrix

Run:
  export GAIT_REGISTERED_API_KEY='gak_your_api_key'
  python3 examples/registered/python/sequence_similarity_demo.py examples/sample_sequences
"""

from __future__ import annotations

import csv
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[3]
BASE_URL = os.environ.get("GAIT_API_BASE_URL", "https://www.w-agent.cn/api")
API_KEY = os.environ.get("GAIT_REGISTERED_API_KEY", "")
DEFAULT_SEQ_ROOT = ROOT / "examples" / "sample_sequences"
OUTPUT_CSV = Path(os.environ.get("GAIT_SIMILARITY_CSV", "sequence_similarity.csv"))
TIMEOUT = 300
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SAME_PERSON_THRESHOLD = 0.7


def main() -> int:
    api_key = API_KEY.strip()
    if not api_key:
        print("export GAIT_REGISTERED_API_KEY before running this demo", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SEQ_ROOT
    seq_dirs = collect_leaf_sequence_dirs(root)
    if len(seq_dirs) < 2:
        print(f"need at least 2 sequence folders under {root}", file=sys.stderr)
        return 2

    headers = {"Authorization": f"Bearer {api_key}"}
    parsed: list[dict[str, Any]] = []
    with requests.Session() as session:
        for seq_dir in seq_dirs:
            print(f"parsing {seq_dir}")
            response = parse_sequence(session, headers, seq_dir)
            for index, sequence in enumerate(response.get("sequences") or []):
                if not isinstance(sequence, dict):
                    continue
                parsed.append({
                    "source": str(seq_dir),
                    "output_index": index,
                    "sequence_id": sequence.get("sequence_id") or "",
                    "frame_count": sequence.get("frame_count") or 0,
                    "features": extract_features(sequence),
                })

    rows = similarity_rows(parsed)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "sequence_a",
            "sequence_b",
            "gait_similarity",
            "face_similarity",
            "reid_similarity",
            "fused_similarity",
            "same_person_likely",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"parsed_output_sequences={len(parsed)}")
    print(f"pair_count={len(rows)}")
    print(f"csv={OUTPUT_CSV.resolve()}")
    return 0


def parse_sequence(session: requests.Session, headers: dict[str, str], seq_dir: Path) -> dict[str, Any]:
    frames = collect_frames(seq_dir)
    created = request_json(session, "POST", "/v1/sequences", headers=headers, json_payload={"frame_count": len(frames)})
    task_id = created["task_id"]
    uploads = created["uploads"]
    if len(uploads) != len(frames):
        raise RuntimeError(f"upload count mismatch: api={len(uploads)} local={len(frames)}")

    parse_frames: list[dict[str, Any]] = []
    for frame, upload in zip(frames, uploads):
        upload_binary(session, upload["upload_url"], frame)
        parse_frames.append({"index": upload["index"], "object_key": upload["object_key"]})

    parsed = request_json(session, "POST", f"/v1/sequences/{task_id}/parse", headers=headers, json_payload={"frames": parse_frames})
    if parsed.get("status") != "succeeded":
        raise RuntimeError(f"parse did not succeed: {json.dumps(parsed, ensure_ascii=False)}")
    return parsed


def collect_leaf_sequence_dirs(root: Path) -> list[Path]:
    dirs: list[Path] = []
    for current, child_dirs, files in os.walk(root):
        image_count = sum(1 for name in files if Path(name).suffix.lower() in ALLOWED_IMAGE_SUFFIXES)
        if image_count > 0 and not child_dirs:
            dirs.append(Path(current))
    return sorted(dirs, key=lambda path: str(path))


def collect_frames(seq_dir: Path) -> list[Path]:
    frames = [path for path in seq_dir.iterdir() if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES]
    frames.sort(key=lambda path: path.name)
    if not frames:
        raise RuntimeError(f"no image frames under {seq_dir}")
    return frames


def upload_binary(session: requests.Session, upload_url: str, path: Path) -> None:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    url = urljoin(BASE_URL.rstrip("/") + "/", upload_url.lstrip("/"))
    resp = session.put(url, data=path.read_bytes(), headers={"Content-Type": content_type}, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} PUT {url}\n{resp.text}")


def request_json(session: requests.Session, method: str, path: str, headers: dict[str, str], json_payload: Any | None = None) -> dict[str, Any]:
    url = urljoin(BASE_URL.rstrip("/") + "/", path.lstrip("/"))
    request_headers = {"Accept": "application/json", **headers}
    if json_payload is not None:
        request_headers["Content-Type"] = "application/json"
    resp = session.request(method, url, headers=request_headers, json=json_payload, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} {method} {url}\n{resp.text}")
    return resp.json() if resp.text else {}


def extract_features(sequence: dict[str, Any]) -> dict[str, list[float]]:
    return {
        "gait_feature": numeric_vector(sequence.get("gait_feature")),
        "face_feature": numeric_vector(sequence.get("face_feature")),
        "reid_feature": numeric_vector(sequence.get("reid_feature")),
    }


def similarity_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for left_index in range(len(items)):
        for right_index in range(left_index + 1, len(items)):
            left = items[left_index]
            right = items[right_index]
            gait = dot_product(left["features"]["gait_feature"], right["features"]["gait_feature"])
            face = dot_product(left["features"]["face_feature"], right["features"]["face_feature"])
            reid = dot_product(left["features"]["reid_feature"], right["features"]["reid_feature"])
            fused = fused_identity_similarity(face or 0.0, gait or 0.0, reid or 0.0)
            rows.append({
                "sequence_a": display_name(left),
                "sequence_b": display_name(right),
                "gait_similarity": "" if gait is None else f"{gait:.6f}",
                "face_similarity": "" if face is None else f"{face:.6f}",
                "reid_similarity": "" if reid is None else f"{reid:.6f}",
                "fused_similarity": f"{fused:.6f}",
                "same_person_likely": str(fused > SAME_PERSON_THRESHOLD).lower(),
            })
    return rows


def display_name(item: dict[str, Any]) -> str:
    source = Path(str(item.get("source") or "")).name
    sequence_id = item.get("sequence_id") or "sequence"
    return f"{source}:{sequence_id}"


def dot_product(left: list[float], right: list[float]) -> float | None:
    if not left or not right:
        return None
    used = min(len(left), len(right))
    return sum(left[index] * right[index] for index in range(used))


def fused_identity_similarity(face_sim: float, gait_sim: float, reid_sim: float) -> float:
    result = max(gait_sim, 0.1)
    if face_sim > 0.45:
        result = max(gait_sim, 0.7)
    elif face_sim > 0.35:
        result *= 1.1
    elif face_sim > 0.4:
        result *= 1.1
    elif face_sim != 0 and face_sim < 0.1:
        result *= 0.9
    if reid_sim > 0.8:
        result *= 1.1
    if face_sim > 0.5:
        result *= 1.1
    if face_sim > 0.6:
        result *= 1.1
    return min(result, 1.0)


def numeric_vector(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    return [float(item) for item in value if isinstance(item, (int, float))]


if __name__ == "__main__":
    raise SystemExit(main())
