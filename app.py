import os
import logging
import time
import hashlib
import jwt
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Environment Variables ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key')
app.config['TELEPO_API_URL'] = os.environ.get('TELEPO_API_URL', 'https://telepo-api.example.com/update')
app.config['TELEPO_API_KEY'] = os.environ.get('TELEPO_API_KEY', 'your_api_key_here')

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'oncall')
DB_USER = os.environ.get('DB_USER', 'oncall_user')
DB_PASS = os.environ.get('DB_PASS', 'password')

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Rate Limiting State ---
ip_request_counter = {}
RATE_LIMIT = 5  # requests
RATE_PERIOD = 60  # seconds

# --- Database Connection Helper ---
def get_db_connection():
    """
    Returns a psycopg2 connection to the PostgreSQL database.
    """
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

# --- Utility Decorators ---
def rate_limited(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = request.remote_addr
        current_time = time.time()
        
        if ip not in ip_request_counter:
            ip_request_counter[ip] = []
        
        # Remove timestamps older than RATE_PERIOD
        ip_request_counter[ip] = [
            t for t in ip_request_counter[ip]
            if current_time - t < RATE_PERIOD
        ]
        
        if len(ip_request_counter[ip]) >= RATE_LIMIT:
            logger.warning(f"Rate limit exceeded for IP: {ip}")
            return jsonify({"status": "error", "message": "Rate limit exceeded"}), 429
        
        # Add this request timestamp
        ip_request_counter[ip].append(current_time)
        return f(*args, **kwargs)
    return decorated_function

def token_required(f):
    """
    Checks for a JWT in the Authorization header (Bearer <token>).
    If invalid or missing, returns 401.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token or not token.startswith('Bearer '):
            logger.warning("Missing or invalid authorization header")
            return jsonify({'message': 'Missing or invalid token'}), 401
        
        token = token.split('Bearer ')[1]
        
        try:
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        except Exception:
            logger.warning("Invalid token detected")
            return jsonify({'message': 'Invalid token'}), 401
            
        return f(*args, **kwargs)
    return decorated

def hash_pin(pin):
    """
    Hashes the PIN with a salt for secure storage.
    """
    salt = os.environ.get('PIN_SALT', 'default_salt_value')
    return hashlib.sha256((pin + salt).encode()).hexdigest()

# --- Database Initialization (for local dev or fallback) ---
def init_db():
    """
    Create tables if they do not exist, including 'division' columns.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                pin TEXT NOT NULL,
                phone TEXT NOT NULL,
                name TEXT,
                email TEXT,
                division TEXT NOT NULL,  -- multiple divisions
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS on_call (
                id SERIAL PRIMARY KEY,
                phone TEXT NOT NULL,
                user_id INTEGER,
                division TEXT NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                details TEXT,
                ip_address TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)

        conn.commit()
        conn.close()
        logger.info("Database initialized (PostgreSQL) with divisions.")
    except Exception as e:
        logger.error(f"init_db error: {str(e)}")

# Uncomment if you want to auto-create tables on startup:
# init_db()

# --- Routes ---
@app.route("/authenticate", methods=["POST"])
@rate_limited
def authenticate():
    """
    Authenticate user based on PIN and set as on-call if successful.
    The user table holds 'division', so we store an on-call record for
    that user's division automatically.
    """
    pin = request.form.get("pin")
    caller_id = request.form.get("caller_id", "unknown")
    ip_address = request.remote_addr
    
    if not pin:
        logger.warning("Authentication attempt with missing PIN")
        return jsonify({"status": "failure", "message": "PIN required"}), 400
    
    hashed = hash_pin(pin)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Find user by hashed pin
        cursor.execute(
            "SELECT id, phone, name, division FROM users WHERE pin = %s",
            (hashed,)
        )
        user = cursor.fetchone()
        
        if not user:
            cursor.execute(
                "INSERT INTO audit_log (event_type, details, ip_address) VALUES (%s, %s, %s)",
                ("failed_auth", f"Caller ID: {caller_id}", ip_address)
            )
            conn.commit()
            conn.close()
            logger.warning(f"Authentication failed for caller ID: {caller_id}")
            return jsonify({"status": "failure", "message": "Invalid PIN"}), 403
        
        user_id = user['id']
        phone_number = user['phone']
        user_name = user['name']
        user_division = user['division']

        # Update last_login
        cursor.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
            (user_id,)
        )

        # Log successful auth
        cursor.execute(
            "INSERT INTO audit_log (event_type, user_id, details, ip_address) VALUES (%s, %s, %s, %s)",
            ("successful_auth", user_id, f"Caller ID: {caller_id}", ip_address)
        )
        
        conn.commit()
        conn.close()

        # Set them on-call for their division
        result = set_on_call_number(phone_number, user_id, user_division, ip_address)
        logger.info(f"User {user_name} (ID: {user_id}, division={user_division}) is now on-call.")

        return jsonify({
            "status": "success",
            "message": f"On-call number updated to {phone_number} (division: {user_division})",
            "telepo_result": result
        })

    except Exception as e:
        logger.error(f"authenticate error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

def set_on_call_number(phone_number, user_id, division, ip_address):
    """
    Update the on_call table for the given division, archiving any older record.
    Then push to Telepo or another external API.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Archive current on-call for this division
        cursor.execute("""
            UPDATE on_call
               SET end_time = CURRENT_TIMESTAMP
             WHERE end_time IS NULL
               AND division = %s
        """, (division,))

        # Insert new on-call row
        cursor.execute("""
            INSERT INTO on_call (phone, user_id, division)
            VALUES (%s, %s, %s)
        """, (phone_number, user_id, division))

        # Log the on-call update
        cursor.execute("""
            INSERT INTO audit_log (event_type, user_id, details, ip_address)
            VALUES (%s, %s, %s, %s)
        """, ("on_call_update", user_id, f"New on-call: {phone_number} (division={division})", ip_address))

        conn.commit()
        conn.close()

        # Push update to Telepo
        try:
            api_url = app.config['TELEPO_API_URL']
            headers = {"Authorization": f"Bearer {app.config['TELEPO_API_KEY']}"}
            payload = {
                "phone_number": phone_number,
                "division": division,
                "updated_at": datetime.now().isoformat(),
                "user_id": user_id
            }

            response = requests.post(api_url, json=payload, headers=headers)
            response_data = response.json()

            if response.status_code != 200:
                logger.error(f"Telepo API error: {response.status_code} - {response_data}")
                return {"status": "error", "message": "API update failed"}
                
            logger.info(f"Successfully updated Telepo for division={division}, phone={phone_number}")
            return {"status": "success", "data": response_data}

        except Exception as api_err:
            logger.error(f"Telepo API request failed: {str(api_err)}")
            return {"status": "error", "message": str(api_err)}

    except Exception as db_err:
        logger.error(f"set_on_call_number error: {str(db_err)}")
        return {"status": "error", "message": str(db_err)}

@app.route("/api/oncall", methods=["GET"])
def get_current_oncall():
    """
    Get current on-call info. Optionally pass ?division=retic_water to filter by division.
    If none specified, default to 'retic_water' for demonstration.
    """
    division = request.args.get("division", "retic_water")
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute("""
            SELECT o.phone, o.start_time, u.name, u.id AS user_id, o.division
              FROM on_call o
              JOIN users u ON o.user_id = u.id
             WHERE o.end_time IS NULL
               AND o.division = %s
             ORDER BY o.start_time DESC
             LIMIT 1
        """, (division,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return jsonify({"status": "success", "on_call": row})
        else:
            return jsonify({"status": "error", "message": f"No on-call user set for division={division}"}), 404

    except Exception as e:
        logger.error(f"get_current_oncall error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/users", methods=["GET"])
@token_required
def get_users():
    """
    Retrieve all users. (Basic user list)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT id, phone, name, email, division, created_at, last_login FROM users")
        rows = cursor.fetchall()
        conn.close()
        return jsonify({"users": rows})
    except Exception as e:
        logger.error(f"get_users error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/users", methods=["POST"])
@token_required
def create_user():
    """
    Create a new user. Must include 'division' in the JSON.
    """
    data = request.json
    if not data or not all(k in data for k in ['pin', 'phone', 'name', 'division']):
        return jsonify({"status": "error", "message": "Missing required fields (pin, phone, name, division)"}), 400
    
    hashed = hash_pin(data['pin'])
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO users (pin, phone, name, email, division) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (hashed, data['phone'], data['name'], data.get('email'), data['division'])
        )
        user_id = cursor.fetchone()[0]
        
        # Audit log
        cursor.execute(
            "INSERT INTO audit_log (event_type, user_id, details, ip_address) VALUES (%s, %s, %s, %s)",
            ("user_created", user_id, f"New user: {data['name']} (division={data['division']})", request.remote_addr)
        )
        
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": "User created successfully",
            "user_id": user_id
        }), 201

    except Exception as e:
        logger.error(f"create_user error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Simple Admin Web Endpoints ---
@app.route("/admin/users", methods=["GET"])
@token_required
def admin_list_users():
    """
    Admin route: Lists all users (full details).
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM users ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()
        return jsonify({"users": rows})
    except Exception as e:
        logger.error(f"admin_list_users error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/admin/users/<int:user_id>", methods=["PATCH"])
@token_required
def admin_update_user(user_id):
    """
    Admin route: Update user record (phone, name, email, division, etc.).
    Expects JSON, e.g. {"phone": "...", "division": "..."}
    """
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No update data provided"}), 400

    fields = []
    values = []
    for key in ["phone", "name", "email", "division"]:
        if key in data:
            fields.append(f"{key} = %s")
            values.append(data[key])

    # If updating pin, handle hashing
    if "pin" in data:
        fields.append("pin = %s")
        values.append(hash_pin(data["pin"]))

    if not fields:
        return jsonify({"status": "error", "message": "No valid fields to update"}), 400

    values.append(user_id)  # for WHERE clause

    query = f"UPDATE users SET {', '.join(fields)} WHERE id = %s RETURNING id"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, tuple(values))
        updated = cursor.fetchone()
        if not updated:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "message": f"No user found with id {user_id}"}), 404

        # Audit log
        cursor.execute(
            "INSERT INTO audit_log (event_type, user_id, details, ip_address) VALUES (%s, %s, %s, %s)",
            ("admin_update_user", user_id, str(data), request.remote_addr)
        )

        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"User {user_id} updated"})
    
    except Exception as e:
        logger.error(f"admin_update_user error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check endpoint for monitoring.
    """
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/token", methods=["POST"])
def get_token():
    """
    Generate JWT token for API access.
    """
    auth = request.authorization
    
    if not auth or not auth.username or not auth.password:
        return jsonify({"message": "Authentication required"}), 401
    
    # Validate admin creds (simplified example)
    if auth.username != "admin" or auth.password != os.environ.get("ADMIN_PASSWORD", "secure_password"):
        return jsonify({"message": "Invalid credentials"}), 401

    # Generate token
    token = jwt.encode({
        'user': auth.username,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, app.config['SECRET_KEY'])
    
    return jsonify({'token': token})

if __name__ == "__main__":
    # For local dev only; in production, run via Gunicorn
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
