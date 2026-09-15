# QUERA — with Auth, QR Codes & Media Sharing

👨‍💻 About Me: Hi, I'm SHARAD SHARMA — a Computer Science Engineering student, Python Developer, and aspiring Backend & AI Engineer. ⚡

A full-stack link/media sharing platform built with:

- Python, Flask
- SQLite
- HTML, CSS, JavaScript (vanilla)
- [qrcode](https://pypi.org/project/qrcode/) + Pillow for QR generation
- Chart.js (CDN) for the admin analytics charts

This started as a simple URL shortener and has been upgraded in place to also
support **authentication, QR codes, image/video/file sharing, public/private
access control, ownership, an admin dashboard, and analytics** — without
throwing away the original shortening engine.

## Problem Statement

Sharing a long link, an image, a video, or a document usually means sending a
messy URL or a whole file. This app gives every one of those a short,
memorable link **and** a scannable QR code, while letting the owner decide
who can see it — and giving admins full oversight of the platform.

## Features

### Original URL shortener (preserved)
- Shorten long URLs into short codes
- Redirect short URLs to their destination
- URL history, search, click counter, edit, delete, clear history
- Legacy links created before this upgrade keep working unchanged

### New: Authentication
- Register / Login / Logout with hashed passwords (Werkzeug `pbkdf2`)
- Session-based auth (signed, httponly cookies)
- Two roles: `user` and `admin`

### New: Multi-content shortening + QR codes
- URL → short link + QR code
- Image upload → short link + QR code (viewable inline)
- Video upload → short link + QR code (streams/plays in-browser, supports seeking)
- File upload → short link + QR code (views or downloads depending on type)
- Every QR code encodes the app's own short URL (`/s/<code>`), never the raw file

### New: Public / Private access control
- Owner chooses Public or Private per resource, changeable any time
- Enforced **server-side** on every access route and API call — not just hidden in the UI
- Public: anyone with the link/QR, no login needed
- Private: owner + admin only; everyone else gets `403 Forbidden`

### New: Ownership
- Every resource belongs to its creator (`owner_id`)
- Users can only edit/delete/view their own resources
- Admins can manage anything

### New: User Dashboard (`/dashboard.html`)
- Create URL / Image / Video / File, pick visibility
- Table of all your resources: type, name/destination, short URL, visibility toggle, clicks, QR, edit/delete

### New: Admin Dashboard (`/admin.html`)
- Manage all users (promote/demote role, delete)
- Manage all resources (edit URL destinations, change visibility, delete)
- Site-wide analytics: totals by type, public vs private, clicks, resources created over time, resources per user (Chart.js)

### Security
- Passwords hashed, never stored in plaintext
- Server-side ownership + visibility checks on every route (not just frontend hiding)
- Secure filenames + random stored filenames (prevents path traversal & collisions)
- Extension/MIME allow-lists per resource type
- Max upload size enforced (`MAX_UPLOAD_MB`, default 50 MB)
- Uploaded files are never executed; raw filesystem paths are never exposed to clients
- Secrets (session key, admin bootstrap credentials) come from environment variables, never hard-coded

### New: AI features (`backend/ai.py`)
All AI output is clearly labeled as AI-assisted and never overrides a user's
or admin's own Public/Private choice. Nothing is fabricated: analytics
insights are built only from real stored data.

- **AI Usage Assistant** — answers "how do I…" questions about the platform
  (Dashboard: 🤖 AI Assistant box). Uses a built-in FAQ matcher by default;
  if `AI_API_KEY` is set (and the optional `anthropic` package installed),
  it answers with a real model instead. Falls back to the FAQ matcher
  automatically on any error.
- **AI Security Analysis** — heuristic risk scan on every URL resource, run
  automatically on creation (raw IPs, punycode, phishing-style keywords,
  non-HTTPS, known shorteners, long URLs). Shown as a 🟢/🟡/🔴 risk badge
  in the Dashboard table and as a risk-distribution chart on the Admin
  Dashboard. Explicitly labeled a heuristic, not a safety guarantee.
- **AI Privacy Recommendation** — suggests Private for uploads whose
  filename suggests sensitive content (e.g. `passport_scan.pdf`). Shown as
  a 💡 suggestion badge; the user still makes the final choice.
- **AI Analytics Insights** — plain-language summaries generated from a
  user's own resource stats (Dashboard) or site-wide stats (Admin
  Dashboard) — access counts, most-used resource, unused resources, public
  vs. private split, count of high-risk URLs.
- **AI Resource Analysis** — metadata-only classification (type, MIME,
  filename). Deep content classification (recognizing what's actually in an
  image/video) would require an external vision API and is documented here
  as a known limitation rather than faked.

## Technology Stack

| Layer      | Technology                     |
|------------|---------------------------------|
| Backend    | Python, Flask, Flask-Blueprints |
| Database   | SQLite                          |
| Auth       | Flask sessions + Werkzeug password hashing |
| QR codes   | `qrcode` + Pillow                |
| Frontend   | HTML, CSS, vanilla JavaScript   |
| Charts     | Chart.js (via CDN)              |
| Deployment | Vercel-compatible (`api/index.py`, `vercel.json`) |

## Architecture

