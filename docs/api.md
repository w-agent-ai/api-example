# W-Agent API Reference

先阅读：

- 系统设计文档：[design.md](/home/watrix/tiandk/agent/gaitAgent/docs/design.md)
- 开发文档：[development.md](/home/watrix/tiandk/agent/gaitAgent/docs/development.md)
- 部署与测试文档：[testing.md](/home/watrix/tiandk/agent/gaitAgent/docs/testing.md)

## Overview

This document defines the V1 public service built on top of [algorithms/sdk/agent.go](/home/watrix/tiandk/agent/gaitAgent/algorithms/sdk/agent.go).

Supported capabilities:

- Video parsing: asynchronous
- Sequence parsing: synchronous

Supported payment modes:

- Registered users: portal email/password login + prepaid wallet + API key for interface calls
- Anonymous users and agents: payment provider selected by deployment

Access model:

- Registered-user task APIs are only available on private routes under `/v1/videos` and `/v1/sequences`.
- Anonymous callers and agents must use `/v1/public/videos` and `/v1/public/sequences`.
- There is no supported "anonymous but non-public" task mode.

Current provider support:

- `mock`: local development fallback when `GAIT_PAYMENT_PROVIDER` is not set
- `x402`: implemented and used for production anonymous public calls when configured
- `ap2`: reserved for later

## Architecture

The service is split into these runtime components:

- API service: authentication, upload negotiation, task lifecycle, billing, payment handling, result delivery
- GPU worker: isolated process calling the gait SDK
- Object storage: input videos, input sequence frames, result JSON, gait images, face images
- PostgreSQL: tasks, billing, payments, users, policies, audit events
- Scheduler and cleanup worker: timeout transitions and object deletion

Current storage implementation notes:

- sequence task metadata supports an optional PostgreSQL repository when `GAIT_DB_DSN` is configured; otherwise it falls back to local JSON files
- video task metadata supports an optional PostgreSQL repository when `GAIT_DB_DSN` is configured; otherwise it falls back to local JSON files
- account metadata supports an optional PostgreSQL repository when `GAIT_DB_DSN` is configured; existing local account files are imported into the database on first switch if the database is empty
- runtime config, admin audit logs, and admin stats snapshots support optional PostgreSQL repositories when `GAIT_DB_DSN` is configured
- uploaded videos, uploaded sequence frames, and generated assets now go through the internal object-store abstraction
- current default object-store implementation is local filesystem storage rooted at `GAIT_OBJECT_STORE_ROOT` or `<GAIT_DATA_DIR>/objects`
- this prepares the code path for a later S3 / MinIO / OSS / COS backend without changing sequence/video business logic

The SDK should not run inside the public HTTP process.

Current MVP runtime notes:

- video tasks are persisted on disk and maintained by the worker tick
- sequence tasks are persisted on disk and recovered on API restart
- payment receipt replay files are cleaned by the same retention maintenance

## Authentication

Portal login:

- `POST /v1/users/register` with `email` and `password`
- `POST /v1/users/login` with `email` and `password`
- successful register/login sets cookie `gait_user_session`

Registered API requests:

- Header: `Authorization: Bearer <api_key>`

Public task requests:

- Header: `X-Task-Token: <task_token>`

When the public-task payment provider is `x402`, payment settlement requests send:

- Header: `PAYMENT-SIGNATURE: <base64-encoded x402 payment payload>`

Compatibility:

- Legacy header `X-Payment-Signature` is also accepted.

Write requests:

- Optional header: `Idempotency-Key: <key>`

Admin requests:

- Header: `Authorization: Bearer <admin_token>`

## Public Base URL

Use this exact public API base URL:

```text
https://www.w-agent.cn/api
```

Do not guess `https://api.w-agent.cn`; it is not the documented API origin and
may fail TLS hostname verification in clients such as Python `requests`.

Registered calls use:

```http
Authorization: Bearer <api_key>
```

## Choose The Right Task

For agents and first-time users, choose by intent instead of API name:

- To decide whether two tracks are the same person, use gait/face/ReID features from sequence parsing. Do not compare raw images or generic image embeddings.
- To get stable person sequences from a video, prefer local video preprocessing first: detect, track, crop, write one folder per person sequence, then upload each folder to the Sequence API.
- To extract 2D/3D keypoints, upload a sequence first and call `POST /v1/sequences/{task_id}/gait-pose`. Do not expect sequence parsing or video parsing to be the keypoint endpoint.
- To find objects or people by text in a single image, use Object Search.

W-Agent's core input for identity and pose APIs is a tracked person sequence, not an arbitrary full scene image. A full video is one possible source for generating those sequences.

## Agent Quickstart: Parse Local Sequences And Compare

The demo package contains small public sequence data under
`examples/sample_sequences`. These sequences are intended to return valid
`gait_feature` and `reid_feature` results.

Run the compact Python demo:

```bash
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
python3 examples/registered/python/sequence_similarity_demo.py examples/sample_sequences
```

The sequence API flow is:

1. `POST /v1/sequences` with `{"frame_count": N}`.
2. `PUT` each image to the returned `uploads[].upload_url`.
3. Keep each returned `uploads[].object_key`.
4. `POST /v1/sequences/{task_id}/parse` with `frames[].index` and `frames[].object_key`.
5. Read features from `response.sequences[]`, for example `response.sequences[0].gait_feature`.

Similarity:

- `gait_feature` compares only with `gait_feature`.
- `face_feature` compares only with `face_feature`.
- `reid_feature` compares only with `reid_feature`.
- Use dot product: `sum(a * b for a, b in zip(feature_a, feature_b))`.
- `face_feature` can be `null` or empty when no usable face is detected; this is not an API failure.

Common first-use errors:

- `400 invalid request body` on `POST /v1/sequences`: you probably uploaded images directly; send only `{"frame_count": N}` first.
- Missing or empty `frames` on `/parse`: pass back `object_key` values returned by create.
- Empty `response.sequences`: the frames did not form a valid moving gait sequence.
- TLS hostname mismatch: use `https://www.w-agent.cn/api`.

## Recommended Workflow: Video To Person Sequences

Use this workflow when starting from a local video and the goal is identity
comparison, pose extraction, or batch review:

1. Run a local video-to-sequence demo.
2. The demo decodes the video locally.
3. It runs person detection and tracking locally.
4. It crops each tracked person into a sequence folder.
5. Upload each sequence folder to the Sequence API.
6. For identity, call `/parse` and read `sequences[].gait_feature`, `sequences[].face_feature`, and `sequences[].reid_feature`.
7. For 2D/3D keypoints, call `/gait-pose` and read `result.pose_2ds` / `result.pose_3ds`.

