import re
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash, check_password_hash

from models import create_user, get_user_by_username, get_user_by_email, get_user_by_id

auth = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Authentication required."}), 401
        return view_func(*args, **kwargs)
    return wrapped


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Authentication required."}), 401
        if session.get("role") != "admin":
            return jsonify({"error": "Admin privileges required."}), 403
        return view_func(*args, **kwargs)
    return wrapped


def user_to_public_dict(user):
    if not user:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "created_at": user["created_at"],
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@auth.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not USERNAME_RE.match(username):
        return jsonify({"error": "Username must be 3-32 characters (letters, numbers, _ . -)."}), 400

    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    if get_user_by_username(username):
        return jsonify({"error": "That username is already taken."}), 409

    if get_user_by_email(email):
        return jsonify({"error": "That email is already registered."}), 409

    password_hash = generate_password_hash(password)
    user_id = create_user(username, email, password_hash, "user", now())
    user = get_user_by_id(user_id)

    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]

    return jsonify({
        "message": "Registration successful.",
        "data": user_to_public_dict(user)
    }), 201


@auth.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("username") or data.get("email") or "").strip()
    password = str(data.get("password", ""))

    if not identifier or not password:
        return jsonify({"error": "Username/email and password are required."}), 400

    user = get_user_by_username(identifier) or get_user_by_email(identifier.lower())

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials."}), 401

    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session.permanent = True

    return jsonify({
        "message": "Login successful.",
        "data": user_to_public_dict(user)
    })


@auth.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out."})


@auth.get("/me")
def me():
    user = get_current_user()
    if not user:
        return jsonify({"data": None})
    return jsonify({"data": user_to_public_dict(user)})
