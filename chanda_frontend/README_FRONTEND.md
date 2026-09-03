# CHANDA ENTERPRISES - FRONTEND APPLICATION

Professional Enterprise Store Management System Frontend
- **Framework**: Flask + Jinja2 Templates
- **Styling**: Custom CSS with Dark Purple Theme, Glassmorphism, 3D Effects
- **Charts**: Chart.js
- **Backend**: FastAPI (http://localhost:8000)
- **Frontend Port**: 5000

---

## 🎨 Design Highlights

✨ **Dark Purple Theme**
- Primary: #4a235a (Deep purple)
- Accent: #b366cc (Light purple)
- Background: Gradient from #0d0618 to #1a0f2e

✨ **Glassmorphism Effects**
- Frosted glass backgrounds
- Backdrop blur filters
- Subtle transparency layers

✨ **3D Cards & Animations**
- Hover animations (translateY, rotateX)
- Smooth transitions
- Professional shadows

✨ **Responsive Design**
- Mobile-friendly
- Tablet-optimized
- Desktop-perfect

---

## 📁 Project Structure

```
frontend_complete/
├── app/
│   └── main.py                    # Flask application
├── static/
│   ├── css/
│   │   └── main.css              # Main styles (dark purple theme)
│   ├── js/
│   │   └── api.js                # API client library
│   ├── images/                   # Logos, icons
│   └── fonts/                    # Custom fonts
├── templates/
│   ├── base.html                 # Base layout (sidebar, topbar)
│   ├── pages/
│   │   ├── login.html           # Login page
│   │   ├── dashboard.html       # Dashboard with KPIs & charts
│   │   ├── materials.html       # Material Master list
│   │   ├── material-form.html   # Material create/edit form
│   │   ├── material-detail.html # Material detail view
│   │   ├── suppliers.html       # Supplier Master list
│   │   ├── supplier-form.html   # Supplier form
│   │   ├── inventory.html       # Inventory overview
│   │   ├── purchases.html       # Purchase/GRN list
│   │   ├── purchase-form.html   # Purchase create form
│   │   ├── purchase-detail.html # Purchase detail
│   │   ├── requests.html        # Employee requests
│   │   ├── request-form.html    # Request create form
│   │   ├── issues.html          # Material issues
│   │   ├── issue-form.html      # Issue create form
│   │   ├── returns.html         # Returns list
│   │   ├── return-form.html     # Return create form
│   │   ├── reports.html         # Reports page
│   │   ├── alerts.html          # Alerts management
│   │   ├── settings.html        # Settings page
│   │   ├── signup.html          # Signup page
│   │   ├── forgot-password.html # Forgot password page
│   │   └── components/          # Reusable components
│   ├── errors/
│   │   ├── 404.html            # 404 error page
│   │   └── 500.html            # 500 error page
│   └── layouts/
├── .env.example                 # Environment variables template
├── requirements.txt             # Python dependencies
└── README_FRONTEND.md          # This file
```

---

## 🚀 Installation & Setup

### Option A: Quick Start (Recommended)

```bash
# 1. Navigate to frontend folder
cd chanda_frontend

# 2. Create Python virtual environment
python3 -m venv venv

# 3. Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env file
cp .env.example .env

# 6. Edit .env (set BACKEND_URL if backend is not on localhost:8000)
# BACKEND_URL=http://localhost:8000
# FLASK_ENV=development

# 7. Run development server
flask run --port 5000

# 8. Open browser
# http://localhost:5000
```

### Option B: Production Setup

```bash
# Using Gunicorn with 4 workers
gunicorn -w 4 -b 0.0.0.0:5000 app.main:app
```

---

## 🔐 Authentication Flow

1. **Login Page** (`/login`)
   - User enters username & password
   - JavaScript calls `API.login()` (FastAPI backend)
   - JWT token stored in localStorage
   - User redirected to dashboard

2. **Protected Pages**
   - `@login_required` decorator checks for `access_token` in session
   - If missing, redirects to login
   - JavaScript API client adds Bearer token to all requests

3. **Logout**
   - Clears localStorage & session
   - Redirects to login page

---

## 📡 API Integration

All API calls go through `static/js/api.js`:

```javascript
// Example: Get materials
const materials = await API.getMaterials(page=1, pageSize=20);

// Example: Create purchase
await API.createPurchase({
    material_code: 'MAT-001',
    supplier_id: 1,
    qty: 100,
    unit_cost: 150
});

// Example: Update QC status
await API.updateQCStatus(purchaseId, 'passed', 'OK');
```

All methods handle:
- JWT authentication (Bearer token)
- Error handling
- JSON serialization
- Response validation

---

## 🎯 Page Modules

### Dashboard (`/dashboard`)
- **KPI Cards**: Stock value, today's purchases/issues, low stock count
- **Charts**: Monthly trends, purchase trends, department consumption
- **Alerts Table**: Recent low/high stock alerts
- **Real-time**: Refreshes every 60 seconds

### Material Master (`/materials`)
- List all 147 materials with pagination
- Search, filter, sort
- Excel import/export
- Create/edit/delete materials
- Batch tracking & FIFO view

### Supplier Master (`/suppliers`)
- List all 32 suppliers
- Rating & performance tracking
- Create/edit suppliers
- Supplied materials view

### Purchase/GRN (`/purchases`)
- Create new purchase orders
- QC workflow (pending → passed/failed)
- Invoice PDF upload
- Auto stock increase on QC pass
- Purchase history

### Employee Requests (`/requests`)
- Employee creates request for material
- Store Manager approves/rejects
- Auto-issue on approval
- Status tracking (pending → approved → completed)

### Material Issues (`/issues`)
- Direct issue or via employee request
- Route card fields (job card, machine, operation, PO)
- Consumption tracking
- Stock auto-deduction

### Returns (`/returns`)
- 4 return types: unused, vendor, rejected, adjustment
- Stock auto-increment
- Reason tracking
- History

### Inventory (`/inventory`)
- Stock summary by material
- Batch tracking with FIFO
- Stock ledger & aging
- Valuation report

### Reports (`/reports`)
- 6 report types: Purchase, Issue, Supplier, Consumption, Department, Stock
- Export: Excel, CSV, JSON
- Date range filtering
- Print support

### Alerts (`/alerts`)
- Low stock alerts (≤1500)
- High stock alerts (≥5000)
- Resolve alerts
- Email notifications

---

## 🎨 Customization

### Change Theme Colors

Edit `static/css/main.css`:

```css
:root {
    --primary-dark: #2d1b4e;        /* Change these */
    --primary-purple: #4a235a;
    --accent-purple: #b366cc;
    /* ... */
}
```

### Add New Page

1. Create template: `templates/pages/new-page.html`
2. Add route in `app/main.py`:
   ```python
   @app.route('/new-page')
   @login_required
   def new_page():
       return render_template('pages/new-page.html')
   ```
3. Add sidebar link in `templates/base.html`

### Add Chart

Use Chart.js (already included):

```javascript
const ctx = document.getElementById('myChart').getContext('2d');
const chart = new Chart(ctx, {
    type: 'bar',
    data: { /* ... */ },
    options: { /* ... */ }
});
```

---

## 🔧 Environment Variables

`.env` file:

```env
# Flask
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your-secret-key-here

# Backend API
BACKEND_URL=http://localhost:8000

# CORS
CORS_ORIGIN=http://localhost:5000
```

---

## 📱 Responsive Breakpoints

- **Desktop**: 1200px+ (full sidebar + content)
- **Tablet**: 768px-1199px (collapsed sidebar, full grid)
- **Mobile**: <768px (minimal sidebar, stacked layout)

---

## 🚨 Common Issues

### "Cannot connect to backend"
- Ensure backend is running: `http://localhost:8000/health`
- Check `BACKEND_URL` in `.env`
- Verify CORS settings in FastAPI backend

### "Login not working"
- Ensure admin user exists: `python seed_admin.py` on backend
- Check browser console for JWT errors
- Verify `/api/v1/auth/login` endpoint responds

### "Charts not rendering"
- Ensure Chart.js is loaded (check browser console)
- Verify data returned from `API.getDashboardKPIs()`
- Check browser DevTools for JavaScript errors

---

## 🌐 Deployment

### Docker (Recommended)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app.main:app"]
```

```bash
docker build -t chanda-frontend .
docker run -p 5000:5000 -e BACKEND_URL=http://backend:8000 chanda-frontend
```

### Nginx Reverse Proxy

```nginx
upstream flask_app {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://flask_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static/ {
        alias /path/to/frontend/static/;
    }
}
```

---

## 📞 Support & Contributions

For issues or feature requests, contact: development@chanda-enterprises.com

---

**Version**: 1.0.0  
**Last Updated**: August 6, 2026  
**Status**: Production Ready


docker compose down       # band karna ho to
docker compose up -d      # dobara start karna ho to (rebuild ki zaroorat nahi agar code nahi badla)
docker compose up -d --build   # agar code/Dockerfile mein kuch change kiya ho