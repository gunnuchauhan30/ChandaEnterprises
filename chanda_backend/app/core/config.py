"""
Central configuration. All values are read from environment variables
(or a .env file in the project root). Nothing is hardcoded so the same
code runs in dev / staging / production by just changing .env.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "Chanda Enterprises - Store Management System"
    ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/chanda_store"

    # --- JWT Auth ---
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_use_a_long_random_value"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8      # 8 hours
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # --- CORS ---
    # Port 5000 is the Flask frontend (see chanda_frontend/Dockerfile / docker-compose.yml).
    # Without it here, every browser-side fetch() from the frontend pages to this
    # API is blocked by CORS and fails silently (looks like "blank page" bugs).
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000", "http://localhost:5000", "http://127.0.0.1:5000",
        "http://localhost:8000", "http://127.0.0.1:8000",
    ]

    # --- Frontend (used to build links inside emails, e.g. password reset) ---
    FRONTEND_URL: str = "http://localhost:5000"

    # --- Stock Alert thresholds (fallback defaults; per-material min/max in DB take priority) ---
    LOW_STOCK_DEFAULT: float = 1500
    HIGH_STOCK_DEFAULT: float = 5000

    # --- Email / SMTP ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@chandaenterprises.com"
    SMTP_FROM_NAME: str = "Chanda Enterprises - Store System"
    SMTP_USE_TLS: bool = True
    EMAIL_ENABLED: bool = False   # flip to True once SMTP creds are filled in .env

    ADMIN_ALERT_EMAILS: List[str] = []
    STORE_MANAGER_ALERT_EMAILS: List[str] = []
    PURCHASE_DEPT_ALERT_EMAILS: List[str] = []

    # --- Scheduled jobs ---
    # Timezone the 12:00 PM daily inventory summary email is scheduled against.
    SCHEDULER_TIMEZONE: str = "Asia/Kolkata"

    # --- File uploads ---
    UPLOAD_DIR: str = "uploads/invoices"
    MAX_UPLOAD_MB: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
