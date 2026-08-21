# W-Agent API Reference

## Overview

This document defines the W-Agent V1 public API for tracked person sequence
parsing, identity features, human 2D/3D keypoints, and Object Search.

Supported capabilities:

- Sequence parsing: synchronous

Supported payment modes:

- Registered users: portal email or phone login + prepaid wallet + API key for interface calls
- Anonymous users and agents: payment provider selected by deployment

Access model:

- Registered-user task APIs are available on private routes under `/v1/sequences`.
- Anonymous callers and agents must use `/v1/public/sequences`, `/v1/public/object-search`, `/v1/public/features/face`, or `/v1/public/features/reid`.
- There is no supported "anonymous but non-public" task mode.

Current provider support:

- `mock`: local development fallback when `GAIT_PAYMENT_PROVIDER` is not set
- `x402`: implemented and used for production anonymous public calls when configured
- `ap2`: reserved for later

## API Workflow Model

For API callers, W-Agent has three main workflows:

- Sequence workflow: create a sequence task, batch-upload ordered person frames with `/uploads/batch`, then call `/parse` for identity features or `/gait-pose` for keypoints.
- Object Search workflow: send one image plus a text prompt and read returned bounding boxes.

The implementation details behind task storage, workers, and cleanup are not
required for normal API integration. Focus on the task state, returned upload
URLs, `object_key` values, and final JSON response shapes.

## Authentication

Portal login:

- `POST /v1/users/register` with `email` + `email_code` + `password`, or `phone` + `sms_code` + `password`. The portal auto-detects whether the single account input is an email or phone number. If both email and phone are supplied, both enabled verification channels must pass before the account is created.
- `POST /v1/users/login` with `identifier` + `password`; `identifier` may be email or phone. The response includes `access_token` for client self-service APIs.
- `POST /v1/users/email-code` sends email verification codes for email registration, password reset, and binding email to a logged-in account
- `POST /v1/users/sms-code` sends Aliyun SMS verification codes for phone registration and binding phone when SMS runtime config is enabled
- `POST /v1/me/bind-email` binds a verified email to the current logged-in account
- `POST /v1/me/bind-phone` binds a verified phone number to the current logged-in account
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

Use the public API base URL for your region:

```text
Mainland China: https://www.w-agent.cn/api
Overseas entry: https://www.h-agent.ai/api
```

Overseas redirects to `w-agent.cn` are expected. Do not guess
`https://api.w-agent.cn`; it is not the documented API origin and may fail TLS
hostname verification in clients such as Python `requests`.

Registered calls use:

```http
Authorization: Bearer <api_key>
```

## Choose The Right Task

For agents and first-time users, choose by intent instead of API name:

- To decide whether two tracks are the same person, use gait/face/ReID features from sequence parsing. Do not compare raw images or generic image embeddings.
- To get stable person sequences from a video, prefer local video preprocessing first: detect, track, crop, write one folder per person sequence, then upload each folder to the Sequence API.
- To extract 2D/3D keypoints, upload a sequence first and call `POST /v1/sequences/{task_id}/gait-pose`.
- To find objects or people by text in a single image, use Object Search.
- To call as a registered user, use `Authorization: Bearer <api_key>` on registered routes and pay from account balance.
- To call anonymously, use public routes, handle HTTP 402 `payment_context`, sign an x402 payment, and retry the same HTTP request.

W-Agent's core input for identity and pose APIs is a tracked person sequence, not an arbitrary full scene image.

Task decision table:

| User intent | Recommended API | Notes |
| --- | --- | --- |
| Judge whether two tracks are the same person | `POST /v1/sequences/{task_id}/parse` | Compare same-type `gait_feature`, `face_feature`, or `reid_feature` by dot product. |
| Get identity features from a local video | Local video-to-sequence demo + Sequence API | Local preprocessing creates sequence folders and JSON files side by side. |
| Get every person's 2D/3D keypoints from a local video | Local video-to-sequence demo + `POST /v1/sequences/{task_id}/gait-pose` | Split the video into one sequence per person first. |
| Find targets in one image by text | `POST /v1/object-search` | Returns one or more boxes in uploaded image coordinates. |
| Compare whether two raw images look alike | Not a W-Agent identity workflow | Do not replace identity matching with raw pixel or generic image similarity. |

## Agent Quickstart: Parse Local Sequences And Compare

The demo package contains small public sequence data under
`examples/seqs`. These sequences are intended to return valid
`gait_feature` and `reid_feature` results.

Run the compact Python demo:

```bash
python3 examples/registered/python/gait_sequence_api_demo.py
```

The sequence API flow is:

1. `POST /v1/sequences` with `{"frame_count": N}`.
2. Upload all images once with `POST /v1/sequences/{task_id}/uploads/batch` as `multipart/form-data`.
3. Keep each returned `uploads[].object_key`.
4. `POST /v1/sequences/{task_id}/parse` with `frames[].index` and `frames[].object_key`.
5. Read features from `response.sequences[]`, for example `response.sequences[0].gait_feature`.

