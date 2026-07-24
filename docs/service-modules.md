# Gait Parsing Service Module Draft

## Goal

This document defines a suggested Go service split for implementing the public gait parsing service.

The purpose is to keep the HTTP layer, billing logic, storage logic, and SDK execution logic decoupled.

## Repository-Level Split

Recommended top-level modules:

- `cmd/api`
- `cmd/worker`
- `internal/app`
- `internal/httpapi`
- `internal/tasks`
- `internal/billing`
- `internal/payments`
- `internal/storage`
- `internal/repository`
- `internal/worker`
- `internal/resultfmt`
- `internal/reid`
- `internal/config`

## API Service Modules

### `internal/httpapi`

Responsibilities:

- routing
- request parsing
- auth extraction
- response formatting
- request id injection
- idempotency handling

Suggested packages:

- `httpapi/middleware`
- `httpapi/handlers/videos`
- `httpapi/handlers/sequences`
- `httpapi/handlers/public`
- `httpapi/handlers/locateanything`
- `httpapi/render`

### `internal/tasks`

Responsibilities:

- task creation
- task status transitions
- retention timestamp calculation
- task queries
- task deletion

Core services:

- `TaskService`
- `VideoTaskService`
- `SequenceTaskService`
- `TransitionService`

### `internal/billing`

Responsibilities:

- price calculation
- billing order creation
- wallet settlement
- billing snapshots

Core services:

- `PricingService`
- `OrderService`
- `WalletService`
- `SettlementService`

### `internal/payments`

Responsibilities:

- x402 verification
- payment receipt replay protection
- payment record creation

Core services:

### `internal/trialusage`

Responsibilities:

- persist no-registration trial counters
- limit cumulative trial amount by IP hash and algorithm bucket
- keep trial quota independent from x402 anonymous payment

### `internal/locateanything`

Responsibilities:

- forward image+prompt requests to the configured 图搜万物 upstream service
- normalize upstream `boxes`/`raw_text` responses for registered and trial HTTP APIs

- `X402Verifier`
- `PaymentService`

### `internal/storage`

Responsibilities:

- object key generation
- upload URL issuance
- signed download URL issuance
- object existence and metadata checks
- object deletion

Core services:

- `ObjectStore`
- `UploadService`
- `AssetService`

Current implementation status:

- local filesystem object store is implemented and used by sequence/video uploads and generated assets
- video, sequence, account, runtime-config, admin-audit, and admin-stats data can now use PostgreSQL repositories when configured
- the object-store boundary is already in place, so a later S3 / MinIO / OSS / COS backend can be added without changing sequence/video business logic

### `internal/resultfmt`

Responsibilities:

- transform SDK result into API JSON
- build `frames[].rect`
- build signed `gait_image` and `face_image`
- attach billing summary

Core services:

- `VideoResultFormatter`
- `SequenceResultFormatter`

### `internal/reid`

Responsibilities:

- decode `reid_structure_raw`
- map `category_index -> label`
- attach thresholds
- generate `reid_summary`

Core services:

- `Decoder`
- `Dictionary`

## Worker Modules

### `internal/worker`

Responsibilities:

- claim paid video tasks that are ready for SDK execution
- maintain worker lease
- execute parsing
- write progress
- finalize task result

Suggested packages:

- `worker/runner`
- `worker/claim`
- `worker/progress`
- `worker/finalize`

### SDK Integration Boundary

The worker should depend on a narrow interface, not directly on HTTP or billing code.

Suggested interface:

```go
type GaitEngine interface {
    StartVideo(videoID string) error
    GetVideoProgress(videoID string) (int, error)
    GetVideoResult(videoID string) ([]*SequenceResult, error)
    RemoveVideo(videoID string) error
    GetSplitSeqFeature(frames [][]byte) ([]*SequenceResult, error)
}
```

The concrete implementation may wrap [algorithms/sdk/agent.go](/home/watrix/tiandk/agent/gaitAgent/algorithms/sdk/agent.go).

## Persistence Layer

### `internal/repository`

Responsibilities:

- SQL read/write logic
- transaction boundaries
- row locking
- worker claim queries

Suggested repositories:

- `TaskRepository`
- `VideoTaskRepository`
- `SequenceTaskRepository`
- `OrderRepository`
- `PaymentRepository`
- `WalletRepository`
- `PolicyRepository`
- `AssetRepository`
- `EventRepository`

## Transaction Boundaries

Recommended atomic operations:

- create task + snapshot policy + insert initial event
- complete upload + extract metadata + create phase 1 order
- settle phase 1 + keep task ready for worker processing
- worker finalize success + persist result + create phase 2 order
- settle phase 2 + move to `succeeded`
- cleanup delete + mark task `deleted`

## Result Formatting Boundary

The raw SDK result should not be returned directly.

Formatting service should:

- convert image ids and rect arrays into `frames[]`
- decode ReID attributes
- attach signed result asset URLs
- keep raw SDK vectors available in output

## Configuration Areas

Recommended config groups:

- server
- database
- object storage
- worker concurrency
- SDK runtime
- billing currency
- x402 verification
- retention defaults
- rate limiting

## Initial Implementation Order

Recommended order:

1. repositories and schema migration wiring
2. task creation and upload negotiation
3. registered sequence parse path
4. registered video parse path
5. public x402 path
6. cleanup worker
7. metrics, tracing, and hardening

## Non-Goals for V1

- multi-region deployment
- AP2 as primary payment flow
- multi-currency settlement
- bulk batch gait sequence parsing
- direct external URL ingestion
