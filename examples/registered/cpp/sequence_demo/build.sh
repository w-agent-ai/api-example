#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
cmake -S . -B build
cmake --build build
echo "built: $(pwd)/build/registered_sequence_demo"