Each sequence frame upload is rejected if the request body exceeds 20 MB; the server does not truncate oversized uploads.

Similarity:

- `gait_feature` compares only with `gait_feature`.
- `face_feature` compares only with `face_feature`.
- `reid_feature` compares only with `reid_feature`.
- Use dot product: `sum(a * b for a, b in zip(feature_a, feature_b))`.
- For face similarity display, convert the face dot product with `min(dot_product * 2, 1)` before formatting as a percentage.
- `face_feature` can be `null` or empty when no usable face is detected; this is not an API failure.

Common first-use errors:

- `400 invalid request body` on `POST /v1/sequences`: you probably uploaded images directly; send only `{"frame_count": N}` first.
- Missing or empty `frames` on `/parse`: pass back `object_key` values returned by create.
- Empty `response.sequences`: the frames did not form a valid moving gait sequence.
- TLS hostname mismatch: use documented public origins such as `https://www.w-agent.cn/api` or `https://www.h-agent.ai/api`, not `https://api.w-agent.cn`.

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
# Edit API_KEY, BASE_URL, and the input path constants in the demo file first.
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

The local video-to-sequence demos are the recommended path when the caller wants
control over local decoding, detection, tracking, and output folders.

Boundary:

- If the goal is pose for every person sequence, use the local video-to-sequence demo and call Gait Pose on each sequence.
- If the caller needs deterministic local output folders, use local preprocessing.

## Quickstart: Video To Each Person's 2D/3D Keypoints

Use this task-level workflow when the user says: "I have a video and want 2D/3D
keypoints for every person sequence."

Recommended flow:

1. Download or open the registered Python demo package.
2. Run `local_video_to_gait_pose_api_demo.py`.
3. The demo performs local person detection, tracking, and cropping.
4. The demo creates one `sequence_XXX` folder per person track.
5. Upload each sequence folder with `POST /v1/sequences`, then `POST /v1/sequences/{task_id}/uploads/batch` as `multipart/form-data`.
6. Call `POST /v1/sequences/{task_id}/gait-pose` for each uploaded sequence.
7. Save each sequence's `result.json`, `pose_2d.csv`, and `pose_3d.csv` beside its frames.

Command:

```bash
# Edit API_KEY, BASE_URL, and the input path constants in the demo file first.
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_gait_pose_api_demo.py /path/to/video.mp4
```

Gait Pose is a sequence API and is clearest when called on locally detected and
tracked sequence images.

Sequence input requirements for identity and pose APIs:

- Use images from one tracked person sequence, ordered by time.
- Prefer person crops, not full surveillance frames with multiple people and large background.
- Keep `frames[].index` in the same temporal order as the images.
- Provide enough moving-person frames. Very short or static tracks may return an empty result or a backend validation error.
- If one track mixes multiple people, the backend may split it into multiple clean output sequences or drop ambiguous frames.
- If images are crops and you need original-video coordinates later, keep local metadata such as `crop_x`, `crop_y`, `crop_w`, and `crop_h`.

Recommended local demo output shape:

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

## Task Types

- `sequence`

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
- `GET /portal/demo-download?type=object-search-api-key-python`
- `GET /portal/demo-download?type=object-search-api-key-cpp`
- `GET /portal/demo-download?type=object-search-api-key-go`
- `GET /portal/demo-download?type=pose-api-key-python`
- `GET /portal/demo-download?type=pose-api-key-cpp`
- `GET /portal/demo-download?type=pose-api-key-go`
- `GET /portal/demo-download?type=gait-api-key-python`
- `GET /portal/demo-download?type=gait-api-key-cpp`
- `GET /portal/demo-download?type=gait-api-key-go`
- `GET /portal/demo-download?type=face-api-key-python`
- `GET /portal/demo-download?type=face-api-key-cpp`
- `GET /portal/demo-download?type=reid-api-key-python`
- `GET /portal/demo-download?type=reid-api-key-cpp`
- `GET /portal/demo-download?type=reid-api-key-go`
- `GET /portal/demo-download?type=object-search-x402-python`
- `GET /portal/demo-download?type=face-x402-python`
- `GET /portal/demo-download?type=reid-x402-python`
- `GET /portal/demo-download?type=pose-x402-python`
- `GET /portal/demo-download?type=gait-x402-python`
- `GET /portal/demo-download?type=object-search-client-windows`
- `GET /portal/demo-download?type=object-search-client-mac`
- `GET /portal/demo-download?type=pose-client-windows`
- `GET /portal/demo-download?type=pose-client-mac`
- `GET /portal/demo-download?type=gait-client-windows`
- `GET /portal/demo-download?type=gait-client-mac`

`type=browser-pose` and `type=browser-gait` return standalone HTML files
directly for the online browser client entry used by the homepage. `type=browser`
is kept as a compatibility alias for the gait browser client.

