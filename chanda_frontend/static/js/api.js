/* ============================================
   API CLIENT FOR CHANDA STORE MANAGEMENT SYSTEM
   Every method below is matched 1:1 against the real FastAPI routes in
   chanda_backend/app/api/v1/*.py (prefix /api/v1). Do not add a frontend
   call without also checking the backend route + params exist.
   ============================================ */

// const API_BASE_URL = 'http://localhost:8000/api/v1';
const API_BASE_URL = window.RAILWAY_BACKEND_URL || 'https://chandaenterprises-production.up.railway.app/api/v1';
let authToken = localStorage.getItem('access_token');
let currentUser = null;

class API {
    static async request(endpoint, options = {}) {
        const url = `${API_BASE_URL}${endpoint}`;
        const headers = { 'Content-Type': 'application/json', ...options.headers };
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

        try {
            const response = await fetch(url, {
                method: options.method || 'GET',
                headers,
                body: options.body ? JSON.stringify(options.body) : undefined,
            });

            if (response.status === 401) {
                this.logout();
                return null;
            }

            let data = null;
            try { data = await response.json(); } catch (_) { data = null; }

            if (!response.ok) {
                const message = (data && (data.detail || data.message)) || `Request failed (${response.status})`;
                showAlert(typeof message === 'string' ? message : JSON.stringify(message), 'danger');
                return null;
            }

            // The backend returns plain JSON arrays for list endpoints (no
            // {items,total} envelope). Every list-page template expects
            // `.items` + `.total`, so normalize here in ONE place instead of
            // changing every backend response_model.
            if (Array.isArray(data)) {
                return { items: data, total: data.length };
            }
            return data;
        } catch (error) {
            console.error('API error:', error);
            showAlert('Network error — is the backend running on ' + API_BASE_URL + '?', 'danger');
            return null;
        }
    }

    // ============= AUTH =============
    static async signup(username, email, password, fullName, role) {
        return this.request('/auth/signup', {
            method: 'POST',
            body: { username, email, password, full_name: fullName, role },
        });
    }

    static async getUsers() {
        const data = await this.request('/auth/users');
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async updateUser(userId, data) {
        return this.request(`/auth/users/${userId}`, { method: 'PATCH', body: data });
    }

    static async deleteUser(userId) {
        // Dedicated implementation: the shared request() helper returns null for
        // BOTH a successful 204-No-Content delete AND a failed request, which
        // would make success and failure indistinguishable here.
        try {
            const response = await fetch(`${API_BASE_URL}/auth/users/${userId}`, {
                method: 'DELETE',
                headers: authToken ? { 'Authorization': `Bearer ${authToken}` } : {},
            });
            if (response.status === 204) return true;
            let data = null;
            try { data = await response.json(); } catch (_) { /* no body */ }
            const message = (data && data.detail) || `Request failed (${response.status})`;
            showAlert(typeof message === 'string' ? message : JSON.stringify(message), 'danger');
            return false;
        } catch (error) {
            showAlert('Network error — is the backend running on ' + API_BASE_URL + '?', 'danger');
            return false;
        }
    }

    static async login(username, password) {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Login failed');
        }

        const data = await response.json();
        authToken = data.access_token;
        localStorage.setItem('access_token', authToken);
        localStorage.setItem('user', JSON.stringify(data.user));
        return data;
    }

    static logout() {
        authToken = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
    }

    static async getCurrentUser() {
        const response = await this.request('/auth/me');
        if (response) currentUser = response;
        return response;
    }

    static async forgotPassword(email) {
        return this.request('/auth/forgot-password', { method: 'POST', body: { email } });
    }

    static async resetPassword(token, newPassword) {
        return this.request('/auth/reset-password', { method: 'POST', body: { token, new_password: newPassword } });
    }

