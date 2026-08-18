# 🚀 Updates Implemented - Request Form + Route Card

Date: 16-Aug-2026 | Status: Ready to Deploy

---

## **UPDATE 1️⃣: Searchable Material Dropdown (Type-Ahead)**

### Location:
`chanda_frontend/templates/pages/request-form.html` (fully rewritten)

### What Changed:
- **Before:** Simple `<select>` dropdown (scroll only)
- **After:** Searchable autocomplete field with live filtering

### How It Works:
1. User starts typing material code or name (e.g., "CN001" or "KNITTED")
2. Dropdown shows top 10 matching materials
3. Display shows: Code, Name, Available Qty
4. User clicks or presses Enter to select
5. Selection highlights in the dropdown and closes automatically

### Features:
- ✅ Type-ahead search (instant filtering)
- ✅ Shows availability for each material
- ✅ UOM (Unit of Measurement) displayed
- ✅ Smooth hover effects
- ✅ Keyboard navigation (Enter key to add)
- ✅ Clicking anywhere else closes the dropdown

### Code Example:
```javascript
// When user types, show matching materials
const matches = allMaterials.filter(m => 
    m.material_code.toLowerCase().includes(search) || 
    m.material_name.toLowerCase().includes(search)
).slice(0, 10);
```

---

## **UPDATE 2️⃣: Multiple Items Selection (Line Items)**

### Location:
`chanda_frontend/templates/pages/request-form.html` (new line items section)

### What Changed:
- **Before:** Single material per request
- **After:** User can add multiple materials in ONE request

### How It Works:
1. Search and select first material, enter qty
2. Click "Add" button → Material added to table
3. Search and select second material, enter qty
4. Click "Add" button → Added to same table
5. Repeat up to 20 items per request
6. Submit once → Creates all requests at once

### UI Changes:
- New "Add Materials" section at top
- Search input + Qty input + Add button
- Line items table showing added materials
- Delete button to remove any item before submitting

### Features:
- ✅ Can add 1-20 items in single request
- ✅ Real-time stock availability check
- ✅ Shows "Backorder" badge if qty > available
- ✅ Department, Job Card, Part Number shared for all items
- ✅ Each item gets its own row in the table

### Frontend Logic:
```javascript
// Array to track all added items
let lineItems = [
    {material_code: 'CN001', requested_qty: 50, available_qty: 100},
    {material_code: 'CN005', requested_qty: 10, available_qty: 5}
];

// On submit, send as:
{
    department: "Production",
    job_card_no: "JC-001",
    items: [
        {material_code: 'CN001', requested_qty: 50},
        {material_code: 'CN005', requested_qty: 10}
    ]
}
```

---

## **UPDATE 3️⃣: Lot No. on Route Card (More Prominent)**

### Location:
`chanda_frontend/templates/pages/route-card-print.html` (line 103)

### What Changed:
- Field label changed from "MTC No / Heat No.:" to **"Lot No. / MTC No / Heat No.:"**
- Lot No. now has **light red background highlight** for visibility
- Still pulls `first.lot_no` from database (auto-generated series)

### Display:
```
Lot No. / MTC No / Heat No.:  [LOT-000001]  (highlighted in light red)
```

### Why:
- Lot No. is critical for traceability
- Visual highlight makes it stand out on the printed route card
- Clear link between Purchase Lot No → Issue Lot No → Route Card

### Verification:
The Lot No. flow is:
1. **Purchase/GRN Created** → Backend auto-generates `LOT-000001`
2. **Issue Created** → `issue.lot_no` copied from purchase batch_no
3. **Route Card Printed** → Shows `LOT-000001` in "Lot No." field ✅

---

## **Backend Changes**

### New Schema (chanda_backend/app/schemas/issues.py):
```python
class EmployeeRequestLineItem(BaseModel):
    material_code: str
    requested_qty: Decimal

class EmployeeRequestBulkIn(BaseModel):
    department: str
    job_card_no: Optional[str] = None
    part_number: Optional[str] = None
    purpose: Optional[str] = None
    items: List[EmployeeRequestLineItem]  # 1-20 items
```

