#!/usr/bin/env python3
"""
Batch tester for registered-user sequence and video APIs.

This script uses a registered API key, recursively processes all leaf sequence
directories under SEQ_ROOT and all video files under VIDEO_ROOT, then writes one
JSON result per item plus summary and similarity reports under RESULT_DIR.

The API result can include optional pose_2ds, pose_3ds, and emotions fields.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[3]

# Registered-user demo configuration.
#
# A registered user pays from their account balance. The client only needs to
# send the API Key in the Authorization header; no x402 wallet signing is used
# in this registered-user flow.
USER_EMAIL = os.environ.get("GAIT_REGISTERED_EMAIL", "user@example.com")
API_KEY = ""
BASE_URL = os.environ.get("GAIT_API_BASE_URL", "https://www.h-agent.ai/api")

# Sequence input:
#   examples/seqs may contain nested folders.
#   Each leaf folder that directly contains images is treated as one sequence.
# Video input:
#   examples/video is scanned recursively for common video file extensions.
SEQ_ROOT = ROOT / "examples" / "seqs"
VIDEO_ROOT = ROOT / "examples" / "video"

# All raw API responses and derived similarity reports are written here.
RESULT_DIR = ROOT / "tmp" / "registered_batch_results"
TIMEOUT = 1800
POLL_INTERVAL = 2.0

ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpeg", ".mpg", ".m4v"}


def main() -> int:
    api_key = load_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    # Discover all local test inputs before making API calls. The summary file
    # is written immediately so a partial run still records what was attempted.
    seq_dirs = collect_leaf_sequence_dirs(SEQ_ROOT)
    videos = collect_video_files(VIDEO_ROOT)
    summary: dict[str, Any] = {
        "started_at": iso_now(),
        "base_url": BASE_URL,
        "user_email": USER_EMAIL,
        "seq_root": str(SEQ_ROOT),
        "video_root": str(VIDEO_ROOT),
        "result_dir": str(RESULT_DIR),
        "sequence_count": len(seq_dirs),
        "video_count": len(videos),
        "sequences": [],
        "videos": [],
    }
    write_json(RESULT_DIR / "summary.json", summary)

    print(f"base_url={BASE_URL}")
    print(f"user_email={USER_EMAIL}")
    print(f"seq_root={SEQ_ROOT} leaf_sequences={len(seq_dirs)}")
    print(f"video_root={VIDEO_ROOT} videos={len(videos)}")
    print(f"result_dir={RESULT_DIR}")
    check_api_health()

    with requests.Session() as session:
        # Validate that the configured API Key belongs to a real registered
        # user before starting a potentially long batch run.
        me = request_json(session, "GET", "/v1/me", headers=headers)
        print(f"authenticated_user={(me.get('user') or {}).get('email', '')}")

        # Sequence parsing is synchronous: create task -> upload frames -> parse
        # -> fetch result. Each item is saved immediately so failures do not
        # discard previous successful results.
        for index, seq_dir in enumerate(seq_dirs, start=1):
            print(f"[sequence {index}/{len(seq_dirs)}] {seq_dir}")
            item = run_and_save("sequence", seq_dir, lambda: run_registered_sequence(session, headers, seq_dir))
            summary["sequences"].append(item)
            write_json(RESULT_DIR / "summary.json", summary)

        # Video parsing is asynchronous: create task -> upload video -> complete
        # upload -> poll result until the worker finishes.
        for index, video_path in enumerate(videos, start=1):
            print(f"[video {index}/{len(videos)}] {video_path}")
            item = run_and_save("video", video_path, lambda: run_registered_video(session, headers, video_path))
            summary["videos"].append(item)
            write_json(RESULT_DIR / "summary.json", summary)

    # After all sequence API results are saved, compute pairwise dot-product
    # similarity across all successful standalone sequence results.
    sequence_similarity = compute_sequence_similarity_report(summary["sequences"])
    sequence_similarity_path = RESULT_DIR / "sequence_similarities.json"
    write_json(sequence_similarity_path, sequence_similarity)
    summary["sequence_similarity"] = {
        "result_file": str(sequence_similarity_path),
        "sequence_count": sequence_similarity["sequence_count"],
        "pair_count": sequence_similarity["pair_count"],
    }
    summary["finished_at"] = iso_now()
    write_json(RESULT_DIR / "summary.json", summary)
    print(f"summary_path={RESULT_DIR / 'summary.json'}")
    print(f"sequence_similarity_path={sequence_similarity_path}")
    return 0


def run_and_save(kind: str, source: Path, fn) -> dict[str, Any]:
    """Run one API operation and persist its full result or error as JSON."""
    started_at = iso_now()
    safe_name = safe_filename(str(source.relative_to(ROOT) if source.is_relative_to(ROOT) else source))
    out_path = RESULT_DIR / kind / f"{safe_name}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = fn()
        record = {
            "kind": kind,
            "source": str(source),
            "started_at": started_at,
            "finished_at": iso_now(),
            "ok": True,
            "result": result,
        }
        print(f"{kind}=ok source={source} result_file={out_path}")
    except Exception as exc:
        record = {
            "kind": kind,
            "source": str(source),
            "started_at": started_at,
            "finished_at": iso_now(),
            "ok": False,
            "error": str(exc),
        }
        print(f"{kind}=failed source={source} error={exc}", file=sys.stderr)
    write_json(out_path, record)
    return {
        "source": str(source),
        "ok": bool(record["ok"]),
        "result_file": str(out_path),
        "task_id": nested_get(record, "result", "task_id") or "",
        "error": record.get("error", ""),
    }


def run_registered_sequence(session: requests.Session, headers: dict[str, str], seq_dir: Path) -> dict[str, Any]:
    """Parse one registered-user sequence directory.

    API flow:
      1. POST /v1/sequences with frame_count.
      2. PUT each frame to the upload_url returned by step 1.
      3. POST /v1/sequences/{task_id}/gait-pose for standalone pose billing.
      4. POST /v1/sequences/{task_id}/parse with index/object_key pairs.
      5. GET /v1/sequences/{task_id}/result to read the stored result.
    """
    frames = collect_frames(seq_dir)
    # The server allocates one upload slot per frame. The object_key from each
    # slot is later passed back to the parse endpoint.
    created = request_json(session, "POST", "/v1/sequences", headers=headers, json_payload={"frame_count": len(frames)})
    task_id = created["task_id"]
    uploads = created["uploads"]
    if len(uploads) != len(frames):
        raise RuntimeError(f"upload count mismatch: api={len(uploads)} local={len(frames)}")

    parse_frames: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        upload = uploads[index]
        upload_binary(session, upload["upload_url"], frame)
        # Use the server-provided index and object_key rather than local
        # filenames. This keeps parsing independent from client file paths.
        parse_frames.append({"index": upload["index"], "object_key": upload["object_key"]})

    # Gait Pose is a separate API and separate billable operation. It returns
    # pose_2ds / pose_3ds without full gait, face or ReID feature extraction.
    gait_pose = request_json(
        session,
        "POST",
        f"/v1/sequences/{task_id}/gait-pose",
        headers=headers,
        json_payload={"frames": parse_frames},
    )

    # Registered sequence parsing returns synchronously after SDK processing and
    # account-balance billing are complete.
    parsed = request_json(
        session,
        "POST",
        f"/v1/sequences/{task_id}/parse",
        headers=headers,
        json_payload={"frames": parse_frames},
    )
    result = request_json(session, "GET", f"/v1/sequences/{task_id}/result", headers=headers)
    return {
        "task_id": task_id,
        "sequence_dir": str(seq_dir),
        "frame_count": len(frames),
        "gait_pose": gait_pose,
        "parsed": parsed,
        "result": result,
    }


def run_registered_video(session: requests.Session, headers: dict[str, str], video_path: Path) -> dict[str, Any]:
    """Upload and parse one registered-user video file.

    The complete endpoint tells the server that upload is finished. The worker
    then processes the video asynchronously, so this demo polls /result.
    """
    filename = video_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    created = request_json(
        session,
        "POST",
        "/v1/videos",
        headers=headers,
        json_payload={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": video_path.stat().st_size,
        },
    )
    task_id = created["task_id"]
    upload_binary(session, created["upload_url"], video_path, content_type=content_type)
    request_json(session, "POST", f"/v1/videos/{task_id}/complete", headers=headers, json_payload={})
    result = wait_registered_video_result(session, headers, task_id)
    return {
        "task_id": task_id,
        "video_path": str(video_path),
        "result": result,
        "similarities": compute_video_similarity(result),
    }


def wait_registered_video_result(session: requests.Session, headers: dict[str, str], task_id: str) -> dict[str, Any]:
    """Poll a video result until it is ready or the demo timeout expires."""
    deadline = time.time() + TIMEOUT
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        resp = raw_request(session, "GET", f"/v1/videos/{task_id}/result", headers=headers)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code not in {409, 402}:
            raise_http(resp)
        last_payload = safe_json(resp)
        time.sleep(POLL_INTERVAL)
    raise RuntimeError(f"timed out waiting for registered video result: task_id={task_id} last={last_payload}")


def collect_leaf_sequence_dirs(root: Path) -> list[Path]:
    """Return leaf directories that directly contain image frames."""
    dirs: list[Path] = []
    if not root.exists():
        return dirs
    for current, child_dirs, files in os.walk(root):
        image_count = sum(1 for name in files if Path(name).suffix.lower() in ALLOWED_IMAGE_SUFFIXES)
        if image_count > 0 and not child_dirs:
            dirs.append(Path(current))
    return sorted(dirs, key=lambda path: str(path))


def collect_video_files(root: Path) -> list[Path]:
    """Return supported video files under root, including nested directories."""
    if not root.exists():
        return []
    return sorted(
        [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in ALLOWED_VIDEO_SUFFIXES],
        key=lambda path: str(path),
    )


def collect_frames(seq_dir: Path) -> list[Path]:
    """Return image frames in deterministic filename order."""
    frames = [path for path in seq_dir.iterdir() if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES]
    frames.sort(key=lambda path: path.name)
    if not frames:
        raise RuntimeError(f"no frames under {seq_dir}")
    return frames


def upload_binary(session: requests.Session, upload_url: str, path: Path, content_type: str | None = None) -> None:
    """Upload one binary file to a service-relative upload URL."""
    mime = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    url = urljoin(BASE_URL.rstrip("/") + "/", upload_url.lstrip("/"))
    resp = session.put(url, data=path.read_bytes(), headers={"Content-Type": mime, "Accept": "application/json"}, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise_http(resp)


def request_json(session: requests.Session, method: str, path: str, headers: dict[str, str] | None = None, json_payload: Any | None = None) -> dict[str, Any]:
    """Send a JSON API request and raise a readable error for non-2xx replies."""
    resp = raw_request(session, method, path, headers=headers, json_payload=json_payload)
    if resp.status_code >= 400:
        raise_http(resp)
    return resp.json() if resp.text else {}


def raw_request(session: requests.Session, method: str, path: str, headers: dict[str, str] | None = None, json_payload: Any | None = None) -> requests.Response:
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    url = urljoin(BASE_URL.rstrip("/") + "/", path.lstrip("/"))
    return session.request(method, url, headers=req_headers, json=json_payload, timeout=TIMEOUT)


def check_api_health() -> None:
    """Fail fast when the configured API endpoint is not reachable."""
    url = urljoin(BASE_URL.rstrip("/") + "/", "healthz")
    try:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
    except Exception as exc:
        raise RuntimeError(f"api health check failed: {url}: {exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(f"api health check failed: HTTP {resp.status_code} {url}\n{resp.text}")


def compute_sequence_similarity_report(sequence_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute pairwise feature similarity across successful sequence results."""
    sequences: list[dict[str, Any]] = []
    for item in sequence_items:
        if not item.get("ok"):
            continue
        result_file = item.get("result_file")
        if not result_file:
            continue
        record = read_json(Path(result_file))
        sequence = sequence_from_registered_record(record)
        if not isinstance(sequence, dict):
            continue
        identity = sequence_identity(sequence, source=item.get("source", ""), task_id=item.get("task_id", ""))
        sequences.append({"identity": identity, "features": extract_features(sequence)})

    pairs = pairwise_similarity(sequences)
    return {
        "generated_at": iso_now(),
        "sequence_count": len(sequences),
        "pair_count": len(pairs),
        "pairs": pairs,
    }


