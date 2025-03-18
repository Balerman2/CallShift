# CallShift
CallShift is a fast, VoIP-based on-call system that lets staff instantly take over shifts with a simple phone call. No apps, no hassle—just dial, enter your PIN, and you're on duty. Supports multiple divisions, logs all actions, and integrates seamlessly with Asterisk PBX. Stay connected, stay ready—CallShift makes on-call easy. 🚀📞

## Overview

This **VoIP On-Call Management System** is a **self-hosted** application that allows designated support staff to call an internal extension, authenticate via PIN, and become the active on-call contact for their division. By using Asterisk as the telephony engine and a Flask (Python) backend, the system integrates real-time telephony events with a database that tracks on-call status. Optionally, the system can also push updates to an external API (for example, Telepo) so third-party services know who the current on-call contact is.

### Key Features

1. **Telephone-based Authentication**: Staff dial an Asterisk extension (e.g. 1000), enter a PIN, and if valid, the system marks them as the new on-call staff member.
2. **Database-Driven**: User PINs, phone numbers, and on-call status are stored in a PostgreSQL database.
3. **Multi-Division Support**: The system can handle multiple “divisions” or “departments,” each with its own on-call schedule. By default, it’s configured for *two* divisions, but you can expand it further.
4. **Optional External Updates**: Via an HTTP POST to a Telepo (or other) API, external systems can be notified of the updated on-call contact in real-time.
5. **Auditing & Logging**: All authentication attempts (both successful and failed) are logged in the database’s `audit_log` table, along with IP addresses, caller IDs, etc.

---

## 1. System Architecture

Below is an outline of the major components:

```
+---------+    Phone Call   +--------------+    AGI Script    +--------------------+
|  Staff  | --------------> |  Asterisk PBX| ---------------> |  authenticate.py   |
+---------+                 +--------------+ (PIN & CallerID)  +--------------------+
                                                                  |
                                                                  v
                                                            +-------------+
                                                            | Flask App   |
                                                            | (app.py)    |
                                                            +-------------+
                                                                  |
                                                                  v
                                                         +------------------+
                                                         | PostgreSQL DB   |
                                                         | (users,on_call) |
                                                         +------------------+
                                                                  |
                                                                  v
                                                        +--------------------+
                                                        | External API (e.g.|
                                                        |  Telepo)          |
                                                        +--------------------+
```

### Components

- **Asterisk PBX**: Manages phone calls, defines dialplan logic (in `extensions.conf`), and uses an AGI script for external logic.
- **AGI Script (`authenticate.py`)**: Reads the user’s entered PIN and caller ID, then sends them to the Flask backend for validation.
- **Flask Application (`app.py`)**: Validates users’ PINs against the database, sets new on-call records, logs to the audit table, and (optionally) pushes to Telepo.
- **PostgreSQL Database**: Tables for `users`, `on_call`, and `audit_log` store persistent data.
- **External API**: Telepo or any third-party service that may require the new on-call phone number.

**Multi-Division**: In the simplest setup, each user belongs to a single division; whichever user authenticates last for that division is the current on-call contact.

---

## 2. Data Model & Tables

### Users Table

| Column      | Type    | Description                                            |
|-------------|---------|--------------------------------------------------------|
| id          | SERIAL  | Primary Key                                           |
| pin         | TEXT    | Hashed PIN (SHA-256 + salt)                           |
| phone       | TEXT    | The user’s phone number                               |
| name        | TEXT    | Display name                                          |
| email       | TEXT    | (Optional) email address                              |
| created_at  | TIMESTAMP (auto) | When the user record was created             |
| last_login  | TIMESTAMP (nullable) | Tracks last login time (updated on auth) |

A separate or extra column for `division` can be added here if you want each user to be tied to a particular department or group.

### On_Call Table

| Column     | Type     | Description                                                    |
|------------|----------|----------------------------------------------------------------|
| id         | SERIAL   | Primary Key                                                   |
| phone      | TEXT     | The phone that is currently on-call                           |
| user_id    | INTEGER  | Foreign key referencing `users(id)`                           |
| start_time | TIMESTAMP (auto) | When this on-call record took effect                 |
| end_time   | TIMESTAMP (nullable) | When the on-call ended (NULL means still active)  |

### Audit_Log Table

| Column     | Type     | Description                                                            |
|------------|----------|------------------------------------------------------------------------|
| id         | SERIAL   | Primary Key                                                           |
| event_type | TEXT     | e.g., `successful_auth`, `failed_auth`, `on_call_update`, `user_created`|
| user_id    | INTEGER  | (nullable) references `users(id)` if relevant                         |
| details    | TEXT     | Extra info about the event (e.g. `Caller ID: +15551234567`)            |
| ip_address | TEXT     | The IP from which the request originated                               |
| timestamp  | TIMESTAMP (auto) | Auto-set time of the event                                    |

With these three tables, you can track **who** is on call, **who** has a valid PIN, and see all relevant logs.

---

## 3. Deployment Steps

### Docker Compose Setup

A typical `docker-compose.yml` might define services:

- **app** (Flask)
- **asterisk** (PBX)
- **db** (PostgreSQL)
- **nginx** (for SSL termination, if used)

Example snippet:

```yaml
version: '3.8'
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      - db
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DB_HOST=${DB_HOST}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASS=${DB_PASS}
  db:
    image: postgres:14
    environment:
      - POSTGRES_DB=${DB_NAME}
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASS}
```

### Building & Running

From your project folder, run:

```bash
docker-compose build
docker-compose up -d
```

### Seeding the Database

```bash
docker-compose exec app python seed_db.py
```

### Testing Locally

Use a softphone (Zoiper, MicroSIP) to dial extension **1000**, enter a test PIN, and watch logs.

```bash
docker-compose logs -f app
docker-compose logs -f asterisk
```

---

## 4. Supporting Multiple Divisions

Currently, the system supports **two divisions** by:

- Storing a `division` column in `users` and `on_call` tables.
- Auto-assigning on-call updates to the authenticated user’s division.

You can expand this to **more divisions** by modifying:
- The `users` table (add `division` field).
- The dialplan (`extensions.conf`) to route calls based on division.

---

## 5. Conclusion

This VoIP On-Call Management System allows staff to seamlessly update their on-call status via phone calls, ensuring **reliable** and **efficient** management of emergency contacts.

With:

✅ **Secure PIN-based authentication**  
✅ **Scalable division support**  
✅ **Audit logs for accountability**  
✅ **Optional external API integration**  

The system is adaptable for future enhancements such as a **web-based admin UI** and **advanced reporting**.

**For troubleshooting and expansion ideas, refer to the full documentation.** 🚀
