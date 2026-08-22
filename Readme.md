# 🏪 Chanda Enterprises — Store Management System

A full-stack **inventory, procurement, and operations platform** for managing materials, suppliers, purchase orders (GRN), critical spares, and real-time alerts — built for small to mid-size retail and distribution businesses.

![Chanda Store Dashboard](Images/Dashboardd.png)

---

## ✨ Features

### 📦 **Inventory Management**
- Real-time stock tracking across all materials
- Material categorization and coding
- Physical count vs. system count reconciliation
- Batch/lot tracking with expiry dates
- Automatic low-stock and overstock alerts

### 🛒 **Procurement & Purchase Orders**
- Create, approve, and track purchase orders (GRN)
- Multi-supplier quotation comparison
- Quality Control (QC) pass/fail workflows
- Invoice matching and payment tracking
- Purchase history and analytics

### 👥 **Supplier Management**
- Centralized supplier database
- Performance metrics (on-time delivery, quality, cost)
- Contact tracking and location mapping
- Payment terms and credit limits
- Supplier scorecards

### 🎯 **Critical Spares Management**
- Flag high-priority items for emergency allocation
- Min/max inventory thresholds
- Automatic reorder triggers
- Safety stock calculations
- Dual approval for critical items

### 📊 **Analytics & Reports**
- Material utilization trends
- Procurement cost analysis
- Supplier performance dashboard
- Inventory valuation (FIFO, LIFO, weighted average)
- Aging analysis (slow-moving inventory)
- Monthly/quarterly compliance reports
- Excel & CSV export for all reports

### 🔔 **Real-Time Alerts**
- Low stock warnings (email + SMS ready)
- Overstock notifications
- Purchase order delays
- Invoice discrepancies
- Quality issues and returns
- Daily inventory summary emails

### 👤 **Role-Based Access Control**
- `admin` — full system access
- `supervisor` — approve orders, manage suppliers
- `staff` — view inventory, create requests
- `viewer` — read-only access
- Audit trail for all sensitive operations

### 🔐 **Security & Compliance**
- JWT-based session authentication
- Password hashing with bcrypt
- HTTPS/SSL for all deployments
- Audit logs for every transaction
- Data encryption at rest and in transit
- GDPR-ready data export

---

## 🏗️ Architecture

![Architecture Diagram](Images/Architecture.png)

**Frontend** (Flask) → **Backend API** (FastAPI) → **PostgreSQL** (Database)

| Layer | Responsibility |
|---|---|
| **Frontend** | User interface, real-time notifications, theme toggle, responsive dashboard |
| **Backend** | REST API, business logic, email/SMS alerts, scheduled jobs, data validation |
| **Database** | Material, supplier, purchase order, inventory, alert data; audit logs |
| **Scheduler** | Daily email summaries, low-stock checks, expiry reminders |

---

## 📸 Screenshots

### Dashboard
![Dashboard](Images/Dashboardd.png)
Real-time KPIs: total materials, suppliers, purchase orders, utilization %, and alerts.

### Materials Management
![Materials](Images/Material-Master-list.png)
Browse all materials with filters, search, and quick actions.

### Material Detail
![Material Detail](Images/Add-New-Material.png)
View/edit material specs, pricing, suppliers, and stock levels.

### Suppliers
![Suppliers](Images/New-Suplier.png)
Manage supplier information, terms, and performance metrics.

### Purchase Orders (GRN)
![Purchases](Images/RouteCard.png)
Create, track, and receive purchase orders with QC workflows.

### Inventory Summary
![Inventory](Images/Inventory-physicalCount.png)
Stock levels, locations, aging analysis, and valuation.

### Alerts
![Alerts](Images/Alert.png)
Active alerts with resolution tracking and audit history.

### Reports
![Reports](Images/Report.png)
Export procurement, inventory, and compliance reports.

