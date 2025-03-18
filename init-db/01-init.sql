CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    pin TEXT NOT NULL,
    phone TEXT NOT NULL,
    name TEXT,
    email TEXT,
    division TEXT NOT NULL,  -- Added for multi-division
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE TABLE IF NOT EXISTS on_call (
    id SERIAL PRIMARY KEY,
    phone TEXT NOT NULL,
    user_id INTEGER,
    division TEXT NOT NULL,  -- Each on-call record belongs to one division
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    user_id INTEGER,
    details TEXT,
    ip_address TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
