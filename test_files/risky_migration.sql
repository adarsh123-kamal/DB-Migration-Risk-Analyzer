-- Each statement below demonstrates a separate rule.
DROP TABLE archived_orders;
ALTER TABLE customers DROP COLUMN legacy_code;
DELETE FROM session_tokens;
TRUNCATE TABLE temporary_imports;
ALTER TABLE customers ALTER COLUMN account_number TYPE BIGINT;
ALTER TABLE customers ADD COLUMN verified BOOLEAN NOT NULL;
CREATE INDEX idx_orders_created_at ON orders(created_at);
UPDATE customer_flags SET enabled = TRUE;
