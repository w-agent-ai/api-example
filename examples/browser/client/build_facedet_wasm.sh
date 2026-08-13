#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v em++ >/dev/null 2>&1; then
  cat >&2 <<'EOF'
em++ not found.

Install and activate Emscripten first:
  git clone https://github.com/emscripten-core/emsdk.git /opt/emsdk
  /opt/emsdk/emsdk install 3.1.64
  /opt/emsdk/emsdk activate 3.1.64
  source /opt/emsdk/emsdk_env.sh
EOF
  exit 1
fi

face_src="../../registered/cpp/face_feature_demo/third_party/libfacedetection/src"

em++ \
  -std=c++17 \
  -O3 \
  -flto \
  -s WASM=1 \
  -s MODULARIZE=1 \
  -s EXPORT_NAME=createFaceDetWasmModule \
  -s ENVIRONMENT=web,worker \
  -s ALLOW_MEMORY_GROWTH=1 \
  -s FILESYSTEM=0 \
  -s EXPORTED_FUNCTIONS='["_malloc","_free","_facedet_create","_facedet_destroy","_facedet_detect_rgba","_facedet_results"]' \
  -s EXPORTED_RUNTIME_METHODS='["cwrap","getValue","HEAPU8","HEAPF32"]' \
  -I"$face_src" \
  facedet_wasm_bindings.cpp \
  "$face_src/facedetectcnn.cpp" \
  "$face_src/facedetectcnn-data.cpp" \
  "$face_src/facedetectcnn-model.cpp" \
  -o facedet_wasm.js

echo "built: $(pwd)/facedet_wasm.js"
echo "built: $(pwd)/facedet_wasm.wasm"
