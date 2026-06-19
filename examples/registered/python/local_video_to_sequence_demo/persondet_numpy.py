from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from persondet_weights import load_weights


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


@dataclass
class Config:
    score_threshold: float = 0.30
    nms_threshold: float = 0.45
    resize_width: int = 640
    default_jump: int = 2
    min_effective_fps: float = 10.0
    max_effective_fps: float = 20.0
    max_age: int = 25
    min_frames: int = 20
    max_frames: int = 120
    min_box_width: int = 64
    min_box_height: int = 128
    match_iou: float = 0.30
    enlarge: float = 0.20
    moving_pair_change_threshold: float = 0.70
    moving_scale_threshold: float = 0.30
    topk: int = 1000


def round_to_multiple(value: float, multiple: int = 32) -> int:
    return max(multiple, int(round(value / multiple)) * multiple)


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


def resize_for_detector(image: np.ndarray, resize_width: int):
    h, w = image.shape[:2]
    if resize_width <= 0 or max(w, h) <= resize_width:
        return image, 1.0, 1.0
    if w >= h:
        rw = resize_width
        rh = round_to_multiple(h * rw / w, 32)
    else:
        rh = resize_width
        rw = round_to_multiple(w * rh / h, 32)
    resized = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_LINEAR)
    return resized, w / resized.shape[1], h / resized.shape[0]


def iou_xyxy(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    iw = np.maximum(0.0, x2 - x1)
    ih = np.maximum(0.0, y2 - y1)
    inter = iw * ih
    area_a = np.maximum(0.0, a[:, 2] - a[:, 0]) * np.maximum(0.0, a[:, 3] - a[:, 1])
    area_b = np.maximum(0.0, b[:, 2] - b[:, 0]) * np.maximum(0.0, b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-6)


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float, topk: int) -> list[int]:
    if len(boxes) == 0:
        return []
    order = scores.argsort()[::-1]
    if len(order) > topk:
        order = order[:topk]
    keep = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        ious = iou_xyxy(boxes[[i]], boxes[rest])[0]
        order = rest[ious <= threshold]
    return keep


