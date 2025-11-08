# main.py
import os
import logging
from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware

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
    MAX_BUFFER, SESSION_SECRET_KEY, SESSION_MAX_AGE,
    JWT_SECRET_KEY
)
from database import init_db, test_db_connection
from auth import authenticate_user
from dependencies import require_auth, optional_auth, require_auth_flexible
from jwt_auth import get_current_user, get_current_tenant_id, require_whatsapp_access

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

if not JWT_SECRET_KEY:
    log.warning("JWT_SECRET_KEY not configured - JWT authentication disabled!")

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
# FastAPI app with Swagger documentation
# ────────────────────────────────
app = FastAPI(
    title="Whatspy - Multi-Tenant WhatsApp API",
    description="""
    # WhatsApp Business API Integration
    
    Multi-tenant WhatsApp messaging API with JWT authentication.
    
    ## Authentication
    
    This API uses JWT Bearer token authentication. Include your JWT token in the Authorization header:
    
    ```
    Authorization: Bearer <your-jwt-token>
    ```
    
    ## Tenant Isolation
    
    All data is automatically filtered by tenant_id extracted from the JWT token.
    
    ## Modules
    
    - **Messages**: Send and receive WhatsApp messages
    - **Contacts**: Manage contact information  
    - **Groups**: Manage WhatsApp groups
    - **Campaigns**: Broadcast messages to multiple recipients
    - **Templates**: Manage reusable message templates
    """,
    version="3.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    openapi_url="/openapi.json"
)

# Add CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",  # Vite default port
        "https://yourdomain.com",  # Add your production domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add session middleware for legacy session-based auth
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
)

# Only add validate_updates if explicitly set to False
if not VALIDATE_UPDATES:
    wa_kwargs["validate_updates"] = False

# Don't add app_secret - not supported in current PyWa version
# The webhook signature validation will be handled by Meta's verification

log.info("Creating WhatsApp client...")

# Create WhatsApp client
try:
    wa = WhatsApp(**wa_kwargs)
    log.info("✅ WhatsApp client created successfully")
except Exception as e:
    log.error(f"❌ Failed to create WhatsApp client: {e}")
    log.warning("⚠️  Running without WhatsApp client - API endpoints only")
    wa = None

# ────────────────────────────────
# Initialize routers with WA client
# ────────────────────────────────
from routers import chat, campaigns, templates, contacts, groups

# Initialize routers with WA client (only if available)
if wa:
    chat.init_wa_client(wa)
    campaigns.init_wa_client(wa)
    templates.init_wa_client(wa)
    log.info("✅ WhatsApp handlers registered")
else:
    log.warning("⚠️  WhatsApp client not available - webhooks disabled")
    log.warning("⚠️  API endpoints will work, but message sending requires WhatsApp setup")

# ────────────────────────────────
# Include routers with authentication
# ────────────────────────────────
# API routes protected by session auth (for HTML UI) or JWT auth (for React)
# Session auth allows the built-in HTML UI to work
app.include_router(
    chat.router, 
    prefix="/api", 
    tags=["Chat"],
    dependencies=[Depends(require_auth)]  # Session auth for HTML UI
)
app.include_router(
    campaigns.router, 
    prefix="/api", 
    tags=["Campaigns"],
    dependencies=[Depends(require_auth)]
)
app.include_router(
    templates.router, 
    prefix="/api", 
    tags=["Templates"],
    dependencies=[Depends(require_auth)]
)
app.include_router(
    contacts.router, 
    prefix="/api", 
    tags=["Contacts"],
    dependencies=[Depends(require_auth)]
)
app.include_router(
    groups.router, 
    prefix="/api", 
    tags=["Groups"],
    dependencies=[Depends(require_auth)]
)

# Mount static files
app.mount("/static", StaticFiles(directory="templates"), name="static")

# ────────────────────────────────
# Public Routes
# ────────────────────────────────

@app.get(
    "/healthz", 
    summary="Health Check",
    tags=["System"],
    response_description="System health status"
)
def health():
    """
    Public health check endpoint.
    
    Returns system status including:
    - Database connectivity
    - WhatsApp API configuration status
    - JWT authentication status
    """
    db_ok = test_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "phone_id_ok": bool(PHONE_ID),
        "token_ok": bool(TOKEN),
        "verify_token_ok": bool(VERIFY_TOKEN),
        "database_ok": db_ok,
        "jwt_enabled": bool(JWT_SECRET_KEY),
        "buffer_size": MAX_BUFFER,
    }


@app.get("/", include_in_schema=False)
def index(request: Request, username: str = Depends(optional_auth)):
    """Root endpoint - redirect to login or chat"""
    if username:
        return RedirectResponse(url="/chat", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


# ────────────────────────────────
# JWT Test Endpoint (for development)
# ────────────────────────────────

@app.get(
    "/api/auth/verify",
    summary="Verify JWT Token",
    tags=["Authentication"],
    response_description="Token verification result"
)
async def verify_jwt(
    current_user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Verify JWT token and return decoded payload.
    
    Use this endpoint to test your JWT token authentication.
    """
    return {
        "valid": True,
        "user_id": current_user.get("user_id"),
        "tenant_id": tenant_id,
        "email": current_user.get("email"),
        "modules": current_user.get("modules", []),
        "token_payload": current_user
    }


# ────────────────────────────────
# Legacy Authentication Routes (Session-based)
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
        
        # Set session
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
# Protected UI Routes (Session-based)
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
    """Handle HTTP exceptions"""
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)  # Different port from CRM APIs