### Settings
![Settings](Images/Setting.png)
Configure thresholds, email templates, and user access.

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Flask, Jinja2, HTML5, CSS3, JavaScript (vanilla + AJAX) |
| **Backend** | FastAPI, Python 3.12, Uvicorn |
| **Database** | PostgreSQL 16, SQLAlchemy ORM, Alembic migrations |
| **Authentication** | JWT (python-jose), bcrypt password hashing |
| **File Uploads** | PDF invoices via werkzeug |
| **Scheduled Tasks** | APScheduler (daily inventory emails) |
| **Email** | SMTP (Gmail, SendGrid, AWS SES ready) |
| **Caching** | In-memory (dict) + database queries |
| **Deployment** | Docker, Docker Compose |
| **Version Control** | Git, GitHub |

---

## ✨ Alert Email Notifiaction 
![Email-Alert](Images/Email-Alert.png)

## 📂 Project Structure

```
chanda_store/
├── chanda_backend/
│   ├── app/
│   │   ├── main.py                      # FastAPI app, CORS, router registration
│   │   ├── core/
│   │   │   ├── config.py                # Settings, env variables
│   │   │   ├── security.py              # JWT, password hashing
│   │   │   └── deps.py                  # Dependency injection
│   │   ├── models.py                    # SQLAlchemy ORM models
│   │   ├── schemas/
│   │   │   ├── materials.py             # Material request/response schemas
│   │   │   ├── suppliers.py             # Supplier schemas
│   │   │   ├── purchases.py             # Purchase order schemas
│   │   │   ├── issues.py                # Issue/alert schemas
│   │   │   └── auth.py                  # Login/token schemas
│   │   ├── api/v1/
│   │   │   ├── materials.py             # Material CRUD
│   │   │   ├── suppliers.py             # Supplier CRUD
│   │   │   ├── purchases.py             # GRN management
│   │   │   ├── critical_spares.py       # Critical items
│   │   │   ├── issues.py                # Stock issues/returns
│   │   │   ├── inventory.py             # Stock levels & valuation
│   │   │   ├── reports.py               # Export & analytics
│   │   │   ├── alerts.py                # Alert management
│   │   │   ├── auth.py                  # Login & user management
│   │   │   └── dashboard.py             # KPI dashboard
│   │   ├── services/
│   │   │   ├── email_service.py         # Email sending
│   │   │   ├── excel_service.py         # Report generation
│   │   │   ├── alert_notify.py          # Alert triggering
│   │   │   ├── scheduled_jobs.py        # APScheduler tasks
│   │   │   └── audit.py                 # Audit logging
│   │   └── db/
│   │       └── session.py               # Database setup
│   ├── alembic/                         # Database migrations
│   ├── schema.sql                       # Database schema
│   ├── data_import.sql                  # Seed data (147 materials, 32 suppliers)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── chanda_frontend/
│   ├── app/
│   │   ├── main.py                      # Flask app entry point
│   │   └── routes.py                    # Page routes
│   ├── templates/
│   │   ├── base.html                    # Layout + navbar
│   │   ├── pages/
│   │   │   ├── dashboard.html           # KPI dashboard
│   │   │   ├── materials.html           # Material list & search
│   │   │   ├── material-form.html       # Add/edit material
│   │   │   ├── suppliers.html           # Supplier management
│   │   │   ├── purchases.html           # GRN list
│   │   │   ├── purchase-form.html       # Create GRN
│   │   │   ├── purchase-detail.html     # GRN QC workflow
│   │   │   ├── inventory.html           # Stock summary & aging
│   │   │   ├── alerts.html              # Alert management
│   │   │   ├── reports.html             # Export dashboards
│   │   │   ├── critical-spares.html     # Critical item list
│   │   │   ├── settings.html            # Config & thresholds
│   │   │   └── login.html               # Authentication
│   │   ├── components/                  # Reusable template blocks
│   │   └── errors/                      # 404, 500 pages
│   ├── static/
│   │   ├── css/
│   │   │   └── main.css                 # Tailwind + custom styles
│   │   └── js/
│   │       └── api.js                   # Frontend API calls
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── docker-compose.yml                   # Multi-container orchestration
├── SETUP.md                             # Quick start guide
├── PRODUCTION_DEPLOYMENT_GUIDE.md       # AWS/DigitalOcean deployment
├── FREE_DEPLOYMENT_GUIDE.md             # Railway/Render instructions
├── RAILWAY_DEPLOYMENT_STEP_BY_STEP.md  # Detailed Railway guide
└── README.md                            # This file
```

