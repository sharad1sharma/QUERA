import os
import re
import sys
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")

# `database.py`, `models.py`, `auth.py`, `admin.py`, `routes.py` and `utils.py`
# are this project's OWN files, sitting right next to this one in backend/ -
# they are not PyPI packages and must never be added to requirements.txt
# (pip would try to fetch an unrelated package called "database" from PyPI,
# which is not this file). Running `python app.py` from inside backend/
# already makes Python find them automatically, but this line makes it work
# even if something else launches this file (an IDE run config, `flask run`,
# a WSGI server) from a different working directory.
sys.path.insert(0, str(BASE_DIR))

from routes import api, redirect_short_url
from auth import auth
from admin import admin_api
from ai import ai_api
from database import init_db
from models import create_user, get_user_by_email
from werkzeug.security import generate_password_hash

FRONTEND_DIR = PROJECT_ROOT / "frontend"
RESERVED_PATHS = {"api", "favicon.ico", "s", "css", "js", "qr_codes"}

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
# Max upload size in bytes (default 50 MB, override with MAX_UPLOAD_MB)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", 50)) * 1024 * 1024

# --- CORS ------------------------------------------------------------------
# The frontend is often opened from a different origin than the API during
# local development (e.g. VS Code "Live Server" on http://localhost:5501
# while Flask runs on http://localhost:5000). Session-cookie login requires
# `credentials: "include"` on the frontend AND `supports_credentials=True`
# here — but browsers refuse to expose the response to JS if the server
# replies with the literal wildcard "Access-Control-Allow-Origin: *" while
# credentials are involved. That silent rejection is what made every
# `fetch(...)` on the admin dashboard (stats, charts, users, resources) fail
# before the tables/charts ever got data. Reflecting the actual request
# origin (instead of a literal "*") fixes it while still accepting requests
# from any localhost/127.0.0.1 dev port out of the box.
#
# For a real deployment, set CORS_ORIGINS in your .env to a comma-separated
# list of the exact origin(s) your frontend is served from, e.g.
#   CORS_ORIGINS=https://your-frontend.example.com
_cors_origins_env = os.environ.get("CORS_ORIGINS")
if _cors_origins_env:
    cors_origins = [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
else:
    cors_origins = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")

CORS(app, origins=cors_origins, supports_credentials=True)

app.register_blueprint(api, url_prefix="/api")
app.register_blueprint(auth, url_prefix="/api/auth")
app.register_blueprint(admin_api, url_prefix="/api/admin")
app.register_blueprint(ai_api, url_prefix="/api/ai")


def ensure_admin_from_env():
    """Create the initial admin account from env vars if it doesn't exist yet.

    No credentials are hard-coded: set ADMIN_EMAIL / ADMIN_USERNAME /
    ADMIN_PASSWORD in your .env file (see .env.example). If they are not set,
    no admin account is created automatically and one can be promoted later
    via the database or another admin.
    """
    email = os.environ.get("ADMIN_EMAIL")
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD")

    if not email or not password:
        return

    if get_user_by_email(email.lower()):
        return

    from datetime import datetime, timezone
    create_user(
        username=username,
        email=email.lower(),
        password_hash=generate_password_hash(password),
        role="admin",
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/css/<path:filename>")
def css_files(filename):
    return send_from_directory(FRONTEND_DIR / "css", filename)


@app.route("/js/<path:filename>")
def js_files(filename):
    return send_from_directory(FRONTEND_DIR / "js", filename)


@app.route("/<page_name>.html")
def html_pages(page_name):
    """Serve the extra frontend pages (login, register, dashboard, admin)."""
    filename = f"{page_name}.html"
    if not (FRONTEND_DIR / filename).exists():
        abort(404)
    return send_from_directory(FRONTEND_DIR, filename)


@app.route("/s/<short_code>", methods=["GET"])
def resource_access(short_code):
    """Canonical shortened-resource route: /s/<code> -> URL redirect, or the
    image/video/file, enforcing public/private access control."""
    return redirect_short_url(short_code)


@app.route("/<short_code>", methods=["GET"])
def redirect_url(short_code):
    """Legacy route kept for backward compatibility with links created
    before /s/<code> existed - same handler as /s/<code>."""
    if short_code in RESERVED_PATHS:
        abort(404)
    return redirect_short_url(short_code)


if __name__ == "__main__":
    init_db()
    ensure_admin_from_env()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", debug=False, port=port)
else:
    # Also run under `flask run` / gunicorn / Vercel, not just `python app.py`
    init_db()
    ensure_admin_from_env()
