# Gait Parsing Service State Machine Draft

## Overview

This document records the public task state model for sequence-based APIs.

The public documentation describes sequence tasks only. Sequence parsing and
Gait Pose both start from uploaded tracked-person frames.

## Sequence State Machine

### States

- `created`
- `parsed`
- `succeeded`
- `failed`
- `expired`
- `deleted`

### Transition Matrix

| From | Trigger | Guard | To | Side Effects |
|---|---|---|---|---|
| `created` | frames uploaded | upload targets exist | `created` | persist uploaded object info |
| `created` | parse request succeeds | billing succeeds or public settlement succeeds | `succeeded` | persist result object, append usage ledger, update summaries |
| `created` | parse request fails | unrecoverable validation or SDK error | `failed` | persist failure info, recompute retention timestamps |
| `succeeded` | retention cleanup | `delete_after_at <= now` | `deleted` | remove stored assets |
| `failed` | retention cleanup | `delete_after_at <= now` | `deleted` | remove stored assets |
| `created` | user deletes task | delete allowed | `deleted` | remove uploaded assets |

### Access Rules by State

| State | Status Query | Result Query | New Payment |
|---|---|---|---|
| `created` | yes | no | depends on parse call |
| `succeeded` | yes | yes | no |
| `failed` | yes | no | no |
| `expired` | yes | no | no |
| `deleted` | yes | no | no |
