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
- `registered/python/local_video_to_sequence_demo/`: Python local video-to-sequence
  demo for registered users.
- `registered/cpp/local_video_to_sequence_demo/`: C++ local video-to-sequence demo
  for registered users.
- `registered/go/local_video_to_sequence_demo/`: Go orchestration demo that runs
  local video-to-sequence preprocessing and uploads with the Go Sequence API
  demo.
- `anonymous/python/local_video_to_sequence_demo/`: Python local video-to-sequence
  demo for anonymous x402 calls.

## Registered User

Registered-user APIs use a normal API Key:

```http
Authorization: Bearer <api_key>
```

Set your registered API Key before running registered-user demos:

```bash
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
```

## Input Mode 1: Sequence Input

Use this when the client already has tracked/cropped person image sequences.
Each sequence folder is uploaded to the Sequence API.

Registered-user examples:

```bash
python3 examples/registered/python/sequence_and_video_api_demo.py
cd examples/registered/go/sequence_demo && ./build.sh && ./registered_sequence_demo
cd examples/registered/cpp/sequence_demo && ./build.sh && ./build/registered_sequence_demo
```

Anonymous x402 example:

```bash
python3 examples/anonymous/python/anonymous_sequence_x402_demo.py
```

## Input Mode 2: Video Input

Use this when the client wants to upload a full video directly. The service
does server-side detection, tracking, sequence parsing, and result generation.

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

## Language Packages

### Python

The Python registered-user demo processes all leaf sequence directories under
`examples/seqs` and all videos under `examples/video`, then writes JSON results
and feature similarity reports under `tmp/registered_batch_results`.

Result JSON may include `pose_2ds`, `pose_3ds`, and `emotions` when the SDK
returns them.

The registered sequence demos also call `POST /v1/sequences/{task_id}/gait-pose`
after uploading frames. Gait Pose is a standalone billable API, currently
priced separately from full sequence parsing at `$0.10 / 1K frames`.

```bash
python3 examples/registered/python/sequence_and_video_api_demo.py
```

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
