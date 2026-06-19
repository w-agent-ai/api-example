# Agent Guide

This file is the first context document for coding agents working in this repository.

## Project Summary

W-Agent is a public gait/video/sequence parsing service built around the local gait SDK. It exposes:

- Registered-user APIs using email login, API keys, prepaid wallet balance, monthly plans, and usage records.
- Anonymous public APIs using x402 payment challenges for per-call payment.
- Admin UI for users, finance, runtime pricing, payment config, portal info, reports, and audit logs.
- User portal with pricing, monthly plans, demo downloads, API docs, login/register, wallet and API key management.

Core capabilities:

- Video parsing: upload full video, worker extracts person sequences, returns gait/face/ReID features, attributes, frame boxes, result assets.
- Sequence parsing: upload tracked person image sequence, synchronously returns identity features, attributes, pose/emotion fields.
- Gait Pose: standalone 2D/3D keypoint API billed separately by sequence frames.

## Important Docs

- System design: [docs/design.md](docs/design.md)
- Data flow and DB writes: [docs/dataflow.md](docs/dataflow.md)
- API reference and examples: [docs/api.md](docs/api.md)
- Development guide: [docs/development.md](docs/development.md)
- Testing and demo guide: [docs/testing.md](docs/testing.md)
- Database dictionary: [docs/database-dictionary.md](docs/database-dictionary.md)
- Current handoff/state: [HANDOFF.md](HANDOFF.md)

## Main Code Map

- API entrypoint: [cmd/api/main.go](cmd/api/main.go)
- Worker entrypoint: [cmd/worker/main.go](cmd/worker/main.go)
- API assembly: [internal/app/api.go](internal/app/api.go)
- Worker assembly: [internal/app/worker.go](internal/app/worker.go)
- User portal and public docs: [internal/httpapi/handlers/users/portal.html](internal/httpapi/handlers/users/portal.html)
- User/API HTTP handler: [internal/httpapi/handlers/users/handler.go](internal/httpapi/handlers/users/handler.go)
- Admin portal: [internal/httpapi/handlers/admin/portal.html](internal/httpapi/handlers/admin/portal.html)
- Admin runtime config: [internal/admincfg](internal/admincfg), [internal/runtimeconfig](internal/runtimeconfig)
- Account, wallets, deposits, monthly plans: [internal/accounts](internal/accounts)
- Sequence service: [internal/sequences](internal/sequences)
- Video service: [internal/videos](internal/videos)
- Trial quota: [internal/trialusage](internal/trialusage)
- 图搜万物 forwarding: [internal/locateanything](internal/locateanything), [internal/httpapi/handlers/locateanything](internal/httpapi/handlers/locateanything)
- Pricing: [internal/pricing](internal/pricing)
- x402 and checkout providers: [internal/payments](internal/payments)
- Usage ledger: [internal/usageledger](internal/usageledger)
- SQL repositories: [internal/repository/sqlrepo](internal/repository/sqlrepo)

## Current Product Decisions

- Public website should be served from the ICP-approved `www.w-agent.cn` domain in mainland deployment.
- API listens on port `3005`, user portal on `3006`, admin portal on `3007`.
- Registered-user task tools and MCP are API-key based. Anonymous x402 payment is public HTTP API flow, not MCP JSON-RPC.
- Admin pricing is configured in CNY. Chinese user UI displays CNY. English user UI converts prices to USD using runtime `cny_usd_exchange_rate`; default is `7`.
- EURC x402 settlement uses runtime `eurc_usd_exchange_rate`; default is `1.15`.
- Monthly plans are configured by admin as CNY pay amount and discount; granted allowance is computed from discount and valid for 30 days after purchase.
- No-registration trial quota is configured by admin and persisted in database `trial_usage`.
- 图搜万物 is configured by admin as an upstream endpoint, timeout, enabled flag, and CNY price per image.
- Demo downloads are shown by calling identity: trial, registered, anonymous. Browser is a usage method, not a caller identity. Trial currently offers Browser/Python packages; registered offers Browser/Python/C++/Go packages; anonymous currently offers Python packages.
- Financial usage records must be persisted in database usage ledger and must not be deleted with task cleanup.

## Build And Test Commands

Set library path before build/test when packages touch OpenCV/SDK-linked code:

```bash
export LD_LIBRARY_PATH=/home/watrix/tiandk/agent/gaitAgent/algorithms/lib_core_64:/home/watrix/tiandk/agent/gaitAgent/algorithms/lib_64:/usr/local/cuda/lib64:/usr/local/lib:$LD_LIBRARY_PATH
```

Common verification:

```bash
go test ./internal/pricing ./internal/runtimeconfig ./internal/httpapi/handlers/admin ./internal/httpapi/handlers/users ./internal/httpapi/handlers/mcp ./internal/httpapi
go build -o /tmp/gait-api.new ./cmd/api
```

Service deployment on this host:

```bash
backup=/opt/gaitagent/bin/gait-api.bak.$(date +%Y%m%d%H%M%S)
cp /opt/gaitagent/bin/gait-api "$backup"
install -m 0755 /tmp/gait-api.new /opt/gaitagent/bin/gait-api
systemctl restart gait-api
systemctl is-active gait-api
```

Basic health checks:

```bash
curl -fsS http://127.0.0.1:3005/healthz
curl -fsS http://127.0.0.1:3006/portal -o /tmp/portal.html
```

## Development Rules

- Preserve existing user changes. Do not run destructive git commands unless explicitly requested.
- Use `rg` for search and `gofmt` for Go changes.
- Use `apply_patch` for manual edits.
- Keep frontend changes consistent with the existing portal/admin visual style.
- When changing pricing, payment, wallet, or usage ledger behavior, update docs and tests in the same change.
- When changing portal demo download links, test the zip endpoints with `curl` and `unzip -t`.
- When changing runtime config payloads, update admin UI, user/MCP pricing views, router tests, and docs together.

## Known Operational Notes

- Production-like service uses `/etc/gaitagent/gait-api.env`.
- Current systemd unit is `gait-api.service`; its binary is `/opt/gaitagent/bin/gait-api`.
- The deployed service listens on `:3005`, `:3006`, and `:3007`.
- PostgreSQL mode is enabled when `GAIT_DB_DSN` is set; otherwise file-backed stores are used.
- Some tests intentionally create fake video files and OpenCV logs warnings; these warnings are usually harmless if tests pass.
