import sqlite3
import csv
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

# Support serverless / read-only environments like Vercel
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DB_DIR = Path("/tmp/database")
    UPLOADS_DIR = Path("/tmp/uploads")
    QR_DIR = Path("/tmp/qr_codes")
else:
    DB_DIR = BASE_DIR / "database"
    UPLOADS_DIR = PROJECT_ROOT / "uploads"
    QR_DIR = PROJECT_ROOT / "qr_codes"

DB_PATH = DB_DIR / "urls.db"
CSV_PATH = DB_DIR / "urls.csv"

IMAGES_DIR = UPLOADS_DIR / "images"
VIDEOS_DIR = UPLOADS_DIR / "videos"
FILES_DIR = UPLOADS_DIR / "files"


def get_connection():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # WAL lets reads (e.g. the admin dashboard's refresh/stats queries) run
    # without waiting on writers (uploads, click tracking, CSV export), which
    # is what made "Refresh" on the admin dashboard feel sluggish under any
    # concurrent activity with the default rollback-journal mode.
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _ensure_dirs():
    for directory in (DB_DIR, UPLOADS_DIR, IMAGES_DIR, VIDEOS_DIR, FILES_DIR, QR_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def init_db():
    """Create all tables (legacy + new) and migrate legacy data if needed."""
    _ensure_dirs()

    with get_connection() as conn:
        # --- Legacy table, preserved for backward compatibility ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_url TEXT NOT NULL,
                short_code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                click_count INTEGER NOT NULL DEFAULT 0
            )
        """)

        # --- New auth + resource model ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                resource_type TEXT NOT NULL,
                original_name TEXT,
                original_url TEXT,
                stored_file_path TEXT,
                mime_type TEXT,
                short_code TEXT NOT NULL UNIQUE,
                visibility TEXT NOT NULL DEFAULT 'public',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                click_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS qr_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_id INTEGER NOT NULL UNIQUE,
                owner_id INTEGER,
                qr_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (resource_id) REFERENCES resources (id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.commit()

        _migrate_legacy_urls(conn)
        _migrate_ai_columns(conn)


def _migrate_ai_columns(conn):
    """Add AI-related columns to the existing `resources` table if they are
    not there yet. Purely additive (ALTER TABLE ... ADD COLUMN) - never
    touches existing rows/columns, so it is safe to run on every startup."""
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(resources)").fetchall()}
    new_columns = [
        ("ai_risk_level", "TEXT"),          # 'low' | 'medium' | 'high' (URLs, AI-assisted heuristic)
        ("ai_risk_reason", "TEXT"),         # human-readable reasons, semicolon-separated
        ("ai_privacy_suggestion", "TEXT"),  # 'public' | 'private' (AI-suggested, never enforced)
        ("ai_privacy_reason", "TEXT"),
    ]
    added_any = False
    for name, col_type in new_columns:
        if name not in existing_cols:
            conn.execute(f"ALTER TABLE resources ADD COLUMN {name} {col_type}")
            added_any = True
    if added_any:
        conn.commit()


def _migrate_legacy_urls(conn):
    """One-time copy of rows from the old 'urls' table into 'resources'.

    Legacy links keep working at /<code> and /s/<code>. They have no owner
    (owner_id = NULL) and stay 'public' so existing shared links do not break;
    only an admin can edit/delete them afterwards.
    """
    already_migrated = conn.execute(
        "SELECT value FROM meta WHERE key = 'legacy_urls_migrated'"
    ).fetchone()
    if already_migrated:
        return

    legacy_rows = conn.execute("SELECT * FROM urls").fetchall()
    for row in legacy_rows:
        exists = conn.execute(
            "SELECT id FROM resources WHERE short_code = ?", (row["short_code"],)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO resources
            (owner_id, resource_type, original_name, original_url, stored_file_path,
             mime_type, short_code, visibility, created_at, updated_at, click_count)
            VALUES (NULL, 'url', NULL, ?, NULL, NULL, ?, 'public', ?, ?, ?)
            """,
            (
                row["original_url"],
                row["short_code"],
                row["created_at"],
                row["updated_at"],
                row["click_count"],
            ),
        )

    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('legacy_urls_migrated', '1')"
    )
    conn.commit()


def export_to_csv():
    """Export all URL-type resources to urls.csv (kept for MS Excel compatibility)."""
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM resources WHERE resource_type = 'url' ORDER BY id"
            ).fetchall()

        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "original_url", "short_code", "created_at", "updated_at", "click_count"])
            for row in rows:
                writer.writerow([
                    row["id"],
                    row["original_url"],
                    row["short_code"],
                    row["created_at"],
                    row["updated_at"],
                    row["click_count"],
                ])
    except Exception as e:
        print(f"[CSV export] Warning: could not write {CSV_PATH}: {e}")