Compiled client download types read the first non-hidden regular file from these
server directories and return `404 client_binary_unavailable` until a binary is
uploaded. The resource download page checks these directories on each `/portal`
request; empty directories render as `-`, and directories with a file render a
link with the real file name. Refresh the page after uploading or replacing
client binaries.

- `object-search-client-windows`: `/data/gaitagent/resource_downloads/clients/object-search/windows/`
- `object-search-client-mac`: `/data/gaitagent/resource_downloads/clients/object-search/mac/`
- `pose-client-windows`: `/data/gaitagent/resource_downloads/clients/pose/windows/`
- `pose-client-mac`: `/data/gaitagent/resource_downloads/clients/pose/mac/`
- `gait-client-windows`: `/data/gaitagent/resource_downloads/clients/gait/windows/`
- `gait-client-mac`: `/data/gaitagent/resource_downloads/clients/gait/mac/`

Other resource download types return ZIP packages.

Resource links display the actual ZIP file name, such as
`gait-api-key-python.zip`. ZIP packages use that file name without
`.zip` as the top-level folder and strip the long source prefixes like
`examples/registered/python/` or `examples/anonymous/python/`. Each
single-algorithm ZIP package includes both `README.md` and `README.zh.md` at
the package root. Those README files are algorithm-specific; for example the
gait package documents only gait recognition, and the face package documents
only face recognition. Subdirectories that are useful as standalone entrypoints
also include English and Chinese README files. Pose and gait Python packages
include both existing-sequence API examples and local-video detection/tracking
examples that generate sequences before calling the API.
ReID packages provide single-person image feature demos only.
Anonymous x402 Python packages are split by algorithm: Object Search, face
feature, ReID feature, gait sequence parsing, and gait-pose.

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
- `POST /v1/admin/users/batch`
- `POST /v1/admin/users/{user_id}/topups`
- `GET /v1/admin/users/{user_id}/ledger`
- `GET /v1/admin/users/{user_id}/deposits`
- `POST /v1/admin/users/{user_id}/deposits/{deposit_id}/settle`
- `GET /v1/admin/sequences`
- `GET /v1/admin/sequences/{task_id}`
- `DELETE /v1/admin/sequences/{task_id}`

User self-service endpoints:

- `POST /v1/users/register`
- `POST /v1/users/login`
- `POST /v1/users/logout`
- `GET /v1/api-keys`
- `GET /v1/api-keys/current/status`
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
- `GET /v1/me/sequences`
- `POST /v1/object-search`

`GET /v1/me/ledger` supports user-side usage-record filtering:

- `limit`: positive integer, capped at `1000`; `all` is accepted for filtered views.
- `start_date`, `end_date`: `YYYY-MM-DD`; when both are provided, the date span must not exceed 6 months.
- `api_key_id`: restrict results to one API Key.
- `reason_code` or `type`: restrict results to one billing reason, such as `sequence_once`, `gait_pose_once`, or `locate_anything`.
- `keyword`: searches ledger reason/task/order/detail text.

The user portal API Key usage dialog calls this endpoint with `api_key_id` and the current filters instead of loading all historical ledger rows in the browser.

Public trial endpoints:

- `POST /v1/public/object-search`
- `POST /v1/public/features/face`
- `POST /v1/public/features/reid`
- `POST /v1/public/object-search/trial`
- `POST /v1/public/sequences`
- `POST /v1/public/sequences/{task_id}/uploads/batch`
- `POST /v1/public/trial/sequences/{task_id}/parse`
- `POST /v1/public/trial/sequences/{task_id}/gait-pose`

Portal behavior:

- `/portal` is both the public landing page and the logged-in user center.
- Public users can read product introduction, supported anonymous payment routes, and download demos before registering.
- Registered users log in with email or phone and password, then manage balance, recharge, API Keys, usage records, and demo downloads.
- The visible product name in the portal is `W-Agent`.
- API Keys are used only for API calls; portal login itself uses the account/password session cookie.

Query parameters:

- `status`
- `limit`

Deployment config:

- `GAIT_ADMIN_TOKEN`
- `GAIT_RUNTIME_CONFIG_PATH`

## Status Model

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

Runtime configuration includes pricing parameters for:
  - `sequence_per_k_frames`
  - `sequence_per_sequence`
  - `gait_pose_per_sequence`
  - `face_per_k_frames`
  - `reid_per_k_frames`
  - `currency`
  - `cny_usd_exchange_rate`
  - `eurc_usd_exchange_rate`
- Runtime configuration also stores trial and Object Search parameters:
  - `trial.enabled`
  - `trial.total_amount` (CNY minor units; applied independently to each trial algorithm bucket)
  - `trial.max_upload_bytes`
  - `locate_anything.enabled`
  - `locate_anything.endpoint`
  - `locate_anything.timeout_seconds`
  - `locate_anything.price_per_image`

