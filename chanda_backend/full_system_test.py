#!/usr/bin/env python3
"""
Full end-to-end test of every module, against the live server.
Run: pip install requests && python3 full_system_test.py
Requires the server running on localhost:8000 and these 4 users existing:
  admin/Admin@123 (role=admin), storemgr/Store@123 (role=store_manager),
  purchaser/Purchase@123 (role=purchase), worker1/Worker@123 (role=production)
Create them via seed_admin.py (admin) and POST /auth/signup (the other three),
or reuse whatever admin credentials you set up -- just adjust the logins below.
"""
import requests, json, sys

BASE = "http://localhost:8000/api/v1"
results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f"  -> {detail}" if detail and status=='FAIL' else ""))

def login(username, password):
    r = requests.post(f"{BASE}/auth/login", data={"username": username, "password": password})
    if r.status_code != 200:
        return None
    return r.json()["access_token"]

def auth(token):
    return {"Authorization": f"Bearer {token}"}

# ---------- AUTH ----------
admin_tok = login("admin", "gunjan30")
check("Admin login", admin_tok is not None)
store_tok = login("storemgr", "Store@123")
check("Store manager login", store_tok is not None)
purch_tok = login("purchaser", "Purchase@123")
check("Purchase login", purch_tok is not None)
worker_tok = login("worker1", "Worker@123")
check("Production worker login", worker_tok is not None)

r = requests.get(f"{BASE}/auth/me", headers=auth(admin_tok))
check("GET /auth/me", r.status_code == 200 and r.json()["username"] == "admin")

r = requests.get(f"{BASE}/materials", headers=auth(admin_tok))
check("Unauthenticated blocked / authenticated allowed", requests.get(f"{BASE}/materials").status_code == 401 and r.status_code == 200)

# ---------- SUPPLIER MASTER ----------
r = requests.post(f"{BASE}/suppliers", headers=auth(purch_tok), json={
    "supplier_name": "Test Steel Traders", "gst_no": "27ABCDE1234F1Z5",
    "phone": "9876543210", "email": "sales@teststeel.com", "payment_terms": "Net 30", "rating": 4.2
})
check("Create supplier (purchase role)", r.status_code == 201, r.text)
supplier_id = r.json()["id"] if r.status_code == 201 else None

r = requests.get(f"{BASE}/suppliers", headers=auth(admin_tok))
check("List suppliers", r.status_code == 200 and len(r.json()) > 0)

r = requests.put(f"{BASE}/suppliers/{supplier_id}", headers=auth(purch_tok), json={
    "supplier_name": "Test Steel Traders Pvt Ltd", "rating": 4.5
})
check("Update supplier", r.status_code == 200 and float(r.json()["rating"]) == 4.5, r.text)

r = requests.post(f"{BASE}/suppliers", headers=auth(worker_tok), json={"supplier_name": "Should Fail Co"})
check("Production role blocked from creating supplier (403)", r.status_code == 403)

# ---------- MATERIAL MASTER ----------
r = requests.post(f"{BASE}/materials", headers=auth(store_tok), json={
    "material_code": "TESTMAT01", "material_name": "Test Hex Bolt M10", "category": "Fasteners",
    "material_type": "PRODUCTION", "uom": "NOS", "min_qty": 500, "max_qty": 5000,
    "opening_qty": 2000, "unit_cost": 12.5, "warehouse": "WH1", "rack": "R3", "bin": "B12",
    "supplier_id": supplier_id, "lead_time_days": 7,
})
check("Create material (store_manager)", r.status_code == 201, r.text)

r = requests.get(f"{BASE}/materials/TESTMAT01", headers=auth(admin_tok))
check("Get material by code, opening=current on creation", r.status_code == 200 and float(r.json()["current_qty"]) == 2000)

r = requests.put(f"{BASE}/materials/TESTMAT01", headers=auth(store_tok), json={"unit_cost": 13.0, "rack": "R4"})
check("Update material", r.status_code == 200 and float(r.json()["unit_cost"]) == 13.0)

