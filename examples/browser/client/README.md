# W-Agent Browser Client

Open `index.html` directly in a browser.

The browser client is one usage method. It is not tied to only trial usage:

- Trial mode: no API key, consumes no-registration trial quota.
- Registered mode: uses `Authorization: Bearer <api_key>`.

Current browser capabilities:

- 图搜万物: image + text prompt, calls `/v1/object-search` or `/v1/public/object-search/trial`.
- Sequence Parse: select multiple ordered image frames.
- Gait Pose: select multiple ordered image frames.
- Local video-to-sequence: select one local video. The browser decodes frames,
  runs lightweight `persondet`, tracks people with IoU matching, crops all valid
  sequences, and uploads each sequence to the Sequence API.

图搜万物 uses the same prompt examples as the public home page:
`猫、公交车、穿红衣服的人` in Chinese and `cat, bus, person in red` in English.
For one selected 图搜万物 image, the file picker shows only the filename; for
multi-file capabilities it shows the first filename and the total file count.

Files:

- `index.html`: UI and API calls.
- `persondet.js`: detector backend selection, JavaScript fallback detector, IoU
  tracking, sequence filtering, and crop export.
- `persondet_weights.js`: generated weights from the Python/C++ demo.
- `persondet_wasm_bindings.cpp`: C ABI wrapper for the C++ detector.
- `build_persondet_wasm.sh`: builds `persondet_wasm.js` and
  `persondet_wasm.wasm` with Emscripten `-O3 -flto -msimd128`.
- `persondet_wasm.js` / `persondet_wasm.wasm`: prebuilt WASM + SIMD detector
  produced by the build script when available.

`/portal/demo-download?type=browser` returns a single HTML file with
`persondet.js` and `persondet_weights.js` embedded. If `persondet_wasm.js` and
`persondet_wasm.wasm` have been built, they are embedded too. The source package
keeps files separate for maintainability.

Build the WASM + SIMD backend:

```bash
cd examples/browser/client
./build_persondet_wasm.sh
```

The browser prefers WASM + SIMD when present and falls back to pure JavaScript
when the WASM files are missing or unsupported. WASM uses the same C++ detector
source as the native local preprocessing demo and does not use ONNX.

Pose display notes:

- `pose_2ds` and `pose_3ds` are returned only by the standalone `gait-pose`
  API.
- `pose_2ds` uses COCO-order `x, y, score` repeated 17 times per frame with
  image-center origin. The browser draws it on a normal canvas as
  `canvas_x = image_width / 2 + x`, `canvas_y = image_height / 2 + y`.
- `pose_3ds` uses H36M-order `x, y, z` repeated 17 times per frame with the
  center as the origin for browser-side rendering.
- The browser draws point indexes on 2D/3D results. The 2D and 3D skeleton edge
  lists can be edited in the result panel as `a-b` pairs, which is useful when
  validating or changing keypoint order definitions.
- Default 2D COCO edges are
  `0-1,0-2,1-3,2-4,5-7,7-9,6-8,8-10,5-6,5-11,6-12,11-13,13-15,12-14,14-16`.
- Default 3D H36M edges are
  `0-1,1-2,2-3,0-4,4-5,5-6,0-7,7-8,8-9,8-11,8-14,9-10,11-12,12-13,14-15,15-16`.
