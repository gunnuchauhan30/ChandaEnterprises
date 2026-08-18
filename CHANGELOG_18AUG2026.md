# Changelog — 18-Aug-2026 Update

Status: ✅ All 7 requested points addressed and tested (unit tests + import/smoke
tests). **Not tested against a live Postgres database** — that requires your
real environment (sandbox here has no Postgres). Run `full_system_test.py`
after deploying, as the original README recommends.

---

## 1. Date column on Requests page
**File:** `chanda_frontend/templates/pages/requests.html`
Added a `Date` column (from `created_at`) to the Material Requests table,
right after Request No. Uses the same IST-corrected `formatDateTime()` (see #2).

## 2. Wrong time on Backorder Queue (showed 04:16 am instead of real IST time)
**File:** `chanda_frontend/static/js/api.js`
Root cause: backend sends naive UTC timestamps (no `Z`/offset). The old
`formatDate`/`formatDateTime` did `new Date(dateString)`, which JS parses as
**local** time when there's no offset — so the raw UTC clock value was shown
as if it were already IST, off by 5:30.
Fix: both functions now explicitly treat the string as UTC if it has no
offset, then render with `timeZone: 'Asia/Kolkata'`. Verified with a script:
`2026-08-17T04:16:00` (naive UTC) now correctly renders as
`17 Aug 2026, 09:46 am`. This fixes the time everywhere it's used
(Backorder Queue "Waiting Since", and the new Requests "Date" column, and
anywhere else `formatDate`/`formatDateTime` is called), regardless of the
viewer's own browser/OS timezone.

## 3. Store access + editable Min/Max + Critical Spare auto-link
- **Min/Max were already editable** on the material creation form; they were
  **not** editable in the Material Master list's inline edit — fixed.
  **File:** `chanda_frontend/templates/pages/materials.html` — inline row
  edit now has editable Min/Max fields, saved via the existing
  `PATCH /materials/{code}` endpoint (already supported both fields, no
  backend change needed).
- **Critical Spare checkbox added to Material Master** (both the inline
  list edit and the "New Material" form). Ticking it calls the existing
  `POST /critical-spares` API (threshold = Min Qty); unticking calls
  `DELETE /critical-spares/{id}`. It's genuinely wired both ways: the
  Critical Spares page and Material Master list both read the same table,
  so it shows up automatically on the Critical Spares page the moment you
  tick it — no separate step.
  **Files:** `materials.html`, `material-form.html` (no backend/DB change —
  used the existing `critical_spares` API that was already built).
- **Store Manager permission review:** confirmed against every
  `require_roles(...)` in `app/api/v1/*.py`. Store Manager already has full
  access to: Materials (create/edit/delete/Excel import-export), Suppliers,
  Purchases/GRN + QC, Issues, Employee Requests, Returns, Inventory
  (batches/ledger/quick-adjust), Critical Spares, Alerts. **Intentionally
  left admin-only** (did not open these up — flagging so you can tell me if
  you want them changed):
  - Creating/deleting user accounts — matches your point 5 requirement.
  - Final reconciliation approval — you'd previously confirmed this should
    stay admin-only.
  - Activity/login audit trail (`/history/*`) — kept as an independent
    admin-side oversight log.

## 4 & 6. Material name on Request page and Issue page
Already implemented in the codebase you gave me (`material_name` is
returned by both `EmployeeRequestOut` and `IssueOut`, and both list pages
already render `CODE — Name`). No code change was needed here — if your
**live site** still shows bare codes like `RM-0012`, that's because the live
Railway deployment is running an older build. This point resolves itself
once you deploy this package.

## 5. Manage Users page / admin-only account creation
Already implemented in the codebase you gave me — `/signup` redirects to the
admin-only `/admin/users` (Manage Users) page, and the backend blocks public
self-signup as `admin`. Same as above: this is a deploy-freshness issue, not
a missing feature. Resolves once you deploy this package.

## 7. Purchase/GRN "Network error" — hardcoded wrong backend URL
**Files:** `chanda_frontend/static/js/api.js`, `chanda_frontend/app/main.py`
- `api.js`: removed the hardcoded fallback to a **different** Railway
  deployment's URL (`chandaenterprises-production...`). It now falls back to
  a safe same-origin `/api/v1` path and logs a clear console error telling
  you to fix `BACKEND_URL`, instead of silently misrouting every API call to
  someone else's backend.
- `main.py`: `BACKEND_URL` env read now also treats an **empty string**
  (not just a missing key) as unset, so it reliably falls back to
  `http://localhost:8000` instead of injecting a blank value into the page.
- Verified: rendering `/login` with a real `BACKEND_URL` set correctly
  injects `window.RAILWAY_BACKEND_URL = ".../api/v1"`; with an empty env var
  it now correctly falls back instead of breaking.
- **You still need to double-check** that your Railway **frontend** service
  actually has `BACKEND_URL` set to your real backend's URL
  (`steadfast-commitment-production-e165.up.railway.app` or wherever your
  backend actually lives) — this code fix stops the *silent wrong fallback*,
  but the right fix is still setting that env var correctly on Railway.

---

## Testing performed (in this sandbox, no live Postgres available)
- ✅ `pytest tests/test_security.py` — 7/7 passed (password hashing, JWT).
- ✅ `python -m py_compile` on every backend `.py` file — no syntax errors.
- ✅ `app.main` (FastAPI) imports cleanly, 70 routes registered.
- ✅ `app.main` (Flask frontend) imports cleanly, `/login` returns 200.
- ✅ `node --check` on `api.js` and every edited inline `<script>` block —
  no syntax errors.
- ✅ Jinja2 template parse check on every edited `.html` file — no syntax
  errors.
- ✅ Scripted verification of the IST timezone fix and the URL-fallback fix
  (see above — both behave correctly across edge cases).
- ⚠️ **Not run:** `full_system_test.py` (needs a live server + real
  Postgres with schema.sql loaded) and Docker build. Please run
  `full_system_test.py` yourself after deploying, same as the original
  README asks, before treating this as fully verified end-to-end.

## Files changed (5 total)
```
chanda_frontend/static/js/api.js                    (timezone fix + URL fallback fix)
chanda_frontend/app/main.py                          (BACKEND_URL empty-string fix)
chanda_frontend/templates/pages/requests.html        (Date column)
chanda_frontend/templates/pages/materials.html       (editable Min/Max + Critical checkbox)
chanda_frontend/templates/pages/material-form.html   (Critical checkbox on create)
```
No database schema changes, no migrations needed — fully backward compatible.