Registered Python example:

```bash
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

The local video-to-sequence demos are the recommended path when the caller wants
control over local decoding, detection, tracking, and output folders. Direct
`/v1/videos` upload is still supported for asynchronous server-side video
parsing, but it is not the simplest path for agents that need per-sequence local
files and JSON side by side.

## Task Types

- `video`
- `sequence`

## Video Workflow

1. Client creates a video task.
2. Service returns object storage upload information.
3. Client uploads the video with `PUT /v1/video-uploads/{task_id}?token=...`.
4. Service extracts video metadata and creates phase 1 billing.
5. Registered users are auto-debited from wallet; public tasks wait for explicit payment settlement.
6. GPU worker parses the video.
7. Service stores result summary and creates phase 2 billing.
8. After phase 2 payment, the full result JSON is returned.
9. Media and results are deleted after retention expires.

Delete endpoints:

- `DELETE /v1/videos/{task_id}`
- `DELETE /v1/public/videos/{task_id}` with `X-Task-Token`

## Sequence Workflow

1. Client creates a sequence task and obtains upload targets for frames.
2. Client uploads frame images.
3. Client calls `parse` with the ordered frame list.
4. Payment is completed before parsing starts.
5. Service returns the parsing result synchronously. The response contains `sequences`, because one uploaded track can split into multiple single-person outputs.
6. The same sequence parse response can be fetched again later until retention cleanup deletes it.

Why a single input sequence returns a `sequences` array:

- A client usually uploads one tracked-person sequence, but tracking IDs can drift when people cross or occlude each other. For example, the first half of one track may be person A, and after a crossing the same track ID may follow person B.
- The backend sequence parser checks the uploaded track with ReID features. If it detects an ID switch or mixed-person frames, it splits the input at the switch point and returns multiple clean single-person output sequences.
- Frames that are ambiguous or not suitable for a clean single-person output may be dropped.

Recommended output layout for demos and agents:

```text
output/
  video_name/
    sequence_001/
      frame_0001.jpg
      frame_0002.jpg
      meta.txt
      result.json
      pose_2d.csv
      pose_3d.csv
    summary.csv