Pricing amounts configured in admin are stored as CNY minor units (fen). Registered-user wallet balance, monthly plan allowance, and usage records use CNY. English UI and public price estimates may show USD equivalents by `cny_usd_exchange_rate`; anonymous x402 settlement is still USD/stablecoin based, and the server converts CNY order amounts to USD cents by `cny_usd_exchange_rate`. CNY to USD conversion is always rounded up to the next USD cent, with any positive USD amount displayed or charged as at least `$0.01`.

Runtime behavior:

- the API process runs retention cleanup every 30 seconds; the worker also runs sequence cleanup during its polling loop
- when `expire_at` is reached, task status becomes `expired`
- when `delete_after_at` is reached for `succeeded` or `failed`, artifacts are removed and task status becomes `deleted`
- when `delete_after_at` is reached for `expired`, artifacts and bulky details are removed and the task status becomes `deleted`
- deleted task records are retained as lightweight summaries; uploaded media, result assets, tokens, and full result JSON are pruned
- sample archives under `<GAIT_DATA_DIR>/sequence_samples` are separate long-lived copies and are not removed by task retention cleanup

## Billing Model

- `rounded_sequence_frames` is rounded up to 100-frame blocks; the frame-fee amount is rounded up to the next CNY minor unit
- when `sequence_per_k_frames = 0`, the sequence frame fee is disabled and omitted from billing details

Sequence parsing:

- registered-user amount = `max(output_sequence_count, 1) * sequence_per_sequence`
- anonymous x402 amount = `input_sequence_count * sequence_per_sequence`
- when `sequence_per_k_frames > 0`, both registered and anonymous sequence parsing also add the rounded sequence frame fee above
- current Sequence API accepts one input sequence per task, so `input_sequence_count = 1`
- `output_sequence_count` is the number of split single-person sequences returned by `GetSplitSeqFeature`; for registered users, no valid output still bills as `1` sequence
- registered users also have a monthly sequence feature extraction limit. The limit counts actual successful output sequences with gait features, not the billing minimum. Default is 100000 sequences per user per calendar month and can be changed in Admin runtime config.
- registered sequence parsing is rejected when the account has no usable CNY balance or has already reached the monthly feature limit.

Gait Pose:

- amount = `1 * gait_pose_per_sequence`
- when `sequence_per_k_frames > 0`, Gait Pose also adds the rounded sequence frame fee above
- default price is `¥0.01 / sequence`

Object Search:

- amount = `1 * locate_anything.price_per_image`
- default registered-user price is `¥0.10 / image`
- trial calls do not charge wallet balance; they consume the runtime-configured per-algorithm trial amount stored in `trial_usage` and append a zero-amount `usage_records` row with `source=trial`
- portal homepage and browser-client trial calls share the same IP bucket for the same algorithm
- trial quota is limited by cumulative amount for the same IP and algorithm bucket; daily request and daily frame limits are not enforced
- Gait Pose is a separate endpoint and is billed independently from full gait sequence parsing

Face Recognition:

- endpoint: `POST /v1/features/face`
- anonymous x402 endpoint: `POST /v1/public/features/face`
- no-registration trial endpoint: `POST /v1/public/features/trial/face`
- input: one corrected/aligned face image in `image_base64`
- output: `feature_dim = 512`, `feature` contains 512 float values
- similarity display: compute same-type feature dot product, then use `min(dot_product * 2, 1)` as the percentage base
- amount = `ceil(face_per_k_frames * 1 / 1000)` CNY minor units
- default price is `¥1.00 / 1000 images`; a single image is rounded up to `¥0.01`
- API examples include Python and C++ packages. They use `face_detect.onnx` with ONNX Runtime CPU for local face detection and five-point landmark detection, then align the face before calling the feature endpoint.
- `face_detect.onnx` is generated from Shiqi Yu libfacedetection `facedetectcnn-data.cpp`; pre-processing and post-processing remain in the client example code.

ReID Recognition:

- endpoint: `POST /v1/features/reid`
- anonymous x402 endpoint: `POST /v1/public/features/reid`
- no-registration trial endpoint: `POST /v1/public/features/trial/reid`
- input: one person image in `image_base64`
- output: `feature_dim = 512`, `feature` contains 512 float values
- amount = `ceil(reid_per_k_frames * 1 / 1000)` CNY minor units
- default price is `¥1.00 / 1000 images`; a single image is rounded up to `¥0.01`

Registered user settlement:

- `GET /v1/api-keys/current/status` checks whether a Bearer API Key is valid and currently usable without creating a task.
- `POST /v1/sequences/{task_id}/parse` automatically charges the wallet before processing
- `POST /v1/sequences/{task_id}/gait-pose` automatically charges the wallet before processing
- `POST /v1/features/face` and `POST /v1/features/reid` synchronously extract one 512-dimensional feature and charge the wallet after successful SDK processing
- `GET /v1/sequences/{task_id}/result` returns the stored sequence parse response for registered users without re-charging

