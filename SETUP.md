# Chanda Enterprises — Store Management System
### Fixed & completed build — run instructions

## Run it (one command)

```bash
docker compose up --build
```

- Frontend: http://localhost:5000
- Backend API docs: http://localhost:8000/docs

First run will initialize Postgres from `chanda_backend/schema.sql` +
`chanda_backend/data_import.sql`. To create an admin login:

```bash
docker compose exec backend python seed_admin.py
```
(adjust if your seed script needs args — check `chanda_backend/README.md`)

## ⚠️ Do this before/after presenting

`chanda_backend/.env` still has a **real Gmail address + real Gmail App
Password** committed in it (used for the low/high-stock email alerts).
This was already leaking in the original zip. It hasn't been touched here
so your demo's email feature keeps working, but:

1. Right after your presentation, go to your Google Account → Security →
   App Passwords, and **revoke** `fzym uoud osog kbdb`.
2. Generate a new one if you still want email alerts, and put it only in
   `.env` — never commit `.env` (a `.gitignore` is now included that
   excludes it).

## What was actually broken, and what changed

**Root cause of "pages are blank":** the frontend's `static/js/api.js` was
calling URLs and expecting response shapes that didn't match the real
FastAPI backend (e.g. `/dashboard/kpis` doesn't exist — the real route is
just `/dashboard`; `/materials` returns a plain JSON array, but every page
was reading `response.items`). On top of that, 9 of the 14 pages
(Suppliers, Purchases, Requests, Issues, Returns, Inventory, Alerts,
Reports, Settings) were literally unbuilt "Coming soon" placeholders, and
8 templates referenced by routes (`material-form.html`,
`material-detail.html`, `supplier-form.html`, `purchase-form.html`,
`purchase-detail.html`, `request-form.html`, `issue-form.html`,
`return-form.html`) didn't exist at all — visiting them 500'd.

Fixed:
- Rewrote `api.js` to match the backend's real routes exactly, and added
  one normalization point so every list page gets a consistent
  `{items, total}` shape regardless of the backend returning a plain array.
- Built all 9 missing pages for real, wired to the real endpoints (list +
  create where applicable): Suppliers, Purchases/GRN (with QC pass/fail),
  Requests (approve/reject), Issues (consumption update), Returns,
  Inventory (summary/valuation/aging), Alerts (resolve), Reports (all 6
  report types + Excel/CSV export), Settings.
- Created the 8 missing templates.
- Fixed `dashboard.html` to call the single real `/dashboard` endpoint
  instead of three endpoints that don't exist.
- **Security fix:** `/auth/signup` let anyone self-assign the `admin` role.
  Signup is now restricted to non-admin roles; admins are created only via
  `seed_admin.py` or by an existing admin.
- **CORS fix:** the frontend's own port (5000) wasn't in `CORS_ORIGINS`,
  which silently blocked browser calls to the API.
- Fixed the password-reset flow end-to-end: the emailed link pointed at a
  hardcoded placeholder domain and the frontend had no `/reset-password`
  route at all (404). Both fixed, and a real reset-password page was added.
- Added `.gitignore` (`.env`, `venv/`, `logs/`, `uploads/`) so secrets and
  junk never get committed going forward.

## Known limitation (by design, not a bug)

List pages show "Page N" with Previous/Next instead of a total page count.
The backend's list endpoints don't return a total row count (only the
current page), so a true "Page 3 of 12" isn't available without changing
backend schemas — for a demo this is a reasonable trade-off. Flag it if
asked; it's an easy backend enhancement later (add a `COUNT(*)` + wrap
responses in `{items, total}` server-side).
