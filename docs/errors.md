# Gait Parsing Service Error Codes Draft

## Error Envelope

All non-2xx responses should return this structure:

```json
{
  "error": {
    "code": "payment_required",
    "message": "phase2 payment required",
    "request_id": "req_xxx",
    "retryable": false,
    "details": {}
  }
}
```

Fields:

- `code`: stable machine-readable error code
- `message`: human-readable error summary
- `request_id`: server-side request trace id
- `retryable`: whether client may retry without changing inputs
- `details`: optional structured payload

Public-task payment-required responses may also include `payment_context`:

```json
{
  "error": {
    "code": "payment_required",
    "message": "payment required",
    "request_id": "req_xxx",
    "retryable": true,
    "details": {}
  },
  "payment_context": {
    "provider": "mock",
    "phase": "sequence_once",
    "order_id": "ord_xxx",
    "amount": "12.34",
    "currency": "USD",
    "expires_at": "2026-05-06T12:00:00Z",
    "pricing_basis": {
      "sequence_count": 1
    },
    "challenge": {
      "mode": "mock",
      "order_id": "ord_xxx"
    }
  }
}
```

If provider is `x402`, the same response also carries header `PAYMENT-REQUIRED`.

## HTTP Status Mapping

- `400 Bad Request`: malformed request or invalid business parameters
- `401 Unauthorized`: missing or invalid registered-user authentication, session, or API key
- `402 Payment Required`: public-task x402 payment required
- `403 Forbidden`: task token mismatch, disabled API key, access denied
- `404 Not Found`: task, order, or resource not found
- `409 Conflict`: invalid task state, duplicate operation, idempotency conflict
- `410 Gone`: task or result has expired or been deleted
- `413 Payload Too Large`: file too large or too many sequence frames
- `415 Unsupported Media Type`: unsupported file format
- `422 Unprocessable Entity`: media is readable but semantically invalid for parsing
- `429 Too Many Requests`: rate limited
- `500 Internal Server Error`: unexpected server error
- `502 Bad Gateway`: upstream dependency failure
- `503 Service Unavailable`: worker unavailable, GPU exhausted, or maintenance
- `504 Gateway Timeout`: upstream processing timeout

## Common Error Codes

### Authentication and Authorization

- `unauthorized`
  - HTTP: `401`
  - Meaning: missing or invalid authentication, including invalid session or invalid API key
- `invalid_credentials`
  - HTTP: `401`
  - Meaning: invalid email or password
- `api_key_disabled`
  - HTTP: `403`
  - Meaning: API key revoked or disabled
- `task_token_invalid`
  - HTTP: `403`
  - Meaning: missing or invalid public task token
- `access_denied`
  - HTTP: `403`
  - Meaning: caller cannot access the target task

### Request Validation

- `invalid_request`
  - HTTP: `400`
  - Meaning: malformed JSON or invalid field type
- `invalid_argument`
  - HTTP: `400`
  - Meaning: semantically invalid argument value
- `unsupported_media_type`
  - HTTP: `415`
  - Meaning: unsupported input format
- `payload_too_large`
  - HTTP: `413`
  - Meaning: input file or sequence exceeds configured limits
- `too_many_frames`
  - HTTP: `413`
  - Meaning: sequence frame count exceeds limit
- `invalid_sequence_order`
  - HTTP: `422`
  - Meaning: frame indices are duplicated, missing, or unordered
- `invalid_video_metadata`
  - HTTP: `422`
  - Meaning: video cannot produce valid frame count, fps, or duration

### Upload and Asset Management

- `upload_not_found`
  - HTTP: `404`
  - Meaning: referenced object key does not exist
- `upload_not_completed`
  - HTTP: `409`
  - Meaning: asset upload not yet finished
- `upload_expired`
  - HTTP: `410`
  - Meaning: upload window expired
- `asset_integrity_mismatch`
  - HTTP: `422`
  - Meaning: checksum or metadata mismatch

### Task Lifecycle

- `task_not_found`
  - HTTP: `404`
  - Meaning: task id does not exist
- `task_state_conflict`
  - HTTP: `409`
  - Meaning: operation not allowed in current task status
