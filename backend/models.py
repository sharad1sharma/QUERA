from database import get_connection, export_to_csv

# ---------------------------------------------------------------------------
# Legacy "urls" table helpers (kept so nothing that relied on them breaks).
# The active application now stores everything -- including plain URLs --
# in the unified `resources` table below.
# ---------------------------------------------------------------------------

def create_url(original_url, short_code, created_at):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO urls
            (original_url, short_code, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (original_url, short_code, created_at, created_at)
        )
        conn.commit()
        row_id = cursor.lastrowid
    return row_id


def get_stats_legacy():
    with get_connection() as conn:
        total_urls = conn.execute("SELECT COUNT(*) AS count FROM urls").fetchone()["count"]
        total_clicks = conn.execute("SELECT COALESCE(SUM(click_count), 0) AS count FROM urls").fetchone()["count"]
        return {"total_urls": total_urls, "total_clicks": total_clicks}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(username, email, password_hash, role, created_at):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (username, email, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, email, password_hash, role, created_at)
        )
        conn.commit()
        return cursor.lastrowid


def get_user_by_id(user_id):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_username(username):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_email(email):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def get_all_users():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()


def count_users():
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]


def set_user_role(user_id, role):
    with get_connection() as conn:
        cursor = conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
        return cursor.rowcount


def delete_user(user_id):
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Resources (URL / Image / Video / File - unified)
# ---------------------------------------------------------------------------

def create_resource(owner_id, resource_type, short_code, created_at, original_name=None,
                     original_url=None, stored_file_path=None, mime_type=None, visibility="public"):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO resources
            (owner_id, resource_type, original_name, original_url, stored_file_path,
             mime_type, short_code, visibility, created_at, updated_at, click_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (owner_id, resource_type, original_name, original_url, stored_file_path,
             mime_type, short_code, visibility, created_at, created_at)
        )
        conn.commit()
        row_id = cursor.lastrowid
    export_to_csv()
    return row_id


def get_resource_by_code(short_code):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM resources WHERE short_code = ?", (short_code,)).fetchone()


def get_resource_by_id(resource_id):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM resources WHERE id = ?", (resource_id,)).fetchone()


def get_resources_for_owner(owner_id, search=""):
    with get_connection() as conn:
        if search:
            pattern = f"%{search}%"
            return conn.execute(
                """
                SELECT * FROM resources
                WHERE owner_id = ?
                  AND (original_url LIKE ? OR short_code LIKE ? OR original_name LIKE ?)
                ORDER BY id DESC
                """,
                (owner_id, pattern, pattern, pattern)
            ).fetchall()
        return conn.execute(
            "SELECT * FROM resources WHERE owner_id = ? ORDER BY id DESC", (owner_id,)
        ).fetchall()


def get_all_resources(search=""):
    with get_connection() as conn:
        if search:
            pattern = f"%{search}%"
            return conn.execute(
                """
                SELECT resources.*, users.username AS owner_username
                FROM resources
                LEFT JOIN users ON users.id = resources.owner_id
                WHERE original_url LIKE ? OR short_code LIKE ? OR original_name LIKE ?
                ORDER BY resources.id DESC
                """,
                (pattern, pattern, pattern)
            ).fetchall()
        return conn.execute(
            """
            SELECT resources.*, users.username AS owner_username
            FROM resources
            LEFT JOIN users ON users.id = resources.owner_id
            ORDER BY resources.id DESC
            """
        ).fetchall()


def update_resource(resource_id, updated_at, original_url=None, visibility=None):
    fields = ["updated_at = ?"]
    params = [updated_at]

    if original_url is not None:
        fields.append("original_url = ?")
        params.append(original_url)

    if visibility is not None:
        fields.append("visibility = ?")
        params.append(visibility)

    params.append(resource_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE resources SET {', '.join(fields)} WHERE id = ?", params
        )
        conn.commit()
        rowcount = cursor.rowcount
    export_to_csv()
    return rowcount