r = requests.get(f"{BASE}/materials?search=Test&page_size=10", headers=auth(admin_tok))
check("Search materials", r.status_code == 200 and any(m["material_code"] == "TESTMAT01" for m in r.json()))

r = requests.get(f"{BASE}/materials/export/excel", headers=auth(admin_tok))
check("Export materials Excel", r.status_code == 200 and r.headers["content-type"].startswith("application/vnd"))

r = requests.post(f"{BASE}/materials", headers=auth(worker_tok), json={"material_code": "X", "material_name": "x"})
check("Production role blocked from creating material (403)", r.status_code == 403)

# ---------- PURCHASE / GRN ----------
r = requests.get(f"{BASE}/materials/MC001", headers=auth(admin_tok))
stock_before_grn = float(r.json()["current_qty"])

r = requests.post(f"{BASE}/purchases", headers=auth(purch_tok), json={
    "material_code": "MC001", "supplier_id": supplier_id, "qty": 250, "unit_cost": 48.5, "invoice_no": "INV-9001"
})
check("Create GRN", r.status_code == 201, r.text)
grn_id = r.json()["id"]

r = requests.get(f"{BASE}/materials/MC001", headers=auth(admin_tok))
check("Stock unchanged while QC pending", float(r.json()["current_qty"]) == stock_before_grn)

r = requests.patch(f"{BASE}/purchases/{grn_id}/qc", headers=auth(store_tok), json={"qc_status": "passed", "qc_remarks": "Sample checked, OK"})
check("QC pass", r.status_code == 200)

r = requests.get(f"{BASE}/materials/MC001", headers=auth(admin_tok))
stock_after_grn = float(r.json()["current_qty"])
check("Stock auto-increased by exactly GRN qty", stock_after_grn == stock_before_grn + 250, f"before={stock_before_grn} after={stock_after_grn}")

with open("dummy_invoice.pdf", "wb") as f:
    f.write(b"%PDF-1.4 dummy test invoice content")
with open("dummy_invoice.pdf", "rb") as f:
    r = requests.post(f"{BASE}/purchases/{grn_id}/invoice", headers=auth(purch_tok), files={"file": ("invoice.pdf", f, "application/pdf")})
check("Invoice PDF upload", r.status_code == 200, r.text)

r = requests.get(f"{BASE}/purchases?material_code=MC001", headers=auth(admin_tok))
check("List purchase history", r.status_code == 200 and len(r.json()) >= 1)

# ---------- EMPLOYEE REQUEST -> AUTO ISSUE ----------
r = requests.get(f"{BASE}/materials/MC001", headers=auth(admin_tok))
stock_before_req = float(r.json()["current_qty"])

r = requests.post(f"{BASE}/employee-requests", headers=auth(worker_tok), json={
    "material_code": "MC001", "requested_qty": 30, "department": "Machining", "job_card_no": "JC-777", "purpose": "Batch run"
})
check("Worker raises employee request", r.status_code == 201, r.text)
req_id = r.json()["id"]

r = requests.patch(f"{BASE}/employee-requests/{req_id}/decision", headers=auth(store_tok), json={"action": "approve"})
check("Store manager approves request", r.status_code == 200 and r.json()["status"] == "completed", r.text)

r = requests.get(f"{BASE}/materials/MC001", headers=auth(admin_tok))
stock_after_req = float(r.json()["current_qty"])
check("Stock auto-deducted by request qty", stock_after_req == stock_before_req - 30, f"before={stock_before_req} after={stock_after_req}")

r = requests.get(f"{BASE}/issues?job_card_no=JC-777", headers=auth(admin_tok))
check("Auto-generated Issue visible with correct job card", r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["job_card_no"] == "JC-777")