```
Browser (frontend/*.html + js/*)
        |  fetch() with credentials: "include"
        v
Flask app (backend/app.py)
        |
        +-- /api/auth/*    -> auth.py      (register, login, logout, me)
        +-- /api/*         -> routes.py    (create/list/edit/delete resources, /api/qr/<code>)
        +-- /api/admin/*   -> admin.py     (users, all resources, analytics)
        +-- /api/ai/*      -> ai.py        (assistant, risk analysis, privacy suggestion, insights)
        +-- /s/<code>, /<code> -> routes.redirect_short_url()
                                     |
                                     +-- visibility + ownership check
                                     +-- url        -> 302 redirect
                                     +-- image/video/file -> send_file() (range-enabled)
                                     +-- click_count incremented
        v
database.py (SQLite: users, resources [+ ai_risk_level, ai_risk_reason,
             ai_privacy_suggestion, ai_privacy_reason], qr_codes, legacy urls table)
```

## Project Structure

```
URL_SHORTERNED_-main/
├── api/
│   └── index.py            # Vercel serverless entrypoint
├── backend/
│   ├── app.py               # Flask app, blueprints, sessions, page routes
│   ├── auth.py               # Register/login/logout, decorators
│   ├── admin.py               # Admin-only routes (users, resources, analytics)
│   ├── ai.py                   # AI assistant, risk analysis, privacy suggestions, insights
│   ├── routes.py               # Resource creation/list/edit/delete, /s/<code>, QR delivery
│   ├── models.py                 # All SQL access (users, resources, qr_codes)
│   ├── database.py                 # Connection, schema, legacy-data migration
│   ├── utils.py                     # Short codes, upload validation, QR generation
│   └── database/urls.csv             # Legacy CSV export (auto-regenerated)
├── frontend/
│   ├── index.html            # Public home page (URL shortener + history)
│   ├── login.html, register.html
│   ├── dashboard.html          # User dashboard (create/manage all resource types)
│   ├── admin.html                # Admin dashboard (users, resources, charts)
│   ├── css/style.css
│   └── js/
│       ├── auth-common.js      # Shared: API base URL, nav, login/admin guards
│       ├── script.js             # Home page logic
│       ├── dashboard.js            # Dashboard logic
│       └── admin.js                  # Admin dashboard logic
├── uploads/{images,videos,files}/   # Uploaded media (gitignored)
├── qr_codes/                         # Generated QR PNGs (gitignored)
├── requirements.txt / backend/requirements.txt
├── .env.example
├── setup.md
└── process.md
```

## Installation & Running Locally

See **[setup.md](setup.md)** for full, step-by-step (Windows-first) instructions.

Quick start:

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy ..\.env.example ..\.env
:: then edit ..\.env and fill in SECRET_KEY (and optionally ADMIN_*)
python app.py
```

Open `http://localhost:5000`.

## Usage

1. Register an account at `/register.html`, then log in.
2. Go to `/dashboard.html` to create a shortened URL or upload an image/video/file.
3. Pick **Public** or **Private** visibility — you can change it later.
4. Share the short link (`/s/<code>`) or the generated QR code.
5. Admins get an extra **Admin** link in the nav leading to `/admin.html`.

## API Overview

| Method | Route                          | Auth        | Purpose |
|--------|---------------------------------|-------------|---------|
| POST   | `/api/auth/register`            | –           | Create account |
| POST   | `/api/auth/login`               | –           | Log in |
| POST   | `/api/auth/logout`               | –           | Log out |
| GET    | `/api/auth/me`                   | –           | Current user (or null) |
| POST   | `/api/shorten`                    | user        | Create a URL short link |
| POST   | `/api/resources/<image\|video\|file>` | user   | Upload media, get short link + QR |
| GET    | `/api/history?search=`              | user        | List your own resources |
| GET/PUT/DELETE | `/api/urls/<id>`             | owner/admin | View/edit/delete one resource |
| DELETE | `/api/history`                        | user        | Clear your own resources |
| GET    | `/api/stats`                            | –           | Your own resource counts |
| GET    | `/api/qr/<short_code>`                    | visibility-checked | QR PNG |
| GET    | `/s/<short_code>`, `/<short_code>`          | visibility-checked | Access/redirect the resource |
| GET/DELETE/PUT | `/api/admin/users*`                 | admin       | Manage users |
| GET/PUT/DELETE | `/api/admin/resources*`             | admin       | Manage all resources |
| GET    | `/api/admin/stats`, `/stats/timeline`, `/stats/by-user` | admin | Analytics |
| POST   | `/api/ai/assistant`                     | user        | Ask a "how do I…" question |
| GET    | `/api/ai/security/<resource_id>`        | owner/admin | URL risk analysis |
| GET    | `/api/ai/privacy/<resource_id>`         | owner/admin | Public/Private suggestion |
| GET    | `/api/ai/insights`                      | user        | Personal analytics insights |
| GET    | `/api/ai/admin/insights`, `/admin/risk-distribution` | admin | Site-wide AI insights |
| GET    | `/api/ai/resource-analysis/<resource_id>` | owner/admin | Metadata-only content notes |

## Screenshots

<img width="1512" height="810" alt="Screenshot 2026-09-12 223206" src="https://github.com/user-attachments/assets/7d968542-f498-42f7-a24a-1923c66e5c6f" />


## Future Improvements

- Object storage (S3/Cloud Storage) for uploads so files survive on serverless platforms like Vercel
- Rate limiting on auth and shortening endpoints
- Email verification / password reset flow
- Per-resource expiry dates
- Bulk import/export of links

## License

This project is provided as-is for learning purposes. Add a license of your choice (e.g. MIT) if you plan to distribute it.
