#!/usr/bin/env python3
"""
Anonymous x402 local video-to-sequence demo.

Input is a local video file. The demo first extracts person sequence folders on
the client CPU, then uploads every extracted sequence folder to the public
Sequence API and pays with x402.
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

import anonymous_sequence_and_video_x402_demo  # noqa: E402
from persondet_numpy import Config, run_video  # noqa: E402


OUTPUT_ROOT = Path(os.environ.get("GAIT_LOCAL_SEQUENCE_OUTPUT", CURRENT_DIR / "output"))


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} video.mp4", file=sys.stderr)
        return 2
    video_path = Path(sys.argv[1]).expanduser().resolve()
    if not video_path.is_file():
        print(f"video file not found: {video_path}", file=sys.stderr)
        return 2

    private_key = anonymous_sequence_and_video_x402_demo.load_private_key()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    old_cwd = Path.cwd()
    try:
        os.chdir(OUTPUT_ROOT)
        run_video(video_path, Config())
    finally:
        os.chdir(old_cwd)

    sequence_root = OUTPUT_ROOT / f"{video_path.stem}_gait_sequences"
    seq_dirs = anonymous_sequence_and_video_x402_demo.collect_leaf_sequence_dirs(sequence_root)
    if not seq_dirs:
        print(f"no sequence folders generated under {sequence_root}", file=sys.stderr)
        return 1

    anonymous_sequence_and_video_x402_demo.RESULT_DIR.mkdir(parents=True, exist_ok=True)
    anonymous_sequence_and_video_x402_demo.check_api_health()
    with requests.Session() as session:
        for index, seq_dir in enumerate(seq_dirs, start=1):
            print(f"[local anonymous sequence {index}/{len(seq_dirs)}] {seq_dir}")
            result = anonymous_sequence_and_video_x402_demo.run_public_sequence_x402(session, private_key, seq_dir)
            out_path = anonymous_sequence_and_video_x402_demo.RESULT_DIR / "local_video_sequence" / f"{seq_dir.name}.json"
            anonymous_sequence_and_video_x402_demo.write_json(out_path, result)
            print(f"uploaded_sequence={seq_dir} result_file={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