    // ============= MATERIALS =============
    static async getMaterials(page = 1, pageSize = 20, search = '', extra = {}) {
        const params = new URLSearchParams({ page, page_size: pageSize, ...extra });
        if (search) params.append('search', search);
        const data = await this.request(`/materials?${params}`);
        // Backend returns a plain JSON array (List[MaterialOut]), not a
        // {items: [...]} paginated wrapper. Every caller in this codebase
        // expects .items though, so normalize here once instead of fixing
        // it in six different templates.
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async getMaterial(materialCode) {
        return this.request(`/materials/${materialCode}`);
    }

    static async createMaterial(data) {
        return this.request('/materials', { method: 'POST', body: data });
    }

    static async updateMaterial(materialCode, data) {
        return this.request(`/materials/${materialCode}`, { method: 'PUT', body: data });
    }

    static async deleteMaterial(materialCode) {
        return this.request(`/materials/${materialCode}`, { method: 'DELETE' });
    }

    // Point: quick current-stock edit from the Material Master list --
    // goes through the audited reconciliation/adjustment path server-side.
    static async quickAdjustStock(materialCode, physicalQty, remarks = '') {
        return this.request('/inventory/quick-adjust', {
            method: 'POST',
            body: { material_code: materialCode, physical_qty: physicalQty, remarks },
        });
    }

    static async importMaterials(file) {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch(`${API_BASE_URL}/materials/import/excel`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` },
            body: formData,
        });
        const data = await response.json().catch(() => null);
        if (!response.ok) {
            const message = (data && (data.detail || data.message)) || `Import failed (HTTP ${response.status})`;
            throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
        }
        return data;
    }

    static async exportMaterials() {
        const response = await fetch(`${API_BASE_URL}/materials/export/excel`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (!response.ok) throw new Error('Export failed');
        return response.blob();
    }

    // ============= SUPPLIERS =============
    static async getSuppliers(page = 1, pageSize = 20, search = '') {
        const params = new URLSearchParams({ page, page_size: pageSize });
        if (search) params.append('search', search);
        const data = await this.request(`/suppliers?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async getSupplier(supplierId) {
        return this.request(`/suppliers/${supplierId}`);
    }

    static async getSupplierMaterials(supplierId) {
        return this.request(`/suppliers/${supplierId}/materials`);
    }

    static async createSupplier(data) {
        return this.request('/suppliers', { method: 'POST', body: data });
    }

    static async updateSupplier(supplierId, data) {
        return this.request(`/suppliers/${supplierId}`, { method: 'PUT', body: data });
    }

    static async deactivateSupplier(supplierId) {
        return this.request(`/suppliers/${supplierId}`, { method: 'DELETE' });
    }

    // ============= PURCHASES / GRN =============
    static async getPurchases(page = 1, pageSize = 20, filters = {}) {
        const params = new URLSearchParams({ page, page_size: pageSize, ...filters });
        const data = await this.request(`/purchases?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async getPurchase(purchaseId) {
        return this.request(`/purchases/${purchaseId}`);
    }

    static async createPurchase(data) {
        return this.request('/purchases', { method: 'POST', body: data });
    }

    static async updateQCStatus(purchaseId, qcStatus, remarks = '') {
        return this.request(`/purchases/${purchaseId}/qc`, {
            method: 'PATCH',
            body: { qc_status: qcStatus, qc_remarks: remarks },
        });
    }

    static async uploadInvoice(purchaseId, file) {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch(`${API_BASE_URL}/purchases/${purchaseId}/invoice`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` },
            body: formData,
        });
        return await response.json();
    }

    // ============= EMPLOYEE REQUESTS =============
    static async getRequests(page = 1, pageSize = 20, filters = {}) {
        const params = new URLSearchParams({ page, page_size: pageSize, ...filters });
        const data = await this.request(`/employee-requests?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async createRequest(data) {
        return this.request('/employee-requests', { method: 'POST', body: data });
    }

    static async approveRequest(requestId) {
        return this.request(`/employee-requests/${requestId}/decision`, {
            method: 'PATCH', body: { action: 'approve' },
        });
    }

    static async rejectRequest(requestId, rejectionReason = '') {
        return this.request(`/employee-requests/${requestId}/decision`, {
            method: 'PATCH', body: { action: 'reject', rejection_reason: rejectionReason },
        });
    }

    static async getBackorders(materialCode = '') {
        const params = materialCode ? `?material_code=${encodeURIComponent(materialCode)}` : '';
        const data = await this.request(`/employee-requests/backorders${params}`);
        return Array.isArray(data) ? data : (data && data.items) || [];
    }

    static async processBackorders(materialCode) {
        return this.request(`/employee-requests/backorders/process/${materialCode}`, { method: 'POST' });
    }

    static async getActivityHistory(page = 1, pageSize = 50, filters = {}) {
        const params = new URLSearchParams({ page, page_size: pageSize, ...filters });
        return this.request(`/history/activity?${params}`);
    }

    static async getLoginHistory(page = 1, pageSize = 50) {
        const params = new URLSearchParams({ page, page_size: pageSize });
        return this.request(`/history/logins?${params}`);
    }

    // ============= ISSUES (Route Card) =============
    static async getIssues(page = 1, pageSize = 20, filters = {}) {
        const params = new URLSearchParams({ page, page_size: pageSize, ...filters });
        const data = await this.request(`/issues?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async createIssue(data) {
        return this.request('/issues', { method: 'POST', body: data });
    }

    static async updateIssueConsumption(issueId, consumedQty, completionStatus = 'completed') {
        return this.request(`/issues/${issueId}/consumption`, {
            method: 'PATCH', body: { consumed_qty: consumedQty, completion_status: completionStatus },
        });
    }

    // ============= RETURNS =============
    static async getReturns(page = 1, pageSize = 20, filters = {}) {
        const params = new URLSearchParams({ page, page_size: pageSize, ...filters });
        const data = await this.request(`/returns?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async createReturn(data) {
        return this.request('/returns', { method: 'POST', body: data });
    }

    // ============= INVENTORY =============
    static async getInventorySummary() {
        return this.request('/inventory/summary');
    }

    static async getStockBatches(materialCode = '', onlyAvailable = true) {
        const params = new URLSearchParams({ only_available: onlyAvailable });
        if (materialCode) params.append('material_code', materialCode);
        const data = await this.request(`/inventory/batches?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async getStockLedger(materialCode = '', page = 1) {
        const params = new URLSearchParams({ page });
        if (materialCode) params.append('material_code', materialCode);
        const data = await this.request(`/inventory/ledger?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async getStockValuation() {
        return this.request('/inventory/valuation');
    }

    static async getStockAging() {
        return this.request('/inventory/aging');
    }

    // ============= PHYSICAL STOCK RECONCILIATION =============
    static async getReconciliations(status = '', page = 1) {
        const params = new URLSearchParams({ page });
        if (status) params.append('status', status);
        const data = await this.request(`/inventory/reconciliations?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async createReconciliation(data) {
        return this.request('/inventory/reconciliations', { method: 'POST', body: data });
    }

    static async decideReconciliation(recoId, action, reviewRemarks = '') {
        return this.request(`/inventory/reconciliations/${recoId}/decision`, {
            method: 'PATCH', body: { action, review_remarks: reviewRemarks },
        });
    }

    // ============= CRITICAL SPARES LIST =============
    static async getCriticalSpares(filters = {}) {
        const params = new URLSearchParams(filters);
        const data = await this.request(`/critical-spares?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async createCriticalSpare(data) {
        return this.request('/critical-spares', { method: 'POST', body: data });
    }

    static async updateCriticalSpare(spareId, data) {
        return this.request(`/critical-spares/${spareId}`, { method: 'PUT', body: data });
    }

    static async deleteCriticalSpare(spareId) {
        return this.request(`/critical-spares/${spareId}`, { method: 'DELETE' });
    }

    // ============= ROUTE CARD =============
    static async getRouteCard(filters = {}) {
        const params = new URLSearchParams(filters);
        const data = await this.request(`/issues/route-card?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async exportRouteCardExcel(filters = {}) {
        const params = new URLSearchParams(filters);
        const response = await fetch(`${API_BASE_URL}/issues/route-card/export/excel?${params}`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (!response.ok) throw new Error('Export failed');
        return response.blob();
    }

    // ============= ALERTS =============
    static async getAlerts(onlyOpen = true, alertType = null) {
        const params = new URLSearchParams();
        if (onlyOpen) params.append('is_resolved', 'false');
        if (alertType) params.append('alert_type', alertType);
        const data = await this.request(`/alerts?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async getLowStockAlerts() {
        return this.request('/alerts/low-stock');
    }

    static async getHighStockAlerts() {
        return this.request('/alerts/high-stock');
    }

    static async resolveAlert(alertId) {
        return this.request(`/alerts/${alertId}/resolve`, { method: 'PATCH' });
    }

    static async confirmHighStockPurchase(materialCode) {
        return this.request(`/alerts/${materialCode}/confirm-high-stock-purchase`, { method: 'POST' });
    }

    // ============= NOTIFICATIONS =============
    // NOTE: called from base.html as getNotifications(1, 10) (page, pageSize)
    // for the bell-icon panel, so we accept that shape here rather than the
    // old unreadOnly-only signature, and enrich the response with unread_count
    // (a separate backend endpoint) since the list endpoint doesn't include it.
    static async getNotifications(page = 1, pageSize = 10, unreadOnly = false) {
        const params = new URLSearchParams({ unread_only: unreadOnly });
        const [data, unread] = await Promise.all([
            this.request(`/notifications?${params}`),
            this.request('/notifications/unread-count'),
        ]);
        const items = Array.isArray(data) ? data : (data && data.items) || [];
        return {
            items: items.slice(0, pageSize),
            unread_count: (unread && unread.unread_count) || 0,
        };
    }

    static async markNotificationRead(notificationId) {
        return this.request(`/notifications/${notificationId}/read`, { method: 'PATCH' });
    }

    static async markAllNotificationsRead() {
        return this.request('/notifications/read-all', { method: 'PATCH' });
    }

    static async getUnreadCount() {
        return this.request('/notifications/unread-count');
    }

    // ============= DASHBOARD =============
    // Backend exposes ONE combined endpoint (GET /dashboard) that returns KPIs
    // + monthly_consumption + purchase_trend + issue_trend + department_consumption
    // all together. There is no /dashboard/kpis or /dashboard/trends route.
    static async getDashboard() {
        return this.request('/dashboard');
    }

    // ============= REPORTS =============
    static async getReport(reportType, dateFrom = null, dateTo = null) {
        const params = new URLSearchParams();
        if (dateFrom) params.append('date_from', dateFrom);
        if (dateTo) params.append('date_to', dateTo);
        const data = await this.request(`/reports/${reportType}?${params}`);
        return { items: Array.isArray(data) ? data : (data && data.items) || [] };
    }

    static async exportReportExcel(reportType, dateFrom = null, dateTo = null) {
        const params = new URLSearchParams();
        if (dateFrom) params.append('date_from', dateFrom);
        if (dateTo) params.append('date_to', dateTo);
        const response = await fetch(`${API_BASE_URL}/reports/${reportType}/export/excel?${params}`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (!response.ok) throw new Error('Export failed');
        return response.blob();
    }

    static async exportReportCsv(reportType, dateFrom = null, dateTo = null) {
        const params = new URLSearchParams();
        if (dateFrom) params.append('date_from', dateFrom);
        if (dateTo) params.append('date_to', dateTo);
        const response = await fetch(`${API_BASE_URL}/reports/${reportType}/export/csv?${params}`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (!response.ok) throw new Error('Export failed');
        return response.blob();
    }
}

/* ============================================
   UTILITY FUNCTIONS
   ============================================ */

function showAlert(message, type = 'info') {
    const alertContainer = document.getElementById('alert-container') || createAlertContainer();
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} fade-in`;
    alert.innerHTML = `
        <i class="icon icon-${type}"></i>
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" style="background:none; border:none; color:inherit; cursor:pointer; font-size:20px;">×</button>
    `;
    alertContainer.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

function createAlertContainer() {
    const container = document.createElement('div');
    container.id = 'alert-container';
    container.style.cssText = 'position:fixed; top:20px; right:20px; max-width:400px; z-index:3000;';
    document.body.appendChild(container);
    return container;
}

function formatCurrency(value) {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value || 0);
}

function formatDate(dateString) {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatDateTime(dateString) {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-IN', {
        year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
}

function downloadFile(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

// Initialize auth on page load
document.addEventListener('DOMContentLoaded', () => {
    if (authToken && !window.location.pathname.includes('/login')) {
        API.getCurrentUser().then(user => {
            if (!user) window.location.href = '/login';
        });
    }
});