---

## 🚀 Getting Started

### Prerequisites
- Docker & Docker Compose (recommended)
- Python 3.12 + Node.js 18+ (if running locally without Docker)
- PostgreSQL 16 (or use Docker for this too)
- Gmail account for email alerts (optional)

### Quick Start with Docker

```bash
# Clone the repository
git clone https://github.com/gunnuchauhan30/ChandaEnterprises.git
cd ChandaEnterprises

# Build and run all services
docker compose up --build

# On first run, create an admin user
docker compose exec backend python seed_admin.py
```

**Access:**
- Frontend: `http://localhost:5000`
- Backend API: `http://localhost:8000/docs` (Swagger)
- Default login: `admin` / (password set during seed_admin.py)

### Local Setup (Without Docker)

**Backend:**
```bash
cd chanda_backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: set DATABASE_URL, JWT_SECRET, SMTP credentials

alembic upgrade head
python -m uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd chanda_frontend
pip install -r requirements.txt

cp .env.example .env
# Edit .env: set BACKEND_URL=http://localhost:8000

python app/main.py
```

---

## 🔐 Environment Variables

### Backend (`.env`)
```dotenv
DATABASE_URL=postgresql://user:password@localhost:5432/chanda_store_prod
JWT_SECRET=your-secret-key-change-this-in-production
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# Email Setup (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=noreply@yourdomain.com

# Alerts
ENABLE_EMAIL_ALERTS=true
DAILY_SUMMARY_HOUR=10

# Security
CORS_ORIGINS=["http://localhost:5000"]
```

### Frontend (`.env`)
```dotenv
BACKEND_URL=http://localhost:8000
DEBUG=false
```

---

## 📊 API Endpoints

| Resource | Method | Endpoint | Auth Required |
|---|---|---|---|
| **Auth** | POST | `/auth/login` | No |
| | GET | `/auth/me` | Yes |
| **Materials** | GET | `/materials` | Yes |
| | POST | `/materials` | Yes (staff+) |
| | GET | `/materials/{id}` | Yes |
| | PUT | `/materials/{id}` | Yes (staff+) |
| **Suppliers** | GET | `/suppliers` | Yes |
| | POST | `/suppliers` | Yes (supervisor+) |
| | GET | `/suppliers/{id}` | Yes |
| **Purchases (GRN)** | GET | `/purchases` | Yes |
| | POST | `/purchases` | Yes (staff+) |
| | GET | `/purchases/{id}` | Yes |
| | POST | `/purchases/{id}/qc-pass` | Yes (supervisor+) |
| | POST | `/purchases/{id}/qc-fail` | Yes (supervisor+) |
| **Inventory** | GET | `/inventory/summary` | Yes |
| | GET | `/inventory/valuation` | Yes |
| | GET | `/inventory/aging` | Yes |
| **Alerts** | GET | `/alerts` | Yes |
| | POST | `/alerts/{id}/resolve` | Yes (supervisor+) |
| **Reports** | GET | `/reports/inventory` | Yes |
| | GET | `/reports/procurement` | Yes |
| | GET | `/reports/supplier-performance` | Yes |
| | GET | `/reports/export?format=xlsx` | Yes |
| **Dashboard** | GET | `/dashboard` | Yes |

---

## 🚢 Deployment

### Option 1: Railway (Recommended — FREE) ⚡

See `RAILWAY_DEPLOYMENT_STEP_BY_STEP.md` for a complete guide.

**Quick summary:**
```bash
# Push to GitHub
git push origin main

# On Railway.app:
# 1. Create project from GitHub repo
# 2. Add PostgreSQL database
# 3. Set environment variables
# 4. Deploy!
```

**Cost:** ₹0/month (free tier: 500 hrs/month)

### Option : Self-Hosted VPS

```bash
# On a Ubuntu 22.04 VPS:
apt update && apt install -y docker.io docker-compose
git clone https://github.com/gunnuchauhan30/ChandaEnterprises.git
cd ChandaEnterprises

# Configure .env with production values
docker compose up -d
```

