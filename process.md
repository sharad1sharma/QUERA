# Development Process

## 1. Existing project analysis

Before writing anything, the existing repository was inspected in full:

- **Backend**: `backend/app.py` (Flask app + static frontend serving + `/<short_code>` redirect),
  `backend/database.py` (SQLite connection + `urls` table), `backend/models.py`
  (CRUD for `urls`), `backend/routes.py` (Blueprint `api` with `/shorten`,
  `/history`, `/urls/<id>`, `/stats`), `backend/utils.py` (short code generator,
  URL validation).
- **Frontend**: a single page (`frontend/index.html`) with a hero shorten form,
  a history table, a stats grid, and an about section, driven by
  `frontend/js/script.js` and styled by `frontend/css/style.css`.
- **Database**: one table, `urls` (id, original_url, short_code, created_at,
  updated_at, click_count), exported to `urls.csv` after every write.
- **Deployment**: `vercel.json` + `api/index.py` expose the Flask app as a
  Vercel serverless function.

This existing shortening engine (unique code generation, redirect, history,
click counting, search, CSV export) was kept and extended rather than
replaced.

## 2. Architecture decisions

- Keep the existing `urls` table untouched (nothing reads/writes it as the
  source of truth anymore, but it is never dropped).
- Add a unified `resources` table that represents **URL, image, video, and
  file** the same way, with `owner_id` and `visibility` columns. This avoids
  four near-duplicate tables and lets ownership/visibility logic live in one
  place.
- Add `users` (auth) and `qr_codes` (one row per resource, generated PNGs on
  disk under `qr_codes/`) tables.
- One-time migration: on first boot, any existing rows in `urls` are copied
  into `resources` as `resource_type='url'`, `owner_id=NULL`, `visibility='public'`,
  so pre-existing shortened links keep working exactly as before.

## 3. Authentication implementation

- `backend/auth.py`: registration (username/email/password validation,
  `werkzeug.security.generate_password_hash`), login (`check_password_hash`),
  logout, `/me`, plus `login_required` / `admin_required` decorators and a
  `get_current_user()` helper backed by Flask's signed session cookie
  (`session['user_id']`, `session['role']`).
- No new auth dependency was introduced — Werkzeug ships with Flask already.

## 4. Database changes

See `backend/database.py`: `init_db()` now creates `users`, `resources`,
`qr_codes`, and a small `meta` table (used only to record that the one-time
legacy migration ran), in addition to the original `urls` table.

## 5. User role implementation

`users.role` is either `'user'` or `'admin'`. Admin bootstrap is optional and
env-driven (`ADMIN_EMAIL` / `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`);
existing admins can also promote/demote other users from the Admin Dashboard.

## 6. Resource ownership

Every row in `resources` has `owner_id` (nullable only for migrated legacy
links). `routes.py` and `admin.py` check `is_owner_or_admin()` before allowing
view/edit/delete of any non-public action.

## 7. URL shortening (extended)

`POST /api/shorten` still exists at the same path/shape the old frontend
used, but now requires login and stores into `resources` instead of `urls`,
so it participates in ownership/visibility like every other resource type.

## 8. Image upload

`POST /api/resources/image` — validates extension against an allow-list
(`png, jpg, jpeg, gif, webp, bmp, svg`), sanitizes the filename with
`werkzeug.utils.secure_filename`, stores it under a random UUID name inside
`uploads/images/`, and creates a `resources` row of type `image`.

## 9. Video upload

Same flow as images, allow-list `mp4, webm, ogg, mov, mkv`, stored under
`uploads/videos/`. Delivery uses Flask's `send_file(..., conditional=True)`
so HTTP Range requests work and the browser can stream/seek.

## 10. File upload

Same flow, allow-list `pdf, doc, docx, xls, xlsx, ppt, pptx, txt, csv, zip, rtf`,
stored under `uploads/files/`. Served inline for browser-friendly types
(PDF, text, images) and as an attachment (forced download) otherwise.

## 11. QR generation

`utils.generate_qr_code(short_code, target_url)` uses the `qrcode` package to
encode the **application's own short URL** (e.g. `https://domain/s/A8xK2`),
never the raw file or destination URL directly. The PNG is saved to
`qr_codes/<short_code>.png` and a `qr_codes` DB row links it to the resource.
QR images are served through `GET /api/qr/<short_code>`, which re-runs the
same visibility/ownership check as the resource itself — a private
resource's QR image cannot be fetched by anyone but its owner or an admin.

## 12. Public/private access control

`resources.visibility` is `'public'` or `'private'`. `redirect_short_url()`
(shared by `/s/<code>` and the legacy `/<code>`) and every resource-reading
API endpoint check this before doing anything else. Private + not
owner/admin → `403`. Non-existent code → `404`.

## 13. User dashboard

`frontend/dashboard.html` + `frontend/js/dashboard.js`: tabs to create a URL
or upload an image/video/file with a visibility selector, and a table of the
user's own resources with inline visibility toggle, QR thumbnail, edit (URL
destination only) and delete.

## 14. Admin dashboard

`frontend/admin.html` + `frontend/js/admin.js`: global stat cards, four
Chart.js charts (creation timeline, resources by type, public vs private,
resources per user), a users table (role change, delete), and an all-resources
table (edit/delete/change visibility for anything, any owner).

## 15. Analytics

`backend/models.py` adds aggregate queries (`get_resource_stats`,
`get_resources_created_per_day`, `get_resource_counts_by_user`), exposed via
`backend/admin.py` at `/api/admin/stats`, `/stats/timeline`, `/stats/by-user`.
These are admin-only; the public `/api/stats` endpoint only ever returns the
current viewer's own numbers so it can't be used to enumerate site-wide data.

## 16. Security

