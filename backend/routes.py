import io
import os
import socket
import mimetypes
import qrcode
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import (
    Blueprint, jsonify, request, redirect, render_template_string,
    send_file, session, abort, has_request_context
)
from werkzeug.exceptions import RequestEntityTooLarge

from database import init_db
from models import (
    create_resource, get_resource_by_code, get_resource_by_id,
    get_resources_for_owner, update_resource, delete_resource,
    increment_resource_clicks, create_qr_record, get_qr_by_resource,
    update_resource_ai,
)
from utils import (
    generate_short_code, is_valid_url, row_to_dict,
    save_uploaded_file, resolve_stored_path, generate_qr_code, QR_DIR,
)
from auth import get_current_user, login_required
from ai import analyze_url_risk, suggest_privacy

api = Blueprint("api", __name__)
init_db()

UPLOAD_TYPES = ("image", "video", "file")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def build_short_url(short_code):
    base_url = os.environ.get("BASE_URL")
    if base_url:
        return base_url.rstrip("/") + "/s/" + short_code

    if has_request_context():
        host_url = request.host_url.rstrip("/")
        if "localhost" in host_url or "127.0.0.1" in host_url:
            local_ip = _get_local_ip()
            if local_ip and local_ip != "127.0.0.1":
                parsed = urlparse(host_url)
                port_str = f":{parsed.port}" if parsed.port else ""
                return f"{parsed.scheme}://{local_ip}{port_str}/s/{short_code}"
        return host_url + "/s/" + short_code
    else:
        local_ip = _get_local_ip()
        port = os.environ.get("PORT", "5000")
        return f"http://{local_ip}:{port}/s/{short_code}"


def resource_to_public_dict(row):
    if not row:
        return None
    data = row_to_dict(row)
    data["short_url"] = build_short_url(row["short_code"])
    qr = get_qr_by_resource(row["id"])
    data["qr_url"] = f"/api/qr/{row['short_code']}" if qr else None
    data.pop("stored_file_path", None)  # never expose raw filesystem paths
    return data


def is_owner_or_admin(resource_row, user):
    if not user:
        return False
    if user["role"] == "admin":
        return True
    return resource_row["owner_id"] == user["id"]


def unique_short_code():
    for _ in range(10):
        code = generate_short_code()
        if not get_resource_by_code(code):
            return code
    return None


# ---------------------------------------------------------------------------
# Create resources
# ---------------------------------------------------------------------------

@api.post("/shorten")
@login_required
def shorten():
    """Create a plain URL short link. Kept at the original endpoint name for
    backward compatibility with the existing frontend."""
    data = request.get_json(silent=True) or {}
    original_url = str(data.get("url", "")).strip()
    visibility = data.get("visibility", "public")
    visibility = "private" if visibility == "private" else "public"

    if not original_url:
        return jsonify({"error": "URL is required"}), 400

    if not is_valid_url(original_url):
        return jsonify({"error": "Please enter a valid URL beginning with http:// or https://"}), 400

    short_code = unique_short_code()
    if not short_code:
        return jsonify({"error": "Could not generate a unique short code"}), 500

    user = get_current_user()
    created_at = now()
    resource_id = create_resource(
        owner_id=user["id"], resource_type="url", short_code=short_code,
        created_at=created_at, original_url=original_url, visibility=visibility,
    )
    _create_qr_for_resource(resource_id, short_code)
    _run_ai_url_risk(resource_id, original_url)
    row = get_resource_by_id(resource_id)

    return jsonify({
        "message": "URL shortened successfully",
        "data": resource_to_public_dict(row)
    }), 201