**Cost:** ₹300-400/month

---

## 🔄 Real Data Included

The system ships with production-grade seed data:

| Entity | Count | Source |
|---|---|---|
| Materials | 147 | `chanda_backend/data_import.sql` |
| Suppliers | 32 | `chanda_backend/data_import.sql` |
| Purchase Orders (GRN) | 43 | `chanda_backend/data_import.sql` |
| Users (demo) | 3 | `seed_admin.py` |

Load automatically on first `docker compose up` or manually:
```bash
psql $DATABASE_URL < chanda_backend/schema.sql
psql $DATABASE_URL < chanda_backend/data_import.sql
```

---

## 🎯 Key Features in Action

### 📦 Inventory Alerts
- Low stock (< min threshold) → email alert
- Overstock (> max threshold) → email alert
- Expiry within 30 days → urgency alert
- Resolved with a single click

### 💳 Purchase Order Workflow
1. **Create** → Supplier, item, qty, price
2. **Approve** → Supervisor sign-off
3. **Receive** → Goods receipt + QC pass/fail
4. **Invoice Match** → Bill vs. PO reconciliation
5. **Payment** → Finance tracking (optional)

### 📊 Smart Reports
- Procurement spend by supplier
- Material utilization over time
- Aging inventory (days in stock)
- Valuation using FIFO / LIFO / weighted avg
- One-click Excel download

### 🤖 Automated Emails
- Daily inventory summary at 10 AM
- Low-stock alerts (real-time)
- Overstock warnings (daily)
- New purchase order confirmations

---

## 🔒 Security

- ✅ **Password hashing:** bcrypt with salt
- ✅ **JWT tokens:** 480-minute expiry, signed secret
- ✅ **HTTPS:** Automatic SSL on all deployments
- ✅ **CORS:** Restricted to frontend origin
- ✅ **Audit logs:** Every create/update/delete tracked
- ✅ **Role-based access:** admin, supervisor, staff, viewer roles
- ✅ **SQL injection protection:** SQLAlchemy ORM parameterized queries
- ✅ **CSRF tokens:** Built into Flask forms

---

## 📈 Performance

| Operation | Time | Notes |
|---|---|---|
| Dashboard load | ~200ms | 5 KPI queries in parallel |
| Material search | ~100ms | Indexed on name, code, category |
| Purchase list | ~150ms | Paginated (50 per page) |
| Report generation | ~2-5s | Depends on data size |
| Email alert trigger | <1s | Async via APScheduler |

---

## 🐛 Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| **"Database connection failed"** | DATABASE_URL wrong or DB down | Check `docker compose logs db`, verify credentials |
| **"Blank dashboard"** | Backend not reachable | Verify `BACKEND_URL` in frontend `.env` |
| **"Email alerts not working"** | SMTP credentials invalid | Re-check Gmail app password, enable 2FA |
| **"504 Gateway Timeout"** | Server overload (first request) | Increase backend resources or upgrade plan |
| **"Can't login"** | Admin user not created | Run `docker compose exec backend python seed_admin.py` |

---

## 📞 Support

- **Email:** gunnuchauhan30@gmail.com
- **GitHub:** [github.com/gunnuchauhan30/ChandaEnterprises](https://github.com/gunnuchauhan30/ChandaEnterprises)
- **Issues:** [GitHub Issues](https://github.com/gunnuchauhan30/ChandaEnterprises/issues)

---

## 📄 License

This project is licensed under the **MIT License**. See `LICENSE` for details.

---

## 🙏 Contributing

Contributions are welcome! Please:
1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 🎉 Next Steps

- [ ] Deploy to Railway (see `RAILWAY_DEPLOYMENT_STEP_BY_STEP.md`)
- [ ] Create admin account: `docker compose exec backend python seed_admin.py`
- [ ] Configure email alerts (update `.env` SMTP vars)
- [ ] Customize thresholds on Settings page
- [ ] Invite team members
- [ ] Start managing inventory!

---

**Built with ❤️ by [Gunjan Chauhan](https://github.com/gunnuchauhan30)**

Happy inventory management! 🚀