```

Keep sequence images and the matching JSON result in the same folder. If an API
result contains multiple split `sequences[]`, save each output sequence
separately and number them in display order.

## Gait Pose Coordinates

`POST /v1/sequences/{task_id}/gait-pose` returns standalone 2D/3D keypoint
results.

Shape:

```json
{
  "result": {
    "pose_2ds": [
      [x0, y0, score0, "...", x16, y16, score16]
    ],
    "pose_3ds": [
      [x0, y0, z0, "...", x16, y16, z16]
    ]
  }
}
```

Important coordinate rules:

- `pose_2ds` outer array is frames. Each frame is `3*17` floats in COCO order: `x,y,score` repeated 17 times.
- `pose_3ds` outer array is frames. Each frame is `3*17` floats in H36M order: `x,y,z` repeated 17 times.
- Coordinates are relative to the uploaded sequence image, not the original full video frame.
- The 2D origin is the uploaded image center.
- If the uploaded image is a crop, map back to original video coordinates with the crop metadata from the local demo, such as `crop_x`, `crop_y`, `crop_w`, and `crop_h`.
- Some frames may have missing or invalid values; callers should skip, filter, or interpolate those frames instead of treating the whole API call as failed.

## Common Wrong Approaches

- Wrong: use image similarity to decide whether two people are the same person. Correct: compare same-type `gait_feature`, `face_feature`, or `reid_feature`.
- Wrong: upload a full video when you need local per-sequence folders and JSON. Correct: run local video-to-sequence preprocessing, then upload each sequence folder.
- Wrong: read `result.gait_feature` at the top level. Correct: read `response.sequences[].gait_feature`.
- Wrong: call sequence parsing and expect `pose_2ds` / `pose_3ds`. Correct: call the standalone `/gait-pose` endpoint.
- Wrong: treat `pose_2ds` as original full-video coordinates. Correct: coordinates are relative to the uploaded sequence image.

Delete endpoints:

- `DELETE /v1/sequences/{task_id}`
- `GET /v1/sequences/{task_id}/result`
- `DELETE /v1/public/sequences/{task_id}` with `X-Task-Token`
- `GET /v1/public/sequences/{task_id}/result` with `X-Task-Token`

## Admin Query APIs

Management endpoints:

- `GET /admin`
- `GET /portal`
- `GET /portal/demo-download?type=registered`
- `GET /portal/demo-download?type=registered-python`
- `GET /portal/demo-download?type=cpp`
- `GET /portal/demo-download?type=go`
- `GET /portal/demo-download?type=anonymous`
- `GET /portal/demo-download?type=anonymous-python`
- `GET /portal/demo-download?type=trial`
- `GET /portal/demo-download?type=browser`

`type=browser` returns a standalone HTML file directly. Other demo download
types return ZIP packages.

GET endpoints also accept `HEAD` for lightweight URL probing. `HEAD` returns
the same status and headers as `GET` with an empty response body.

- `GET /v1/portal/bootstrap`
- `GET /v1/payment-capabilities`
- `GET /v1/admin/overview`
- `GET /v1/admin/runtime-config`
- `PUT /v1/admin/runtime-config`
- `GET /v1/admin/users`
- `POST /v1/admin/users`
- `GET /v1/admin/users/{user_id}`
- `POST /v1/admin/users/{user_id}/topups`
- `GET /v1/admin/users/{user_id}/ledger`
- `GET /v1/admin/users/{user_id}/deposits`
- `POST /v1/admin/users/{user_id}/deposits/{deposit_id}/settle`
- `GET /v1/admin/videos`
- `GET /v1/admin/videos/{task_id}`
- `DELETE /v1/admin/videos/{task_id}`
- `GET /v1/admin/sequences`
- `GET /v1/admin/sequences/{task_id}`
- `DELETE /v1/admin/sequences/{task_id}`

User self-service endpoints:

- `POST /v1/users/register`
- `POST /v1/users/login`
- `POST /v1/users/logout`
- `GET /v1/me`
- `GET /v1/me/wallet`
- `GET /v1/me/ledger`
- `GET /v1/me/deposits`
- `POST /v1/me/deposits`
- `GET /v1/me/api-keys`
- `POST /v1/me/api-keys`
- `POST /v1/me/api-keys/{key_id}/pause`
- `POST /v1/me/api-keys/{key_id}/resume`
- `DELETE /v1/me/api-keys/{key_id}`
- `GET /v1/me/videos`
- `GET /v1/me/sequences`
- `POST /v1/object-search`

Public trial endpoints:

- `POST /v1/public/object-search/trial`
- `POST /v1/public/sequences/trial/parse`
- `POST /v1/public/sequences/trial/gait-pose`

Portal behavior:

- `/portal` is both the public landing page and the logged-in user center.
- Public users can read product introduction, supported anonymous payment routes, and download demos before registering.
- Registered users log in with email and password, then manage balance, recharge, API Keys, usage records, and demo downloads.
- The visible product name in the portal is `W-Agent`.
- API Keys are used only for API calls; portal login itself uses the email/password session cookie.

Query parameters:

- `status`
- `limit`

Deployment config:

- `GAIT_ADMIN_TOKEN`
- `GAIT_RUNTIME_CONFIG_PATH`

## Status Model

Video task statuses:

- `created`
- `uploaded`
- `awaiting_payment_1`
- `processing`
- `succeeded_awaiting_payment_2`
- `succeeded`
- `failed`
- `expired`
- `deleted`

Sequence task statuses:

- `created`
- `awaiting_payment`
- `processing`
- `succeeded`
- `failed`
- `expired`
- `deleted`

## Retention Policy

Task cleanup is configuration-driven. Each task stores:

- `expire_at`
- `delete_after_at`

Policy fields:

- `upload_pending_ttl`
- `payment_phase1_ttl`
- `payment_phase2_ttl`
- `result_retention_ttl`
- `failed_retention_ttl`
- `deleted_record_ttl`

Environment variables:

- `GAIT_UPLOAD_PENDING_TTL`
- `GAIT_PAYMENT_PHASE1_TTL`
- `GAIT_PAYMENT_PHASE2_TTL`
- `GAIT_RESULT_RETENTION_TTL`
- `GAIT_FAILED_RETENTION_TTL`
- `GAIT_DELETED_RECORD_TTL`

Runtime config file:

- default path: `<GAIT_DATA_DIR>/runtime/config.json`
- override path: `GAIT_RUNTIME_CONFIG_PATH`
- `PUT /v1/admin/runtime-config` updates this file and applies the new retention values to current API tasks immediately
- worker refreshes the same file periodically and applies updated retention to video tasks without manual env edits
- the same runtime config also stores pricing parameters for:
  - `sequence_per_k_frames`
  - `sequence_per_sequence`
  - `video_per_k_frames`
  - `gait_pose_per_k_frames`
  - `currency`
  - `cny_usd_exchange_rate`
  - `eurc_usd_exchange_rate`
- runtime config also stores trial and 图搜万物 parameters:
  - `trial.enabled`
  - `trial.total_amount`
  - `trial.max_upload_bytes`
  - `locate_anything.enabled`
  - `locate_anything.endpoint`
  - `locate_anything.timeout_seconds`
  - `locate_anything.price_per_image`

Pricing amounts configured in admin are stored as CNY minor units (fen). Registered-user wallet balance, monthly plan allowance, and usage records use CNY. English UI and public price estimates may show USD equivalents by `cny_usd_exchange_rate`; anonymous x402 settlement is still USD/stablecoin based, and the server converts CNY order amounts to USD cents by `cny_usd_exchange_rate`. CNY to USD conversion is always rounded up to the next USD cent, with any positive USD amount displayed or charged as at least `$0.01`.

Runtime behavior:

- when `expire_at` is reached, task status becomes `expired`
- when `delete_after_at` is reached for `succeeded` or `failed`, artifacts are removed and task status becomes `deleted`
- deleted task records are retained until `deleted_record_ttl` and then removed
- payment receipt replay files older than `deleted_record_ttl` are removed automatically

## Billing Model

Video parsing:

- amount = `video_frame_count * video_per_k_frames / 1000`

Video result fetch:

- amount = `sequence_count * sequence_per_sequence + total_sequence_frames * sequence_per_k_frames / 1000`

Sequence parsing:

- registered-user amount = `max(output_sequence_count, 1) * sequence_per_sequence`
- anonymous x402 amount = `input_sequence_count * sequence_per_sequence`
- current Sequence API accepts one input sequence per task, so `input_sequence_count = 1`
- `output_sequence_count` is the number of split single-person sequences returned by `GetSplitSeqFeature`; for registered users, no valid output still bills as `1` sequence

Gait Pose:

- amount = `sequence_frame_count * gait_pose_per_k_frames / 1000`
- default price is `¥0.01 / 1K frames`

图搜万物:

- amount = `1 * locate_anything.price_per_image`
- default registered-user price is `¥0.10 / image`
- trial calls do not charge wallet balance; they consume the runtime-configured trial total amount stored in `trial_usage` and append a zero-amount `usage_records` row with `source=trial`
- portal homepage and browser-client trial calls share the same cumulative trial amount bucket for the same IP
- Gait Pose is a separate endpoint and is billed independently from full gait sequence parsing

Registered user settlement:

- `POST /v1/sequences/{task_id}/parse` automatically charges the wallet before processing
- `POST /v1/sequences/{task_id}/gait-pose` automatically charges the wallet before processing
- `GET /v1/sequences/{task_id}/result` returns the stored sequence parse response for registered users without re-charging
- `PUT /v1/video-uploads/{task_id}?token=...` automatically attempts phase 1 wallet settlement for registered users after upload completes
- `POST /v1/videos/{task_id}/complete` retries registered user phase 1 wallet settlement after a topup
- `GET /v1/videos/{task_id}/result` automatically attempts phase 2 wallet settlement before returning full result

Deposit workflow:

- `POST /v1/me/deposits` creates a user deposit order
- `POST /v1/me/deposits/{deposit_id}/checkout` recreates or resumes a hosted checkout session
- `GET /v1/me/deposits` lists the caller's deposit orders
- `GET /v1/me/deposits/{deposit_id}` returns a single deposit order
- `POST /v1/admin/users/{user_id}/deposits/{deposit_id}/settle` credits the wallet and marks the deposit `settled`
- `POST /v1/payments/webhooks/stripe` handles Stripe checkout webhook settlement
- `POST /v1/payments/webhooks/paddle` handles Paddle webhook settlement
- `POST /v1/payments/webhooks/wechat_pay` handles WeChat Pay notify settlement
- `POST /v1/payments/webhooks/alipay` handles Alipay notify settlement
- `GET /payments/mock/checkout/{deposit_id}` opens the hosted mock checkout page for browser testing
- `POST /v1/payments/mock/complete/{deposit_id}` completes the hosted mock checkout and settles the deposit
- current implementation supports:
  - `provider=manual`: create a pending offline/manual deposit order
  - `provider=hosted_mock`: local hosted mock checkout for browser testing
  - `provider=stripe`: hosted Stripe Checkout
  - `provider=paddle`: hosted Paddle Checkout
  - `provider=wechat_pay`: WeChat Pay H5 checkout
  - `provider=alipay`: Alipay page or WAP checkout
  - if `provider` is omitted, the server selects a checkout provider from `channel` and deployment config

`POST /v1/me/deposits` response shape:

```json
{
  "deposit": {
    "deposit_id": "dep_123",
    "status": "awaiting_checkout",
    "provider": "hosted_mock",
    "checkout_provider": "hosted_mock",
    "checkout_status": "open",
    "checkout_url": "http://example.com/payments/mock/checkout/dep_123"
  },
  "checkout": {
    "provider": "hosted_mock",
    "status": "open",
    "url": "http://example.com/payments/mock/checkout/dep_123",
    "session_id": "chk_dep_123"
  }
}
```

Pricing payload shape:

```json
{
  "currency": "USD",
  "video_per_k_frames": 4000,
  "sequence_per_k_frames": 2000,
  "sequence_per_sequence": 50,
  "gait_pose_per_k_frames": 10
}
```

## Data Conventions

- Timestamps use RFC3339 UTC strings
- Money values use decimal strings
- Large outputs are stored in object storage
- API result payloads may be gzip-compressed

## OpenCV Rect Convention

All `rect` objects follow OpenCV `Rect` semantics:

```json
{
  "x": 12,
  "y": 34,
  "width": 56,
  "height": 78
}
```

## ReID Structure Decoding

Each raw ReID attribute value is decoded as:

- `raw_value` is the original SDK output
- `score = (raw_value % 100) / 100.0`
- `uncertain = raw_value < 100`
- `category_index = raw_value >= 100 ? raw_value / 100 - 1 : null`
- `valid = !uncertain && score >= threshold`

Example:

```json
{
  "key": "gender",
  "name": "性别",
  "raw_value": 180,
  "category_index": 0,
  "uncertain": false,
  "score": 0.8,
  "threshold": 0.57,
  "valid": true,
  "label": "男"
}
```

Unknown example:

```json
{
  "key": "gender",
  "name": "性别",
  "raw_value": 50,
  "category_index": null,
  "uncertain": true,
  "score": 0.5,
  "threshold": 0.57,
  "valid": false,
  "label": null
}
```

ReID attribute keys, in order:

1. `gender`
2. `age`
3. `hair_style`
4. `hair_color`
5. `hat_type`
6. `hat_color`
7. `mask`
8. `mask_color`
9. `bag_type`
10. `bag_color`
11. `umbrella`
12. `umbrella_color`
13. `upper_type`
14. `upper_length`
15. `upper_color`
16. `upper_pattern`
17. `lower_type`
18. `lower_length`
19. `lower_color`
20. `lower_pattern`
21. `shoe_type`
22. `shoe_color`

## Registered Video APIs

### POST /v1/videos

Authentication required:

- `Authorization: Bearer <api_key>`

Request:

```json
{
  "filename": "demo.mp4",
  "content_type": "video/mp4",
  "size_bytes": 12345678
}
```

Response:

```json
{
  "task_id": "vid_xxx",
  "status": "created",
  "object_key": "videos/vid_xxx/input.mp4",
  "upload_url": "https://...",
  "upload_expires_at": "2026-05-06T12:00:00Z"
}
```

### PUT /v1/video-uploads/{task_id}?token=...

Uploads the binary video body. This is the actual upload step for both registered and public video tasks.

Registered-user behavior:

- the service probes video metadata
- creates phase 1 billing
- automatically tries wallet deduction
- if wallet balance is insufficient, returns `409 wallet_insufficient_balance`

Successful response example:

```json
{
  "task_id": "vid_xxx",
  "object_key": "videos/vid_xxx/input.bin",
  "size_bytes": 12345678,
  "status": "uploaded"
}
```

### POST /v1/videos/{task_id}/complete

Authentication required:

- `Authorization: Bearer <api_key>`

Purpose:

- retry registered-user phase 1 wallet settlement after upload is already complete
- current implementation does not upload media and does not require a request body

Response:

```json
{
  "task_id": "vid_xxx",
  "status": "uploaded",
  "current_payment_phase": null,
  "video_meta": {
    "frame_count": 1234,
    "fps": 25.0,
    "duration_ms": 49360,
    "size_bytes": 12345678
  },
  "billing": {
    "phase1": {
      "status": "paid",
      "amount": "12.34",
      "currency": "USD"
    },
    "phase2": null
  }
}
```

### GET /v1/videos/{task_id}

Authentication required:

- `Authorization: Bearer <api_key>`

Response:

```json
{
  "task_id": "vid_xxx",
  "status": "processing",
  "progress": {
    "percent": 76
  },
  "current_payment_phase": null,
  "video_meta": {
    "frame_count": 1234,
    "fps": 25.0,
    "duration_ms": 49360,
    "size_bytes": 12345678
  },
  "billing": {
    "phase1": {
      "status": "paid",
      "amount": "12.34",
      "currency": "USD"
    },
    "phase2": null
  },
  "expire_at": "2026-05-06T12:00:00Z",
  "delete_after_at": "2026-05-07T12:00:00Z"
}
```

### GET /v1/videos/{task_id}/result

Authentication required:

- `Authorization: Bearer <api_key>`

Response:

```json
{
  "task_id": "vid_xxx",
  "status": "succeeded",
  "frame_count": 1234,
  "sequence_count": 8,
  "total_sequence_frames": 276,
  "billing": {
    "phase1": {
      "status": "paid",
      "amount": "12.34",
      "currency": "USD"
    },
    "phase2": {
      "status": "paid",
      "amount": "5.67",
      "currency": "USD"
    }
  },
  "expires_at": "2026-05-06T12:00:00Z",
  "sequences": [
    {
      "sequence_id": "seq_001",
      "batch": 0,
      "frame_count": 37,
      "frames": [
        {
          "frame_id": 101,
          "rect": {
            "x": 12,
            "y": 34,
            "width": 56,
            "height": 78
          }
        }
      ],
      "gait_feature": [],
      "reid_feature": [],
      "face_feature": [],
      "reid_structure_raw": [],
      "reid_attributes": [],
      "reid_summary": "",
      "emotions": [],
      "gait_images": [],
      "gait_image": {
        "url": "https://...",
        "expires_at": "2026-05-06T12:00:00Z"
      },
      "face_image": {
        "url": "https://...",
        "expires_at": "2026-05-06T12:00:00Z"
      }
    }
  ]
}
```

## Anonymous Video APIs

### POST /v1/public/videos

Request:

```json
{
  "filename": "demo.mp4",
  "content_type": "video/mp4",
  "size_bytes": 12345678
}
```

Response:

```json
{
  "task_id": "vid_xxx",
  "task_token": "tok_xxx",
  "status": "created",
  "object_key": "videos/vid_xxx/input.mp4",
  "upload_url": "https://...",
  "upload_expires_at": "2026-05-06T12:00:00Z"
}
```

### PUT /v1/video-uploads/{task_id}?token=...

For public video tasks, upload completes media ingest and creates phase 1 billing.

Typical response:

```json
{
  "task_id": "vid_xxx",
  "object_key": "videos/vid_xxx/input.bin",
  "size_bytes": 12345678,
  "status": "awaiting_payment_1"
}
```

### POST /v1/public/videos/{task_id}/settle-phase1

Headers:

- `X-Task-Token: <task_token>`

Missing or invalid payment proof may return HTTP `402`.

- `mock` provider typically returns `payment_verification_failed`
- `x402` provider may return `payment_required`

402 body:

```json
{
  "error": {
    "code": "payment_required",
    "message": "phase1 payment required"
  },
  "payment_context": {
    "provider": "mock",
    "phase": "video_phase1",
    "order_id": "ord_xxx",
    "amount": "12.34",
    "currency": "USD",
    "expires_at": "2026-05-06T12:00:00Z",
    "pricing_basis": {
      "frame_count": 1234,
      "billable_frame_count": 1234,
      "rate_per_k_frames": 4000
    },
    "challenge": {
      "mode": "mock",
      "order_id": "ord_xxx"
    }
  }
}
```

When provider is `x402`, the same `402` response also includes header `PAYMENT-REQUIRED`.

Paid response:

```json
{
  "task_id": "vid_xxx",
  "status": "uploaded",
  "order": {
    "order_id": "ord_xxx",
    "phase": "video_phase1",
    "status": "paid",
    "amount": "12.34",
    "currency": "USD"
  }
}
```

### GET /v1/public/videos/{task_id}

Headers:

- `X-Task-Token: <task_token>`

Response:

```json
{
  "task_id": "vid_xxx",
  "status": "succeeded_awaiting_payment_2",
  "progress": {
    "percent": 100
  },
  "current_payment_phase": "video_phase2",
  "video_meta": {
    "frame_count": 1234,
    "fps": 25.0,
    "duration_ms": 49360,
    "size_bytes": 12345678
  },
  "expire_at": "2026-05-06T12:00:00Z",
  "delete_after_at": "2026-05-07T12:00:00Z"
}
```

### GET /v1/public/videos/{task_id}/result

Headers:

- `X-Task-Token: <task_token>`

If phase 2 is unpaid, return HTTP `402`.

402 body:

```json
{
  "error": {
    "code": "payment_required",
    "message": "phase2 payment required"
  },
  "payment_context": {
    "provider": "mock",
    "phase": "video_phase2",
    "order_id": "ord_yyy",
    "amount": "5.67",
    "currency": "USD",
    "expires_at": "2026-05-06T12:00:00Z",
    "pricing_basis": {
      "sequence_count": 8,
      "billable_sequences": 8,
      "rate_per_sequence": 50,
      "sequence_amount": 400,
      "total_sequence_frames": 276,
      "billable_frame_count": 276,
      "rate_per_k_frames": 2000,
      "frame_amount": 552
    },
    "challenge": {
      "mode": "mock",
      "order_id": "ord_yyy"
    }
  }
}
```

If phase 2 is paid, return the same full result shape as the registered `GET /v1/videos/{task_id}/result`.

### DELETE /v1/public/videos/{task_id}

Headers:

- `X-Task-Token: <task_token>`

Marks the task for early cleanup.

## Registered Sequence APIs

### POST /v1/sequences

Authentication required:

- `Authorization: Bearer <api_key>`

Request:

```json
{
  "frame_count": 4
}
```

Response:

```json
{
  "task_id": "seq_xxx",
  "uploads": [
    {
      "index": 0,
      "object_key": "sequences/seq_xxx/000000.jpg",
      "upload_url": "https://...",
      "upload_expires_at": "2026-05-06T12:00:00Z"
    }
  ]
}
```

### POST /v1/sequences/{task_id}/parse

Authentication required:

- `Authorization: Bearer <api_key>`

Request:

```json
{
  "frames": [
    {
      "index": 0,
      "object_key": "sequences/seq_xxx/000000.jpg"
    },
    {
      "index": 1,
      "object_key": "sequences/seq_xxx/000001.jpg"
    }
  ]
}
```

Optional lightweight compatibility:

```json
{
  "frames": [
    {
      "index": 0,
      "content_base64": "..."
    }
  ]
}
```

Response:

```json
{
  "task_id": "seq_xxx",
  "status": "succeeded",
  "sequence_count": 2,
  "sequences": [
    {
      "sequence_id": "seq_xxx_split_01",
      "batch": 0,
      "frame_count": 3,
      "frames": [
        { "frame_id": 0, "box": [120, 40, 220, 260] },
        { "frame_id": 1, "box": [123, 42, 224, 263] },
        { "frame_id": 2, "box": [126, 44, 228, 266] }
      ],
      "gait_feature": [],
      "reid_feature": [],
      "face_feature": [],
      "reid_structure_raw": [],
      "reid_attributes": [],
      "reid_summary": "",
      "emotions": [],
      "gait_images": [],
      "gait_image": {
        "url": "https://...",
        "expires_at": "2026-05-06T12:00:00Z"
      },
      "face_image": {
        "url": "https://...",
        "expires_at": "2026-05-06T12:00:00Z"
      }
    },
    { "sequence_id": "seq_xxx_split_02", "frame_count": 0, "frames": [] }
  ]
}
```

Sequence result fields:

- `sequences`: all split single-person sequences returned by `GetSplitSeqFeature`. One uploaded track can produce multiple outputs when tracking mixed different people or stray frames. This mainly handles tracking ID switches: when two people cross, the tracker may continue the same ID on another person; the backend uses ReID features to detect this and split the input at the switch point. Invalid or ambiguous frames may be dropped by the SDK.
- `sequence_count`: number of returned `sequences`.
- `frames`: frame IDs and optional boxes returned by the SDK for this output sequence. When the SDK does not return frame-level mapping, this field is an empty array and `frame_count` is `0`; clients should not assume it equals the uploaded input frame count.
- `emotions`: emotion output returned by the SDK.
- `gait_images`: response-compatible field for per-frame gait crops. Public API responses currently keep it as an empty array and do not embed image bytes.
- `gait_image` / `face_image`: signed task-scoped asset URLs. These URLs expire with the task retention window; after expiry or cleanup, downloading returns an error instead of another task's asset.

Runnable Python example:

```python
import math
import os
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE_URL = os.getenv("W_AGENT_BASE_URL", "https://www.w-agent.cn")
API_KEY = os.getenv("W_AGENT_API_KEY", "gak_replace_me")
IMAGE_DIR = Path(os.getenv("W_AGENT_IMAGE_DIR", "./sequence_frames"))


