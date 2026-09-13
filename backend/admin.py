from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request

from auth import admin_required, get_current_user, user_to_public_dict
from models import (
    get_all_users, delete_user, set_user_role,
    get_all_resources, get_resource_by_id, update_resource, delete_resource,
    get_resource_stats, get_resources_created_per_day, get_resource_counts_by_user,
)
from routes import resource_to_public_dict  # reuse the same shaping/short-url logic

admin_api = Blueprint("admin_api", __name__)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@admin_api.get("/users")
@admin_required
def list_users():
    users = get_all_users()
    return jsonify({"data": [user_to_public_dict(u) for u in users]})


@admin_api.delete("/users/<int:user_id>")
@admin_required
def remove_user(user_id):
    current = get_current_user()
    if current and current["id"] == user_id:
        return jsonify({"error": "You cannot delete your own account while logged in."}), 400

    if delete_user(user_id) == 0:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "User deleted successfully"})


@admin_api.put("/users/<int:user_id>/role")
@admin_required
def change_role(user_id):
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    if role not in ("user", "admin"):
        return jsonify({"error": "Role must be 'user' or 'admin'."}), 400

    if set_user_role(user_id, role) == 0:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "Role updated successfully"})


# ---------------------------------------------------------------------------
# All resources (any owner)
# ---------------------------------------------------------------------------

@admin_api.get("/resources")
@admin_required
def list_all_resources():
    search = request.args.get("search", "").strip()
    rows = get_all_resources(search)
    data = []
    for row in rows:
        item = resource_to_public_dict(row)
        item["owner_username"] = row["owner_username"] if "owner_username" in row.keys() else None
        data.append(item)
    return jsonify({"data": data})


@admin_api.put("/resources/<int:resource_id>")
@admin_required
def admin_edit_resource(resource_id):
    row = get_resource_by_id(resource_id)
    if not row:
        return jsonify({"error": "Resource not found"}), 404

    data = request.get_json(silent=True) or {}
    updates = {}

    if "url" in data and row["resource_type"] == "url":
        updates["original_url"] = str(data.get("url", "")).strip()

    if "visibility" in data and data["visibility"] in ("public", "private"):
        updates["visibility"] = data["visibility"]

    update_resource(resource_id, now(), **updates)
    row = get_resource_by_id(resource_id)
    return jsonify({"message": "Resource updated successfully", "data": resource_to_public_dict(row)})


@admin_api.delete("/resources/<int:resource_id>")
@admin_required
def admin_delete_resource(resource_id):
    if delete_resource(resource_id) == 0:
        return jsonify({"error": "Resource not found"}), 404
    return jsonify({"message": "Resource deleted successfully"})


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@admin_api.get("/stats")
@admin_required
def admin_stats():
    return jsonify({"data": get_resource_stats()})


@admin_api.get("/stats/timeline")
@admin_required
def admin_stats_timeline():
    days_count = int(request.args.get("days", 14))
    rows = get_resources_created_per_day(days_count)
    
    db_counts = {r["day"]: r["count"] for r in rows}
    
    data = []
    today = datetime.now(timezone.utc)
    for i in range(days_count - 1, -1, -1):
        day_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        data.append({"day": day_str, "count": db_counts.get(day_str, 0)})
        
    return jsonify({"data": data})


@admin_api.get("/stats/by-user")
@admin_required
def admin_stats_by_user():
    rows = get_resource_counts_by_user()
    return jsonify({"data": [{"username": r["username"], "count": r["count"]} for r in rows]})
