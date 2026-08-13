#!/usr/bin/env python3
"""
Registered-user local video-to-human-keypoints demo.

Input is a local video file. The demo detects and tracks people locally, writes
one sequence folder per person, then calls the registered Gait Pose API for each
sequence folder.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

CURRENT_DIR = Path(__file__).resolve().parent
PYTHON_DEMO_DIR = CURRENT_DIR.parent
sys.path.insert(0, str(PYTHON_DEMO_DIR))
sys.path.insert(0, str(CURRENT_DIR))

import gait_pose_api_demo  # noqa: E402
from persondet_numpy import Config, run_video  # noqa: E402


# Local tracking output. The detector writes one folder per completed track.
OUTPUT_ROOT = Path("./output")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} video.mp4", file=sys.stderr)
        return 2
    video_path = Path(sys.argv[1]).expanduser().resolve()
    if not video_path.is_file():
        print(f"video file not found: {video_path}", file=sys.stderr)
        return 2

    api_key = gait_pose_api_demo.load_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    old_cwd = Path.cwd()
    try:
        # run_video performs local CPU detection and tracking with gait_detect.onnx.
        # No API call or billing happens until sequence folders are uploaded below.
        os.chdir(OUTPUT_ROOT)
        run_video(video_path, Config())
    finally:
        os.chdir(old_cwd)

    # Only leaf folders that contain images are uploaded as person sequences.
    sequence_root = OUTPUT_ROOT / f"{video_path.stem}_gait_sequences"
    seq_dirs = gait_pose_api_demo.collect_leaf_sequence_dirs(sequence_root)
    if not seq_dirs:
        print(f"no sequence folders generated under {sequence_root}", file=sys.stderr)
        return 1

    out_dir = gait_pose_api_demo.RESULT_DIR / "local_video_gait_pose"
    out_dir.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        for index, seq_dir in enumerate(seq_dirs, start=1):
            print(f"[local gait-pose sequence {index}/{len(seq_dirs)}] {seq_dir}")
            # Each local track is charged as one registered human keypoint API call.
            result = gait_pose_api_demo.run_registered_gait_pose(session, headers, seq_dir)
            out_path = out_dir / f"{seq_dir.name}.json"
            gait_pose_api_demo.write_json(out_path, result)
            print(f"pose_sequence={seq_dir} result_file={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
