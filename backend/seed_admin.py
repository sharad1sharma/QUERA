"""
One-off script to create (or promote) the admin account.

Usage:
    cd backend
    python seed_admin.py

Credentials are NEVER hardcoded here. Set them in your .env file (see
.env.example) or as environment variables before running this script:

    ADMIN_EMAIL=you@example.com
    ADMIN_USERNAME=admin
    ADMIN_PASSWORD=choose-a-strong-password

It is safe to run more than once: if the email already exists it just
resets the password and makes sure the role is 'admin'.

Note: app.py already does this automatically on every startup via
ensure_admin_from_env() if ADMIN_EMAIL/ADMIN_PASSWORD are set - this
script is only needed if you want to (re)promote an admin manually,
e.g. without restarting the server.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

from database import init_db, get_connection

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    email = os.environ.get("ADMIN_EMAIL")
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD")

    if not email or not password:
        print(
            "ADMIN_EMAIL and ADMIN_PASSWORD must be set (in .env or the "
            "environment) before running this script. Nothing was created.\n"
            "See .env.example for the expected variables."
        )
        sys.exit(1)

    email = email.strip().lower()
    init_db()
    password_hash = generate_password_hash(password)

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE users SET password_hash = ?, role = 'admin' WHERE id = ?",
                (password_hash, existing["id"]),
            )
            conn.commit()
            print(f"Existing user updated to admin: {email}")
        else:
            conn.execute(
                """
                INSERT INTO users (username, email, password_hash, role, created_at)
                VALUES (?, ?, ?, 'admin', ?)
                """,
                (username, email, password_hash, now()),
            )
            conn.commit()
            print(f"Admin user created: {email}")


if __name__ == "__main__":
    main()
