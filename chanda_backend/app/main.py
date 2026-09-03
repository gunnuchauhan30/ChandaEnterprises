import logging
import logging.handlers
import os
import traceback
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.limiter import limiter
from app.api.v1.router import api_router
from app.db.session import SessionLocal, engine
from app.services.audit import log_error
from app.services.scheduled_jobs import start_scheduler
from app.services.seed_materials import seed_materials_if_empty

# --- Logging: console + rotating file, so logs survive process restarts and
# don't grow unbounded on disk (production requirement; console-only logging
# is fine for local dev but disappears on server reboot / restarts). ---
os.makedirs("logs", exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    "logs/chanda.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(), _file_handler])
logger = logging.getLogger("chanda")

app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise Store Management System API — Material Master, Purchase/GRN, "
                "Inventory, Issue/Route Card, Returns, Alerts, Reports.",
    version="1.0.0",
    # In production, hide interactive API docs unless explicitly enabled --
    # publicly exposed Swagger/Redoc on a live ERP is an unnecessary attack
    # surface (schema disclosure, "try it out" against prod data).
    docs_url="/api/docs" if settings.ENV != "production" else None,
    redoc_url="/api/redoc" if settings.ENV != "production" else None,
    openapi_url="/api/openapi.json" if settings.ENV != "production" else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Belt-and-suspenders: Railway assigns/changes *.up.railway.app subdomains
    # for this app's own services, and the CORS_ORIGINS env var has drifted
    # out of sync with the live frontend URL more than once. Trust any
    # railway.app subdomain in addition to the explicit allow-list above so
    # a stale/missing env var never hard-blocks the app's own frontend.
    allow_origin_regex=r"https://.*\.up\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

_scheduler = None


@app.on_event("startup")
def _launch_scheduler():
    global _scheduler
    # Guard against double-start under `uvicorn --reload` (spawns 2 processes)
    # and under gunicorn multi-worker: only the first worker to grab this
    # env flag runs the scheduler, so the summary email doesn't fire N times.
    if os.environ.get("CHANDA_SCHEDULER_STARTED") == "1":
        return
    os.environ["CHANDA_SCHEDULER_STARTED"] = "1"
    _scheduler = start_scheduler()


@app.on_event("startup")
def _seed_materials():
    # Idempotent (ON CONFLICT DO NOTHING at the DB level) so it's safe even
    # if every gunicorn worker runs this at the same time on a fresh deploy.
    seed_materials_if_empty(engine)


@app.on_event("shutdown")
def _stop_scheduler():
    if _scheduler:
        _scheduler.shutdown(wait=False)


@app.get("/", tags=["Health"])
def root():
    return {"app": settings.APP_NAME, "status": "running", "docs": "/api/docs"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


def _write_error_log(request: Request, status_code: int, message: str, tb: str = ""):
    try:
        db = SessionLocal()
        user_id = None
        # best-effort: don't fail error logging if auth wasn't resolved
        log_error(db, str(request.url.path), request.method, status_code, message, tb, user_id)
        db.close()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to write error log")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code >= 500:
        _write_error_log(request, exc.status_code, str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error("Unhandled exception: %s\n%s", exc, tb)
    _write_error_log(request, 500, str(exc), tb)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