- `task_expired`
  - HTTP: `410`
  - Meaning: task expired before requested action
- `task_deleted`
  - HTTP: `410`
  - Meaning: task artifacts already deleted
- `result_not_ready`
  - HTTP: `409`
  - Meaning: worker has not finished yet

### Billing and Payment

- `wallet_insufficient_balance`
  - HTTP: `409`
  - Meaning: registered user balance is insufficient
- `billing_order_not_found`
  - HTTP: `404`
  - Meaning: order id does not exist
- `billing_order_expired`
  - HTTP: `410`
  - Meaning: payment window expired
- `billing_order_already_paid`
  - HTTP: `409`
  - Meaning: duplicate settlement request
- `payment_required`
  - HTTP: `402`
  - Meaning: public-task x402 payment required
- `payment_verification_failed`
  - HTTP: `402`
  - Meaning: x402 proof or receipt invalid
- `payment_receipt_replayed`
  - HTTP: `409`
  - Meaning: duplicate payment proof already used
- `payment_mismatch`
  - HTTP: `409`
  - Meaning: paid amount or currency does not match the order
- `payment_provider_unavailable`
  - HTTP: `503`
  - Meaning: payment dependency unavailable

### Processing

- `worker_unavailable`
  - HTTP: `503`
  - Meaning: no worker capacity available
- `gpu_resource_exhausted`
  - HTTP: `503`
  - Meaning: GPU quota or concurrency exhausted
- `processing_timeout`
  - HTTP: `504`
  - Meaning: parsing exceeded timeout
- `processing_failed`
  - HTTP: `500`
  - Meaning: worker failed while executing SDK logic
- `sdk_init_failed`
  - HTTP: `503`
  - Meaning: SDK initialization failed
- `sdk_runtime_failed`
  - HTTP: `500`
  - Meaning: SDK call failed during processing

### Idempotency and Rate Limits

- `idempotency_conflict`
  - HTTP: `409`
  - Meaning: same idempotency key used with different request body
- `rate_limited`
  - HTTP: `429`
  - Meaning: per-user or per-IP rate limit exceeded

### Internal and Dependency Errors

- `internal_error`
  - HTTP: `500`
  - Meaning: unexpected server failure
- `storage_unavailable`
  - HTTP: `503`
  - Meaning: object storage dependency unavailable
- `database_unavailable`
  - HTTP: `503`
  - Meaning: database unavailable
- `accounts_unavailable`
  - HTTP: `503`
  - Meaning: accounts service is disabled while a registered-user flow requires wallet or identity data

## Endpoint-Specific Notes

### GET /v1/sequences/{task_id}/result

Possible business errors:

- `result_not_ready`
- `processing_failed`
- `task_expired`
- `task_deleted`
- `unauthorized`
- `access_denied`

### POST /v1/me/deposits

Possible business errors:

- `invalid_argument`
- `unauthorized`
- `user_not_found`

### POST /v1/admin/users/{user_id}/deposits/{deposit_id}/settle

Possible business errors:

- `deposit_not_found`
- `deposit_already_settled`
- `user_not_found`
- `invalid_argument`

### DELETE /v1/sequences/{task_id}

Possible business errors:

- `unauthorized`
- `task_not_found`
- `task_deleted`
- `task_state_conflict`
- `access_denied`

### POST /v1/sequences/{task_id}/parse

Possible business errors:

- `unauthorized`
- `access_denied`
- `invalid_sequence_order`
- `upload_not_found`
- `upload_not_completed`
- `wallet_insufficient_balance`
- `processing_failed`

## Retry Guidance

Safe to retry:

- `rate_limited`
- `worker_unavailable`
- `storage_unavailable`
- `database_unavailable`
- `payment_required`
- `payment_provider_unavailable`

Retry only after state changes:

- `result_not_ready`
- `wallet_insufficient_balance`
- `upload_not_completed`

Do not retry without changing inputs:

- `invalid_request`
- `invalid_argument`
- `unsupported_media_type`
- `invalid_sequence_order`
- `asset_integrity_mismatch`
- `task_token_invalid`