def request_json(session, method, path, **kwargs):
    url = urljoin(BASE_URL.rstrip("/") + "/", path.lstrip("/"))
    resp = session.request(method, url, timeout=120, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed: {resp.status_code} {resp.text}")
    return resp.json()


def upload_binary(session, upload_url, path):
    url = urljoin(BASE_URL.rstrip("/") + "/", upload_url.lstrip("/"))
    with open(path, "rb") as f:
        resp = session.put(url, data=f, headers={"Content-Type": "image/jpeg"}, timeout=120)
    if resp.status_code >= 400:
        raise RuntimeError(f"upload {path} failed: {resp.status_code} {resp.text}")


def parse_sequence(image_dir):
    frames = sorted(
        p for p in image_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if not frames:
        raise RuntimeError(f"no images found in {image_dir}")

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {API_KEY}"})

    created = request_json(session, "POST", "/v1/sequences", json={"frame_count": len(frames)})
    task_id = created["task_id"]
    parse_frames = []

    for path, upload in zip(frames, created["uploads"]):
        upload_binary(session, upload["upload_url"], path)
        parse_frames.append({
            "index": upload["index"],
            "object_key": upload["object_key"],
        })

    parsed = request_json(
        session,
        "POST",
        f"/v1/sequences/{task_id}/parse",
        json={"frame_count": len(frames), "frames": parse_frames},
    )
    sequences = parsed.get("sequences") or []
    if not sequences:
        raise RuntimeError(f"no valid output sequence: {parsed}")
    return sequences[0]


def l2_normalize(values):
    norm = math.sqrt(sum(float(x) * float(x) for x in values))
    return [float(x) / norm for x in values] if norm else []


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


if __name__ == "__main__":
    seq = parse_sequence(IMAGE_DIR)
    gait_feature = seq.get("gait_feature") or []
    print("sequence_id:", seq.get("sequence_id"))
    print("frame_count:", seq.get("frame_count"))
    print("gait_feature_dim:", len(gait_feature))
    # To compare two outputs, use dot product between L2-normalized features.
    # If your SDK/config returns already normalized vectors, direct dot product is equivalent.
    similarity_to_self = dot(l2_normalize(gait_feature), l2_normalize(gait_feature))
    print("self_similarity:", similarity_to_self)
```

### GET /v1/sequences/{task_id}/result

Authentication required.

Returns the stored sequence parse response after successful parse. Shape is the same as `POST /v1/sequences/{task_id}/parse`: `task_id`, `status`, `sequence_count`, and `sequences`.

### POST /v1/sequences/{task_id}/gait-pose

Authentication required:

- `Authorization: Bearer <api_key>`

Purpose:

- Runs the standalone SDK `agentGaitGetSeqGaitPose` interface.
- Returns only frame alignment and pose outputs.
- Bills independently with `gait_pose_once`.

Request shape is the same as `POST /v1/sequences/{task_id}/parse`:

```json
{
  "frames": [
    {
      "index": 0,
      "object_key": "sequences/seq_xxx/000000.jpg"
    },
    {
      "index": 1,
      "object_key": "sequences/seq_xxx/000001.jpg"
    }
  ]
}
```

Response:

```json
{
  "task_id": "seq_xxx",
  "status": "succeeded",
  "result": {
    "sequence_id": "seq_xxx",
    "frame_count": 2,
    "frames": [],
    "pose_2ds": [],
    "pose_3ds": [],
    "emotions": [],
    "billing": {
      "amount": "1",
      "currency": "USD",
      "pricing_basis": {
        "frame_count": 2,
        "billable_frame_count": 2,
        "rate_per_k_frames": 10
      }
    }
  }
}
```

Result fields:

- `pose_2ds`: per-frame 2D pose data. Each frame contains 17 COCO-order keypoints, and each keypoint is stored as `x, y, score`. The origin is the image center; convert to top-left image coordinates with `image_width / 2 + x` and `image_height / 2 + y` before drawing on a canvas. Default COCO edges: `0-1,0-2,1-3,2-4,5-7,7-9,6-8,8-10,5-6,5-11,6-12,11-13,13-15,12-14,14-16`.
- `pose_3ds`: per-frame 3D pose data. Each frame contains 17 H36M-order keypoints, and each keypoint is stored as `x, y, z`. The 3D coordinate origin is also the center; renderers should not recenter the skeleton by bounding-box center unless intentionally changing the view.
- `emotions`: emotion output returned by the SDK.
- `billing`: the independent `gait_pose_once` charge for this call.

## 图搜万物 API

### POST /v1/object-search

Authentication required:

- `Authorization: Bearer <api_key>` or login session cookie

Compatibility alias:

- `POST /v1/locate-anything`

Purpose:

- Forwards an image and a text prompt to the configured 图搜万物 upstream service.
- Charges the registered user's wallet with `locate_anything`.
- The configured upstream endpoint should accept `{"image_base64":"...","prompt":"..."}` and return `{"boxes":[...],"raw_text":"..."}`.

Request:

```json
{
  "image_base64": "<base64 encoded image>",
  "prompt": "person"
}
```

Response:

```json
{
  "boxes": [
    { "x1": 10, "y1": 20, "x2": 120, "y2": 260, "label": "person" }
  ],
  "raw_text": "",
  "billing": {
    "amount": 10,
    "currency": "CNY",
    "price_amount": 10,
    "price_currency": "CNY",
    "charge_amount": 10,
    "charge_currency": "CNY",
    "order_id": "locate_xxx"
  }
}
```

Minimal Python demo:

```bash
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
python3 examples/registered/python/object_search_api_demo.py examples/sample_sequences/ID_0001/001811.jpg 'person'
```

### POST /v1/public/object-search/trial

Authentication is not required.

Compatibility alias:

- `POST /v1/public/locate-anything/trial`

Purpose:

- Provides a quick no-registration trial path.
- Consumes the runtime-configured trial quota by IP.
- Does not charge wallet balance and does not use x402.

Request:

```json
{
  "image_base64": "<base64 encoded image>",
  "prompt": "person",
  "fingerprint": "optional-client-fingerprint"
}
```

Response includes the same `boxes` fields plus a `trial` object:

```json
{
  "boxes": [],
  "trial": {
    "allowed": true,
    "total_amount": 10000,
    "amount_used": 10,
    "remaining_amount": 9990
  }
}
```

## Anonymous Sequence APIs

### POST /v1/public/sequences

Request:

```json
{
  "frame_count": 4
}
```

Response:

```json
{
  "task_id": "seq_xxx",
  "task_token": "tok_xxx",
  "uploads": [
    {
      "index": 0,
      "object_key": "sequences/seq_xxx/000000.jpg",
      "upload_url": "https://...",
      "upload_expires_at": "2026-05-06T12:00:00Z"
    }
  ]
}
```

### POST /v1/public/sequences/{task_id}/parse

Headers:

- `X-Task-Token: <task_token>`

Request:

```json
{
  "frame_count": 4,
  "frames": [
    {
      "index": 0,
      "object_key": "sequences/seq_xxx/000000.jpg"
    },
    {
      "index": 1,
      "object_key": "sequences/seq_xxx/000001.jpg"
    }
  ]
}
```

`frames[].object_key` must be copied from the `POST /v1/public/sequences` create response after uploading each frame to `uploads[].upload_url`.

Unpaid request may return HTTP `402`.

402 body:

```json
{
  "error": {
    "code": "payment_required",
    "message": "sequence payment required"
  },
  "payment_context": {
    "provider": "mock",
    "phase": "sequence_once",
    "order_id": "ord_seq_xxx",
    "amount": "1.23",
    "currency": "USD",
    "expires_at": "2026-05-06T12:00:00Z",
    "pricing_basis": {
      "frame_count": 4,
      "sequence_count": 1,
      "billable_sequences": 1,
      "rate_per_sequence": 50,
      "sequence_amount": 50,
      "billable_frame_count": 4,
      "rate_per_k_frames": 2000,
      "frame_amount": 8
    },
    "challenge": {
      "mode": "mock",
      "order_id": "ord_seq_xxx"
    }
  }
}
```

Paid request returns the same result shape as the registered sequence parse API.

### POST /v1/public/sequences/{task_id}/gait-pose

Headers:

- `X-Task-Token: <task_token>`

Request:

```json
{
  "frame_count": 4,
  "frames": [
    {
      "index": 0,
      "object_key": "sequences/seq_xxx/000000.jpg"
    },
    {
      "index": 1,
      "object_key": "sequences/seq_xxx/000001.jpg"
    }
  ]
}
```

`frames[].object_key` must be copied from the `POST /v1/public/sequences` create response after uploading each frame to `uploads[].upload_url`.

Unpaid request may return HTTP `402` with `payment_context.phase = "gait_pose_once"`.

Paid request returns the same Gait Pose result shape as `POST /v1/sequences/{task_id}/gait-pose`.

### GET /v1/public/sequences/{task_id}

Headers:

- `X-Task-Token: <task_token>`

Returns task status and upload progress summary.

### GET /v1/public/sequences/{task_id}/result

Headers:

- `X-Task-Token: <task_token>`

Returns the stored sequence parse response after successful parse. Shape is the same as `POST /v1/sequences/{task_id}/parse`: `task_id`, `status`, `sequence_count`, and `sequences`.

### DELETE /v1/public/sequences/{task_id}

Headers:

- `X-Task-Token: <task_token>`

Marks the task for early cleanup.

### Mock Payment Provider

If `GAIT_PAYMENT_PROVIDER` is not set, the local development default is `mock`.
Production anonymous public calls should use `GAIT_PAYMENT_PROVIDER=x402`.

For mock settlement, either of the following is accepted:

- send JSON body field `settlement_ref`
- or send request header `X-Mock-Payment: paid`

When using the header shortcut, the server will synthesize a settlement reference automatically.

### x402 Payment Provider

To enable x402 in deployment:

- `GAIT_PAYMENT_PROVIDER=x402`
- `GAIT_X402_FACILITATOR_URL=<facilitator base url>`
- `GAIT_X402_NETWORK=<network>`
- `GAIT_X402_ASSET=<asset>`
- `GAIT_X402_PAY_TO=<receiver address>`
- `GAIT_X402_ROUTES_JSON=<json array of enabled routes>` optional, overrides single-route deployment into multi-accept deployment

Behavior:

- unpaid responses return `402`
- response header contains `PAYMENT-REQUIRED`
- response body keeps `payment_context` for debugging and non-agent clients
- client pays and retries settlement with `PAYMENT-SIGNATURE`
- legacy headers `X-Payment-Required` and `X-Payment-Signature` are also accepted for compatibility

Anonymous x402 client flow:

1. Create a public task and upload input frames or video.
2. Call the paid public endpoint once without payment, for example `POST /v1/public/sequences/{task_id}/parse`.
3. The server returns HTTP `402` with `payment_context.challenge` and header `PAYMENT-REQUIRED`.
4. Sign the challenge with an x402-compatible client/wallet.
5. Retry the same HTTP request with `PAYMENT-SIGNATURE: <signed x402 payment payload>`.

Example 402 response shape for sequence parsing:

```json
{
  "error": {
    "code": "payment_required",
    "message": "sequence parse payment required"
  },
  "payment_context": {
    "provider": "x402",
    "phase": "sequence_parse",
    "order_id": "ord_xxx",
    "amount": "0.01",
    "currency": "USD",
    "expires_at": "2026-06-20T12:00:00Z",
    "pricing_basis": {
      "input_sequence_count": 1,
      "rate_per_sequence": 10
    },
    "challenge": {
      "x402Version": 1,
      "accepts": [
        {
          "scheme": "exact",
          "network": "eip155:8453",
          "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
          "payTo": "0xReceiverAddress",
          "maxAmountRequired": "10000",
          "extra": {
            "assetSymbol": "USDC",
            "assetTransferMethod": "eip3009"
          }
        }
      ]
    }
  }
}
```

The exact challenge fields are deployment-dependent. Agents should parse `payment_context.challenge.accepts` instead of hard-coding one network or token. The Python x402 demos under `examples/anonymous/python/` show the full create-upload-preview-402-sign-retry flow.

Current project API also exposes `GET /v1/payment-capabilities`, and `/v1/portal/bootstrap` includes the same `payment_capabilities` payload.

For `x402`, this payload separates:

- `facilitator_supported_kinds`: current Coinbase CDP x402 official network/scheme support
- `project_supported_kinds`: the network/asset/payee combinations actually enabled in this deployment

As of 2026-05-19, the bundled CDP support list is aligned with the current live CDP facilitator `/supported` response:

- `eip155:84532` `Base Sepolia`
- `eip155:8453` `Base Mainnet`
- `eip155:137` `Polygon Mainnet`
- `eip155:42161` `Arbitrum One`
- `eip155:480` `World Chain`
- `eip155:4801` `World Chain Sepolia`
- `solana:mainnet` `Solana Mainnet`

The deployment may still choose to enable only one configured public payment route even when the facilitator supports more.

Current production anonymous x402 routes are:

| Network | Currency | Token contract | Method |
|---|---|---|---|
| Base Mainnet (`eip155:8453`) | USDC | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | EIP-3009 |
| Polygon Mainnet (`eip155:137`) | USDC | `0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359` | EIP-3009 |
| Arbitrum One (`eip155:42161`) | USDC | `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` | EIP-3009 |
| Base Mainnet (`eip155:8453`) | USDT | `0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2` | Permit2 |
| Polygon Mainnet (`eip155:137`) | USDT | `0xc2132D05D31c914a87C6611C10748AEb04B58e8F` | Permit2 |
| Arbitrum One (`eip155:42161`) | USDT | `0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9` | Permit2 |
| Base Mainnet (`eip155:8453`) | EURC | `0x60a3E35Cc302bFA44Cb288Bc5a4F316Fdb1adb42` | EIP-3009, converted from USD by `eurc_usd_exchange_rate` |

Route JSON example:

```json
[
  {
    "network": "eip155:8453",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "pay_to": "0xYourReceiver",
    "scheme": "exact",
    "asset_symbol": "USDC",
    "currency": "USD",
    "decimals": 6,
    "token_name": "USD Coin",
    "token_version": "2",
    "asset_transfer_method": "eip3009"
  },
  {
    "network": "eip155:137",
    "asset": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
    "pay_to": "0xYourReceiver",
    "scheme": "exact",
    "asset_symbol": "USDT",
    "currency": "USD",
    "decimals": 6,
    "token_name": "Tether USD",
    "token_version": "1",
    "asset_transfer_method": "permit2",
    "allowance_target": "0x000000000022D473030F116dDEE9F6B43aC78BA3"
  }
]
```

Recommended route policy for this project:

- keep admin-configured task prices in CNY minor units
- convert CNY to USD for anonymous x402 settlement using `cny_usd_exchange_rate`, rounded up to the next USD cent
- enable `USDC` routes on supported networks with `asset_transfer_method=eip3009`
- enable `USDT` routes on supported networks with `asset_transfer_method=permit2`
- enable `EURC` on routes where you want the server to convert the USD order amount by `fx_usd_per_asset` or runtime `eurc_usd_exchange_rate`

When a route uses `permit2`, the server now includes:

- `extra.assetTransferMethod=permit2`
- `extra.allowanceTarget=0x000000000022D473030F116dDEE9F6B43aC78BA3`

The top-level `extensions` field in the `402` challenge may also advertise facilitator gas-sponsoring capabilities such as:

- `eip2612GasSponsoring`
- `erc20ApprovalGasSponsoring`

Whether a buyer can complete a first-time Permit2 payment without a manual on-chain approval depends on the facilitator-advertised extension and the wallet client capability.

`EURC` support in this project works differently from `USDC` / `USDT`:

- admin task pricing is configured in CNY minor units; public x402 USD amount is derived using `cny_usd_exchange_rate` and rounded up to the next USD cent
- server converts the USD order amount into `EURC` using runtime `eurc_usd_exchange_rate`
- default exchange rate is `1.15`, meaning `1 EUR = 1.15 USD`
- the rate is stored in admin runtime config and can be updated without restarting the service

### Registered User Recharge Checkout Providers

Anonymous public-task payment and registered-user wallet recharge are configured separately.

Anonymous/public-task payment still uses:

- `GAIT_PAYMENT_PROVIDER`

Registered-user recharge checkout uses:

- `GAIT_CHECKOUT_DEFAULT_PROVIDER`
- `GAIT_PUBLIC_BASE_URL`

Optional registered-user checkout providers:

- Stripe
  - `GAIT_STRIPE_SECRET_KEY`
  - `GAIT_STRIPE_WEBHOOK_SECRET`
  - `GAIT_STRIPE_API_BASE_URL`
- Paddle
  - `GAIT_PADDLE_API_KEY`
  - `GAIT_PADDLE_WEBHOOK_SECRET`
  - `GAIT_PADDLE_API_BASE_URL`
- WeChat Pay
  - `GAIT_WECHAT_PAY_APP_ID`
  - `GAIT_WECHAT_PAY_MERCHANT_ID`
  - `GAIT_WECHAT_PAY_SERIAL_NO`
  - `GAIT_WECHAT_PAY_PRIVATE_KEY_PEM` or `GAIT_WECHAT_PAY_PRIVATE_KEY_PATH`
  - `GAIT_WECHAT_PAY_API_V3_KEY`
  - `GAIT_WECHAT_PAY_API_BASE_URL`
- Alipay
  - `GAIT_ALIPAY_APP_ID`
  - `GAIT_ALIPAY_PRIVATE_KEY_PEM` or `GAIT_ALIPAY_PRIVATE_KEY_PATH`
  - `GAIT_ALIPAY_PUBLIC_KEY_PEM` or `GAIT_ALIPAY_PUBLIC_KEY_PATH`
  - `GAIT_ALIPAY_GATEWAY_URL`

Provider selection rules:

- `channel=manual_offline` creates a pending manual deposit order
- `channel=alipay` prefers `alipay`
- `channel=wechat` or `channel=wechat_pay` prefers `wechat_pay`
- `channel=card` prefers `stripe`, then `paddle`, then `hosted_mock`
- region-specific wallet/bank methods such as `paypal`, `ideal`, `pix`, `upi`, `blik` prefer `paddle`, then `stripe`, then `hosted_mock`