### POST /v1/features/face

Extract a 512-dimensional face feature from one corrected/aligned face image.

```json
{
  "image_base64": "/9j/4AAQSkZJRg..."
}
```

Response:

```json
{
  "task_id": "face_feature_1786000000000000000",
  "status": "succeeded",
  "feature_dim": 512,
  "feature": [0.01, -0.02, 0.03],
  "billing": {
    "phase": "face_feature_once",
    "amount": "1",
    "currency": "CNY"
  }
}
```

### POST /v1/features/reid

Extract a 512-dimensional ReID feature from one person image.

```json
{
  "image_base64": "/9j/4AAQSkZJRg..."
}
```

Response shape is the same as face recognition, with `phase = reid_feature_once`.

### POST /v1/public/features/trial/face

No-registration trial face feature extraction. Request body is the same as
`POST /v1/features/face`, with optional `fingerprint`. The response returns
`feature`, `feature_dim`, and a `trial` object with consumed and remaining trial
amount. It consumes the independent `face_feature_once` trial bucket and does
not charge a registered wallet.

### POST /v1/public/features/trial/reid

No-registration trial ReID feature extraction. Request body is the same as
`POST /v1/features/reid`, with optional `fingerprint`. The response returns
`feature`, `feature_dim`, and a `trial` object with consumed and remaining trial
amount. It consumes the independent `reid_feature_once` trial bucket and does
not charge a registered wallet.

### POST /v1/users/login

Request:

```json
{
  "email": "user@example.com",
  "password": "secret"
}
```

or:

```json
{
  "identifier": "13800138000",
  "password": "secret"
}
```

Response includes the login session token. The same token is also set as the `gait_user_session` cookie for browser portal use.

```json
{
  "access_token": "gus_xxx",
  "token_type": "Bearer",
  "user": {
    "user_id": "usr_xxx",
    "email": "user@example.com"
  },
  "api_keys": [],
  "wallets": [],
  "expires_at": "2026-07-06T00:00:00Z"
}
```

Desktop clients can use:

```http
Authorization: Bearer gus_xxx
```

for login-session APIs such as `GET /v1/api-keys`. Task parse APIs still use `Authorization: Bearer gak_xxx`.

### POST /v1/me/bind-email

Requires the login session token or `gait_user_session` cookie. Send the verification code first with `POST /v1/users/email-code` using `purpose=bind_email`.

```json
{
  "email": "user@example.com",
  "email_code": "123456"
}
```

### POST /v1/me/bind-phone

Requires the login session token or `gait_user_session` cookie. Send the verification code first with `POST /v1/users/sms-code` using `purpose=bind_phone`.

```json
{
  "phone": "13800138000",
  "sms_code": "123456"
}
```

### GET /v1/api-keys

Returns the current logged-in user's active API Keys, including the full `gak_xxx` secret needed by desktop/browser clients to call task APIs.

Authentication:

- `Authorization: Bearer <access_token returned by /v1/users/login>`
- Browser session cookie `gait_user_session`

API Key Bearer tokens (`gak_xxx`) are rejected for this endpoint, because they must not be able to enumerate other full keys on the same account.

Response:

```json
{
  "user_id": "usr_xxx",
  "api_keys": [
    {
      "id": "key_xxx",
      "key_id": "key_xxx",
      "name": "default",
      "key": "gak_xxx",
      "key_prefix": "gak_08885d26",
      "valid": true,
      "usable": true,
      "balance_status": "ok",
      "remaining_credits": 42183,
      "currency": "CNY",
      "wallet_balance": 40000,
      "monthly_balance": 2183
    }
  ],
  "count": 1
}
```

Client handling:

- `count=0`: show "当前账号没有可用 API Key".
- `count=1`: auto-fill `api_keys[0].key`.
- `count>1`: let the user choose by `name`, `key_prefix`, and balance status.
- `usable=false` or `balance_status=insufficient_balance`: block paid operations until recharge or monthly plan purchase.

### GET /v1/api-keys/current/status

Use this endpoint when a desktop or browser client needs to validate a configured API Key before starting work. It does not create any task and does not charge the wallet.

Authentication:

- `Authorization: Bearer <api_key>`

Rate limit:

- Same client IP: up to 60 checks per minute.
- Same submitted API Key token: up to 20 checks per minute.
- When limited, the endpoint returns HTTP `429` with the same JSON shape and message `请求过于频繁，请稍后再试`.

Valid and usable:

```json
{
  "valid": true,
  "usable": true,
  "balance_status": "ok",
  "remaining_credits": 1234,
  "message": "",
  "currency": "CNY",
  "wallet_balance": 1000,
  "monthly_balance": 234
}
```

Valid but no usable balance:

```json
{
  "valid": true,
  "usable": false,
  "balance_status": "insufficient_balance",
  "remaining_credits": 0,
  "message": "余额不足，请充值后继续使用"
}
```

