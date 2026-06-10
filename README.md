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
- `examples/cpu_detect`: local CPU person detection preprocessing demo. It
  extracts person sequence folders from videos before calling the Sequence API.

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
python3 examples/registered/python/batch_demo.py
```

MCP demo:

```bash
python3 examples/registered/python/mcp_demo.py
```

### Local Video-To-Sequence Input

Users can either upload full videos directly to W-Agent, or process videos
locally first and upload the extracted person sequences. The CPU preprocessing
demo is included in the language packages and is shared by registered and
anonymous flows:

```bash
cd examples/cpu_detect
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build -j
cpp/build/video_sequence_demo /path/to/video.mp4
```

The output directory `video_gait_sequences/` contains one folder per detected
person sequence. Each folder can be uploaded through the registered Sequence API
demos or the anonymous x402 Sequence API demos.

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
python3 examples/anonymous/python/x402_sequence_demo.py
python3 examples/anonymous/python/x402_batch_demo.py
```

## Notes

- Do not commit real API Keys or wallet private keys.
- Sequence demos expect a local directory of ordered person crop images.
- Video demos expect a local video file path.
- Upload URLs returned by the API are service-relative paths and are resolved
  against `GAIT_API_BASE_URL`.

## Contact

Email: support@mail.w-agent.cn
