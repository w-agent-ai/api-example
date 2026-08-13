#!/usr/bin/env python3
"""
Anonymous x402 local video-to-human-keypoints demo.

Input is a local video file. The demo detects and tracks people locally, writes
one sequence folder per person, then calls the public Gait Pose API for each
sequence folder with x402 payment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PYTHON_DEMO_DIR = CURRENT_DIR.parent
sys.path.insert(0, str(PYTHON_DEMO_DIR))
sys.path.insert(0, str(CURRENT_DIR))

import anonymous_gait_pose_x402_demo  # noqa: E402
from persondet_numpy import Config, run_video  # noqa: E402


OUTPUT_ROOT = Path("./output")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} video.mp4", file=sys.stderr)
        return 2
    video_path = Path(sys.argv[1]).expanduser().resolve()
    if not video_path.is_file():
        print(f"video file not found: {video_path}", file=sys.stderr)
        return 2

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    old_cwd = Path.cwd()
    try:
        os.chdir(OUTPUT_ROOT)
        run_video(video_path, Config())
    finally:
        os.chdir(old_cwd)

    sequence_root = OUTPUT_ROOT / f"{video_path.stem}_gait_sequences"
    seq_dirs = collect_leaf_sequence_dirs(sequence_root)
    if not seq_dirs:
        print(f"no sequence folders generated under {sequence_root}", file=sys.stderr)
        return 1

    for index, seq_dir in enumerate(seq_dirs, start=1):
        print(f"[local x402 gait-pose sequence {index}/{len(seq_dirs)}] {seq_dir}")
        anonymous_gait_pose_x402_demo.SEQ_DIR = seq_dir
        anonymous_gait_pose_x402_demo.main()
    return 0


def collect_leaf_sequence_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        if anonymous_gait_pose_x402_demo.collect_frames(path):
            child_dirs = [item for item in path.iterdir() if item.is_dir()]
            if not any(anonymous_gait_pose_x402_demo.collect_frames(child) for child in child_dirs):
                out.append(path)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
