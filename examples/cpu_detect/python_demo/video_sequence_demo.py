from __future__ import annotations

import sys
from pathlib import Path

from persondet_numpy import Config, run_video


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} video.mp4", file=sys.stderr)
        raise SystemExit(1)
    run_video(Path(sys.argv[1]), Config())


if __name__ == "__main__":
    main()
