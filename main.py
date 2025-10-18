# main.py
import os
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from pywa import WhatsApp

# ────────────────────────────────
# Load environment variables FIRST
# ────────────────────────────────
# Get the directory where main.py is located
BASE_DIR = Path(__file__).resolve().parent

# Load .env from the same directory as main.py
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# Now import config (after .env is loaded)
from routers import chat, campaigns, templates
from config import (
    PHONE_ID, TOKEN, VERIFY_TOKEN, CALLBACK_URL,
    APP_ID, APP_SECRET, WEBHOOK_DELAY, VALIDATE_UPDATES,
    MAX_BUFFER
)

# ────────────────────────────────
# Logging setup
# ────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("whatspy")

if not PHONE_ID or not TOKEN or not VERIFY_TOKEN:
    log.warning("Missing one of WHATSAPP_PHONE_ID / WHATSAPP_TOKEN / VERIFY_TOKEN")

# ────────────────────────────────
# Jinja2 Templates for HTML rendering
# ────────────────────────────────
jinja_templates = Jinja2Templates(directory="templates")

# ────────────────────────────────
# FastAPI app
# ────────────────────────────────
app = FastAPI(title="Whatspy (PyWa + FastAPI)", version="2.0.0")

# ────────────────────────────────
# Build WhatsApp client kwargs
# ────────────────────────────────
wa_kwargs = dict(
    phone_id=PHONE_ID,
    token=TOKEN,
    server=app,
    verify_token=VERIFY_TOKEN,
    webhook_challenge_delay=WEBHOOK_DELAY,
)

if not VALIDATE_UPDATES:
    wa_kwargs["validate_updates"] = False
elif APP_SECRET:
    wa_kwargs["app_secret"] = APP_SECRET
else:
    log.warning("No APP_SECRET provided; signature validation disabled.")

if APP_ID and APP_SECRET and CALLBACK_URL:
    wa_kwargs.update(app_id=APP_ID, app_secret=APP_SECRET, callback_url=CALLBACK_URL)
elif CALLBACK_URL:
    log.warning("CALLBACK_URL set but APP_ID/APP_SECRET missing; skipping auto-registration.")

# Create WhatsApp client
wa = WhatsApp(**wa_kwargs)

# ────────────────────────────────
# Initialize routers with WA client
# ────────────────────────────────
chat.init_wa_client(wa)
campaigns.init_wa_client(wa)
templates.init_wa_client(wa)

# ────────────────────────────────
# Include routers
# ────────────────────────────────
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(campaigns.router, prefix="/api", tags=["Campaigns"])
app.include_router(templates.router, prefix="/api", tags=["Templates"])

# ────────────────────────────────
# Health & Index
# ────────────────────────────────
@app.get("/healthz", summary="Health Check")
def health():
    return {
        "status": "ok",
        "phone_id_ok": bool(PHONE_ID),
        "token_ok": bool(TOKEN),
        "verify_token_ok": bool(VERIFY_TOKEN),
        "callback_url_registered": bool(APP_ID and APP_SECRET and CALLBACK_URL),
        "buffer_size": MAX_BUFFER,
    }

@app.get("/", include_in_schema=False)
def index():
    return {
        "ok": True,
        "version": "2.0.0",
        "see": ["/healthz", "/chat", "/dashboard", "/docs"],
    }

# ────────────────────────────────
# UI Routes
# ────────────────────────────────
@app.get("/chat", include_in_schema=False)
def chat_ui(request: Request):
    return jinja_templates.TemplateResponse("chat.html", {"request": request})

@app.get("/dashboard", include_in_schema=False)
def dashboard(request: Request):
    return jinja_templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "phone_id": PHONE_ID,
            "webhook": CALLBACK_URL or "(not set)",
            "verify_token": VERIFY_TOKEN,
            "buffer_size": MAX_BUFFER,
        },
    )