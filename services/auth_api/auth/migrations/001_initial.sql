-- Migration 001: Initial Auth Schema
-- Run with: psql $DATABASE_URL -f auth/migrations/001_initial.sql

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── USERS ───────────────────────────────────────────────────────────────────
CREATE TYPE auth_provider_enum AS ENUM ('local', 'google');

CREATE TABLE users (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email          VARCHAR(254) NOT NULL,
    password_hash  TEXT,                          -- NULL for OAuth-only accounts
    auth_provider  auth_provider_enum NOT NULL DEFAULT 'local',
    provider_id    TEXT,                          -- Google sub claim
    display_name   VARCHAR(128) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_email_unique UNIQUE (email),
    CONSTRAINT users_local_needs_password
        CHECK (auth_provider != 'local' OR password_hash IS NOT NULL)
);

CREATE INDEX idx_users_email       ON users (email);
CREATE INDEX idx_users_provider_id ON users (provider_id) WHERE provider_id IS NOT NULL;

-- ─── REFRESH TOKENS ──────────────────────────────────────────────────────────
CREATE TABLE refresh_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash TEXT        NOT NULL,
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_id  UUID        NOT NULL,
    is_revoked BOOLEAN     NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_hash      ON refresh_tokens (token_hash);
CREATE INDEX idx_refresh_tokens_family_id ON refresh_tokens (family_id);
CREATE INDEX idx_refresh_tokens_user_id   ON refresh_tokens (user_id);

-- ─── USER PREFERENCES ────────────────────────────────────────────────────────
CREATE TABLE user_preferences (
    user_id       UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme         VARCHAR(32) NOT NULL DEFAULT 'system',
    settings_json JSONB       NOT NULL DEFAULT '{}',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── USER HISTORY ────────────────────────────────────────────────────────────
CREATE TABLE user_history (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action_type   VARCHAR(64) NOT NULL,
    metadata_json JSONB       NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_user_history_user_created ON user_history (user_id, created_at DESC);

-- ─── updated_at TRIGGER ──────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
