-- Safe baseline schema and row-scoped changes.
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);

UPDATE customers SET email = 'new@example.com' WHERE id = 1;
DELETE FROM customers WHERE id = 99;

-- DROP TABLE abandoned_customers;
INSERT INTO audit_log(message) VALUES ('DELETE FROM customers; DROP TABLE customers;');