Invalid API Key:

```json
{
  "valid": false,
  "usable": false,
  "balance_status": "unknown",
  "remaining_credits": 0,
  "message": "API Key 无效"
}
```

Client handling:

- `valid=false`: ask the user to re-enter the API Key.
- `valid=true && usable=false`: block paid operations and ask the user to recharge or buy a monthly plan.
- `valid=true && usable=true`: allow normal API use.

Deposit workflow:

- `POST /v1/me/deposits` creates a user deposit order
- `POST /v1/me/monthly-plans` with a third-party payment channel creates the same kind of `account_deposits` checkout order with `detail.purchase_kind=monthly_plan`
- `POST /v1/me/deposits/{deposit_id}/checkout` recreates or resumes a hosted checkout session
- `GET /v1/me/deposits` lists the caller's deposit orders
- `GET /v1/me/deposits/{deposit_id}` returns a single deposit order
- `POST /v1/admin/users/{user_id}/deposits/{deposit_id}/settle` credits the wallet and marks the deposit `settled`
- `POST /v1/payments/webhooks/wechat_pay` handles WeChat Pay notify settlement
- `POST /v1/payments/webhooks/alipay` handles Alipay notify settlement
- `POST /v1/payments/webhooks/crypto` handles third-party crypto provider IPN/webhook settlement
- current implementation supports:
  - `provider=wechat_pay`: WeChat Pay Native checkout
  - `provider=alipay`: Alipay page or WAP checkout
  - `provider=crypto` / `channel=crypto`: create a third-party crypto provider payment order for the selected network/token; provider webhook confirmation credits the original deposit amount into the CNY wallet
  - if `provider` is omitted, the server selects a checkout provider from `channel` and deployment config
  - manual/offline recharge orders are not supported; administrators can use backend top-up for balance adjustments

Recharge checkout and monthly-plan checkout intentionally share the same checkout order creation path for Alipay and WeChat Pay. Provider/channel selection, CNY/USD handling, checkout session creation, and `account_deposits` persistence must stay identical for those hosted checkout channels. Crypto recharge also uses the checkout provider abstraction, but is limited to balance recharge: the provider creates a payment order and the verified provider webhook settles the deposit. Monthly-plan purchase does not use crypto directly; overseas users can recharge by crypto first, then buy plans with wallet balance.

WeChat Pay settlement primarily relies on the WeChat asynchronous notify webhook. The API also supports WeChat order query by `out_trade_no` as a reconciliation path for delayed or missing webhooks; both paths use the same deposit lookup, amount validation, and `SettleDeposit` code. WeChat promotions can make `amount.payer_total` lower than the merchant order amount, so validation uses `amount.total` against `account_deposits.amount`; `amount.payer_total` is stored in `detail_json.wechat_pay_payer_total` only for audit. Alipay validation uses `total_amount` against `account_deposits.amount`; discount-related paid/receipt fields are not used as the order amount.

`POST /v1/me/deposits` response shape:

```json
{
  "deposit": {
    "deposit_id": "dep_123",
    "status": "awaiting_checkout",
    "provider": "alipay",
    "checkout_provider": "alipay",
    "checkout_status": "open",
    "checkout_url": "https://openapi.alipay.com/gateway.do?..."
  },
  "checkout": {
    "provider": "alipay",
    "status": "open",
    "url": "https://openapi.alipay.com/gateway.do?...",
    "session_id": "ali_dep_123"
  }
}
```

Pricing payload shape:

```json
{
  "currency": "USD",
  "sequence_per_k_frames": 2000,
  "sequence_per_sequence": 50,
  "gait_pose_per_sequence": 1,
  "face_per_k_frames": 100,
  "reid_per_k_frames": 100
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
  "name": "gender",
  "raw_value": 180,
  "category_index": 0,
  "uncertain": false,
  "score": 0.8,
  "threshold": 0.57,
  "valid": true,
  "label": "male"
}
```

Unknown example:

