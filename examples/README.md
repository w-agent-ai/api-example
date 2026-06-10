# W-Agent API demos

This directory separates demos by caller type:

- `registered/`: registered users who call APIs with an API Key.
- `anonymous/`: anonymous agents who call public APIs with x402 payment.
- `seqs/`: local test sequence images.
- `video/`: local test videos.
- `cpu_detect/`: client-side CPU person detection demo that extracts sequence
  images from videos before calling the Sequence API.

## Registered User

Registered-user APIs use a normal API Key:

```http
Authorization: Bearer <api_key>
```

Set your registered API Key before running registered-user demos:

```bash
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
```

## Client-Side Video Preprocessing

If a client wants to process videos locally and only upload tracked person
sequence images to W-Agent, use the CPU person detection demo. It extracts
person sequence folders from a video, and the output can then be uploaded with
either registered-user Sequence API demos or anonymous x402 Sequence API demos.

```bash
cd examples/cpu_detect
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build -j
cpp/build/video_sequence_demo /path/to/video.mp4
```

The output contains one folder per detected person sequence under
`video_gait_sequences/`. Each folder is an ordered image sequence that can be
uploaded with the registered or anonymous sequence demos.

Python reference/demo path:

```bash
python3 examples/cpu_detect/python_demo/video_sequence_demo.py /path/to/video.mp4
```

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
python3 examples/registered/python/batch_demo.py
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
python3 examples/registered/python/mcp_demo.py
```

### Go

The Go demos have no third-party dependencies.

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

The C++ demos require `libcurl` and `nlohmann/json`.

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
python3 examples/anonymous/python/x402_batch_demo.py
```

```bash
python3 examples/anonymous/python/x402_sequence_demo.py
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
