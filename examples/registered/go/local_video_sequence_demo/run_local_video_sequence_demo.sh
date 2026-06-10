#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /path/to/video.mp4" >&2
  exit 2
fi

cd "$(dirname "$0")"
video_path="$1"
video_abs="$(cd "$(dirname "$video_path")" && pwd)/$(basename "$video_path")"
video_stem="$(basename "$video_path")"
video_stem="${video_stem%.*}"

# The local detector is C++ for speed and model compatibility. The upload path
# below still uses the Go registered Sequence API demo.
detector_dir="$(pwd)/cpp_detector"
sequence_demo_dir="$(cd ../sequence_demo && pwd)"
sequence_root="$detector_dir/${video_stem}_gait_sequences"

cmake -S "$detector_dir" -B "$detector_dir/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$detector_dir/build" -j
"$detector_dir/build/local_video_sequence_extractor" "$video_abs"

if [[ ! -d "$sequence_root" ]]; then
  echo "sequence output not found: $sequence_root" >&2
  exit 1
fi

"$sequence_demo_dir/build.sh"

found=0
while IFS= read -r -d '' seq_dir; do
  found=1
  echo "uploading sequence: $seq_dir"
  GAIT_SEQUENCE_DIR="$seq_dir" "$sequence_demo_dir/registered_sequence_demo"
done < <(find "$sequence_root" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

if [[ "$found" -eq 0 ]]; then
  echo "no sequence folders generated under $sequence_root" >&2
  exit 1
fi
