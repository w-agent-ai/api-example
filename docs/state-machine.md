# Gait Parsing Service State Machine Draft

## Overview

This document defines the task state transitions, triggers, guards, and side effects for V1.

Two task types exist:

- `video`
- `sequence`

The task state machine is shared across registered-user tasks and public tasks. Payment trigger mechanics differ, but status semantics remain broadly similar.

## Video State Machine

### States

- `created`
- `uploaded`
- `awaiting_payment_1`
- `processing`
- `succeeded_awaiting_payment_2`
- `succeeded`
- `failed`
- `expired`
- `deleted`

### Transition Matrix

| From | Trigger | Guard | To | Side Effects |
|---|---|---|---|---|
| `created` | upload completed by `PUT /v1/video-uploads/{task_id}?token=...` | object exists and metadata valid | `uploaded` | persist object info and video metadata |
| `uploaded` | phase 1 order created | none | `awaiting_payment_1` | create `video_phase1` order, set `current_payment_phase`, recompute retention timestamps |
| `awaiting_payment_1` | registered wallet payment succeeds | order status is `pending` | `uploaded` | mark order `paid`, append wallet ledger, trigger worker processing |
| `awaiting_payment_1` | public payment verified | order status is `pending` | `uploaded` | mark order `paid`, create payment row, trigger worker processing |
| `awaiting_payment_1` | payment window expires | unpaid | `expired` | record expiration event, schedule cleanup |
| `uploaded` | worker starts SDK job | phase 1 already paid | `processing` | set `started_at`, clear `current_payment_phase` |
| `processing` | SDK succeeds | result persisted | `succeeded_awaiting_payment_2` | persist result JSON and assets, create `video_phase2` order, set `current_payment_phase` |
| `processing` | SDK progress reaches 100 | result persisted | `succeeded_awaiting_payment_2` | call `GetVideoResult`, persist result JSON and assets, create `video_phase2` order, set `current_payment_phase` |
| `processing` | SDK reports task missing | `GetVideoProgress` returns `-1` | `processing` | restart SDK video job with `StartVideo`, keep task paid and retryable |
| `processing` | SDK or worker fails | unrecoverable error or timeout | `failed` | set failure info, recompute retention timestamps |
| `succeeded_awaiting_payment_2` | registered wallet payment succeeds | order status is `pending` | `succeeded` | mark order `paid`, append wallet ledger, set `released_at` |
| `succeeded_awaiting_payment_2` | public payment verified | order status is `pending` | `succeeded` | mark order `paid`, create payment row, set `released_at` |
| `succeeded_awaiting_payment_2` | payment window expires | unpaid | `expired` | record expiration event, deny result access |
| `created` | user deletes task | delete allowed | `deleted` | remove uploaded assets if any, record deletion |
| `uploaded` | user deletes task | delete allowed | `deleted` | remove uploaded assets if any, record deletion |
| `awaiting_payment_1` | user deletes task | delete allowed | `deleted` | cancel pending order, remove uploaded assets |
| `succeeded_awaiting_payment_2` | user deletes task | delete allowed | `deleted` | cancel pending order, remove result assets |
| `succeeded` | user deletes task | delete allowed | `deleted` | remove media and result assets |
| `failed` | retention cleanup | `delete_after_at <= now` | `deleted` | remove stored assets |
| `expired` | retention cleanup | `delete_after_at <= now` | `deleted` | remove stored assets |
| `succeeded` | retention cleanup | `delete_after_at <= now` | `deleted` | remove stored assets |

### Access Rules by State

| State | Status Query | Result Query | New Payment |
|---|---|---|---|
| `created` | yes | no | no |
| `uploaded` | yes | no | no |
| `awaiting_payment_1` | yes | no | yes |
| `processing` | yes | no | no |
| `succeeded_awaiting_payment_2` | yes | no | yes |
| `succeeded` | yes | yes | no |
| `failed` | yes | no | no |
| `expired` | yes | no | no |
| `deleted` | limited | no | no |

## Sequence State Machine

### States

- `created`
- `awaiting_payment`
- `processing`
- `succeeded`
- `failed`
- `expired`
- `deleted`

### Transition Matrix

