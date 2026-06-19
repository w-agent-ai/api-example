# Project Handoff

Last updated: 2026-06-15

## Current State

The repository implements and deploys the W-Agent gait parsing API, user portal, admin portal, and worker integration.

Recent local commit before this handoff:

- `9d12fce Add CNY pricing display and grouped demo downloads`

Current working tree at the time this file was created should be clean after committing these handoff docs.

## Recent Completed Work

- Mainland deployment adjusted to serve from the ICP-approved `www.w-agent.cn` path.
- User portal footer shows ICP filing number `京ICP备2026031914号`.
- Previously hidden x402/anonymous payment content was restored after ICP approval.
- Admin finance pages gained filtering/export improvements and separated consumption records from recharge records.
- Usage records were moved to durable database-backed ledger semantics; financial records should not be pruned with task cleanup.
- User portal usage records are now rendered as a real table with time-range filtering, preset day/month shortcuts, charge-method column, and export of filtered results.
- User portal recharge panel is currently a compact 3-column layout: recharge mode, amount/payment method, and recharge/history actions.
- Portal legal flows were added: user agreement, privacy policy, forced read/accept before registration.
- Email verification and password reset were added through Aliyun SMTP.
- Monthly plans were added:
  - admin configurable pay amount and discount
  - default examples were later replaced in runtime by current admin settings
  - user portal displays active plan, remaining allowance, expiry, and auto-renew settings
  - monthly allowance is consumed before recharge balance
- Monthly plan purchase now defaults to auto-renew enabled. Enabling auto-renew must go through payment-channel agreement authorization; unsupported providers return a clear error.
- Closing auto-renew currently updates local state; production-grade cancellation still needs payment-channel agreement/subscription cancellation integration.
- Admin pricing now uses CNY amounts. User portal displays CNY in Chinese and converted USD in English through `cny_usd_exchange_rate`.
- Runtime pricing config now includes:
  - `currency`
  - `sequence_per_k_frames`
  - `sequence_per_sequence`
  - `video_per_k_frames`
  - `gait_pose_per_k_frames`
  - `cny_usd_exchange_rate`
  - `eurc_usd_exchange_rate`
- Demo downloads were restructured:
  - Registered group: all, Python, C++, Go
  - Anonymous group: all, Python
  - Backend alias `anonymous-python` was added.
- User portal was redesigned into a unified top-navigation shell:
  - public home is a minimal playground page for 图搜万物, sequence parsing, and Gait Pose trial
  - 图搜万物 prompt placeholder is `猫、公交车、穿红衣服的人` / `cat, bus, person in red`
  - file picker display matches the browser client: single 图搜万物 image shows only the filename; multi-file capabilities show filename and count
  - public docs, auth pages, and logged-in user center use the same top-left navigation order
  - top-right language/login/account controls share the same visual style
  - footer shows contact email, user agreement, privacy policy, and ICP filing
  - the left navigation is fixed to the viewport (`left: 24px; top: 18px`) so it does not shift when switching between logged-out docs, login, and logged-in sections
  - standalone payment-method page was removed; anonymous Agent and x402 content now belongs to Agent access

## Current Runtime Pricing Notes

Admin prices are CNY cents/fen. English UI converts those values to USD by:

```text
USD cents ~= CNY fen / cny_usd_exchange_rate
```

Default `cny_usd_exchange_rate` is `7`, meaning `1 USD = 7 CNY`.

The current deployed runtime config was migrated from old USD values by multiplying by 7 so English-visible prices stayed approximately unchanged.

Important distinction:

- Pricing display conversion is UI/display behavior.
- Wallet balances, deposits, and ledger entries should still use their actual stored currency.
- x402 stablecoin settlement requires care: do not assume CNY can be sent directly through USDC/USDT/EURC without conversion logic.

## Deployment State On This Host

Systemd service:

- `gait-api.service`
- binary: `/opt/gaitagent/bin/gait-api`
- env file: `/etc/gaitagent/gait-api.env`
- working directory: `/home/watrix/tiandk/agent/gaitAgent`

