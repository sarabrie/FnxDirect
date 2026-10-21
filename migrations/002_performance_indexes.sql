CREATE INDEX IF NOT EXISTS conversations_user_updated_idx
    ON conversations (user_id, updated_at DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS hidden_conversations_user_conversation_idx
    ON hidden_conversations (user_id, conversation_id);

CREATE INDEX IF NOT EXISTS message_feedback_dislike_created_idx
    ON message_feedback (created_at DESC)
    WHERE rating = 'DISLIKE';

CREATE INDEX IF NOT EXISTS users_email_lower_idx
    ON users (LOWER(email));
