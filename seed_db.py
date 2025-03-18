#!/usr/bin/env python3
import os
import sys
import hashlib
import psycopg2

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'oncall')
DB_USER = os.environ.get('DB_USER', 'oncall_user')
DB_PASS = os.environ.get('DB_PASS', 'password')
SALT = os.environ.get('PIN_SALT', 'default_salt_value')

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def hash_pin(pin):
    return hashlib.sha256((pin + SALT).encode()).hexdigest()

def seed_database():
    """
    Seed the PostgreSQL database with initial users, each belonging to a division.
    """
    users = [
        {
            'name': 'Admin User',
            'pin': '1234',
            'phone': '+15551234567',
            'email': 'admin@example.com',
            'division': 'retic_water'
        },
        {
            'name': 'Support Team Lead',
            'pin': '5678',
            'phone': '+15559876543',
            'email': 'support@example.com',
            'division': 'surface_water'
        }
    ]
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        for user in users:
            hashed = hash_pin(user['pin'])
            try:
                cursor.execute(
                    """
                    INSERT INTO users (pin, phone, name, email, division)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (hashed, user['phone'], user['name'], user['email'], user['division'])
                )
                new_id = cursor.fetchone()[0]
                print(f"Added user: {user['name']} (ID: {new_id}, division={user['division']})")
            except psycopg2.Error as e:
                print(f"Could not add user {user['name']}: {str(e)}")

        conn.commit()
        conn.close()
        print("Database seeded successfully.")

    except Exception as e:
        print(f"Database connection error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    seed_database()