@api.post("/resources/<resource_type>")
@login_required
def upload_resource(resource_type):
    if resource_type not in UPLOAD_TYPES:
        return jsonify({"error": "Unknown resource type."}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file_storage = request.files["file"]
    if not file_storage or file_storage.filename == "":
        return jsonify({"error": "No file selected."}), 400

    visibility = request.form.get("visibility", "public")
    visibility = "private" if visibility == "private" else "public"

    try:
        stored_path, original_name, mime_type = save_uploaded_file(file_storage, resource_type)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RequestEntityTooLarge:
        return jsonify({"error": "Uploaded file is too large."}), 413

    short_code = unique_short_code()
    if not short_code:
        return jsonify({"error": "Could not generate a unique short code"}), 500

    user = get_current_user()
    created_at = now()
    resource_id = create_resource(
        owner_id=user["id"], resource_type=resource_type, short_code=short_code,
        created_at=created_at, original_name=original_name, stored_file_path=stored_path,
        mime_type=mime_type, visibility=visibility,
    )
    _create_qr_for_resource(resource_id, short_code)
    _run_ai_privacy_suggestion(resource_id)
    row = get_resource_by_id(resource_id)

    return jsonify({
        "message": f"{resource_type.capitalize()} uploaded successfully",
        "data": resource_to_public_dict(row)
    }), 201


def _create_qr_for_resource(resource_id, short_code):
    target_url = build_short_url(short_code)
    qr_filename = generate_qr_code(short_code, target_url)
    create_qr_record(resource_id, get_current_user()["id"] if get_current_user() else None, qr_filename, now())


def _run_ai_url_risk(resource_id, original_url):
    """Best-effort AI risk scan on creation. Never blocks or fails resource
    creation - any error here is swallowed so the AI layer stays optional."""
    try:
        level, reasons = analyze_url_risk(original_url)
        update_resource_ai(resource_id, ai_risk_level=level, ai_risk_reason="; ".join(reasons))
    except Exception:
        pass


def _run_ai_privacy_suggestion(resource_id):
    """Best-effort AI privacy suggestion on creation. Suggestion only - never
    changes the visibility the user actually chose."""
    try:
        row = get_resource_by_id(resource_id)
        suggested, reasons = suggest_privacy(row)
        update_resource_ai(resource_id, ai_privacy_suggestion=suggested, ai_privacy_reason="; ".join(reasons))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# List / view / edit / delete own resources
# ---------------------------------------------------------------------------

@api.get("/history")
@login_required
def history():
    """Current user's own resources (any type). Kept the original endpoint
    name/shape for backward compatibility; it now returns the caller's own
    resources instead of every resource on the server, which is required for
    per-user ownership."""
    search = request.args.get("search", "").strip()
    user = get_current_user()
    rows = get_resources_for_owner(user["id"], search)
    return jsonify({"data": [resource_to_public_dict(row) for row in rows]})


@api.get("/urls/<int:resource_id>")
@login_required
def get_url(resource_id):
    row = get_resource_by_id(resource_id)
    user = get_current_user()

    if not row:
        return jsonify({"error": "Resource not found"}), 404
    if not is_owner_or_admin(row, user):
        return jsonify({"error": "You do not have permission to view this resource."}), 403

    return jsonify({"data": resource_to_public_dict(row)})


@api.put("/urls/<int:resource_id>")
@login_required
def edit_url(resource_id):
    row = get_resource_by_id(resource_id)
    user = get_current_user()

    if not row:
        return jsonify({"error": "Resource not found"}), 404
    if not is_owner_or_admin(row, user):
        return jsonify({"error": "You do not have permission to edit this resource."}), 403

    data = request.get_json(silent=True) or {}
    updates = {}

    if "url" in data:
        new_url = str(data.get("url", "")).strip()
        if row["resource_type"] != "url":
            return jsonify({"error": "Only URL resources have an editable destination."}), 400
        if not is_valid_url(new_url):
            return jsonify({"error": "Please enter a valid URL"}), 400
        updates["original_url"] = new_url

    if "visibility" in data:
        visibility = data.get("visibility")
        if visibility not in ("public", "private"):
            return jsonify({"error": "Visibility must be 'public' or 'private'."}), 400
        updates["visibility"] = visibility

    update_resource(resource_id, now(), **updates)
    row = get_resource_by_id(resource_id)

    return jsonify({
        "message": "Resource updated successfully",
        "data": resource_to_public_dict(row)
    })


@api.delete("/urls/<int:resource_id>")
@login_required
def remove_url(resource_id):
    row = get_resource_by_id(resource_id)
    user = get_current_user()

    if not row:
        return jsonify({"error": "Resource not found"}), 404
    if not is_owner_or_admin(row, user):
        return jsonify({"error": "You do not have permission to delete this resource."}), 403

    delete_resource(resource_id)
    return jsonify({"message": "Resource deleted successfully"})


@api.delete("/history")
@login_required
def remove_history():
    """Clears only the current user's own resources (never other users')."""
    user = get_current_user()
    for row in get_resources_for_owner(user["id"]):
        delete_resource(row["id"])
    return jsonify({"message": "History cleared successfully"})


@api.get("/stats")
def stats():
    """Lightweight stats for the current viewer: their own resources when
    logged in, otherwise nothing sensitive is revealed. Full site-wide
    analytics live in the Admin Dashboard (/api/admin/stats)."""
    user = get_current_user()
    if not user:
        return jsonify({"data": {"total_urls": 0, "total_clicks": 0}})

    rows = get_resources_for_owner(user["id"])
    url_rows = [r for r in rows if r["resource_type"] == "url"]
    total_clicks = sum(r["click_count"] for r in rows)

    return jsonify({"data": {
        "total_urls": len(url_rows),
        "total_resources": len(rows),
        "total_clicks": total_clicks,
    }})


# ---------------------------------------------------------------------------
# QR code delivery (respects the same visibility rules as the resource)
# ---------------------------------------------------------------------------

@api.get("/qr/<short_code>")
def get_qr(short_code):
    row = get_resource_by_code(short_code)
    if not row:
        abort(404)

    if row["visibility"] == "private" and not is_owner_or_admin(row, get_current_user()):
        abort(403)

    # Generate QR on-the-fly in memory — works on Vercel serverless where
    # /tmp is ephemeral and QR files saved during a previous invocation
    # are no longer present. This is always fresh and needs no disk I/O.
    target_url = build_short_url(short_code)
    img = qrcode.make(target_url)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", download_name=f"{short_code}.png")


# ---------------------------------------------------------------------------
# Public/private resource access: /s/<short_code> (and legacy /<short_code>)
# ---------------------------------------------------------------------------

NOT_FOUND_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Short URL not found</title>
    <style>
        body { font-family: sans-serif; text-align: center; padding: 4rem 1rem; color: #333; }
        a { color: #1565c0; }
    </style>
</head>
<body>
    <h1>Short URL not found</h1>
    <p>This link does not exist or was deleted.</p>
    <p><a href="/">Back to URL Shortener</a></p>
</body>
</html>
"""

FORBIDDEN_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Private resource</title>
    <style>
        body { font-family: sans-serif; text-align: center; padding: 4rem 1rem; color: #333; }
        a { color: #1565c0; }
    </style>
</head>
<body>
    <h1>🔒 This resource is private</h1>
    <p>Only the owner or an admin can access it. Please log in with the right account.</p>
    <p><a href="/login.html">Log in</a> &middot; <a href="/">Back home</a></p>
</body>
</html>
"""


def redirect_short_url(short_code):
    row = get_resource_by_code(short_code)

    if not row:
        return render_template_string(NOT_FOUND_PAGE), 404

    if row["visibility"] == "private" and not is_owner_or_admin(row, get_current_user()):
        return render_template_string(FORBIDDEN_PAGE), 403

    increment_resource_clicks(short_code)

    resource_type = row["resource_type"]

    if resource_type == "url":
        return redirect(row["original_url"], code=302)

    # image / video / file -> serve the stored upload
    try:
        absolute_path = resolve_stored_path(row["stored_file_path"])
    except ValueError:
        abort(404)

    if not absolute_path.exists():
        abort(404)

    mime_type = row["mime_type"] or mimetypes.guess_type(str(absolute_path))[0] or "application/octet-stream"
    as_attachment = resource_type == "file" and not mime_type.startswith(("application/pdf", "text/", "image/"))

    return send_file(
        absolute_path,
        mimetype=mime_type,
        as_attachment=as_attachment,
        download_name=row["original_name"] or absolute_path.name,
        conditional=True,  # enables HTTP Range requests so video can stream/seek
    )
