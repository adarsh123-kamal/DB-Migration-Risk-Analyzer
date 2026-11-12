
CREATE TABLE employees (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE INDEX idx_employee_name
ON employees(name);

DROP TABLE employees;

DELETE FROM customers;

UPDATE employees
SET name = 'Unknown';
