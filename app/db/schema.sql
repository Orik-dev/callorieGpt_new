CREATE TABLE IF NOT EXISTS users_tbl (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tg_id BIGINT NOT NULL UNIQUE,
    tg_name VARCHAR(255),
    free_tokens INT DEFAULT 0,
    expiration_date DATE,
    payment_method_id VARCHAR(255),
    last_subscription_days INT DEFAULT 0,
    last_subscription_amount FLOAT DEFAULT 0,
    failed_autopay_attempts INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payment_tbl (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tg_id BIGINT NOT NULL,
    status VARCHAR(50),
    payment_id VARCHAR(255) UNIQUE,
    method_id VARCHAR(255),
    amount FLOAT,
    days INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
