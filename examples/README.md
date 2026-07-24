# W-Agent API demos

This directory separates API demos by caller type, and download packages are
grouped by language. Inside each language package, the three input modes are
parallel:

```text
1. Sequence input: upload an already tracked person image sequence.
2. Video input: upload a full video directly to the Video API.
3. Local video-to-sequence input: process a video locally, then upload the
   extracted person sequence folders to the Sequence API.
```

- `registered/`: registered users who call APIs with an API Key.
- `anonymous/`: anonymous agents who call public APIs with x402 payment.
- `trial/`: no-registration browser trial demos limited by server-side IP quota.
- `browser/`: standalone browser clients for no-registration trial and local
  visual demos. Registered-user ZIP packages no longer include these browser
  client files; use the Python, C++, or Go packages for registered API-Key
  integration examples.
- `registered/python/local_video_to_sequence_demo/`: Python local video-to-sequence
  demo for registered users.
- `registered/cpp/local_video_to_sequence_demo/`: C++ local video-to-sequence demo
  for registered users.
- `registered/go/local_video_to_sequence_demo/`: Go orchestration demo that runs
  local video-to-sequence preprocessing and uploads with the Go Sequence API
  demo.
- `anonymous/python/local_video_to_sequence_demo/`: Python local video-to-sequence
  demo for anonymous x402 calls.
- `browser/client/`: pure browser client used by the trial/browser download
  entrypoints.

## Registered User

Registered-user APIs use a normal API Key:

```http
Authorization: Bearer <api_key>
```

Set your registered API Key before running registered-user demos:

```bash
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
```

Base URL:

- Mainland China: `https://www.w-agent.cn/api`
- Overseas entry: `https://www.h-agent.ai/api`
- Overseas redirects to `w-agent.cn` are expected.
- Do not guess `https://api.w-agent.cn`; that hostname is not documented and may
  fail TLS hostname verification.

## Choose The Right Demo

Choose by task intent:

- Same-person identity comparison: use sequence parsing and compare
  `gait_feature`, `face_feature`, or `reid_feature` with same-type dot product.
  Do not use raw image similarity for identity.
- Video to stable person sequences: use `local_video_to_sequence_demo` first.
  It runs local detection/tracking/cropping, writes sequence folders, then calls
  the Sequence API.
- 2D/3D human keypoints: upload sequence frames first, then call
  `POST /v1/sequences/{task_id}/gait-pose`.
- Single-image text search: use `object_search_api_demo.py`.
- Registered calls use `Authorization: Bearer <api_key>` and registered routes.
- Anonymous calls use public routes, receive HTTP 402, sign an x402 payment, and
  retry the same HTTP request.

W-Agent's core identity and pose input is a tracked person sequence. A video is
usually a source from which sequences are generated.

## Input Mode 1: Sequence Input

Use this when the client already has tracked/cropped person image sequences.
Each sequence folder is uploaded to the Sequence API.
The server runs `GetSplitSeqFeature`, so one uploaded track can return multiple
single-person results in `sequences` when tracking mixed different people or
contains stray frames.

Input requirements:

- Use one tracked person sequence per folder, ordered by time.
- Person crops are recommended. Full surveillance frames with multiple people
  are not the intended input.
- Keep enough moving-person frames; very short or static tracks can return
  empty results or validation errors.
- If local crops need to be mapped back to the original video, keep crop
  metadata beside the frames.

Registered-user examples:

```bash
python3 examples/registered/python/sequence_and_video_api_demo.py
python3 examples/registered/python/sequence_similarity_demo.py examples/sample_sequences
cd examples/registered/go/sequence_demo && ./build.sh && ./registered_sequence_demo
cd examples/registered/cpp/sequence_demo && ./build.sh && ./build/registered_sequence_demo
```

Anonymous x402 example:

```bash
python3 examples/anonymous/python/anonymous_sequence_x402_demo.py
```

