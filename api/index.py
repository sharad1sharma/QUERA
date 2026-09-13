import os
import sys
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import app
from database import init_db

# Initialize database schema on startup
init_db()

# Expose WSGI handler for Vercel
if __name__ == "__main__":
    app.run()
