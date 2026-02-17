CREATE TABLE IF NOT EXISTS users_tbl (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tg_id BIGINT NOT NULL UNIQUE,
    tg_name VARCHAR(255),
    free_tokens INT DEFAULT 0,
    expiration_date DATE,
    payment_method_id VARCHAR(255),
    last_subscription_days INT DEFAULT 0,
    last_subscription_amount FLOAT DEFAULT 0,
    failed_autopay_attempts INT DEFAULT 0,
    timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
    email VARCHAR(255) DEFAULT NULL,
    email_confirmed TINYINT DEFAULT 0,
    gender VARCHAR(10) DEFAULT NULL,
    height_cm INT DEFAULT NULL,
    weight_kg FLOAT DEFAULT NULL,
    birth_year INT DEFAULT NULL,
    activity_level VARCHAR(20) DEFAULT NULL,
    calorie_goal INT DEFAULT NULL
);

-- Миграция для существующей БД (запустить вручную на проде):
-- ALTER TABLE users_tbl
--   ADD COLUMN gender VARCHAR(10) DEFAULT NULL,
--   ADD COLUMN height_cm INT DEFAULT NULL,
--   ADD COLUMN weight_kg FLOAT DEFAULT NULL,
--   ADD COLUMN birth_year INT DEFAULT NULL,
--   ADD COLUMN activity_level VARCHAR(20) DEFAULT NULL,
--   ADD COLUMN calorie_goal INT DEFAULT NULL;

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