## Input Mode 2: Video Input

Use this when the client wants to upload a full video directly. The service
does server-side detection, tracking, gait sequence parsing, and result generation.

Registered-user examples:

```bash
python3 examples/registered/python/sequence_and_video_api_demo.py
cd examples/registered/go/video_demo && ./build.sh && ./registered_video_demo
cd examples/registered/cpp/video_demo && ./build.sh && ./build/registered_video_demo
```

Anonymous x402 example:

```bash
python3 examples/anonymous/python/anonymous_sequence_and_video_x402_demo.py
```

## Input Mode 3: Local Video To Sequence

If a client wants to process videos locally and only upload tracked person
sequence images to W-Agent, use the local video-to-sequence demo inside the
chosen language package. It extracts person sequence folders from a video, then
uploads those folders with the Sequence API.

```bash
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
./examples/registered/cpp/local_video_to_sequence_demo/run_local_video_to_sequence_api_demo.sh /path/to/video.mp4
./examples/registered/go/local_video_to_sequence_demo/run_local_video_to_sequence_api_demo.sh /path/to/video.mp4
python3 examples/anonymous/python/local_video_to_sequence_demo/local_video_to_sequence_x402_demo.py /path/to/video.mp4
```

Each local demo writes one folder per detected person sequence and then uploads
the generated sequence folders.

### Task Quickstart: Video To Each Person's 2D/3D Keypoints

When the user has a video and wants keypoints for every person sequence, use the
local video-to-sequence demo first and call Gait Pose per generated sequence:

1. Run the registered Python local video-to-sequence demo.
2. Let it generate one sequence folder per tracked person.
3. Upload each sequence folder to the Sequence API.
4. Call `POST /v1/sequences/{task_id}/gait-pose` for each sequence.
5. Save `result.json`, `pose_2d.csv`, and `pose_3d.csv` beside that sequence's frames.

```bash
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

Do not upload a multi-person video and expect video parsing to return complete
per-person `pose_2ds` / `pose_3ds`. Gait Pose is a sequence API.

Gait Pose coordinate rules:

- `pose_2ds[i]` and `pose_3ds[i]` correspond to the uploaded sequence frame at
  the same ordered position unless returned frame mapping says otherwise.
- Coordinates are relative to the uploaded sequence image, not the original
  full video frame.
- If frames are crops, map 2D points back to original video coordinates with
  local `crop_x` and `crop_y`.

Recommended output shape for agents:

```text
output/
  video_name/
    sequence_xxx/
      frame_000001.jpg
      frame_000002.jpg
      meta.txt              # crop/frame mapping from local preprocessing
      result.json           # sequence parse or gait-pose API response
      pose_2d.csv           # optional, for gait-pose output
      pose_3d.csv           # optional, for gait-pose output
    summary.csv
