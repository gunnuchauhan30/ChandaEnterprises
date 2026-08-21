# Chanda Enterprises Store System — Changes Implemented

Sab changes real DB schema + working API + wired frontend ke saath ho gaye hain.
Koi dummy/placeholder data nahi — jo bhi list khaali hogi (Critical Spares,
Reconciliations) wo aapke real usage se hi bharegi.

## 1. Dashboard
- "Total Stock Value" box **remove** kar diya
- **Low Stock Items** aur **High Stock Items** — dono boxes ab side-by-side
  simple counts dikhate hain (backend `/api/v1/dashboard` already ye counts
  return kar raha tha, sirf frontend display fix karna tha)

## 2. Branding + Theme
- Sidebar mein "CE" text ki jagah ab **circular red "e" logo** (inline SVG,
  koi external image dependency nahi)
- Poora UI dark-purple se **white background + red/orange (Chanda brand
  colors)** theme mein convert — sidebar, KPI cards, buttons, headings,
  login/signup/forgot-password/reset-password pages sab

## 3. Critical Spares List (naya page — `/critical-spares`)
- Standalone list, Materials se linked (live stock data ke liye)
- Har spare ka apna machine name, priority (critical/high/medium), aur
  threshold quantity — threshold se niche jaate hi "Attention Needed" badge
- Add / Edit / Delete — store_manager aur purchase role kar sakte hain

## 4. Route Card (naya page — `/route-card`)
- Aapke Excel format ke exact columns: Sr No, Date, Part Name, Issue Qty,
  Job-Card No, Lot No, Issue By, Department, Remark, Shift, Received
- Ye **existing Issues data ka hi formatted view/report** hai (Option A jo
  finalize hua tha) — koi naya duplicate data-entry nahi
- Date range, department, job-card, shift filters + Excel export button

## 5. Inventory → Physical Stock Reconciliation (naya tab)
- Inventory page ke andar naya "Physical Reconciliation" tab
- Store Manager: material select karke physical count enter karta hai →
  system automatically current stock (system_qty) se compare karke
  difference nikalta hai
- Status **"pending"** rehta hai jab tak **Admin approve/reject** na kare
- Approve hone par hi stock update hota hai — aur ye aapke existing
  stock-ledger ADJUSTMENT trigger system ke through hi hota hai (koi
  parallel/duplicate stock-update code path nahi banaya, taaki data
  consistency bani rahe)

## 6. Daily Automated Email (12:00 PM)
- APScheduler background job — har din 12:00 PM (Asia/Kolkata timezone,
  `.env` mein `SCHEDULER_TIMEZONE` se configurable) admin ko
  **Inventory Summary** email jaati hai
- Content: total stock value, total materials, low/high stock count,
  aaj ke purchases/issues, pending employee requests, pending QC,
  **pending reconciliations**, aur **critical spares jo threshold se neeche
  hain** — sab real data se
- `ADMIN_ALERT_EMAILS` (`.env`) mein jo bhi emails hain unko jaayegi

---

## Setup / Run Instructions

1. `chanda_backend/schema.sql` already updated hai naye tables ke saath
   (`critical_spares`, `stock_reconciliations`) — fresh DB setup automatically
   in tables ke saath aayega (docker-compose init scripts already ise use
   karte hain)
2. Agar koi **purani/existing database** already chal rahi hai (fresh setup
   nahi), toh sirf naye tables add karne ke liye:
   ```
   cd chanda_backend
   alembic upgrade head
   ```
3. `requirements.txt` mein `apscheduler` add ho gaya hai — dobara install karo:
   ```
   pip install -r requirements.txt
   ```
4. Baaki sab kuch (`docker-compose up`, `.env` values) pehle jaisa hi hai —
   koi naya env variable required nahi (SCHEDULER_TIMEZONE optional hai,
   default Asia/Kolkata already set hai)

## Files Changed / Added (quick reference)
```
Backend:
  schema.sql                                          (edited - new tables)
  alembic/versions/0002_critical_spares_and_...py      (new)
  app/models.py                                        (edited - new models)
  app/schemas/misc.py                                  (edited - new schemas)
  app/api/v1/critical_spares.py                        (new)
  app/api/v1/inventory.py                              (edited - reconciliation endpoints)
  app/api/v1/issues.py                                 (edited - route-card endpoints)
  app/api/v1/router.py                                 (edited - register router)
  app/services/email_service.py                        (edited - summary email)
  app/services/scheduled_jobs.py                       (new - 12PM scheduler)
  app/core/config.py                                   (edited - timezone setting)
  app/main.py                                           (edited - start scheduler)
  requirements.txt                                     (edited - apscheduler)

Frontend:
  static/css/main.css                                  (edited - white/red theme)
  templates/base.html                                  (edited - logo, nav links)
  templates/pages/dashboard.html                       (edited - KPI boxes)
  templates/pages/critical-spares.html                 (new)
  templates/pages/route-card.html                      (new)
  templates/pages/inventory.html                       (edited - reconciliation tab)
  templates/pages/login.html, signup.html,
    forgot-password.html, reset-password.html          (edited - theme colors)
  static/js/api.js                                     (edited - new API methods)
  app/main.py                                           (edited - new Flask routes)
```
