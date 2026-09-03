from fastapi import APIRouter

from app.api.v1 import (
    auth, materials, suppliers, purchases, issues, inventory, alerts, dashboard, reports,
    critical_spares, history,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(materials.router)
api_router.include_router(suppliers.router)
api_router.include_router(purchases.router)
api_router.include_router(issues.router)
api_router.include_router(inventory.router)
api_router.include_router(alerts.router)
api_router.include_router(dashboard.router)
api_router.include_router(reports.router)
api_router.include_router(critical_spares.router)
api_router.include_router(history.router)

# Safety alias: keep this working even if main.py ever imports this module
# as `import app.api.v1.router as api_router` and does `api_router.router`
# instead of `from app.api.v1.router import api_router`. Both styles have
# been used in this project before and caused a boot crash when mismatched.
router = api_router
