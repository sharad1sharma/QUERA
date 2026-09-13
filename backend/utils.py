import mimetypes
import secrets
import string
import uuid
from pathlib import Path
from urllib.parse import urlparse

from werkzeug.utils import secure_filename

import qrcode

from database import IMAGES_DIR, VIDEOS_DIR, FILES_DIR, QR_DIR

ALPHABET = string.ascii_letters + string.digits

ALLOWED_EXTENSIONS = {
    "image": {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"},
    "video": {"mp4", "webm", "ogg", "mov", "mkv"},
    "file": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "zip", "rtf"},
}

TYPE_DIRS = {
    "image": IMAGES_DIR,
    "video": VIDEOS_DIR,
    "file": FILES_DIR,
}


def generate_short_code(length=6):
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def row_to_dict(row):
    return dict(row) if row else None


def get_file_extension(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def is_allowed_upload(filename, resource_type):
    ext = get_file_extension(filename)
    allowed = ALLOWED_EXTENSIONS.get(resource_type, set())
    return bool(ext) and ext in allowed


def save_uploaded_file(file_storage, resource_type):
    """Validate and store an uploaded file with a random, safe name.

    Returns (stored_relative_path, original_name, mime_type) or raises ValueError.
    """
    original_name = secure_filename(file_storage.filename or "")
    if not original_name:
        raise ValueError("Invalid filename.")

    if not is_allowed_upload(original_name, resource_type):
        raise ValueError(f"File type not allowed for {resource_type} uploads.")

    ext = get_file_extension(original_name)
    stored_name = f"{uuid.uuid4().hex}.{ext}"

    target_dir = TYPE_DIRS[resource_type]
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / stored_name

    # Prevent any possibility of path traversal - destination must stay inside target_dir
    if target_dir.resolve() not in destination.resolve().parents:
        raise ValueError("Invalid upload path.")

    file_storage.save(destination)

    mime_type = file_storage.mimetype or mimetypes.guess_type(original_name)[0] or "application/octet-stream"

    # Use the actual directory name (e.g. "images", plural) so the relative
    # path always matches where the file was really saved.
    relative_path = f"{target_dir.name}/{stored_name}"
    return relative_path, original_name, mime_type


def resolve_stored_path(relative_path):
    """Turn a 'image/xxxx.png'-style relative path back into an absolute Path,
    guaranteed to stay inside the uploads directory."""
    from database import UPLOADS_DIR

    candidate = (UPLOADS_DIR / relative_path).resolve()
    if UPLOADS_DIR.resolve() not in candidate.parents:
        raise ValueError("Invalid stored path.")
    return candidate


def generate_qr_code(short_code, data_url):
    """Generate a QR PNG encoding `data_url` and save it as qr_codes/<short_code>.png."""
    QR_DIR.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(data_url)
    qr_path = QR_DIR / f"{short_code}.png"
    img.save(qr_path)
    return f"{short_code}.png"
