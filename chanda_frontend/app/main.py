"""
CHANDA ENTERPRISES - Frontend Application
Serves Jinja2 templates and integrates with FastAPI backend API

Run: flask run --port 5000
Backend should be running on: http://localhost:8000
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
import os
from datetime import datetime

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Frontend configuration
BACKEND_URL = os.environ.get('BACKEND_URL', 'http://localhost:8000')

# ============================================
# AUTHENTICATION DECORATORS
# ============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

def anonymous_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'access_token' in session:
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# CONTEXT PROCESSORS
# ============================================

@app.context_processor
def inject_user():
    user = session.get('user', {})
    return dict(current_user=user, datetime=datetime)

@app.context_processor
def inject_config():
    return dict(
        BACKEND_URL=BACKEND_URL,
        APP_VERSION='1.0.0',
        APP_NAME='Chanda Enterprises Store Management',
    )

# ============================================
# ROUTES - AUTHENTICATION
# ============================================

@app.route('/login', methods=['GET', 'POST'])
@anonymous_required
def login():
    """Login page"""
    if request.method == 'POST':
        # Frontend just renders form; actual auth handled via JavaScript/API
        pass
    return render_template('pages/login.html')

@app.route('/signup', methods=['GET'])
@login_required
def signup():
    """Redirects the old public signup URL to the new admin-only Manage Users page."""
    return redirect(url_for('manage_users'))

@app.route('/admin/users', methods=['GET'])
@login_required
def manage_users():
    """Admin-only: create employee accounts (with role) and manage existing ones."""
    return render_template('pages/manage-users.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Logout"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
@anonymous_required
def forgot_password():
    """Forgot password page"""
    return render_template('pages/forgot-password.html')

@app.route('/reset-password', methods=['GET'])
@anonymous_required
def reset_password():
    """Reset password page — reached via the token link emailed by /auth/forgot-password"""
    token = request.args.get('token', '')
    return render_template('pages/reset-password.html', token=token)

# ============================================
# ROUTES - DASHBOARD & MAIN
# ============================================

@app.route('/')
@login_required
def index():
    """Redirect to dashboard"""
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page with KPIs and charts"""
    return render_template('pages/dashboard.html')

# ============================================
# ROUTES - INVENTORY MANAGEMENT
# ============================================

@app.route('/materials')
@login_required
def materials():
    """Materials master list"""
    return render_template('pages/materials.html')

@app.route('/materials/new')
@login_required
def create_material():
    """Create new material"""
    return render_template('pages/material-form.html', action='create')

@app.route('/materials/<material_code>')
@login_required
def material_detail(material_code):
    """Material detail and edit"""
    return render_template('pages/material-detail.html', material_code=material_code)

@app.route('/suppliers')
@login_required
def suppliers():
    """Suppliers master list"""
    return render_template('pages/suppliers.html', page='suppliers')

@app.route('/suppliers/new')
@login_required
def create_supplier():
    """Create new supplier"""
    return render_template('pages/supplier-form.html', action='create')

@app.route('/inventory')
@login_required
def inventory():
    """Inventory overview"""
    return render_template('pages/inventory.html', page='inventory')

@app.route('/critical-spares')
@login_required
def critical_spares():
    """Critical Spares List"""
    return render_template('pages/critical-spares.html', page='critical-spares')

# ============================================
# ROUTES - PURCHASING
# ============================================

@app.route('/purchases')
@login_required
def purchases():
    """Purchase/GRN list"""
    return render_template('pages/purchases.html', page='purchases')

@app.route('/purchases/new')
@login_required
def create_purchase():
    """Create new purchase/GRN"""
    return render_template('pages/purchase-form.html', action='create')

@app.route('/purchases/<purchase_id>')
@login_required
def purchase_detail(purchase_id):
    """Purchase detail"""
    return render_template('pages/purchase-detail.html', purchase_id=purchase_id)

# ============================================
# ROUTES - OPERATIONS
# ============================================

@app.route('/requests')
@login_required
def requests():
    """Employee requests list"""
    return render_template('pages/requests.html', page='requests')

@app.route('/requests/new')
@login_required
def create_request():
    """Create new request"""
    return render_template('pages/request-form.html', action='create')

@app.route('/requests/backorders')
@login_required
def backorders():
    """Point 12: FIFO backorder queue - requests still waiting on stock."""
    return render_template('pages/backorders.html', page='backorders')

@app.route('/history')
@login_required
def history():
    """Point 4: full activity history (admin-only, enforced by the API)."""
    return render_template('pages/history.html', page='history')

@app.route('/issues')
@login_required
def issues():
    """Material issues list"""
    return render_template('pages/issues.html', page='issues')

@app.route('/route-card')
@login_required
def route_card():
    """Route Card - formatted view/export of Issues data"""
    return render_template('pages/route-card.html', page='route-card')

@app.route('/route-card/print/<job_card_no>')
@login_required
def route_card_print(job_card_no):
    """Point 9: auto-generated, printable single-page Route Card for one job card.
    All fields are pulled live from stock/issue data -- nothing is retyped."""
    return render_template('pages/route-card-print.html', job_card_no=job_card_no)

@app.route('/issues/new')
@login_required
def create_issue():
    """Create new issue"""
    return render_template('pages/issue-form.html', action='create')

@app.route('/returns')
@login_required
def returns():
    """Returns list"""
    return render_template('pages/returns.html', page='returns')

@app.route('/returns/new')
@login_required
def create_return():
    """Create new return"""
    return render_template('pages/return-form.html', action='create')

# ============================================
# ROUTES - REPORTING
# ============================================

@app.route('/reports')
@login_required
def reports():
    """Reports page"""
    return render_template('pages/reports.html', page='reports')

@app.route('/alerts')
@login_required
def alerts():
    """Alerts page"""
    return render_template('pages/alerts.html', page='alerts')

# ============================================
# ROUTES - ADMIN
# ============================================

@app.route('/settings')
@login_required
def settings():
    """Settings page"""
    return render_template('pages/settings.html', page='settings')

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('errors/500.html'), 500

# ============================================
# UTILITY ENDPOINTS (JSON)
# ============================================

@app.route('/api/frontend/config')
def frontend_config():
    """Frontend configuration"""
    return jsonify({
        'backend_url': BACKEND_URL,
        'app_name': 'Chanda Enterprises Store Management',
        'version': '1.0.0',
    })

# ============================================
# RUN
# ============================================

if __name__ == '__main__':
    os.makedirs('logs', exist_ok=True)
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.environ.get('FLASK_ENV') == 'development',
    )