```json
{
  "key": "gender",
  "name": "gender",
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

## Registered Sequence APIs

### POST /v1/sequences

Authentication required:

- `Authorization: Bearer <api_key>`

Input requirements:

- Frames should come from one tracked person sequence and stay in temporal order.
- Person crops are recommended. Full scene images with multiple people are not the intended input.
- Very short, static, or heavily occluded tracks may produce an empty `sequences` array or a validation error.
- If one uploaded track contains an identity switch, the backend may split it into multiple output sequences or drop ambiguous frames.

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

### POST /v1/sequences/{task_id}/uploads/batch

Authentication required:

- `Authorization: Bearer <api_key>`

Upload multiple sequence frames in one `multipart/form-data` request. The total
batch request body must not exceed 32 MB.

Fields:

- `upload_token`: token parsed from `uploads[].upload_url`
- `frames`: repeated file parts, in sequence order

Frame indexes are assigned by multipart order. The first `frames` part is index
0, the second is index 1, and so on. File names are ignored by the API.

MCP JSON-RPC clients cannot send multipart file parts. Use the MCP tool
`upload_sequence_frames_batch` with `frames[].content_base64`; it applies the
same array-order indexing rule.

Example:

```bash
curl -X POST "https://www.w-agent.cn/api/v1/sequences/seq_xxx/uploads/batch" \
  -H "Authorization: Bearer gak_xxx" \
  -F "upload_token=..." \
  -F "frames=@./images/000000.jpg;type=image/jpeg" \
  -F "frames=@./images/000001.jpg;type=image/jpeg"
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
- `frames`: frame IDs and optional boxes returned by the SDK for this output sequence. When one input sequence is split into multiple output sequences, clients should use these frame IDs to map each returned sequence back to the original uploaded frames. When the SDK does not return frame-level mapping, this field is an empty array and `frame_count` is `0`.
- `gait_feature`: for registered users, 512-dimensional gait features are rotated by the user's bound 512x512 orthogonal matrix before being returned. The same user gets stable rotated features across calls; different users get different rotations.
- `emotions`: emotion output returned by the SDK.
- `gait_images`: response-compatible field for per-frame gait crops. Public API responses currently keep it as an empty array and do not embed image bytes.
- `gait_image` / `face_image`: signed task-scoped asset URLs. These URLs expire with the task retention window; after expiry or cleanup, downloading returns an error instead of another task's asset.

Quota errors:

- `429 monthly_sequence_feature_limit_exceeded`: the account has reached the configured monthly sequence feature extraction limit.
- `409 wallet_insufficient_balance`: registered account has no usable recharge or monthly balance. Registered sequence/video task creation also returns this before upload starts.

Runnable Python example:

```python
import math
import os
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests

BASE_URL = os.getenv("W_AGENT_BASE_URL", "https://www.w-agent.cn/api")
API_KEY = os.getenv("W_AGENT_API_KEY")
IMAGE_DIR = Path(os.getenv("W_AGENT_IMAGE_DIR", "./sequence_frames"))

if not API_KEY:
    raise RuntimeError("Set W_AGENT_API_KEY")


def request_json(session, method, path, **kwargs):
    url = urljoin(BASE_URL.rstrip("/") + "/", path.lstrip("/"))
    resp = session.request(method, url, timeout=120, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed: {resp.status_code} {resp.text}")
    return resp.json()


def upload_token_from_uploads(uploads):
    token = parse_qs(urlparse(str(uploads[0]["upload_url"])).query).get("token", [""])[0]
    if not token:
        raise RuntimeError("upload_url has no token")
    return token


def upload_frames_batch(session, task_id, upload_token, frames):
    files = []
    handles = []
    try:
        for index, path in enumerate(frames):
            handle = path.open("rb")
            handles.append(handle)
            files.append(("frames", (f"{index:06d}{path.suffix.lower()}", handle, "image/jpeg")))
        url = urljoin(BASE_URL.rstrip("/") + "/", f"v1/sequences/{task_id}/uploads/batch")
        resp = session.post(url, data={"upload_token": upload_token}, files=files, timeout=120)
        if resp.status_code >= 400:
            raise RuntimeError(f"batch upload failed: {resp.status_code} {resp.text}")
    finally:
        for handle in handles:
            handle.close()


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
    uploads = created["uploads"]
    upload_frames_batch(session, task_id, upload_token_from_uploads(uploads), frames)
    parse_frames = [{"index": upload["index"], "object_key": upload["object_key"]} for upload in uploads]

    parsed = request_json(
        session,
        "POST",
        f"/v1/sequences/{task_id}/parse",
        json={"frames": parse_frames},
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
        "sequence_count": 1,
        "billable_sequences": 1,
        "rate_per_sequence": 1,
        "sequence_amount": 1
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

Frame and coordinate rules:

- `pose_2ds[i]` and `pose_3ds[i]` correspond to the uploaded sequence frame at the same ordered position unless `frames` provides a more explicit mapping.
- Coordinates are relative to the uploaded sequence image, not the original full video frame.
- If uploaded images are person crops, map 2D coordinates back to the original video frame by adding local crop metadata such as `crop_x` and `crop_y`.
- Invalid or low-quality frames may produce empty, null, or low-score pose entries depending on SDK output; clients should filter by array length and score.

## Object Search API

### POST /v1/object-search

Authentication required:

- `Authorization: Bearer <api_key>`

Compatibility alias:

- `POST /v1/locate-anything`

Purpose:

- Forwards an image and a text prompt to the configured Object Search upstream service.
- Charges the registered user's wallet with `locate_anything`.
- On the portal homepage, logged-in users with an active API Key use their default API Key for Object Search, so non-technical users can keep using the homepage experience after registration and top-up/monthly-plan purchase. The online browser Pose/Gait clients opened from the same logged-in portal session follow the same rule: logged-in users are billed through the default API Key, while non-logged-in users use the trial endpoints.
- The configured upstream endpoint should accept `{"image_base64":"...","prompt":"..."}` and return `{"boxes":[...],"raw_text":"..."}`.

Input and output rules:

- `image_base64` should be raw base64 content without the `data:image/...;base64,` prefix.
- JPEG and PNG are the safest image formats.
- `prompt` can be Chinese or English when the configured upstream model supports it.
- `boxes` may contain zero, one, or many matches.
- No match is a successful response with `boxes: []`, not an API failure.
- Box coordinates are pixel coordinates in the uploaded image: `x1,y1` top-left and `x2,y2` bottom-right.
- `label` is generated by the upstream model and is not a fixed taxonomy.

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
# Edit API_KEY, IMAGE_PATH, and PROMPT in the demo file first.
python3 examples/registered/python/object_search_api_demo.py
```