```

Keep the sequence frames and the corresponding API result JSON in the same
folder. If one uploaded track returns multiple split `sequences[]`, save each
split result as its own output sequence.

## Language Packages

### Python

The Python registered-user demo processes all leaf sequence directories under
`examples/sample_sequences` and all videos under `examples/video`, then writes JSON results
and feature similarity reports under `tmp/registered_batch_results`.

Result JSON includes `emotions` when the SDK returns them. Sequence parsing no
longer embeds `pose_2ds` or `pose_3ds`; those keypoints are provided only by
the standalone `POST /v1/sequences/{task_id}/gait-pose` API.

Similarity reports first compute dot-product scores for `gait_feature`,
`reid_feature`, and `face_feature`, then fuse the three scores into
`fused_similarity`. The default same-person threshold is `0.7`; scores above
`0.7` are usually likely to be the same person.

Feature vectors live under `response.sequences[]`, not at the top level. For
example: `response.sequences[0].gait_feature`. Compare only same-type vectors:
gait to gait, face to face, and ReID to ReID. `face_feature` can be empty when
no usable face is detected; this is not an API failure.

The registered sequence demos also call `POST /v1/sequences/{task_id}/gait-pose`
after uploading frames. Gait Pose is a standalone billable API, currently
priced separately from full gait sequence parsing at `¥0.01 / sequence`.

Gait Pose coordinate notes:

- `pose_2ds` outer array is frames; each frame is `3*17` COCO-order floats:
  `x0,y0,score0...x16,y16,score16`.
- `pose_3ds` outer array is frames; each frame is `3*17` H36M-order floats:
  `x0,y0,z0...x16,y16,z16`.
- Coordinates are relative to the uploaded sequence image. If the sequence
  image is a crop from a video, use crop metadata from the local demo to map
  points back to the original video frame.

```bash
python3 examples/registered/python/sequence_and_video_api_demo.py
```

For a compact local-folder-to-CSV identity comparison:

```bash
python3 examples/registered/python/sequence_similarity_demo.py examples/sample_sequences
```

Minimal Object Search runnable example:

```bash
python3 examples/registered/python/object_search_api_demo.py examples/sample_sequences/ID_0001/001811.jpg 'person'
```

Object Search rules:

- The demo sends raw base64 without a `data:image/...;base64,` prefix.
- JPEG and PNG are the safest formats.
- Prompts can be Chinese or English when the configured upstream model supports them.
- `boxes` are pixel coordinates in the uploaded image.
- No match returns `boxes: []`, not an error.
- `label` is generated by the upstream model and is not a fixed category list.

The MCP demo calls the integrated `/mcp` JSON-RPC endpoint directly. It lists
available MCP tools, reads service metadata, creates a sequence task, uploads
sequence frames through MCP, runs standalone human 2D/3D keypoints, parses the
sequence, fetches the stored result, and creates a video task. Set `API_KEY` in
the script before running it.

MCP task tools are for registered API Key users. Anonymous x402 payment uses
the public HTTP APIs and the anonymous Python x402 demos below, not the MCP
JSON-RPC tool flow.

```bash
python3 examples/registered/python/mcp_api_demo.py
```

### Go

The Go package contains registered-user sequence and video API demos. Its
`local_video_to_sequence_demo` runs local preprocessing first, then uploads the
generated sequence folders with the Go sequence demo.

```bash
cd examples/registered/go/sequence_demo
./build.sh
./registered_sequence_demo
```

```bash
cd examples/registered/go/video_demo
./build.sh
./registered_video_demo
```

### C++

The C++ package contains registered-user sequence and video API demos plus the
CPU video-to-sequence preprocessing source. API demos require `libcurl` and
`nlohmann/json`.

```bash
sudo apt-get install -y libcurl4-openssl-dev nlohmann-json3-dev
cd examples/registered/cpp/sequence_demo
./build.sh
./build/registered_sequence_demo
```

```bash
cd examples/registered/cpp/video_demo
./build.sh
./build/registered_video_demo
```

## Anonymous Agent

Anonymous public APIs do not use an API Key. The client receives HTTP 402,
signs an x402 payment payload with an EVM wallet private key, and retries the
same operation with payment headers.

Current anonymous demos are Python only:

```bash
python3 examples/anonymous/python/anonymous_sequence_and_video_x402_demo.py
```

```bash
python3 examples/anonymous/python/anonymous_sequence_x402_demo.py
```

Other languages can call the same public HTTP APIs, but they need compatible
x402 signing support for the accepted EVM payment methods.

Current anonymous x402 payment routes:

| Network | Currency | Method |
|---|---|---|
| Base Mainnet | USDC | EIP-3009 |
| Polygon Mainnet | USDC | EIP-3009 |
| Arbitrum One | USDC | EIP-3009 |
| Base Mainnet | USDT | Permit2 |
| Polygon Mainnet | USDT | Permit2 |
| Arbitrum One | USDT | Permit2 |
| Base Mainnet | EURC | EIP-3009, converted from USD by the server EURC rate |
