#!/usr/bin/env python3
"""
Registered-user face feature demo.

Edit API_KEY and IMAGE_PATH before running.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import cv2
import requests

from facedet_onnx import FaceDetectorONNX, align_face, detect_best_face


# Fill in your registered W-Agent API Key. It is sent as:
# Authorization: Bearer <api_key>
API_KEY = "gak_your_api_key"

# Public API base URL. Keep /api at the end when using the official website.
BASE_URL = "https://www.w-agent.cn/api"

# Local input image. This demo may receive a scene image, because it detects the
# best face locally with face_detect.onnx and aligns it before calling the API.
IMAGE_PATH = Path("example.jpg")

# Network timeout in seconds for the API call.
TIMEOUT = 120


def main() -> int:
    api_key = API_KEY.strip()
    if not api_key or api_key == "gak_your_api_key":
        print("edit API_KEY in face_feature_api_demo.py before running this demo", file=sys.stderr)
        return 2
    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else IMAGE_PATH
    if not image_path.is_file():
        print(f"image file not found: {image_path}", file=sys.stderr)
        return 2

    # Read the original image with OpenCV. The API endpoint expects an aligned
    # face crop, so we do detection and alignment locally first.
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        print(f"failed to read image: {image_path}", file=sys.stderr)
        return 2
    # face_detect.onnx is the exported Shiqi Yu libfacedetection network.
    # The Python helper keeps the same preprocessing, decode, NMS, and 5-point
    # landmark logic as the C++ demo.
    detector = FaceDetectorONNX()
    face = detect_best_face(bgr, detector)

    # Align the face by the detected eye landmarks. The server only extracts the
    # 512-dimensional feature from this aligned crop.
    aligned = align_face(bgr, face)
    ok, encoded = cv2.imencode(".jpg", aligned, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise RuntimeError("failed to encode aligned face")

    # The HTTP API accepts raw base64 without a data:image/... prefix.
    payload = {
        "image_base64": base64.b64encode(encoded.tobytes()).decode("ascii"),
        "idempotency_key": str(image_path.resolve()),
    }
    response = requests.post(
        f"{BASE_URL.rstrip('/')}/v1/features/face",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    print(f"detected_face_score={face.score:.4f} box={face.box}")
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
