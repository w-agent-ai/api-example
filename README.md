# W-Agent API Examples

W-Agent provides public APIs for video parsing, tracked person sequence parsing,
identity features, ReID structured attributes, emotion output, and human 2D/3D
keypoints.

Global website: https://www.h-agent.ai

China mainland website: https://www.w-agent.cn

Default global API base URL:

```text
https://www.h-agent.ai/api
```

China mainland API base URL:

```text
https://www.w-agent.cn/api
```

Machine-readable API docs:

```text
https://www.h-agent.ai/openapi.json
https://www.h-agent.ai/.well-known/w-agent.md
https://www.h-agent.ai/.well-known/ai-plugin.json
```

MCP endpoint:

```text
https://www.h-agent.ai/mcp
```

## Repository Contents

- `examples/registered/python`: registered-user API Key demos and MCP demo.
- `examples/registered/go`: registered-user Go demos.
- `examples/registered/cpp`: registered-user C++ demos.
- `examples/anonymous/python`: anonymous x402 payment demos.
- `examples/registered/python/local_video_to_sequence_demo`: Python local
  video-to-sequence demo for registered users.
- `examples/registered/cpp/local_video_to_sequence_demo`: C++ local
  video-to-sequence demo for registered users.
- `examples/registered/go/local_video_to_sequence_demo`: Go orchestration demo
  that runs local preprocessing and uploads with the Go Sequence API demo.
- `examples/anonymous/python/local_video_to_sequence_demo`: Python local
  video-to-sequence demo for anonymous x402 calls.

Download packages are grouped by language. Inside each language package, the
three input modes are parallel:

```text
1. Sequence input: upload an already tracked person image sequence.
2. Video input: upload a full video directly to the Video API.
3. Local video-to-sequence input: process a video locally, then upload the
   extracted person sequence folders to the Sequence API.
```

## Registered User Flow

Registered-user APIs use an API Key:

```http
Authorization: Bearer <api_key>
```

Set your API Key before running demos:

```bash
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.h-agent.ai/api'
```

### Python

```bash
pip install requests
python3 examples/registered/python/sequence_and_video_api_demo.py
```

MCP demo:

```bash
python3 examples/registered/python/mcp_api_demo.py
```

### Local Video-To-Sequence Input

Users can either upload full videos directly to W-Agent, or process videos
locally first and upload the extracted person sequences. Each language package
has its own local video-to-sequence entry:

```bash
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
./examples/registered/cpp/local_video_to_sequence_demo/run_local_video_to_sequence_api_demo.sh /path/to/video.mp4
./examples/registered/go/local_video_to_sequence_demo/run_local_video_to_sequence_api_demo.sh /path/to/video.mp4
python3 examples/anonymous/python/local_video_to_sequence_demo/local_video_to_sequence_x402_demo.py /path/to/video.mp4
```

Each local demo writes one folder per detected person sequence and then uploads
the generated sequence folders.

### Go

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

Ubuntu:

```bash
sudo apt-get install -y libcurl4-openssl-dev nlohmann-json3-dev
```

Build and run:

```bash
cd examples/registered/cpp/sequence_demo
./build.sh
./build/registered_sequence_demo
```

```bash
cd examples/registered/cpp/video_demo
./build.sh
./build/registered_video_demo
```

## Anonymous x402 Flow

Anonymous public APIs do not use an API Key. The server returns HTTP 402, the
client signs an x402 payment payload with an EVM wallet, and then retries the
same request with payment headers.

Install dependencies:

```bash
pip install requests eth-account 'x402[evm]' web3
```

Set a test wallet private key before running:

```bash
export GAIT_TEST_WALLET_PRIVATE_KEY='0x...'
export GAIT_API_BASE_URL='https://www.h-agent.ai/api'
```

Run:

```bash
python3 examples/anonymous/python/anonymous_sequence_x402_demo.py
python3 examples/anonymous/python/anonymous_sequence_and_video_x402_demo.py
```

## Notes

- Do not commit real API Keys or wallet private keys.
- Sequence demos expect a local directory of ordered person crop images.
- Video demos expect a local video file path.
- Upload URLs returned by the API are service-relative paths and are resolved
  against `GAIT_API_BASE_URL`.

## Contact

Email: support@w-agent.cn