def compute_video_similarity(video_result: dict[str, Any]) -> dict[str, Any]:
    """Compute pairwise feature similarity among sequences in one video."""
    raw_sequences = video_result.get("sequences") or []
    sequences: list[dict[str, Any]] = []
    for index, sequence in enumerate(raw_sequences):
        if not isinstance(sequence, dict):
            continue
        sequences.append({"identity": sequence_identity(sequence, index=index), "features": extract_features(sequence)})
    pairs = pairwise_similarity(sequences)
    return {
        "sequence_count": len(sequences),
        "pair_count": len(pairs),
        "pairs": pairs,
    }


def pairwise_similarity(sequences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare every sequence pair once: (0,1), (0,2), ..., (n-2,n-1)."""
    pairs: list[dict[str, Any]] = []
    for left_index in range(len(sequences)):
        for right_index in range(left_index + 1, len(sequences)):
            left = sequences[left_index]
            right = sequences[right_index]
            pairs.append({
                "left": left["identity"],
                "right": right["identity"],
                "similarity": feature_similarity(left["features"], right["features"]),
            })
    return pairs


def sequence_from_registered_record(record: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the sequence object from a saved registered-user result file."""
    parsed_sequence = nested_get(record, "result", "parsed", "sequence")
    if isinstance(parsed_sequence, dict):
        return parsed_sequence
    result_sequence = nested_get(record, "result", "result")
    return result_sequence if isinstance(result_sequence, dict) else None


def extract_features(sequence: dict[str, Any]) -> dict[str, list[float]]:
    """Read the three feature vectors used for similarity comparison."""
    return {
        "gait_feature": numeric_vector(sequence.get("gait_feature")),
        "reid_feature": numeric_vector(sequence.get("reid_feature")),
        "face_feature": numeric_vector(sequence.get("face_feature")),
    }


def feature_similarity(left: dict[str, list[float]], right: dict[str, list[float]]) -> dict[str, Any]:
    """Compute gait, ReID and face similarities for two feature sets."""
    return {
        name: dot_product(left.get(name) or [], right.get(name) or [])
        for name in ("gait_feature", "reid_feature", "face_feature")
    }


def dot_product(left: list[float], right: list[float]) -> dict[str, Any]:
    """Return dot-product similarity and dimension diagnostics."""
    left_len = len(left)
    right_len = len(right)
    if left_len == 0 or right_len == 0:
        return {
            "score": None,
            "left_dim": left_len,
            "right_dim": right_len,
            "used_dim": 0,
            "skipped": True,
            "reason": "empty_feature",
        }
    used_dim = min(left_len, right_len)
    return {
        "score": sum(left[index] * right[index] for index in range(used_dim)),
        "left_dim": left_len,
        "right_dim": right_len,
        "used_dim": used_dim,
        "skipped": False,
        "dimension_mismatch": left_len != right_len,
    }


def numeric_vector(value: Any) -> list[float]:
    """Keep only numeric feature values and convert them to float."""
    if not isinstance(value, list):
        return []
    return [float(item) for item in value if isinstance(item, (int, float))]


def sequence_identity(sequence: dict[str, Any], source: str = "", task_id: str = "", index: int | None = None) -> dict[str, Any]:
    """Build a small stable identity block for similarity report entries."""
    identity: dict[str, Any] = {
        "sequence_id": sequence.get("sequence_id") or "",
        "frame_count": sequence.get("frame_count") or 0,
    }
    if source:
        identity["source"] = source
    if task_id:
        identity["task_id"] = task_id
    if index is not None:
        identity["index"] = index
    batch = sequence.get("batch")
    if batch is not None:
        identity["batch"] = batch
    return identity


def raise_http(resp: requests.Response) -> None:
    raise RuntimeError(f"HTTP {resp.status_code} {resp.request.method} {resp.request.url}\n{resp.text}")


def safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_api_key() -> str:
	api_key = os.environ.get("GAIT_REGISTERED_API_KEY", "").strip() or API_KEY.strip()
	if not api_key:
		raise RuntimeError("export GAIT_REGISTERED_API_KEY before running this demo")
	return api_key


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:180] or "item"


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"fatal_error={exc}", file=sys.stderr)
        raise