Ports:

- API: `3005`
- User portal: `3006`
- Admin portal: `3007`

Common restart flow:

```bash
export LD_LIBRARY_PATH=/home/watrix/tiandk/agent/gaitAgent/algorithms/lib_core_64:/home/watrix/tiandk/agent/gaitAgent/algorithms/lib_64:/usr/local/cuda/lib64:/usr/local/lib:$LD_LIBRARY_PATH
go build -o /tmp/gait-api.new ./cmd/api
backup=/opt/gaitagent/bin/gait-api.bak.$(date +%Y%m%d%H%M%S)
cp /opt/gaitagent/bin/gait-api "$backup"
install -m 0755 /tmp/gait-api.new /opt/gaitagent/bin/gait-api
systemctl restart gait-api
systemctl is-active gait-api
```

## Verification Checklist

For normal API/portal changes:

```bash
export LD_LIBRARY_PATH=/home/watrix/tiandk/agent/gaitAgent/algorithms/lib_core_64:/home/watrix/tiandk/agent/gaitAgent/algorithms/lib_64:/usr/local/cuda/lib64:/usr/local/lib:$LD_LIBRARY_PATH
go test ./internal/pricing ./internal/runtimeconfig ./internal/httpapi/handlers/admin ./internal/httpapi/handlers/users ./internal/httpapi/handlers/mcp ./internal/httpapi
go build -o /tmp/gait-api.new ./cmd/api
```

For demo-download changes:

```bash
for kind in trial browser trial-python registered registered-python cpp go anonymous anonymous-python; do
  out="/tmp/w-agent-${kind}.zip"
  curl -fsS "http://127.0.0.1:3006/portal/demo-download?type=${kind}" -o "$out"
  unzip -t "$out"
done
```

For deployed service:

```bash
curl -fsS http://127.0.0.1:3005/healthz
curl -fsS http://127.0.0.1:3006/portal -o /tmp/portal.html
```

## Open Items And Risks

- Browser client currently supports 图搜万物, sequence parsing, and Gait Pose for trial/registered identities. Browser x402/anonymous is still deferred because it needs a browser wallet/x402 signing flow.
- User portal recharge and monthly-plan layouts are mostly settled, but still validate against the deployed page after edits; HTML/CSS is embedded into the `gait-api` binary.
- Full video trial is still deferred; current trial endpoints cover 图搜万物, sequence parsing, and Gait Pose. This avoids opening a large unauthenticated async video upload path before abuse limits are designed.
- Real auto-renew requires signed/authorized recurring payment support from Alipay, WeChat Pay, PayPal, or another provider. Enabling must create a provider agreement; disabling should eventually call provider-side agreement/subscription cancellation, not only update local state.
- x402 payment paths should be audited after CNY pricing changes. The display layer is converted, but stablecoin settlement must be explicit about USD-denominated payment amounts.
- The user portal still contains some static JSON examples showing `"currency": "USD"` for API response examples. This may be acceptable for payment examples, but review if public documentation must be fully CNY-aware.
- CPU detect examples are present and downloadable, but model/runtime performance and platform packaging remain active product areas.
- Some older docs describe planned modules as "draft" or "suggested"; prefer current code and `docs/dataflow.md` for exact behavior.

## How To Continue Safely

- Start by reading [AGENTS.md](AGENTS.md), then [docs/design.md](docs/design.md), then [docs/dataflow.md](docs/dataflow.md).
- Before editing, run `git status --short`.
- After changing runtime config structs or pricing, update:
  - `internal/pricing`
  - `internal/runtimeconfig`
  - admin portal/runtime config UI
  - trial quota and 图搜万物 runtime config fields when touched
  - user portal pricing display
  - MCP/user pricing views
  - router/admin tests
  - docs
- After changing frontend portal HTML, build `./cmd/api` because HTML is embedded/served by the Go binary.
