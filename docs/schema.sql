-- Deprecated reference only.
-- The runtime database schema is defined by db/migrations/*.sql.
-- Do not use this file to initialize or audit a live W-Agent database.

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    name TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX users_email_uidx ON users (email) WHERE deleted_at IS NULL;

CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    name TEXT,
    status TEXT NOT NULL,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX api_keys_key_hash_uidx ON api_keys (key_hash);

CREATE TABLE wallets (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    currency TEXT NOT NULL,
    available_balance NUMERIC(20, 8) NOT NULL DEFAULT 0,
    locked_balance NUMERIC(20, 8) NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX wallets_user_currency_uidx ON wallets (user_id, currency);

CREATE TABLE tasks (
    id BIGSERIAL PRIMARY KEY,
    public_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    owner_type TEXT NOT NULL,
    owner_id BIGINT,
    status TEXT NOT NULL,
    task_token_hash TEXT,
    idempotency_key TEXT,
    current_payment_phase TEXT,
    pricing_policy_id BIGINT,
    pricing_snapshot_json JSONB NOT NULL,
    retention_policy_id BIGINT,
    retention_snapshot_json JSONB NOT NULL,
    expire_at TIMESTAMPTZ,
    delete_after_at TIMESTAMPTZ,
    status_entered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX tasks_public_id_uidx ON tasks (public_id);
CREATE INDEX tasks_status_expire_idx ON tasks (status, expire_at);
CREATE INDEX tasks_status_delete_after_idx ON tasks (status, delete_after_at);
CREATE INDEX tasks_owner_idx ON tasks (owner_type, owner_id, created_at DESC);

CREATE TABLE video_tasks (
    task_id BIGINT PRIMARY KEY REFERENCES tasks(id),
    input_object_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 TEXT,
    duration_ms BIGINT,
    fps NUMERIC(10, 4),
    frame_count BIGINT,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    sequence_count BIGINT,
    total_sequence_frames BIGINT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    failure_code TEXT,
    failure_message TEXT
);

CREATE TABLE sequence_tasks (
    task_id BIGINT PRIMARY KEY REFERENCES tasks(id),
    declared_frame_count BIGINT NOT NULL,
    uploaded_frame_count BIGINT NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    failure_code TEXT,
    failure_message TEXT
);

CREATE TABLE task_assets (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES tasks(id),
    asset_role TEXT NOT NULL,
    sequence_id TEXT,
    frame_index BIGINT,
    object_key TEXT NOT NULL,
    mime_type TEXT,
    size_bytes BIGINT,
    sha256 TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX task_assets_task_role_idx ON task_assets (task_id, asset_role);
CREATE UNIQUE INDEX task_assets_object_key_uidx ON task_assets (object_key);

CREATE TABLE task_results (
    task_id BIGINT PRIMARY KEY REFERENCES tasks(id),
    schema_version TEXT NOT NULL,
    result_object_key TEXT NOT NULL,
    summary_json JSONB NOT NULL,
    released_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE pricing_policies (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    owner_type TEXT NOT NULL,
    currency TEXT NOT NULL,
    version BIGINT NOT NULL,
    video_per_k_frames BIGINT NOT NULL,
    sequence_per_k_frames BIGINT NOT NULL,
    gait_pose_per_k_frames BIGINT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE retention_policies (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    owner_type TEXT NOT NULL,
    version BIGINT NOT NULL,
    upload_pending_ttl_sec BIGINT NOT NULL,
    payment_phase1_ttl_sec BIGINT NOT NULL,
    payment_phase2_ttl_sec BIGINT NOT NULL,
    result_retention_ttl_sec BIGINT NOT NULL,
    failed_retention_ttl_sec BIGINT NOT NULL,
    deleted_record_ttl_sec BIGINT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE billing_orders (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES tasks(id),
    phase TEXT NOT NULL,
    owner_type TEXT NOT NULL,
    currency TEXT NOT NULL,
    amount NUMERIC(20, 8) NOT NULL,
    status TEXT NOT NULL,
    pricing_policy_id BIGINT REFERENCES pricing_policies(id),
    pricing_snapshot_json JSONB NOT NULL,
    quantity_snapshot_json JSONB NOT NULL,
    due_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX billing_orders_task_phase_uidx ON billing_orders (task_id, phase);
CREATE INDEX billing_orders_status_idx ON billing_orders (status, due_at);

CREATE TABLE payments (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES billing_orders(id),
    protocol TEXT NOT NULL,
    rail TEXT NOT NULL,
    provider_payment_id TEXT,
    receipt_ref TEXT,
    request_ref TEXT,
    amount NUMERIC(20, 8) NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    receipt_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX payments_provider_payment_id_uidx ON payments (provider_payment_id) WHERE provider_payment_id IS NOT NULL;
CREATE INDEX payments_order_idx ON payments (order_id, status);

CREATE TABLE wallet_ledger (
    id BIGSERIAL PRIMARY KEY,
    wallet_id BIGINT NOT NULL REFERENCES wallets(id),
    task_id BIGINT REFERENCES tasks(id),
    order_id BIGINT REFERENCES billing_orders(id),
    direction TEXT NOT NULL,
    amount NUMERIC(20, 8) NOT NULL,
    currency TEXT NOT NULL,
    balance_before NUMERIC(20, 8) NOT NULL,
    balance_after NUMERIC(20, 8) NOT NULL,
    reason_code TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX wallet_ledger_wallet_idx ON wallet_ledger (wallet_id, created_at DESC);

CREATE TABLE task_events (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES tasks(id),
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    reason_code TEXT,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator_type TEXT,
    operator_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX task_events_task_idx ON task_events (task_id, created_at DESC);

CREATE TABLE trial_usage (
    public_id TEXT PRIMARY KEY,
    day_key TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    fingerprint_hash TEXT NOT NULL DEFAULT '',
    request_count BIGINT NOT NULL DEFAULT 0,
    frame_count BIGINT NOT NULL DEFAULT 0,
    amount_used BIGINT NOT NULL DEFAULT 0,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX trial_usage_day_identity_uidx ON trial_usage (day_key, ip_hash, fingerprint_hash);
CREATE INDEX trial_usage_last_seen_idx ON trial_usage (last_seen_at DESC);