- `werkzeug.utils.secure_filename` + a randomly generated stored filename
  (UUID) for every upload — the original filename is kept only as a display
  label (`original_name`), never used as a path.
- Every stored path is re-resolved and checked to stay inside `uploads/`
  before being served, closing off path traversal even if a stored value
  were ever tampered with.
- Extension allow-lists per resource type; `Flask`'s `MAX_CONTENT_LENGTH`
  enforces a request size cap (`413` on oversized uploads).
- Raw filesystem paths are stripped from every JSON response
  (`resource_to_public_dict` pops `stored_file_path`).
- Session cookies are `HttpOnly` + `SameSite=Lax`; `SECRET_KEY` is read from
  the environment, never hard-coded.

## 17. Testing

Manual + scripted checks were run against the Flask test client, covering:
registration/login/logout, creating a public URL and confirming redirect via
both `/s/<code>` and the legacy `/<code>`, uploading an image/video/file and
confirming inline display / range-enabled streaming / download respectively,
rejecting a disallowed extension, creating a private resource and confirming
`403` for an anonymous visitor and for a different logged-in user while the
owner and an admin can still access it, confirming a non-owner gets `403` on
delete, confirming non-admins get `403` on `/api/admin/*`, and confirming the
one-time legacy-`urls`-to-`resources` migration copies existing rows
correctly (owner NULL, visibility public, click counts preserved). See
`README.md`/`setup.md` for the manual step-by-step version of the same
checklist.

## 18. Deployment considerations

- Local/traditional hosting: works as-is, uploads and QR codes persist on disk.
- Vercel (serverless): `api/index.py` + `vercel.json` still work for the API
  and redirects, but `/tmp` storage is ephemeral — uploaded media and QR PNGs
  will not survive between invocations/deployments there. For production use
  with real file uploads, use a host with persistent disk or add object
  storage (S3-compatible), noted under "Future Improvements" in `README.md`.

## Request flow (end to end)

```
User
 |
 v
Login (POST /api/auth/login) -> session cookie set
 |
 v
Dashboard (GET /dashboard.html)
 |
 v
Create Resource (POST /api/shorten or /api/resources/<type>)
 |
 v
Short code generated, resources row created
 |
 v
QR generated (qrcode -> qr_codes/<code>.png), qr_codes row created
 |
 v
Public/Private chosen at creation, changeable later (PUT /api/urls/<id>)
 |
 v
Someone opens /s/<code> or scans the QR
 |
 v
Backend: find resource -> check visibility -> check session/ownership if private
 |
 v
Resource returned: url -> redirect | image -> inline | video -> stream | file -> view/download
 |
 v
click_count incremented
```

## Phase: AI features (added after the original upgrade)

The rest of the upgraded platform (auth, ownership, resources, QR, admin
analytics) was already complete before this phase. The only gap against the
original spec was Section 21 (AI features) — no AI code, DB columns, or UI
existed anywhere in the codebase. This phase added it as a self-contained
layer without touching anything that already worked:

1. **Inspection** — confirmed via full read-through and `grep` that no
   AI-related code, routes, or DB fields existed yet.
2. **Database** — added four nullable columns to `resources`
   (`ai_risk_level`, `ai_risk_reason`, `ai_privacy_suggestion`,
   `ai_privacy_reason`) via an additive `ALTER TABLE ... ADD COLUMN`
   migration in `database.py` that runs safely on every startup and never
   touches existing data.
3. **Backend** — new `backend/ai.py` blueprint (`/api/ai/*`):
   - Usage Assistant: built-in FAQ matcher, with an optional external-AI
     hook (`AI_API_KEY` + `anthropic` package) that silently falls back to
     the FAQ matcher on any failure.
   - Security analysis: transparent heuristic scoring for URL resources
     (raw IPs, punycode, phishing keywords, non-HTTPS, known shorteners,
     length), run automatically whenever a URL is shortened.
   - Privacy recommendation: filename-based heuristic suggesting Private
     for likely-sensitive uploads, run automatically on upload. Never
     changes the visibility the user actually chose.
   - Analytics insights: plain-language summaries built only from each
     user's/the site's real stored stats — no invented numbers.
   - Resource analysis: honest metadata-only notes, with the vision-model
     limitation documented rather than faked.
   Both auto-run hooks (`_run_ai_url_risk`, `_run_ai_privacy_suggestion` in
   `routes.py`) are wrapped in `try/except` so a failure in the AI layer can
   never block resource creation - the app degrades gracefully if the AI
   layer misbehaves or an external provider is unreachable.
4. **Frontend** — AI Assistant chat box + 🟢/🟡/🔴 risk and 💡 privacy
   badges on the Dashboard; an AI risk-distribution chart + AI Insights
   panel on the Admin Dashboard. Existing table columns, forms, and styling
   conventions were reused rather than replaced.
5. **Security hygiene found during inspection** — `backend/seed_admin.py`
   had a real-looking hardcoded email/password. Rewritten to read
   `ADMIN_EMAIL`/`ADMIN_USERNAME`/`ADMIN_PASSWORD` from the environment only,
   and to refuse to run (exit 1, no account created) if they're missing —
   consistent with the rest of the app's "never hardcode credentials" rule
   and with the project's own requirement not to invent admin credentials.
6. **Testing** — ran the actual Flask server locally end-to-end (not just
   read the code) and exercised: existing auth/ownership/visibility
   regressions, automatic risk-flagging of a suspicious URL vs. a benign
   one, automatic "suggests private" on a sensitively-named upload, the
   assistant/insights/risk-distribution endpoints, and role-based access to
   the new admin-only AI endpoints. All passed against a fresh database.
   See the Change Report delivered alongside this project for the full
   pass/fail list and known limitations (e.g. browser QR-camera scanning
   and the optional external-AI path are not testable in this environment).
