from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


MODEL_NAME = "face_detect.onnx"


@dataclass
class FaceCandidate:
    score: float
    box: tuple[int, int, int, int]
    landmarks: list[tuple[float, float]]


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -88.3762626647949, 88.3762626647949)))


def preprocess_bgr_to_libfacedet_tensor(bgr: np.ndarray) -> np.ndarray:
    height, width = bgr.shape[:2]
    rows = ((height - 1) // 32 + 1) * 16
    cols = ((width - 1) // 32 + 1) * 16
    out = np.zeros((1, 32, rows, cols), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            for fy in (-1, 0, 1):
                src_y = r * 2 + fy
                if src_y < 0 or src_y >= height:
                    continue
                for fx in (-1, 0, 1):
                    src_x = c * 2 + fx
                    if src_x < 0 or src_x >= width:
                        continue
                    offset = (fy + 1) * 3 + fx + 1
                    out[0, offset * 3 : offset * 3 + 3, r, c] = bgr[src_y, src_x, :3]
    return out


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    xx1 = max(ax1, bx1)
    yy1 = max(ay1, by1)
    xx2 = min(ax2, bx2)
    yy2 = min(ay2, by2)
    inter = max(0.0, xx2 - xx1) * max(0.0, yy2 - yy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    denom = area_a + area_b - inter
    return inter / denom if denom > 0 else 0.0


class FaceDetectorONNX:
    def __init__(self, model_path: Path | None = None, confidence_threshold: float = 0.2, nms_threshold: float = 0.45, topk: int = 1000, keep_topk: int = 512):
        self.model_path = Path(model_path or Path(__file__).with_name(MODEL_NAME))
        if not self.model_path.exists():
            raise FileNotFoundError(f"face detector ONNX model not found: {self.model_path}")
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.topk = topk
        self.keep_topk = keep_topk
        self.session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def detect(self, bgr: np.ndarray) -> list[FaceCandidate]:
        tensor = preprocess_bgr_to_libfacedet_tensor(bgr)
        outputs = self.session.run(None, {self.input_name: tensor})
        levels = [
            (outputs[0], outputs[1], outputs[2], outputs[3], 8),
            (outputs[4], outputs[5], outputs[6], outputs[7], 16),
            (outputs[8], outputs[9], outputs[10], outputs[11], 32),
        ]
        candidates: list[tuple[float, tuple[float, float, float, float], list[tuple[float, float]]]] = []
        for cls, reg, kps, obj, stride in levels:
            candidates.extend(self._decode_level(cls[0], reg[0], kps[0], obj[0], stride))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if self.topk > -1:
            candidates = candidates[: self.topk]

        kept: list[tuple[float, tuple[float, float, float, float], list[tuple[float, float]]]] = []
        for candidate in candidates:
            if all(iou(candidate[1], prev[1]) <= self.nms_threshold for prev in kept):
                kept.append(candidate)
            if self.keep_topk > -1 and len(kept) >= self.keep_topk:
                break

        faces: list[FaceCandidate] = []
        for score, box, landmarks in kept:
            x1, y1, x2, y2 = box
            faces.append(
                FaceCandidate(
                    score=score,
                    box=(int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                    landmarks=[(float(x), float(y)) for x, y in landmarks],
                )
            )
        return faces

    def _decode_level(self, cls: np.ndarray, reg: np.ndarray, kps: np.ndarray, obj: np.ndarray, stride: int):
        scores = np.sqrt(sigmoid(cls[0]) * sigmoid(obj[0]))
        ys, xs = np.where(scores >= self.confidence_threshold)
        out = []
        for y, x in zip(ys, xs):
            prior_x = float(x * stride)
            prior_y = float(y * stride)
            cx = float(reg[0, y, x]) * stride + prior_x
            cy = float(reg[1, y, x]) * stride + prior_y
            width = math.exp(float(reg[2, y, x])) * stride
            height = math.exp(float(reg[3, y, x])) * stride
            box = (cx - width * 0.5, cy - height * 0.5, cx + width * 0.5, cy + height * 0.5)
            landmarks = []
            for idx in range(5):
                landmarks.append(
                    (
                        float(kps[idx * 2, y, x]) * stride + prior_x,
                        float(kps[idx * 2 + 1, y, x]) * stride + prior_y,
                    )
                )
            out.append((float(scores[y, x]), box, landmarks))
        return out


def align_face(bgr: np.ndarray, face: FaceCandidate) -> np.ndarray:
    if len(face.landmarks) < 2:
        raise ValueError("face landmarks missing")
    left_eye = np.asarray(face.landmarks[0], dtype=np.float32)
    right_eye = np.asarray(face.landmarks[1], dtype=np.float32)
    eye_center = (left_eye + right_eye) * 0.5
    angle = math.degrees(math.atan2(float(right_eye[1] - left_eye[1]), float(right_eye[0] - left_eye[0])))
    eye_distance = float(np.linalg.norm(right_eye - left_eye))
    scale = 48.0 / max(eye_distance, 1.0)
    rot = cv2.getRotationMatrix2D((float(eye_center[0]), float(eye_center[1])), angle, scale)
    rot[0, 2] += 56.0 - float(eye_center[0])
    rot[1, 2] += 44.0 - float(eye_center[1])
    return cv2.warpAffine(bgr, rot, (112, 112), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def detect_best_face(bgr: np.ndarray, detector: FaceDetectorONNX | None = None) -> FaceCandidate:
    faces = (detector or FaceDetectorONNX()).detect(bgr)
    if not faces:
        raise ValueError("no face detected")
    return max(faces, key=lambda face: face.score * max(1, face.box[2] * face.box[3]))