### New Endpoint (chanda_backend/app/api/v1/issues.py):
```python
@router.post("/employee-requests/bulk", status_code=201)
def create_bulk_request(payload: EmployeeRequestBulkIn, ...):
    """Create multiple material requests at once"""
    # Creates separate EmployeeRequest record for each item
    # Links all by department/job_card
    # Returns first request_no as reference
```

### Updated API Method (chanda_frontend/static/js/api.js):
```javascript
static async createRequest(data) {
    if (data.items && Array.isArray(data.items)) {
        // Bulk: Use /employee-requests/bulk endpoint
        return this.request('/employee-requests/bulk', { method: 'POST', body: data });
    } else {
        // Single: Use /employee-requests endpoint (backward compatible)
        return this.request('/employee-requests', { method: 'POST', body: data });
    }
}
```

---

## **Files Modified**

| File | Changes | Lines |
|------|---------|-------|
| `chanda_frontend/templates/pages/request-form.html` | Complete rewrite - searchable dropdown + multi-item | 320→450 |
| `chanda_frontend/static/js/api.js` | Updated createRequest method | +8 lines |
| `chanda_frontend/templates/pages/route-card-print.html` | Lot No. highlighting + label update | +2 lines |
| `chanda_backend/app/schemas/issues.py` | Added EmployeeRequestBulkIn schema | +18 lines |
| `chanda_backend/app/api/v1/issues.py` | Added create_bulk_request endpoint | +53 lines |

---

## **Testing Checklist**

### Frontend:
- [ ] Search for material using code (e.g., "CN001") — should filter and show
- [ ] Search for material using name (e.g., "KNITTED") — should filter and show
- [ ] Type garbage (e.g., "ZZZZ") — should show "No suggestions"
- [ ] Add material with qty less than available — no warning
- [ ] Add material with qty more than available — show "Backorder" badge
- [ ] Add same material twice — should show error "already added"
- [ ] Add 5 different materials — all show in table
- [ ] Delete one item from table — removes from list
- [ ] Submit empty form — error "Add at least one material"
- [ ] Submit with all fields filled (5 items) — should create all 5 requests

### Backend:
- [ ] Check `/employee-requests/bulk` endpoint exists
- [ ] POST with 3 items → 3 EmployeeRequest records created
- [ ] All 3 records have same department/job_card/part_number
- [ ] Response shows "Created 3 requests in bulk starting from REQ-XXX"
- [ ] Each request gets its own request_no (REQ-001, REQ-002, REQ-003)

### Route Card:
- [ ] Print route card → Lot No. field visible and highlighted
- [ ] Lot No. matches the source Purchase Lot No.
- [ ] Background color is light red (good visibility)

---

## **Deployment Steps**

### 1. **Update Backend**
```bash
cd chanda_backend
pip install -r requirements.txt  # Ensure all deps
alembic upgrade head              # Run migrations
```

### 2. **Update Frontend**
```bash
cd chanda_frontend
# No new dependencies — just code changes
```

### 3. **Restart Services**
```bash
docker-compose down
docker-compose up -d
```

### 4. **Quick Smoke Test**
- Login as production user
- Go to `/requests/new`
- Try searchable dropdown
- Try adding 3 materials
- Submit

---

## **Backward Compatibility**

✅ **Single Request API Still Works:**
```python
POST /employee-requests
{
    "material_code": "CN001",
    "requested_qty": 50,
    "department": "Production"
}
```

✅ **Bulk Request API (NEW):**
```python
POST /employee-requests/bulk
{
    "department": "Production",
    "items": [
        {"material_code": "CN001", "requested_qty": 50},
        {"material_code": "CN005", "requested_qty": 10}
    ]
}
```

Both work side-by-side. Frontend automatically chooses the right endpoint based on payload structure.

---

## **Known Limitations**

- Max 20 items per bulk request (configurable in schema)
- Each item creates separate request record (not line items in single record)
- Lot No. on Route Card is already present, just enhanced visually

---

## **Future Improvements** (Optional)

1. Batch approval — approve all 5 requests at once
2. Request grouping — show all related requests together on /requests page
3. Partial completion — each item tracked separately for partial fulfillment
4. Export — export all line items as Excel

---

**Status:** ✅ Ready to Deploy  
**Testing:** All manual test cases documented  
**Rollback:** Code is backward compatible, no migrations needed

