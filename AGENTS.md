# Agent Guide

This repository is a public W-Agent API examples repository. It is intended for
coding agents and developers who want to call the hosted W-Agent APIs, not to
develop or deploy the W-Agent backend service.

## Base URLs

- Mainland China: `https://www.w-agent.cn/api`
- Overseas entry: `https://www.h-agent.ai/api`
- Overseas redirects to `w-agent.cn` are expected.
- Do not use `https://api.w-agent.cn` unless it is explicitly documented.

Machine-readable references:

- OpenAPI: `https://www.w-agent.cn/api/openapi.json`
- Agent markdown: `https://www.w-agent.cn/api/.well-known/w-agent.md`
- GitHub examples: `https://github.com/w-agent-ai/api-example`
- Task recipes: `recipes/`
- MCP config example: `mcp-config.example.json`

## Task Selection

- Same person or not: upload one tracked person sequence, call
  `POST /v1/sequences/{task_id}/parse`, then compare same-type
  `gait_feature`, `face_feature`, or `reid_feature` by dot product.
- Video to identity features: use `/v1/videos` for server-side asynchronous
  parsing, or run `local_video_to_sequence_demo` first if you need local
  sequence folders and JSON files side by side.
- Video to each person's 2D/3D keypoints: run local video-to-sequence
  preprocessing, upload each generated sequence, then call
  `POST /v1/sequences/{task_id}/gait-pose` for each sequence.
- Existing single-person sequence to keypoints: upload sequence frames, then
  call `POST /v1/sequences/{task_id}/gait-pose`.
- Image text search: call `POST /v1/object-search` with raw `image_base64` and
  `prompt`.

## Important Boundaries

- Do not use raw image similarity for identity matching.
- Do not compare different feature types with each other.
- Sequence parse returns `sequences[]`; one uploaded track can be split when
  ReID detects an ID switch.
- Video parsing mainly returns person sequences, boxes, identity features,
  attributes, and emotions. It is not the complete per-person pose endpoint.
- `pose_2ds` and `pose_3ds` are relative to uploaded sequence images, not
  original full video frames. If uploaded images are crops, use local crop
  metadata to map coordinates back to the original video.
- Object Search boxes are original-image pixel coordinates. No match returns
  `boxes: []` and is not an error.

## Authentication

Registered API calls:

```http
Authorization: Bearer <api_key>
```

Anonymous calls use public routes and the x402 HTTP 402 payment flow. Do not mix
API key routes and anonymous public routes unless the documentation explicitly
says to.

## Fastest Runnable Paths

Registered local video to sequences:

```bash
pip install requests opencv-python numpy
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

Registered sequence similarity with included sample data:

```bash
pip install requests
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
python3 examples/registered/python/sequence_similarity_demo.py examples/sample_sequences
```

Object Search:

```bash
pip install requests
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
python3 examples/registered/python/object_search_api_demo.py examples/sample_sequences/ID_0001/001811.jpg 'person'
```

## Safety

- Never commit real API keys, wallet private keys, or customer data.
- Prefer environment variables for credentials.
- Keep generated outputs outside the repository or under an ignored output
  directory.
