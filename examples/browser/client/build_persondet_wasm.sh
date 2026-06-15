#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v em++ >/dev/null 2>&1; then
  cat >&2 <<'EOF'
em++ not found.

Install and activate Emscripten first:
  git clone https://github.com/emscripten-core/emsdk.git /opt/emsdk
  /opt/emsdk/emsdk install latest
  /opt/emsdk/emsdk activate latest
  source /opt/emsdk/emsdk_env.sh
EOF
  exit 1
fi

cpp_src="../../registered/cpp/local_video_to_sequence_demo"

em++ \
  -std=c++17 \
  -O3 \
  -flto \
  -msimd128 \
  -s WASM=1 \
  -s MODULARIZE=1 \
  -s EXPORT_NAME=createPersonDetWasmModule \
  -s ENVIRONMENT=web,worker \
  -s ALLOW_MEMORY_GROWTH=1 \
  -s FILESYSTEM=0 \
  -s EXPORTED_FUNCTIONS='["_malloc","_free","_persondet_create","_persondet_destroy","_persondet_detect_rgba","_persondet_results"]' \
  -s EXPORTED_RUNTIME_METHODS='["cwrap","getValue","HEAPU8","HEAPF32"]' \
  -I"$cpp_src" \
  persondet_wasm_bindings.cpp \
  "$cpp_src/persondet.cpp" \
  "$cpp_src/persondet_weights.cpp" \
  -o persondet_wasm.js

echo "built: $(pwd)/persondet_wasm.js"
echo "built: $(pwd)/persondet_wasm.wasm"