def delete_resource(resource_id):
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
        conn.commit()
        rowcount = cursor.rowcount
    export_to_csv()
    return rowcount


def increment_resource_clicks(short_code):
    with get_connection() as conn:
        conn.execute(
            "UPDATE resources SET click_count = click_count + 1 WHERE short_code = ?",
            (short_code,)
        )
        conn.commit()


def get_resource_stats():
    with get_connection() as conn:
        def count(query, params=()):
            return conn.execute(query, params).fetchone()["count"]

        return {
            "total_users": count("SELECT COUNT(*) AS count FROM users"),
            "total_resources": count("SELECT COUNT(*) AS count FROM resources"),
            "total_urls": count("SELECT COUNT(*) AS count FROM resources WHERE resource_type = 'url'"),
            "total_images": count("SELECT COUNT(*) AS count FROM resources WHERE resource_type = 'image'"),
            "total_videos": count("SELECT COUNT(*) AS count FROM resources WHERE resource_type = 'video'"),
            "total_files": count("SELECT COUNT(*) AS count FROM resources WHERE resource_type = 'file'"),
            "public_resources": count("SELECT COUNT(*) AS count FROM resources WHERE visibility = 'public'"),
            "private_resources": count("SELECT COUNT(*) AS count FROM resources WHERE visibility = 'private'"),
            "total_qr_codes": count("SELECT COUNT(*) AS count FROM qr_codes"),
            "total_clicks": conn.execute(
                "SELECT COALESCE(SUM(click_count), 0) AS count FROM resources"
            ).fetchone()["count"],
        }


def get_resources_created_per_day(days=14):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS count
            FROM resources
            GROUP BY day
            ORDER BY day DESC
            LIMIT ?
            """,
            (days,)
        ).fetchall()


def get_resource_counts_by_user():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT users.username AS username, COUNT(resources.id) AS count
            FROM users
            LEFT JOIN resources ON resources.owner_id = users.id
            GROUP BY users.id
            ORDER BY count DESC
            """
        ).fetchall()


# ---------------------------------------------------------------------------
# QR codes
# ---------------------------------------------------------------------------

def create_qr_record(resource_id, owner_id, qr_path, created_at):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO qr_codes (resource_id, owner_id, qr_path, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(resource_id) DO UPDATE SET qr_path = excluded.qr_path
            """,
            (resource_id, owner_id, qr_path, created_at)
        )
        conn.commit()


def get_qr_by_resource(resource_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM qr_codes WHERE resource_id = ?", (resource_id,)
        ).fetchone()


# ---------------------------------------------------------------------------
# AI-assisted fields on resources (risk analysis / privacy suggestion)
# ---------------------------------------------------------------------------

def update_resource_ai(resource_id, ai_risk_level=None, ai_risk_reason=None,
                        ai_privacy_suggestion=None, ai_privacy_reason=None):
    fields = []
    params = []

    if ai_risk_level is not None:
        fields.append("ai_risk_level = ?")
        params.append(ai_risk_level)
    if ai_risk_reason is not None:
        fields.append("ai_risk_reason = ?")
        params.append(ai_risk_reason)
    if ai_privacy_suggestion is not None:
        fields.append("ai_privacy_suggestion = ?")
        params.append(ai_privacy_suggestion)
    if ai_privacy_reason is not None:
        fields.append("ai_privacy_reason = ?")
        params.append(ai_privacy_reason)

    if not fields:
        return 0

    params.append(resource_id)
    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE resources SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount


def get_ai_risk_distribution():
    """Real counts of resources by AI risk level (for the admin risk chart).
    Never fabricated - resources that have not been analyzed show as 'unrated'."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(ai_risk_level, 'unrated') AS level, COUNT(*) AS count
            FROM resources
            WHERE resource_type = 'url'
            GROUP BY level
            """
        ).fetchall()
        return [{"level": r["level"], "count": r["count"]} for r in rows]