class PersonDetectorNumpy:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.w = load_weights()
        self.strides = (8, 16, 32)

    def conv1x1(self, x: np.ndarray, name: str, relu: bool) -> np.ndarray:
        weight = self.w[name + ".w"][:, :, 0, 0]
        bias = self.w[name + ".b"]
        y = x.reshape(-1, x.shape[2]) @ weight.T + bias
        y = y.reshape(x.shape[0], x.shape[1], weight.shape[0]).astype(np.float32, copy=False)
        if relu:
            np.maximum(y, 0.0, out=y)
        return y

    def depthwise3x3(self, x: np.ndarray, name: str, stride: int, relu: bool = True) -> np.ndarray:
        weight = self.w[name + ".dw.w"][:, 0]
        bias = self.w[name + ".dw.b"]
        h, w, c = x.shape
        out_h = (h + 2 - 3) // stride + 1
        out_w = (w + 2 - 3) // stride + 1
        y = np.empty((out_h, out_w, c), dtype=np.float32)
        for ch in range(c):
            filtered = cv2.filter2D(
                x[:, :, ch],
                cv2.CV_32F,
                weight[ch],
                borderType=cv2.BORDER_CONSTANT,
            )
            y[:, :, ch] = filtered[::stride, ::stride] + bias[ch]
        if relu:
            np.maximum(y, 0.0, out=y)
        return y

    def dwblock(self, x: np.ndarray, name: str, stride: int) -> np.ndarray:
        x = self.depthwise3x3(x, name, stride, True)
        return self.conv1x1(x, name + ".pw", True)

    def reorg_conv_bgr(self, image: np.ndarray) -> np.ndarray:
        weight = self.w["stem_reorg.w"][:, :, 0, 0]
        bias = self.w["stem_reorg.b"]
        h, w = image.shape[:2]
        out_h = (h + 1) // 2
        out_w = (w + 1) // 2
        padded = np.pad(image.astype(np.float32), ((1, 1), (1, 1), (0, 0)), mode="constant")
        cols = []
        for ic in range(3):
            for ky in range(3):
                for kx in range(3):
                    cols.append(padded[ky : ky + h : 2, kx : kx + w : 2, ic][:out_h, :out_w])
        patches = np.stack(cols, axis=2)
        y = patches.reshape(-1, 27) @ weight.T + bias
        y = y.reshape(out_h, out_w, 16).astype(np.float32, copy=False)
        np.maximum(y, 0.0, out=y)
        return y

    @staticmethod
    def upsample_nearest(x: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
        ys = np.minimum(x.shape[0] - 1, np.arange(out_h) * x.shape[0] // out_h)
        xs = np.minimum(x.shape[1] - 1, np.arange(out_w) * x.shape[1] // out_w)
        return x[ys[:, None], xs[None, :], :]

    def head(self, x: np.ndarray, name: str):
        if name + "_stem.dw.w" in self.w:
            x = self.dwblock(x, name + "_stem", 1)
        if name + "_extra.dw.w" in self.w:
            x = self.dwblock(x, name + "_extra", 1)
        obj = self.conv1x1(x, name + "_obj", False)[:, :, 0]
        box = self.conv1x1(x, name + "_box", False)
        return obj, box

    def forward(self, image: np.ndarray):
        x = self.reorg_conv_bgr(image)
        x = self.dwblock(x, "stem1", 2)
        x = self.dwblock(x, "stem2", 2)
        p8 = self.dwblock(x, "stage8_0", 1)
        if "stage8_1.dw.w" in self.w:
            p8 = self.dwblock(p8, "stage8_1", 1)
        p16 = self.dwblock(p8, "stage16_0", 2)
        if "stage16_1.dw.w" in self.w:
            p16 = self.dwblock(p16, "stage16_1", 1)
        p32 = self.dwblock(p16, "stage32_0", 2)
        if "stage32_1.dw.w" in self.w:
            p32 = self.dwblock(p32, "stage32_1", 1)

        u16 = self.conv1x1(p16, "lat16", False) + self.upsample_nearest(p32, p16.shape[0], p16.shape[1])
        u8 = self.conv1x1(p8, "lat8", False) + self.upsample_nearest(u16, p8.shape[0], p8.shape[1])

        outputs = [(self.head(u8, "head8"), 8), (self.head(u16, "head16"), 16)]
        if "head32_obj.w" in self.w:
            outputs.append((self.head(p32, "head32"), 32))
        return outputs

    def decode(self, outputs, width: int, height: int):
        boxes_all = []
        scores_all = []
        for (obj, box), stride in outputs:
            score = sigmoid(obj)
            ys, xs = np.where(score >= self.cfg.score_threshold)
            if len(xs) == 0:
                continue
            tx = box[ys, xs, 0]
            ty = box[ys, xs, 1]
            tw = np.clip(box[ys, xs, 2], -8.0, 8.0)
            th = np.clip(box[ys, xs, 3], -8.0, 8.0)
            bw = np.exp(tw) * stride
            bh = np.exp(th) * stride
            cx = (xs.astype(np.float32) + tx) * stride
            cy = (ys.astype(np.float32) + ty) * stride
            boxes = np.stack([cx - bw * 0.5, cy - bh * 0.5, cx + bw * 0.5, cy + bh * 0.5], axis=1)
            boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, width - 1)
            boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, height - 1)
            boxes_all.append(boxes)
            scores_all.append(score[ys, xs])
        if not boxes_all:
            return []
        boxes = np.concatenate(boxes_all).astype(np.float32)
        scores = np.concatenate(scores_all).astype(np.float32)
        keep = nms(boxes, scores, self.cfg.nms_threshold, self.cfg.topk)
        return [
            {
                "bbox": [float(boxes[i, 0]), float(boxes[i, 1]), float(boxes[i, 2]), float(boxes[i, 3])],
                "score": float(scores[i]),
            }
            for i in keep
        ]

    def detect(self, bgr: np.ndarray):
        image, sx, sy = resize_for_detector(bgr, self.cfg.resize_width)
        outputs = self.forward(image)
        dets = self.decode(outputs, image.shape[1], image.shape[0])
        for det in dets:
            x1, y1, x2, y2 = det["bbox"]
            det["bbox"] = [x1 * sx, y1 * sy, x2 * sx, y2 * sy]
        return dets


def choose_jump(video_fps: float, cfg: Config) -> int:
    jump = max(1, cfg.default_jump)
    if video_fps <= 0 or not math.isfinite(video_fps):
        return jump
    while jump > 1 and video_fps / jump < cfg.min_effective_fps:
        jump -= 1
    while video_fps / jump > cfg.max_effective_fps:
        jump += 1
    return max(1, jump)


@dataclass
class Track:
    track_id: int
    box: np.ndarray
    missed: int = 0
    seq_id: int = 0


@dataclass
class Sequence:
    seq_id: int
    track_id: int
    frame_size: tuple[int, int]
    frames: list[dict] = field(default_factory=list)
    crops: list[np.ndarray] = field(default_factory=list)


def rect_inter(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return [x1, y1, max(0, x2 - x1), max(0, y2 - y1)]


def is_sequence_moving(width: int, height: int, rects: list[list[int]], cfg: Config) -> bool:
    if not rects:
        return False
    centers_x = [r[0] + r[2] // 2 for r in rects if r[2] > 0 and r[3] > 0]
    centers_y = [r[1] + r[3] // 2 for r in rects if r[2] > 0 and r[3] > 0]
    widths = [r[2] for r in rects if r[2] > 0 and r[3] > 0]
    heights = [r[3] for r in rects if r[2] > 0 and r[3] > 0]
    if not widths:
        return False
    common = rects[0]
    for r1 in rects:
        common = rect_inter(common, r1)
        for r2 in rects:
            inter = rect_inter(r1, r2)
            change = 1.0 - min(
                inter[2] * inter[3] / max(1, r1[2] * r1[3]),
                inter[2] * inter[3] / max(1, r2[2] * r2[3]),
            )
            if change > cfg.moving_pair_change_threshold:
                return True
    avg_w = sum(widths) / len(widths)
    avg_h = sum(heights) / len(heights)
    if common[2] < avg_w * cfg.moving_scale_threshold or common[3] < avg_h * cfg.moving_scale_threshold:
        return True
    scale_x = (max(centers_x) - min(centers_x)) / max(avg_w, 1)
    scale_y = (max(centers_y) - min(centers_y)) / max(avg_h, 1)
    if scale_y < 0.1:
        top_y = min(r[1] for r in rects)
        bottom_y = max(r[1] + r[3] for r in rects)
        tap = height // 20
        if top_y > tap and bottom_y < height - tap:
            return False
    return not (scale_x < cfg.moving_scale_threshold and scale_y < cfg.moving_scale_threshold)


def enlarge_box(box, ratio: float, width: int, height: int):
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    x1 -= bw * ratio * 0.5
    y1 -= bh * ratio * 0.5
    x2 += bw * ratio * 0.5
    y2 += bh * ratio * 0.5
    x1 = max(0, int(math.floor(x1)))
    y1 = max(0, int(math.floor(y1)))
    x2 = min(width, int(math.ceil(x2)))
    y2 = min(height, int(math.ceil(y2)))
    return [x1, y1, max(0, x2 - x1), max(0, y2 - y1)]


def write_sequence(output_dir: Path, video_stem: str, seq: Sequence, cfg: Config) -> bool:
    if len(seq.frames) < cfg.min_frames:
        return False
    det_rects = [f["det"] for f in seq.frames]
    if not is_sequence_moving(seq.frame_size[0], seq.frame_size[1], det_rects, cfg):
        return False
    seq_dir = output_dir / f"{video_stem}_seq{seq.seq_id:06d}_track{seq.track_id:06d}"
    seq_dir.mkdir(parents=True, exist_ok=True)
    with (seq_dir / "meta.txt").open("w", encoding="utf-8") as f:
        f.write(f"sequence_id={seq.seq_id}\ntrack_id={seq.track_id}\nframes={len(seq.frames)}\n")
        f.write("columns=frame_id score det_x det_y det_w det_h crop_x crop_y crop_w crop_h crop_file\n")
        for item, crop in zip(seq.frames, seq.crops):
            name = f"frame_{item['frame_id']:06d}.jpg"
            cv2.imwrite(str(seq_dir / name), crop)
            det = item["det"]
            crop_box = item["crop"]
            f.write(
                f"{item['frame_id']} {item['score']:.6f} "
                f"{det[0]} {det[1]} {det[2]} {det[3]} "
                f"{crop_box[0]} {crop_box[1]} {crop_box[2]} {crop_box[3]} {name}\n"
            )
    return True


def run_video(path: Path, cfg: Config):
    detector = PersonDetectorNumpy(cfg)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(path)
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    jump = choose_jump(fps, cfg)
    output_dir = Path(f"{path.stem}_gait_sequences")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"video_fps={fps:.3f} jump={jump} effective_fps={(fps / jump) if fps > 0 else 0:.3f} output_dir={output_dir}")

    tracks: list[Track] = []
    seqs: dict[int, Sequence] = {}
    next_track_id = 1
    next_seq_id = 1
    saved = 0
    static_filtered = 0
    frame_id = 0
    processed = 0
    t0 = time.perf_counter()

    def finish_track(track: Track):
        nonlocal saved, static_filtered
        seq = seqs.pop(track.seq_id, None)
        if seq is None:
            return
        if write_sequence(output_dir, path.stem, seq, cfg):
            saved += 1
        elif len(seq.frames) >= cfg.min_frames:
            static_filtered += 1

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_id += 1
        if (frame_id - 1) % jump != 0:
            continue
        processed += 1
        h, w = frame.shape[:2]
        dets = []
        for det in detector.detect(frame):
            x1, y1, x2, y2 = det["bbox"]
            bw, bh = x2 - x1, y2 - y1
            if bw < cfg.min_box_width or bh < cfg.min_box_height:
                continue
            dets.append({"box": np.array([x1, y1, x2, y2], dtype=np.float32), "score": det["score"]})

        matched_tracks = set()
        matched_dets = set()
        if tracks and dets:
            tb = np.stack([t.box for t in tracks])
            db = np.stack([d["box"] for d in dets])
            pairs = []
            ious = iou_xyxy(tb, db)
            for ti in range(ious.shape[0]):
                for di in range(ious.shape[1]):
                    if ious[ti, di] >= cfg.match_iou:
                        pairs.append((float(ious[ti, di]), ti, di))
            pairs.sort(reverse=True)
            for _, ti, di in pairs:
                if ti in matched_tracks or di in matched_dets:
                    continue
                matched_tracks.add(ti)
                matched_dets.add(di)
                tracks[ti].box = dets[di]["box"]
                tracks[ti].missed = 0
                append_sequence_frame(seqs[tracks[ti].seq_id], frame, frame_id, dets[di], cfg)

        for ti, track in enumerate(tracks):
            if ti not in matched_tracks:
                track.missed += 1

        for di, det in enumerate(dets):
            if di in matched_dets:
                continue
            seq_id = next_seq_id
            next_seq_id += 1
            track = Track(next_track_id, det["box"], 0, seq_id)
            next_track_id += 1
            tracks.append(track)
            seqs[seq_id] = Sequence(seq_id, track.track_id, (w, h))
            append_sequence_frame(seqs[seq_id], frame, frame_id, det, cfg)

        alive = []
        for track in tracks:
            if track.missed > cfg.max_age:
                finish_track(track)
            else:
                alive.append(track)
        tracks = alive

        if processed % 20 == 0:
            dt = time.perf_counter() - t0
            print(f"processed={processed} frame={frame_id} active_tracks={len(tracks)} saved_sequences={saved} static_filtered={static_filtered} fps={processed / max(dt, 1e-6):.2f}")

    for track in tracks:
        finish_track(track)
    dt = time.perf_counter() - t0
    print(f"done processed={processed} saved_sequences={saved} static_filtered={static_filtered} time_sec={dt:.2f} fps={processed / max(dt, 1e-6):.2f}")


def append_sequence_frame(seq: Sequence, frame: np.ndarray, frame_id: int, det: dict, cfg: Config):
    if len(seq.frames) >= cfg.max_frames:
        return
    h, w = frame.shape[:2]
    box = det["box"]
    det_rect = [int(round(box[0])), int(round(box[1])), int(round(box[2] - box[0])), int(round(box[3] - box[1]))]
    crop_rect = enlarge_box(box, cfg.enlarge, w, h)
    if crop_rect[2] <= 0 or crop_rect[3] <= 0:
        return
    x, y, cw, ch = crop_rect
    seq.frames.append({"frame_id": frame_id, "score": det["score"], "det": det_rect, "crop": crop_rect})
    seq.crops.append(frame[y : y + ch, x : x + cw].copy())


def run_image(path: Path, cfg: Config):
    detector = PersonDetectorNumpy(cfg)
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(path)
    t0 = time.perf_counter()
    dets = detector.detect(image)
    ms = (time.perf_counter() - t0) * 1000
    out = image.copy()
    for det in dets:
        x1, y1, x2, y2 = [int(round(v)) for v in det["bbox"]]
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(out, f"{det['score']:.2f}", (x1, max(0, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    out_path = path.with_name(path.stem + "_numpy_det.jpg")
    cv2.imwrite(str(out_path), out)
    print(f"detections={len(dets)} time={ms:.2f}ms output={out_path}")
