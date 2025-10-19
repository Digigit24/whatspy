# main.py
import os
import logging
from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware
from routers import chat, campaigns, templates, contacts, groups
from fastapi.staticfiles import StaticFiles

from pywa import WhatsApp

# ────────────────────────────────
# Load environment variables FIRST
# ────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# Now import config and other modules

from config import (
    PHONE_ID, TOKEN, VERIFY_TOKEN, CALLBACK_URL,
    APP_ID, APP_SECRET, WEBHOOK_DELAY, VALIDATE_UPDATES,
    MAX_BUFFER, SESSION_SECRET_KEY, SESSION_MAX_AGE
)
from database import init_db, test_db_connection
from auth import authenticate_user
from dependencies import require_auth, optional_auth

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
# Initialize Database
# ────────────────────────────────
try:
    log.info("🔄 Initializing database...")
    init_db()
    if test_db_connection():
        log.info("✅ Database initialized and connected")
    else:
        log.error("❌ Database connection test failed")
except Exception as e:
    log.error(f"❌ Database initialization failed: {e}")

# ────────────────────────────────
# Jinja2 Templates
# ────────────────────────────────
jinja_templates = Jinja2Templates(directory="templates")

# ────────────────────────────────
# FastAPI app
# ────────────────────────────────
app = FastAPI(title="Whatspy (PyWa + FastAPI)", version="3.0.0")

# Add session middleware for authentication
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=False  # Set to True in production with HTTPS
)

# ────────────────────────────────
# Build WhatsApp client
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

log.info("WhatsApp client initialized. Webhook registered at root path '/'")

# Create WhatsApp client
wa = WhatsApp(**wa_kwargs)

# ────────────────────────────────
# Initialize routers with WA client
# ────────────────────────────────
chat.init_wa_client(wa)
campaigns.init_wa_client(wa)
templates.init_wa_client(wa)

# ────────────────────────────────
# Include routers with authentication
# ────────────────────────────────
app.include_router(chat.router, prefix="/api", tags=["Chat"], dependencies=[Depends(require_auth)])
app.include_router(campaigns.router, prefix="/api", tags=["Campaigns"], dependencies=[Depends(require_auth)])
app.include_router(templates.router, prefix="/api", tags=["Templates"], dependencies=[Depends(require_auth)])
app.include_router(chat.router, prefix="/api", tags=["Chat"], dependencies=[Depends(require_auth)])
app.include_router(campaigns.router, prefix="/api", tags=["Campaigns"], dependencies=[Depends(require_auth)])
app.include_router(templates.router, prefix="/api", tags=["Templates"], dependencies=[Depends(require_auth)])
app.include_router(contacts.router, prefix="/api", tags=["Contacts"], dependencies=[Depends(require_auth)])
app.include_router(groups.router, prefix="/api", tags=["Groups"], dependencies=[Depends(require_auth)])
app.mount("/static", StaticFiles(directory="templates"), name="static")

# ────────────────────────────────
# Public Routes
# ────────────────────────────────

@app.get("/healthz", summary="Health Check")
def health():
    """Public health check endpoint"""
    db_ok = test_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "phone_id_ok": bool(PHONE_ID),
        "token_ok": bool(TOKEN),
        "verify_token_ok": bool(VERIFY_TOKEN),
        "database_ok": db_ok,
        "buffer_size": MAX_BUFFER,
    }


@app.get("/", include_in_schema=False)
def index(request: Request, username: str = Depends(optional_auth)):
    """Root endpoint - redirect to login or chat"""
    if username:
        return RedirectResponse(url="/chat", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


# ────────────────────────────────
# Authentication Routes
# ────────────────────────────────

@app.get("/login", include_in_schema=False)
def login_page(request: Request, username: str = Depends(optional_auth)):
    """Show login page"""
    if username:
        return RedirectResponse(url="/chat", status_code=303)
    
    error = request.query_params.get("error")
    return jinja_templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error}
    )


@app.post("/login", include_in_schema=False)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    remember: bool = Form(False)
):
    """Handle login form submission"""
    try:
        user = authenticate_user(username, password)
        
        if not user:
            return RedirectResponse(
                url="/login?error=Invalid credentials",
                status_code=303
            )
        
        # Set session (user is now a dict, not SQLAlchemy object)
        request.session["username"] = user["username"]
        if remember:
            request.session["remember"] = True
        
        log.info(f"✅ User '{username}' logged in successfully")
        return RedirectResponse(url="/chat", status_code=303)
        
    except Exception as e:
        log.error(f"❌ Login error: {e}")
        return RedirectResponse(
            url="/login?error=Login failed. Please try again.",
            status_code=303
        )


@app.get("/logout", include_in_schema=False)
def logout(request: Request):
    """Logout and clear session"""
    username = request.session.get("username")
    request.session.clear()
    log.info(f"✅ User '{username}' logged out")
    return RedirectResponse(url="/login", status_code=303)


# ────────────────────────────────
# Protected UI Routes
# ────────────────────────────────

@app.get("/chat", include_in_schema=False)
def chat_ui(request: Request, username: str = Depends(require_auth)):
    """Chat interface - requires authentication"""
    return jinja_templates.TemplateResponse(
        "chat.html",
        {"request": request, "username": username}
    )


@app.get("/logs", include_in_schema=False)
def logs_ui(request: Request, username: str = Depends(require_auth)):
    """Webhook logs interface - requires authentication"""
    return jinja_templates.TemplateResponse(
        "logs.html",
        {"request": request, "username": username}
    )


@app.get("/dashboard", include_in_schema=False)
def dashboard(request: Request, username: str = Depends(require_auth)):
    """Dashboard - requires authentication"""
    return jinja_templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "username": username,
            "phone_id": PHONE_ID,
            "webhook": CALLBACK_URL or "(not set)",
            "verify_token": VERIFY_TOKEN,
            "buffer_size": MAX_BUFFER,
        },
    )


# ────────────────────────────────
# Exception Handlers
# ────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions - redirect 303 to login"""
    if exc.status_code == 303 and exc.headers and exc.headers.get("Location"):
        return RedirectResponse(url=exc.headers["Location"], status_code=303)
    
    # For API calls, return JSON
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    # For page requests, show error or redirect
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=303)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )