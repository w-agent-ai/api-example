from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np


MODEL_PATH = "onnx/gait_detect_dynamic_slim.onnx"
INPUT_SIZE = 640
SCORE_THRESHOLD = 0.30
NMS_THRESHOLD = 0.45
MAX_DET = 100


def letterbox_rgb(image_bgr: np.ndarray, size: int = INPUT_SIZE):
    h, w = image_bgr.shape[:2]
    scale = min(size / max(w, 1), size / max(h, 1))
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    resized = cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    pad_x = (size - new_w) // 2
    pad_y = (size - new_h) // 2
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
    blob = rgb.transpose(2, 0, 1).astype(np.float32)[None] / 255.0
    return blob, scale, pad_x, pad_y


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float):
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / np.maximum(areas[i] + areas[order[1:]] - inter, 1e-6)
        order = order[1:][iou <= threshold]
    return keep


def decode(output: np.ndarray, image_w: int, image_h: int, scale: float, pad_x: int, pad_y: int):
    pred = output[0]
    if pred.shape[0] == 5:
        pred = pred.T
    if pred.shape[-1] != 5:
        raise RuntimeError(f"unexpected ONNX output shape: {output.shape}")

    scores = pred[:, 4].astype(np.float32)
    xywh = pred[:, :4].astype(np.float32)
    boxes = np.stack(
        [
            xywh[:, 0] - xywh[:, 2] * 0.5,
            xywh[:, 1] - xywh[:, 3] * 0.5,
            xywh[:, 0] + xywh[:, 2] * 0.5,
            xywh[:, 1] + xywh[:, 3] * 0.5,
        ],
        axis=1,
    )
    mask = scores >= SCORE_THRESHOLD
    boxes = boxes[mask]
    scores = scores[mask]
    if len(scores) == 0:
        return []

    boxes[:, 0] = (boxes[:, 0] - pad_x) / scale
    boxes[:, 1] = (boxes[:, 1] - pad_y) / scale
    boxes[:, 2] = (boxes[:, 2] - pad_x) / scale
    boxes[:, 3] = (boxes[:, 3] - pad_y) / scale
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, image_w - 1)
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, image_h - 1)
    valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
    boxes = boxes[valid]
    scores = scores[valid]
    keep = nms(boxes, scores, NMS_THRESHOLD)[:MAX_DET]
    return [(float(scores[i]), *[float(v) for v in boxes[i]]) for i in keep]


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} image.jpg", file=sys.stderr)
        raise SystemExit(1)
    image_path = Path(sys.argv[1])
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)

    net = cv2.dnn.readNetFromONNX(MODEL_PATH)
    blob, scale, pad_x, pad_y = letterbox_rgb(image)
    t0 = time.perf_counter()
    net.setInput(blob)
    output = net.forward()
    dets = decode(output, image.shape[1], image.shape[0], scale, pad_x, pad_y)
    ms = (time.perf_counter() - t0) * 1000.0

    out = image.copy()
    for score, x0, y0, x1, y1 in dets:
        p0 = (int(round(x0)), int(round(y0)))
        p1 = (int(round(x1)), int(round(y1)))
        cv2.rectangle(out, p0, p1, (0, 0, 255), 2)
        cv2.putText(out, f"{score:.2f}", (p0[0], max(0, p0[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        print(f"{score:.4f} {p0[0]} {p0[1]} {p1[0] - p0[0]} {p1[1] - p0[1]}")
    out_path = image_path.with_name(image_path.stem + "_onnx_det.jpg")
    cv2.imwrite(str(out_path), out)
    print(f"detections={len(dets)} time={ms:.2f}ms output={out_path}")


if __name__ == "__main__":
    main()
