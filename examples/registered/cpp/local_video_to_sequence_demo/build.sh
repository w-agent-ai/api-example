#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
echo "built: $(pwd)/build/local_video_sequence_extractor"
echo "built: $(pwd)/build/local_video_to_gait_api_demo"
