# config.py
import os
from typing import Optional
from urllib.parse import quote_plus
from pathlib import Path
from dotenv import load_dotenv

# ────────────────────────────────
# Load environment variables FIRST
# ────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# ────────────────────────────────
# Environment Variables
# ────────────────────────────────
PHONE_ID: str = os.getenv("WHATSAPP_PHONE_ID", "")
TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
VERIFY_TOKEN: str = os.getenv("VERIFY_TOKEN", "")
CALLBACK_URL: str = os.getenv("CALLBACK_URL", "")

# Support both FB_ and META_ prefixes
APP_ID: Optional[str] = os.getenv("FB_APP_ID") or os.getenv("META_APP_ID")
APP_SECRET: Optional[str] = os.getenv("FB_APP_SECRET") or os.getenv("META_APP_SECRET")

WEBHOOK_DELAY: float = float(os.getenv("WEBHOOK_CHALLENGE_DELAY", "0"))
VALIDATE_UPDATES: bool = os.getenv("VALIDATE_UPDATES", "true").lower() not in ("0", "false", "no")

# Flow configuration (optional)
FLOW_ID: Optional[str] = os.getenv("FLOW_ID")
FLOW_TOKEN: Optional[str] = os.getenv("FLOW_TOKEN")
FLOW_CTA: str = os.getenv("FLOW_CTA", "Open")
FLOW_ACTION: str = os.getenv("FLOW_ACTION", "navigate")
FLOW_SCREEN: Optional[str] = os.getenv("FLOW_SCREEN")

# Buffer settings
MAX_BUFFER: int = int(os.getenv("MESSAGE_BUFFER", "200"))

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ────────────────────────────────
# Database Configuration
# ────────────────────────────────
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "whatspy_db")

# Build DATABASE_URL with proper URL encoding
if DB_PASSWORD:
    # URL-encode the password to handle special characters
    encoded_password = quote_plus(DB_PASSWORD)
    DATABASE_URL = f"postgresql://neondb_owner:npg_qAK3fB1JrCXH@ep-bitter-truth-a4padv8v-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
else:
    # Fallback to environment variable
    DATABASE_URL = os.getenv("DATABASE_URL", f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# ────────────────────────────────
# Authentication Configuration
# ────────────────────────────────
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin@123")
SESSION_SECRET_KEY: str = os.getenv("SESSION_SECRET_KEY", "change-this-to-a-random-secret-key-min-32-chars")

# Session settings
SESSION_MAX_AGE: int = 86400  # 24 hours in seconds

# ────────────────────────────────
# JWT Configuration (for Django CRM integration)
# ────────────────────────────────
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")  # MUST match Django app's SECRET_KEY
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

if not JWT_SECRET_KEY:
    import warnings
    warnings.warn("JWT_SECRET_KEY not set! JWT authentication will not work.")