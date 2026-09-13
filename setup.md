# Setup Guide (Windows-first)

## 1. Requirements

- Python 3.10+ (project developed/tested with Python 3.12)
- pip
- A modern browser
- (Optional) Git, if cloning instead of downloading a zip

## 2. Install Python (Windows)

Download from https://www.python.org/downloads/ and, during install, check
**"Add python.exe to PATH"**. Verify:

```bash
python --version
```

## 3. Get the project

If you already have the folder, skip this. Otherwise:

```bash
git clone https://github.com/sharad1sharma/URL_SHORTERNED_.git
cd URL_SHORTERNED_
```

## 4. Create a virtual environment

From the project root:

```bash
cd backend
python -m venv venv
```

## 5. Activate the virtual environment

Windows (cmd/PowerShell):

```bash
venv\Scripts\activate
```

macOS/Linux:

```bash
source venv/bin/activate
```

## 6. Install dependencies

```bash
pip install -r requirements.txt
```

## 7. Configure `.env`

From the project root (one level above `backend/`):

```bash
copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux
```

Edit `.env` and set:

```
SECRET_KEY=<generate one, see below>
ADMIN_EMAIL=
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
MAX_UPLOAD_MB=50
```

Generate a strong `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

`ADMIN_EMAIL` / `ADMIN_USERNAME` / `ADMIN_PASSWORD` are optional: if set, the
app creates that admin account automatically the first time it starts (only
if no user with that email exists yet). Leave them blank if you'd rather
register normally and promote a user to admin later.

## 8. Database initialization / migration

No manual step needed — `init_db()` runs automatically on startup and:
- creates the `users`, `resources`, and `qr_codes` tables if missing
- migrates any rows from the old `urls` table into `resources` (one-time, safe to run repeatedly)
- adds the AI columns (`ai_risk_level`, `ai_risk_reason`, `ai_privacy_suggestion`,
  `ai_privacy_reason`) to `resources` if they aren't there yet (additive, safe to run repeatedly)

## 9. Create the admin account (if not using `.env` auto-create)

Register normally at `/register.html`, then either:
- set `ADMIN_EMAIL`/`ADMIN_PASSWORD` in `.env` to that email before first run, or
- have an existing admin promote you from the Admin Dashboard → Users table, or
- run `python seed_admin.py` from `backend/` with `ADMIN_EMAIL`/`ADMIN_USERNAME`/
  `ADMIN_PASSWORD` set in `.env` or the environment (the script refuses to run,
  with no account created, if they're missing — it never invents or hardcodes
  credentials).

## 10. Run the Flask application

From `backend/`:

```bash
python app.py
```

## 11. Open the application

Visit `http://localhost:5000`.

Do not open `frontend/index.html` directly as a file — always go through the
Flask server so shortened links, uploads and QR codes work correctly.

## 12. Test authentication

- Register a new account at `/register.html`
- Log out, log back in at `/login.html` with the same credentials
- Confirm the top nav shows your username and a Logout link

## 13. Test URL shortening

- On the Dashboard, create a URL with **Public** visibility
- Open the generated short link in a new incognito window (no login) — it should redirect

## 14. Test image upload

- Dashboard → Image tab → choose a `.jpg`/`.png` → Upload
- Open the short link — the image should display inline

## 15. Test video upload

- Dashboard → Video tab → choose a `.mp4` → Upload
- Open the short link — the video should play/stream in the browser

## 16. Test file upload

- Dashboard → File tab → choose a `.pdf`/`.docx`/etc. → Upload
- Open the short link — it should view (PDF) or download depending on type

## 17. Test QR scanning

- Every created resource shows a QR thumbnail in the dashboard table
- Scan it with a phone camera — it should open the same short link

## 18. Test public/private access

- Create a **Private** resource, log out, try opening its short link → expect "This resource is private" (403)
- Log in as a *different* user and try the same link → expect the same 403
- Log back in as the owner → access works

## 19. Test user ownership

- As User A, create a resource
- Log in as User B and try `DELETE /api/urls/<A's id>` (or click Delete on a URL you don't own via the API) → expect `403 Forbidden`

## 20. Test admin permissions

- Promote a user to `admin` (via `.env` bootstrap or another admin)
- Log in as that admin, open `/admin.html`
- Confirm you can see every user's resources, edit/delete any of them, and view the analytics charts

## 21. Test the AI Usage Assistant

- Dashboard → 🤖 AI Assistant box → ask e.g. "how do I make my file private?"
- Expect a concrete, app-specific answer (built-in FAQ by default, or a real
  model's answer if you set `AI_API_KEY` — see step 7)

## 22. Test AI security analysis

- Shorten an unusual URL, e.g. `http://192.168.1.1/login-verify-account`
- It should show a 🔴 high risk badge in the Dashboard table (hover for reasons)
- Shorten `https://example.com` — it should show 🟢 low risk

## 23. Test AI privacy recommendation

- Upload a file named something like `passport_scan.pdf` with **Public** visibility
- Expect a 💡 "suggests private" badge in the Dashboard AI column
- Confirm the resource stays Public until you change it yourself — the suggestion never overrides your choice

## 24. Test AI analytics insights

- Dashboard: scroll to confirm your own insights reflect resources you actually created
- Admin Dashboard: check the 🤖 AI Insights panel and the new AI risk distribution chart use real counts (compare against the stats cards above them)

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Admin dashboard charts stay blank | Check `CORS_ORIGINS` in `.env` matches how you're opening the page, or that Chart.js loaded (see browser console) |
| "Authentication required" on every API call | Cookies aren't being sent — make sure you're accessing the app through the Flask server (`http://localhost:5000`), not a separate static server without matching CORS |
| AI Assistant only gives generic/FAQ answers | Expected unless `AI_API_KEY` is set and the `anthropic` package is installed — this is a documented, optional upgrade, not a bug |
| Uploads/QR codes disappear after redeploying on Vercel | Expected — see "Notes on deploying to Vercel" below; use a host with persistent disk for production |

## Notes on deploying to Vercel

Vercel's filesystem is read-only/ephemeral outside `/tmp`, so uploaded images,
videos, files and generated QR codes will **not persist** between requests or
deployments there. For production use with real uploads, deploy to a host
with persistent disk (Render, Railway, a VM, etc.) or add object storage
(S3-compatible) — see **Future Improvements** in `README.md`.
