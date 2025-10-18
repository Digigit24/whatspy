# config.py
import os
from typing import Optional

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