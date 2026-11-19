import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy.engine import URL


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

APP_ENV = os.getenv("APP_ENV", "development").lower()

# Allow a full connection string for any SQLAlchemy-supported database
# (MySQL, Microsoft SQL Server, PostgreSQL, ...). When it is provided it
# takes precedence over the individual MYSQL_* variables.
_database_url_env = os.getenv("DATABASE_URL")

if _database_url_env:
    database_url = _database_url_env
else:
    database_url = URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE"),
    )

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be configured in backend/.env")
if APP_ENV == "production" and len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must contain at least 32 characters in production")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")
if not urlparse(FRONTEND_URL).scheme or not urlparse(FRONTEND_URL).netloc:
    raise RuntimeError("FRONTEND_URL must be an absolute URL")

# Browser origins allowed to call the API (comma separated). Falls back to the
# local Vite dev servers outside production; production must list real origins.
_default_cors = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", _default_cors if APP_ENV != "production" else FRONTEND_URL).split(",")
    if origin.strip()
]
# Interactive API docs are useful in development but are an information leak in production.
ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false" if APP_ENV == "production" else "true").strip().lower() in {"1", "true", "yes", "on"}
# Set to true only when the app runs behind a reverse proxy you control (nginx, etc.)
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").strip().lower() in {"1", "true", "yes", "on"}
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "")
if not 1 <= SMTP_PORT <= 65535:
    raise RuntimeError("SMTP_PORT must be between 1 and 65535")

# WhatsApp Cloud API (Meta). Left unset by default so the app never sends
# messages until an operator deliberately configures the channel.
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "").strip()
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0")

# Daily notification automation. Disabled by default so local and test
# environments never send reminders. Even when enabled it starts as a dry run
# until an operator explicitly opts into live delivery.
def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


AUTOMATION_ENABLED = _env_flag("AUTOMATION_ENABLED", False)
AUTOMATION_DRY_RUN = _env_flag("AUTOMATION_DRY_RUN", True)
AUTOMATION_INTERVAL_HOURS = float(os.getenv("AUTOMATION_INTERVAL_HOURS", "24"))
AUTOMATION_FEE_REMINDER_DAYS = int(os.getenv("AUTOMATION_FEE_REMINDER_DAYS", "3"))
AUTOMATION_COOLDOWN_DAYS = int(os.getenv("AUTOMATION_COOLDOWN_DAYS", "3"))
AUTOMATION_AUTO_CERTIFICATES = _env_flag("AUTOMATION_AUTO_CERTIFICATES", True)
AUTOMATION_CHANNELS = [
    channel.strip()
    for channel in os.getenv("AUTOMATION_CHANNELS", "email").split(",")
    if channel.strip() in {"email", "whatsapp"}
] or ["email"]

# Finance: GST is stored inclusively inside fee/expense amounts. This rate is
# used only to derive the tax component for the GST report; change it per
# deployment without touching code.
GST_RATE_PERCENT = float(os.getenv("GST_RATE_PERCENT", "18"))

# Fee receipt and student payment-claim emails. The default is a dry run so a
# developer clicking through the flow never emails a real student. Set
# FEE_RECEIPT_EMAIL_MODE=live to deliver through SMTP.
FEE_RECEIPT_EMAIL_MODE = os.getenv("FEE_RECEIPT_EMAIL_MODE", "dry_run").strip().lower()
if FEE_RECEIPT_EMAIL_MODE not in {"dry_run", "live"}:
    FEE_RECEIPT_EMAIL_MODE = "dry_run"


def payment_emails_are_dry_run() -> bool:
    return FEE_RECEIPT_EMAIL_MODE != "live"

# Online admission registration-fee payments. Manual is the default so local
# development and automated tests never contact a payment gateway. Set
# ADMISSION_PAYMENT_PROVIDER=razorpay together with Razorpay keys to enable the
# optional online flow.
ADMISSION_PAYMENT_PROVIDER = os.getenv("ADMISSION_PAYMENT_PROVIDER", "manual").strip().lower()
if ADMISSION_PAYMENT_PROVIDER not in {"manual", "razorpay"}:
    ADMISSION_PAYMENT_PROVIDER = "manual"
ADMISSION_PAYMENT_CURRENCY = os.getenv("ADMISSION_PAYMENT_CURRENCY", "INR").strip().upper() or "INR"
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
RAZORPAY_API_URL = os.getenv("RAZORPAY_API_URL", "https://api.razorpay.com/v1").rstrip("/")