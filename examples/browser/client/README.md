# W-Agent Browser Client

Open `index.html` directly in a browser.

The browser client is one usage method. It is not tied to only trial usage:

- Trial mode: no API key, consumes no-registration trial quota.
- Registered mode: uses `Authorization: Bearer <api_key>`.

Current downloadable browser clients:

- Gait Pose: select one local video, extract local person sequences, then call
  the standalone `gait-pose` API for selected sequences. The browser renders
  the returned `pose_2ds` into a local 2D video and renders `pose_3ds` on canvas.
- Gait recognition: select two local videos, extract local person sequences,
  call sequence parsing for identity features, and compare selected sequences
  from video 1 against one or more selected sequences from video 2.
- Local video-to-sequence: the browser decodes frames, runs lightweight
  `persondet`, tracks people with IoU matching, crops all valid sequences, and
  uploads each sequence to the relevant API.
- 图搜万物 runs directly on the website playground and does not have a browser
  client download.

Default local extraction settings are independent by tool:

- Gait Pose: parse every 1 frame, keep static sequences, minimum person box
  64x128, minimum sequence length 20 frames.
- Gait recognition: parse every 3 frames, filter static sequences, minimum
  person box 64x128, minimum sequence length 20 frames.

The Settings dialog stores Gait Pose and Gait recognition settings separately
in browser local storage and, when a cache directory is selected, in
`w_agent.json`.

Billing prompts:

- Manual mode asks for confirmation before uploading sequences and shows the
  estimated sequence count and cost.
- Auto mode does not ask for confirmation, but shows the total cost after
  processing finishes.
- Trial usage messages include the remaining free quota. The "sign in" link
  opens `/portal#login` in a new tab so the current client page is not replaced.
- Sequence cards keep short in-progress text such as `API calling` and
  `Rendering video`.

Browser video decoding depends on the codec inside the file, not just the file
extension. H.264 MP4 is recommended. MP4 files encoded as `mp4v` / MPEG-4 Part 2
may fail to decode in Chrome, Edge, and other modern browsers. Convert them
before use:

```bash
ffmpeg -i input.mp4 -c:v libx264 -pix_fmt yuv420p -movflags +faststart -an output_h264.mp4
```

The language selector switches the browser client between Chinese and English
without reloading the page.

Files:

- `index.html`: UI and API calls.
- `persondet.js`: detector backend selection, ONNX Runtime Web detector,
  JavaScript fallback detector, IoU tracking, sequence filtering, and crop
  export.
- `gait_detect.onnx`: browser person detector model. The browser prefers
  official `onnxruntime-web` WASM inference with this model.
- `ort.wasm.min.js` / `ort-wasm-simd.wasm` / `ort-wasm.wasm`: local copy of
  official `onnxruntime-web` 1.18.0 runtime files. They are served from the
  same site instead of an external CDN.
- `persondet_weights.js`: generated JavaScript fallback weights converted from
  the C++ demo weights.
- `persondet_wasm_bindings.cpp`: C ABI wrapper for the C++ detector.
- `build_persondet_wasm.sh`: builds `persondet_wasm.js` and
  `persondet_wasm.wasm` with Emscripten `-O3 -flto -msimd128`.
- `persondet_wasm.js` / `persondet_wasm.wasm`: prebuilt WASM + SIMD detector
  produced by the build script when available.
- `facedet_wasm_bindings.cpp`: C ABI wrapper for Shiqi Yu's
  `libfacedetection`, returning face boxes and five landmarks.
- `build_facedet_wasm.sh`: builds `facedet_wasm.js` and
  `facedet_wasm.wasm` with Emscripten. The portal homepage uses these files for
  face candidate detection before browser-side alignment and `/v1/features/face`.

`/portal/demo-download?type=browser-pose&open=1` opens the standalone Gait Pose
browser client inline. `/portal/demo-download?type=browser-gait&open=1` opens the
standalone Gait Recognition browser client inline. The online `open=1` page
serves ONNX Runtime Web and the ONNX model from `/portal/browser-assets`,
embeds the old C++ WASM detector as fallback, and intentionally omits
`persondet_weights.js` so browsers do not parse the large JavaScript fallback
weights when ONNX/WASM is available. Without `open=1`, the same routes return
downloadable HTML attachments with `persondet.js`, `persondet_weights.js`, and
the old detector WASM embedded for compatibility; if ORT/ONNX files are not next
to the downloaded HTML, the page falls back to the embedded detector.

Build the WASM + SIMD backend:

```bash
cd examples/browser/client
./build_persondet_wasm.sh
./build_facedet_wasm.sh
```

The browser prefers ONNX Runtime Web + WASM when present, falls back to the
native C++ detector compiled to WASM, and then falls back to pure JavaScript
weights when the WASM files are missing or unsupported.

When replacing the primary detector model, replace `gait_detect.onnx` in the
browser client and Python local video-to-sequence demo folders. The old
`persondet_weights.js` file is only a browser fallback for environments where
ONNX Runtime Web and native WASM are unavailable.

The current detector defaults are `score_threshold = 0.35` and
`nms_threshold = 0.50`.

Pose display notes:

- `pose_2ds` and `pose_3ds` are returned only by the standalone `gait-pose`
  API.
- `pose_2ds` uses COCO-order `x, y, score` repeated 17 times per frame with
  image-center origin. The browser draws it on a normal canvas as
  `canvas_x = image_width / 2 + x`, `canvas_y = image_height / 2 + y`.
- `pose_3ds` uses H36M-order `x, y, z` repeated 17 times per frame with the
  center as the origin for browser-side rendering.
- The browser draws 2D keypoints onto sequence frames, records them into a local
  WebM video with `MediaRecorder`, and renders 3D keypoints on a synchronized
  canvas without point indexes.
- Default 2D COCO edges are
  `0-1,0-2,1-3,2-4,5-7,7-9,6-8,8-10,5-6,5-11,6-12,11-13,13-15,12-14,14-16`.
- Default 3D H36M edges are
  `0-1,1-2,2-3,0-4,4-5,5-6,0-7,7-8,8-9,8-11,8-14,9-10,11-12,12-13,14-15,15-16`.
