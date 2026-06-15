#!/usr/bin/env python3
"""
Complete MCP client demo for registered W-Agent users.

The demo uses plain JSON-RPC 2.0 requests against:

    http://116.198.210.0:3005/mcp

It demonstrates the MCP flow end to end:

1. Initialize MCP and list tools.
2. Read service metadata and pricing.
3. Create a sequence task.
4. Upload each sequence frame through the MCP base64 upload tool.
5. Run standalone human 2D/3D keypoints.
6. Parse the sequence.
7. Fetch the stored sequence result.
8. Create a video task and read its initial status.

Large video bytes are intentionally not uploaded through MCP in this demo.
For production video uploads, use the normal HTTP upload_url returned by the
video task creation API. Base64 video upload through MCP is only suitable for
very small files.

Anonymous x402 payment is intentionally not implemented through MCP here.
Anonymous agents should use the public HTTP API demos under
examples/anonymous/python, receive HTTP 402 payment_context, sign the x402
payment, and retry the HTTP request.
"""

import base64
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


ROOT = Path(__file__).resolve().parents[3]

MCP_URL = "http://116.198.210.0:3005/mcp"
API_KEY = "gak_your_api_key"

SEQ_DIR = ROOT / "examples" / "seqs" / "user" / "day_cl02" / "19-day_cl02-44581" / "imgs"
VIDEO_PATH = ROOT / "examples" / "video" / "0000.avi"
RESULT_PATH = ROOT / "tmp" / "mcp_api_demo_result.json"

ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main():
    if not API_KEY or API_KEY == "gak_your_api_key":
        raise RuntimeError("set API_KEY in this file before running registered MCP task tools")

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)

    initialized = rpc("initialize", {"clientInfo": {"name": "w-agent-python-mcp-demo"}}, 1)
    tools = rpc("tools/list", None, 2)
    service_info = call_tool("get_service_info", {}, 3)
    pricing = call_tool("get_pricing", {}, 4)

    frames = collect_frames(SEQ_DIR)
    created_sequence = call_tool(
        "create_sequence_task",
        {
            "api_key": API_KEY,
            "frame_count": len(frames),
        },
        10,
    )
    ensure_no_tool_error(created_sequence)

    task_id = created_sequence["task_id"]
    uploads = created_sequence["uploads"]
    parse_frames = []

    for frame, upload in zip(frames, uploads):
        upload_token = token_from_upload_url(upload["upload_url"])
        uploaded = call_tool(
            "upload_sequence_frame",
            {
                "api_key": API_KEY,
                "task_id": task_id,
                "index": upload["index"],
                "upload_token": upload_token,
                "content_base64": file_base64(frame),
                "content_type": mimetypes.guess_type(frame.name)[0] or "image/jpeg",
            },
            100 + upload["index"],
        )
        ensure_no_tool_error(uploaded)
        parse_frames.append({"index": upload["index"], "object_key": upload["object_key"]})

    gait_pose = call_tool(
        "get_sequence_human_keypoints",
        {
            "api_key": API_KEY,
            "task_id": task_id,
            "frames": parse_frames,
        },
        200,
    )
    ensure_no_tool_error(gait_pose)

    parsed = call_tool(
        "parse_sequence",
        {
            "api_key": API_KEY,
            "task_id": task_id,
            "frames": parse_frames,
        },
        201,
    )
    ensure_no_tool_error(parsed)

    sequence_result = call_tool(
        "get_sequence_result",
        {
            "api_key": API_KEY,
            "task_id": task_id,
        },
        202,
    )
    ensure_no_tool_error(sequence_result)

    video_created = call_tool(
        "create_video_task",
        {
            "api_key": API_KEY,
            "filename": VIDEO_PATH.name,
            "content_type": mimetypes.guess_type(VIDEO_PATH.name)[0] or "video/avi",
            "size_bytes": VIDEO_PATH.stat().st_size if VIDEO_PATH.exists() else 0,
        },
        300,
    )
    ensure_no_tool_error(video_created)

    video_status = call_tool(
        "get_video_status",
        {
            "api_key": API_KEY,
            "task_id": video_created["task_id"],
        },
        301,
    )
    ensure_no_tool_error(video_status)

    report = {
        "mcp_url": MCP_URL,
        "initialized": initialized,
        "tool_names": [item["name"] for item in tools["tools"]],
        "service_info": service_info,
        "pricing": pricing,
        "sequence": {
            "task_id": task_id,
            "seq_dir": str(SEQ_DIR),
            "frame_count": len(frames),
            "gait_pose": summarize_gait_pose(gait_pose),
            "parsed": summarize_sequence_parse(parsed),
            "result": summarize_sequence_parse(sequence_result),
        },
        "video": {
            "created": video_created,
            "status": video_status,
        },
    }
    write_json(RESULT_PATH, report)

    print(f"mcp_url={MCP_URL}")
    print(f"sequence_task_id={task_id}")
    print(f"sequence_frame_count={len(frames)}")
    print(f"video_task_id={video_created['task_id']}")
    print(f"result_file={RESULT_PATH}")


def rpc(method, params=None, request_id=1):
    """Send one JSON-RPC request to the W-Agent MCP endpoint."""
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params

    response = requests.post(MCP_URL, json=payload, timeout=1800)
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise RuntimeError(body["error"])
    return body["result"]


def call_tool(name, arguments=None, request_id=100):
    """Call one MCP tool and decode the JSON text returned by the server."""
    result = rpc(
        "tools/call",
        {
            "name": name,
            "arguments": arguments or {},
        },
        request_id,
    )
    text = result["content"][0]["text"]
    return json.loads(text)


def collect_frames(seq_dir):
    """Read one local sequence directory in stable filename order."""
    frames = [path for path in seq_dir.iterdir() if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES]
    frames.sort(key=lambda path: path.name)
    if not frames:
        raise RuntimeError(f"no sequence images found under {seq_dir}")
    return frames


def token_from_upload_url(upload_url):
    """Extract the one-time upload token from a server returned upload_url."""
    token = parse_qs(urlparse(upload_url).query).get("token", [""])[0]
    if not token:
        raise RuntimeError(f"upload_url has no token: {upload_url}")
    return token


def file_base64(path):
    """Return raw file bytes encoded as base64 text for MCP upload tools."""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def ensure_no_tool_error(payload):
    """Raise when the MCP tool returned an application-level error payload."""
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(payload["error"])


def summarize_gait_pose(payload):
    """Keep the output report small while proving the real result shape."""
    result = payload.get("result") or {}
    return {
        "task_id": payload.get("task_id", ""),
        "status": payload.get("status", ""),
        "frame_count": result.get("frame_count", 0),
        "pose_2ds_count": len(result.get("pose_2ds") or []),
        "pose_3ds_count": len(result.get("pose_3ds") or []),
        "billing": result.get("billing"),
    }


def summarize_sequence_parse(payload):
    """Keep feature vectors out of stdout and store only dimensions/counts."""
    sequences = payload.get("sequences") or []
    result = sequences[0] if sequences else {}
    return {
        "task_id": payload.get("task_id", ""),
        "status": payload.get("status", ""),
        "sequence_count": payload.get("sequence_count") or len(sequences),
        "sequence_id": result.get("sequence_id", ""),
        "frame_count": result.get("frame_count", 0),
        "gait_feature_dim": len(result.get("gait_feature") or []),
        "face_feature_dim": len(result.get("face_feature") or []),
        "reid_feature_dim": len(result.get("reid_feature") or []),
        "billing": result.get("billing"),
    }


def write_json(path, data):
    """Write UTF-8 pretty JSON."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