### POST /v1/public/object-search

Authentication is not required.

Compatibility alias:

- `POST /v1/public/locate-anything`

Purpose:

- Provides anonymous x402 paid Object Search.
- A request without a payment signature returns HTTP `402` with `payment_context.challenge`.
- The client signs the x402 challenge and retries the same request with `PAYMENT-SIGNATURE`.
- Successful paid calls are recorded as public `locate_anything` usage.

Request:

```json
{
  "image_base64": "<base64 encoded image>",
  "prompt": "person",
  "idempotency_key": "optional-client-key"
}
```

Minimal Python x402 demo:

```bash
# Edit EVM_PRIVATE_KEY, IMAGE_PATH, and PROMPT in the demo file first.
python3 examples/anonymous/python/anonymous_object_search_x402_demo.py
```

### POST /v1/public/features/face

Authentication is not required.

Purpose:

- Provides anonymous x402 paid face feature extraction.
- A request without a payment signature returns HTTP `402` with `payment_context.challenge`.
- The client signs the x402 challenge and retries the same request with `PAYMENT-SIGNATURE`.
- The input should be one detected and aligned face image.

Request:

```json
{
  "image_base64": "<base64 encoded aligned face image>",
  "idempotency_key": "optional-client-key"
}
```

Minimal Python x402 demo:

```bash
# Edit EVM_PRIVATE_KEY and IMAGE_PATH in the demo file first.
python3 examples/anonymous/python/anonymous_face_x402_demo.py
```

### POST /v1/public/features/reid

Authentication is not required.

Purpose:

- Provides anonymous x402 paid ReID feature extraction.
- A request without a payment signature returns HTTP `402` with `payment_context.challenge`.
- The client signs the x402 challenge and retries the same request with `PAYMENT-SIGNATURE`.
- The input should be one cropped person image.

Request:

```json
{
  "image_base64": "<base64 encoded person image>",
  "idempotency_key": "optional-client-key"
}
```

Minimal Python x402 demo:

```bash
# Edit EVM_PRIVATE_KEY and IMAGE_PATH in the demo file first.
python3 examples/anonymous/python/anonymous_reid_x402_demo.py
```

### POST /v1/public/object-search/trial

Authentication is not required.

Compatibility alias:

- `POST /v1/public/locate-anything/trial`

Purpose:

- Provides a quick no-registration trial path.
- Consumes the runtime-configured trial amount quota by IP and algorithm bucket.
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
    "total_amount": 10,
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

### POST /v1/public/sequences/{task_id}/uploads/batch

Headers:

- `X-Task-Token: <task_token>`

Upload multiple sequence frames in one `multipart/form-data` request. The total
batch request body must not exceed 32 MB.

Fields:

- `upload_token`: token parsed from `uploads[].upload_url`
- `frames`: repeated file parts, in sequence order

Frame indexes are assigned by multipart order. The first `frames` part is index
0, the second is index 1, and so on. File names are ignored by the API.

### POST /v1/public/sequences/{task_id}/parse

Headers:

- `X-Task-Token: <task_token>`

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

`frames[].object_key` must be copied from the `POST /v1/public/sequences` create response after uploading the sequence images with `/uploads/batch`.

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
      "billable_frame_count": 100,
      "rate_per_k_frames": 2000,
      "frame_amount": 200
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

`frames[].object_key` must be copied from the `POST /v1/public/sequences` create response after uploading the sequence images with `/uploads/batch`.

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

1. Create a public task and upload input frames.
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

Registered-user checkout providers:

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

- `channel=alipay` prefers `alipay`
- `channel=wechat_pay` prefers `wechat_pay`
- `channel=crypto` creates a third-party crypto provider recharge order; the user must pay the exact provider order amount/address shown in the QR modal before expiry
- `channel=wechat` or `channel=wechat_pay` prefers `wechat_pay`
- `channel=manual_offline` and other offline/manual channels are rejected; PayPal, international card, Apple Pay, and Google Pay are not supported