r = requests.post(f"{BASE}/employee-requests", headers=auth(worker_tok), json={"material_code": "MC001", "requested_qty": 5, "department": "Machining"})
req_id2 = r.json()["id"]
r = requests.patch(f"{BASE}/employee-requests/{req_id2}/decision", headers=auth(store_tok), json={"action": "reject", "rejection_reason": "Not required this week"})
check("Reject request path", r.status_code == 200 and r.json()["status"] == "rejected")

r = requests.post(f"{BASE}/employee-requests", headers=auth(worker_tok), json={"material_code": "MC001", "requested_qty": 999999, "department": "Machining"})
req_id3 = r.json()["id"]
r = requests.patch(f"{BASE}/employee-requests/{req_id3}/decision", headers=auth(store_tok), json={"action": "approve"})
check("Approve blocked when insufficient stock", r.status_code == 400, r.text)

# ---------- DIRECT ISSUE / ROUTE CARD ----------
r = requests.get(f"{BASE}/materials/MC002", headers=auth(admin_tok))
mc002_before = float(r.json()["current_qty"])

r = requests.post(f"{BASE}/issues", headers=auth(store_tok), json={
    "material_code": "MC002", "job_card_no": "JC-888", "production_order_no": "PO-2026-045",
    "part_number": "PN-556", "machine": "CNC-04", "operation": "Turning", "department": "Machining",
    "shift": "Day", "required_qty": 60, "issue_qty": 60, "remark": "Route card direct issue"
})
check("Direct route-card issue created", r.status_code == 201, r.text)
issue_id = r.json()["id"]

r = requests.get(f"{BASE}/materials/MC002", headers=auth(admin_tok))
mc002_after = float(r.json()["current_qty"])
check("Route-card issue deducted stock", mc002_after == mc002_before - 60, f"before={mc002_before} after={mc002_after}")

r = requests.patch(f"{BASE}/issues/{issue_id}/consumption", headers=auth(worker_tok), json={"consumed_qty": 55, "completion_status": "completed"})
check("Update consumption (pending qty tracking)", r.status_code == 200 and float(r.json()["consumed_qty"]) == 55)

# ---------- RETURNS ----------
r = requests.post(f"{BASE}/returns", headers=auth(store_tok), json={
    "material_code": "MC002", "return_type": "unused", "qty": 5, "reference_issue_id": issue_id, "reason": "Excess material returned to store"
})
check("Return: unused material", r.status_code == 201, r.text)

r = requests.post(f"{BASE}/returns", headers=auth(store_tok), json={
    "material_code": "MC001", "return_type": "vendor_return", "qty": 10, "supplier_id": supplier_id, "reason": "Quality issue"
})
check("Return: vendor return", r.status_code == 201, r.text)

r = requests.post(f"{BASE}/returns", headers=auth(store_tok), json={
    "material_code": "MC001", "return_type": "rejected", "qty": 3, "reason": "Rejected in QC"
})
check("Return: rejected material", r.status_code == 201, r.text)

r = requests.post(f"{BASE}/returns", headers=auth(store_tok), json={
    "material_code": "MC001", "return_type": "adjustment", "adjustment_qty": -2, "reason": "Physical count correction"
})
check("Return: stock adjustment", r.status_code == 201, r.text)

r = requests.get(f"{BASE}/returns?material_code=MC001", headers=auth(admin_tok))
check("List returns", r.status_code == 200 and len(r.json()) >= 3)

# ---------- INVENTORY ----------
r = requests.get(f"{BASE}/inventory/batches?material_code=MC001", headers=auth(admin_tok))
check("FIFO batch tracking", r.status_code == 200)

r = requests.get(f"{BASE}/inventory/ledger?material_code=MC001", headers=auth(admin_tok))
check("Stock ledger (full movement history)", r.status_code == 200 and len(r.json()) > 0)

r = requests.get(f"{BASE}/inventory/valuation", headers=auth(admin_tok))
check("Stock valuation view", r.status_code == 200)

r = requests.get(f"{BASE}/inventory/aging", headers=auth(admin_tok))
check("Stock aging view", r.status_code == 200)

