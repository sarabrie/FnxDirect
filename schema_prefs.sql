ALTER TABLE user_preferences
    ADD COLUMN IF NOT EXISTS preferred_name TEXT,
    ADD COLUMN IF NOT EXISTS response_length TEXT NOT NULL DEFAULT 'standard',
    ADD COLUMN IF NOT EXISTS tone TEXT NOT NULL DEFAULT 'simple';