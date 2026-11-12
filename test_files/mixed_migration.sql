-- This dangerous-looking SQL is only a comment and must be ignored:
-- DROP TABLE users;
/* UPDATE users SET admin = TRUE; */

CREATE TABLE migration_notes (note VARCHAR(200));
INSERT INTO migration_notes(note) VALUES ('DELETE FROM users; DROP TABLE users;');
DELETE FROM users WHERE id = 42;
UPDATE users SET display_name = 'DROP TABLE users' WHERE id = 42;

DROP TABLE obsolete_events;
ALTER TABLE users DROP COLUMN deprecated_label;
DELETE FROM expired_sessions;
TRUNCATE TABLE import_buffer;
ALTER TABLE users ALTER COLUMN age TYPE BIGINT;
ALTER TABLE users ADD COLUMN marketing_opt_in BOOLEAN NOT NULL;
CREATE INDEX idx_users_created_at ON users(created_at);
UPDATE settings SET value = 'enabled';