r = requests.get(f"{BASE}/inventory/summary", headers=auth(admin_tok))
check("Inventory summary (opening/current/reserved/available)", r.status_code == 200)

# ---------- ALERTS ----------
r = requests.get(f"{BASE}/alerts/low-stock", headers=auth(admin_tok))
check("Low stock alert view", r.status_code == 200)

r = requests.get(f"{BASE}/alerts/high-stock", headers=auth(admin_tok))
check("High stock alert view", r.status_code == 200)

r = requests.get(f"{BASE}/alerts", headers=auth(admin_tok))
check("Alerts list (DB trigger-generated)", r.status_code == 200)
open_alerts = [a for a in r.json() if not a["is_resolved"]]
if open_alerts:
    aid = open_alerts[0]["id"]
    r = requests.patch(f"{BASE}/alerts/{aid}/resolve", headers=auth(store_tok))
    check("Resolve an alert", r.status_code == 200 and r.json()["is_resolved"] == True)
else:
    check("Resolve an alert", True, "skipped - no open alerts to resolve")

r = requests.post(f"{BASE}/alerts/MC003/confirm-high-stock-purchase", headers=auth(purch_tok))
check("High-stock purchase confirmation endpoint", r.status_code == 200)

# ---------- NOTIFICATIONS ----------
r = requests.get(f"{BASE}/notifications", headers=auth(admin_tok))
check("List notifications", r.status_code == 200)

r = requests.get(f"{BASE}/notifications/unread-count", headers=auth(admin_tok))
check("Unread notification count", r.status_code == 200 and "unread_count" in r.json())

r = requests.patch(f"{BASE}/notifications/read-all", headers=auth(admin_tok))
check("Mark all notifications read", r.status_code == 200)

# ---------- DASHBOARD ----------
r = requests.get(f"{BASE}/dashboard", headers=auth(admin_tok))
d = r.json()
check("Dashboard loads with all KPIs", r.status_code == 200 and all(k in d for k in [
    "total_stock_qty", "total_stock_value", "todays_purchase_count", "todays_issue_count",
    "low_stock_count", "high_stock_count", "monthly_consumption", "purchase_trend",
    "issue_trend", "department_consumption"
]))
check("Dashboard reflects today's GRN", d["todays_purchase_count"] >= 1)
check("Dashboard reflects today's issues", d["todays_issue_count"] >= 1)

# ---------- REPORTS ----------
for rpt in ["purchase", "issue", "supplier", "consumption", "department", "stock"]:
    r = requests.get(f"{BASE}/reports/{rpt}", headers=auth(admin_tok))
    check(f"Report JSON: {rpt}", r.status_code == 200, r.text[:200])
    r = requests.get(f"{BASE}/reports/{rpt}/export/excel", headers=auth(admin_tok))
    check(f"Report Excel export: {rpt}", r.status_code == 200)
    r = requests.get(f"{BASE}/reports/{rpt}/export/csv", headers=auth(admin_tok))
    check(f"Report CSV export: {rpt}", r.status_code == 200)

# ---------- RBAC edge cases ----------
r = requests.delete(f"{BASE}/materials/TESTMAT01", headers=auth(store_tok))
check("store_manager blocked from deleting material (admin-only)", r.status_code == 403)

r = requests.delete(f"{BASE}/materials/TESTMAT01", headers=auth(admin_tok))
check("Admin can deactivate material", r.status_code == 204)

# ---------- SUMMARY ----------
passed = sum(1 for s,_,_ in results if s == "PASS")
failed = sum(1 for s,_,_ in results if s == "FAIL")
print(f"\n{'='*50}\nTOTAL: {len(results)}  PASSED: {passed}  FAILED: {failed}\n{'='*50}")
if failed:
    print("\nFAILED TESTS:")
    for s,n,d in results:
        if s == "FAIL":
            print(f" - {n}: {d}")
sys.exit(1 if failed else 0)
