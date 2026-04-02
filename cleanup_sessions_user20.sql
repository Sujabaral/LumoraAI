BEGIN;

-- 1) keep newest 40 sessions for this user
DROP TABLE IF EXISTS keep_sessions;
CREATE TEMP TABLE keep_sessions AS
SELECT id
FROM chat_session
WHERE user_id = 20
ORDER BY COALESCE(updated_at, created_at) DESC
LIMIT 40;

-- 2) sessions to delete
DROP TABLE IF EXISTS del_sessions;
CREATE TEMP TABLE del_sessions AS
SELECT id
FROM chat_session
WHERE user_id = 20
  AND id NOT IN (SELECT id FROM keep_sessions);

-- 3) delete children first (labels -> messages)
DELETE FROM message_label
WHERE message_id IN (
  SELECT id FROM chat_message
  WHERE session_id IN (SELECT id FROM del_sessions)
);

-- session-linked tables (if they exist in your DB)
DELETE FROM user_feedback       WHERE session_id IN (SELECT id FROM del_sessions);
DELETE FROM distortion_event    WHERE session_id IN (SELECT id FROM del_sessions);
DELETE FROM user_emotion_event  WHERE session_id IN (SELECT id FROM del_sessions);

-- 4) delete chat rows
DELETE FROM chat_message WHERE session_id IN (SELECT id FROM del_sessions);
DELETE FROM chat_history WHERE session_id IN (SELECT id FROM del_sessions);

-- 5) finally delete sessions
DELETE FROM chat_session WHERE id IN (SELECT id FROM del_sessions);

COMMIT;