| From | Trigger | Guard | To | Side Effects |
|---|---|---|---|---|
| `created` | parse requested | frame manifest valid | `awaiting_payment` | create `sequence_once` order |
| `awaiting_payment` | registered wallet payment succeeds | order status is `pending` | `processing` | mark order `paid`, append wallet ledger |
| `awaiting_payment` | public payment verified | order status is `pending` | `processing` | mark order `paid`, create payment row |
| `awaiting_payment` | payment window expires | unpaid | `expired` | record expiration event |
| `processing` | SDK succeeds | result built | `succeeded` | optionally persist result object and images |
| `processing` | SDK or worker fails | none | `failed` | set failure info |
| `created` | user deletes task | delete allowed | `deleted` | remove uploaded frame assets |
| `awaiting_payment` | user deletes task | delete allowed | `deleted` | cancel pending order, remove frame assets |
| `succeeded` | retention cleanup | `delete_after_at <= now` | `deleted` | remove frame assets and result assets |
| `failed` | retention cleanup | `delete_after_at <= now` | `deleted` | remove stored assets |
| `expired` | retention cleanup | `delete_after_at <= now` | `deleted` | remove stored assets |

### Access Rules by State

| State | Status Query | Parse Retry | Result Access |
|---|---|---|---|
| `created` | yes | yes | no |
| `awaiting_payment` | yes | yes | no |
| `processing` | yes | no | no |
| `succeeded` | yes | no | yes |
| `failed` | yes | maybe new task | no |
| `expired` | yes | no | no |
| `deleted` | limited | no | no |

## Retention Recalculation Rules

Each status transition recomputes:

- `expire_at`
- `delete_after_at`

Suggested mapping:

| State | expire_at | delete_after_at |
|---|---|---|
| `created` | `created_at + upload_pending_ttl` | null |
| `uploaded` | `status_entered_at + payment_phase1_ttl` | null |
| `awaiting_payment_1` | `status_entered_at + payment_phase1_ttl` | null |
| `processing` | none | null |
| `succeeded_awaiting_payment_2` | `status_entered_at + payment_phase2_ttl` | `status_entered_at + payment_phase2_ttl` |
| `succeeded` | null | `status_entered_at + result_retention_ttl` |
| `failed` | null | `status_entered_at + failed_retention_ttl` |
| `expired` | null | `status_entered_at + deleted_record_ttl` |
| `deleted` | null | null |

For sequence tasks:

| State | expire_at | delete_after_at |
|---|---|---|
| `created` | `created_at + upload_pending_ttl` | null |
| `awaiting_payment` | `status_entered_at + payment_phase1_ttl` | null |
| `processing` | none | null |
| `succeeded` | null | `status_entered_at + result_retention_ttl` |
| `failed` | null | `status_entered_at + failed_retention_ttl` |
| `expired` | null | `status_entered_at + deleted_record_ttl` |
| `deleted` | null | null |

## Billing Lifecycle

Order statuses:

- `pending`
- `paid`
- `waived`
- `expired`
- `canceled`

Payment statuses:

- `initiated`
- `confirmed`
- `failed`
- `expired`

Rules:

- Only one active order may exist for a given `task_id + phase`.
- Transition to `uploaded`, `processing`, or `succeeded` must be atomic with successful payment settlement.
- `GET /result` for public phase 2 must create the phase 2 order only once.
- Already paid orders must not be charged again.

## Worker Lease Rules

Worker-side recommendations:

- A worker should only start SDK execution after phase 1 has been paid.
- A claim should write `started_at` or equivalent processing timestamp before entering `processing`.
- A lease timeout should allow orphaned tasks to be marked failed or restarted by policy.
- SDK crashes should not leave tasks permanently in `processing`.

Current single-machine implementation:

- `videos.Service.ProcessPending` scans `uploaded` and `processing` video tasks on every worker tick.
- `uploaded` means phase 1 is already paid and SDK processing has not started yet.
- `processing` means SDK processing has started or should be resumed after restart.
- If the worker restarts and the SDK no longer knows the video, `GetVideoProgress` returns `-1`; the worker calls `StartVideo` again and keeps the task in `processing`.
- When progress becomes `100`, worker calls `GetVideoResult` in the next `ProcessTask` pass and creates the phase 2 order.
- `sequences.Service.ProcessPending` scans paid `processing` sequence tasks with `PendingParse` saved, then replays the real SDK sequence parse.
- This recovery is intentionally single-machine. Multi-machine worker support still needs a lease/owner column before enabling concurrent workers.

## Audit Event Recommendations

Every transition should emit a `task_events` row with:

- `event_type`
- `from_status`
- `to_status`
- `reason_code`
- `payload_json`
- `operator_type`
- `operator_id`

Recommended `event_type` values:

- `task_created`
- `upload_completed`
- `billing_created`
- `payment_confirmed`
- `worker_started`
- `worker_progress`
- `worker_succeeded`
- `worker_failed`
- `result_released`
- `task_expired`
- `task_deleted`
- `cleanup_completed`
