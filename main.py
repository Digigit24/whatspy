# main.py
import os
import logging
from collections import deque
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from pywa import WhatsApp

# ────────────────────────────────
# Env & logging
# ────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("whatspy")

PHONE_ID: str = os.getenv("WHATSAPP_PHONE_ID", "")
TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
VERIFY_TOKEN: str = os.getenv("VERIFY_TOKEN", "")
CALLBACK_URL: str = os.getenv("CALLBACK_URL", "")  # e.g. https://whatsapp.example.com/webhook
APP_ID: Optional[str] = os.getenv("FB_APP_ID")
APP_SECRET: Optional[str] = os.getenv("FB_APP_SECRET")
WEBHOOK_DELAY: float = float(os.getenv("WEBHOOK_CHALLENGE_DELAY", "0"))
VALIDATE_UPDATES: bool = os.getenv("VALIDATE_UPDATES", "true").lower() not in ("0", "false", "no")

MAX_BUFFER = int(os.getenv("MESSAGE_BUFFER", "200"))
templates = Jinja2Templates(directory="templates")

if not PHONE_ID or not TOKEN or not VERIFY_TOKEN:
    log.warning("Missing one of WHATSAPP_PHONE_ID / WHATSAPP_TOKEN / VERIFY_TOKEN")

# ────────────────────────────────
# FastAPI app
# ────────────────────────────────
app = FastAPI(title="Whatspy (PyWa + FastAPI)", version="1.1.0")

# ────────────────────────────────
# In-memory buffers (simple observability)
# ────────────────────────────────
messages_buffer: deque = deque(maxlen=MAX_BUFFER)
statuses_buffer: deque = deque(maxlen=MAX_BUFFER)

def strip_message(m) -> Dict[str, Any]:
    return {
        "id": getattr(m, "id", None),
        "from": getattr(m, "from_user", None),
        "name": getattr(getattr(m, "contact", None), "name", None) if hasattr(m, "contact") else None,
        "type": getattr(m, "type", None),
        "text": getattr(m, "text", None),
        "timestamp": getattr(m, "timestamp", None),
    }

def strip_status(s) -> Dict[str, Any]:
    return {
        "id": getattr(s, "id", None),
        "message_id": getattr(s, "message_id", None),
        "status": getattr(s, "status", None),
        "recipient": getattr(s, "recipient", None),
        "timestamp": getattr(s, "timestamp", None),
    }

# ────────────────────────────────
# Build robust WhatsApp client kwargs
# ────────────────────────────────
wa_kwargs: Dict[str, Any] = dict(
    phone_id=PHONE_ID,
    token=TOKEN,
    server=app,  # mount webhook routes on this FastAPI app
    verify_token=VERIFY_TOKEN,
    webhook_challenge_delay=WEBHOOK_DELAY,
)

# Validation is recommended; you can disable if you don't have APP_SECRET
if not VALIDATE_UPDATES:
    wa_kwargs["validate_updates"] = False
elif APP_SECRET:
    # When provided, pywa can validate `X-Hub-Signature-256`
    wa_kwargs["app_secret"] = APP_SECRET
else:
    # Keep running, but warn (pywa also warns). You can set VALIDATE_UPDATES=false to hide warning.
    log.warning("No FB_APP_SECRET provided; signature validation disabled. Set VALIDATE_UPDATES=false to suppress warning.")

# Only include callback_url if BOTH app creds exist (prevents crash)
if APP_ID and APP_SECRET and CALLBACK_URL:
    wa_kwargs.update(app_id=APP_ID, app_secret=APP_SECRET, callback_url=CALLBACK_URL)
elif CALLBACK_URL:
    log.warning(
        "CALLBACK_URL is set but FB_APP_ID/FB_APP_SECRET missing; "
        "skipping auto-registration to avoid crash. "
        "Set webhook manually in Meta App Dashboard or provide both creds."
    )

# Create WA client (safe — won't raise for missing app creds now)
wa = WhatsApp(**wa_kwargs)

# ────────────────────────────────
# Bot listeners
# ────────────────────────────────
@wa.on_message()
def on_message(client: WhatsApp, message):
    try:
        messages_buffer.appendleft(strip_message(message))
        text = (message.text or "").strip()

        if not text:
            return message.reply_text("I only understand text for now 🙂")

        low = text.lower()
        if low in {"hi", "hello", "hey"}:
            return message.reply_text(
                "👋 Hey! Try:\n"
                "• /help – show commands\n"
                "• /echo <text> – I’ll repeat it\n"
                "• /flow – send a sample Flow (if enabled)\n"
            )

        if low.startswith("/help"):
            return message.reply_text(
                "🧰 Commands:\n"
                "• /help – show this\n"
                "• /echo <text>\n"
                "• /flow – send a sample Flow (requires FLOW_ID / FLOW_TOKEN)\n"
            )

        if low.startswith("/echo"):
            parts = text.split(" ", 1)
            return message.reply_text(parts[1] if len(parts) > 1 else "(nothing to echo)")

        if low.startswith("/flow"):
            flow_id = os.getenv("FLOW_ID")
            flow_token = os.getenv("FLOW_TOKEN")
            flow_cta = os.getenv("FLOW_CTA", "Open")
            flow_action = os.getenv("FLOW_ACTION", "navigate")
            flow_screen = os.getenv("FLOW_SCREEN", None)

            if not flow_id:
                return message.reply_text("No FLOW_ID configured on server.")

            try:
                msg_id = client.send_flow(
                    to=message.from_user,
                    flow_id=flow_id,
                    flow_token=flow_token,
                    flow_cta=flow_cta,
                    flow_action=flow_action,
                    screen=flow_screen,
                )
                return  # success; no need to reply
            except AttributeError:
                return message.reply_text(
                    "Your pywa version may not support send_flow(). Upgrade pywa and ensure Flows are enabled in Meta."
                )
            except Exception as e:
                log.exception("Flow send failed")
                return message.reply_text(f"Flow send failed: {e}")

        # default echo
        return message.reply_text("Echo: " + text)
    except Exception:
        log.exception("on_message failed")

# ────────────────────────────────
# Status listener (PyWa version compatible)
# ────────────────────────────────
_status_decorator = None
if hasattr(wa, "on_status"):
    _status_decorator = wa.on_status()                 # some versions
elif hasattr(wa, "on_message_status"):
    _status_decorator = wa.on_message_status()         # other versions
elif hasattr(wa, "on_statuses"):
    _status_decorator = wa.on_statuses()               # rare naming

if _status_decorator:
    @_status_decorator
    def _status_cb(*args, **kwargs):
        try:
            # Try to pull the status object from common call patterns
            s = kwargs.get("status")
            if s is None and len(args) >= 2:
                s = args[1]  # (client, status)
            if s is not None:
                statuses_buffer.appendleft(strip_status(s))
                log.info("Status update: %s", getattr(s, "status", "unknown"))
        except Exception:
            log.exception("status callback failed")
else:
    log.warning(
        "No status listener decorator found on this pywa version. "
        "Skipping status tracking."
    )

# ────────────────────────────────
# API models
# ────────────────────────────────
class SendTextIn(BaseModel):
    to: str = Field(..., description="WhatsApp phone in international format (no +), e.g., 15551234567")
    text: str = Field(..., min_length=1, max_length=4096)

class FlowSendIn(BaseModel):
    to: str
    flow_id: str
    flow_token: Optional[str] = None
    flow_cta: Optional[str] = "Open"
    flow_action: Optional[str] = "navigate"
    screen: Optional[str] = None

# ────────────────────────────────
# HTTP endpoints
# ────────────────────────────────
@app.get("/healthz", summary="Health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "phone_id_ok": bool(PHONE_ID),
        "token_ok": bool(TOKEN),
        "verify_token_ok": bool(VERIFY_TOKEN),
        "callback_url_registered": bool(APP_ID and APP_SECRET and CALLBACK_URL),
        "buffer_size": MAX_BUFFER,
    }

@app.get("/dashboard", include_in_schema=False)
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "phone_id": PHONE_ID,
            "webhook": CALLBACK_URL or "(not set or not auto-registered)",
            "verify_token": VERIFY_TOKEN,
            "buffer_size": MAX_BUFFER,
            "messages": list(messages_buffer)[:10],
            "statuses": list(statuses_buffer)[:10],
            "endpoints": [
                "GET  /healthz",
                "GET  /dashboard",
                "POST /send/text",
                "POST /send/flow  (if supported)",
                "GET  /messages",
                "GET  /statuses",
                "GET  /docs",
                "GET  /redoc",
            ],
        },
    )

# Keep JSON index lightweight but helpful
@app.get("/", include_in_schema=False)
def index() -> Dict[str, Any]:
    return {
        "ok": True,
        "see": ["/healthz", "/dashboard", "/docs"],
    }

@app.post("/send/text", response_model=Dict[str, Any], summary="Send a text message")
def send_text(payload: SendTextIn):
    try:
        msg_id = wa.send_text(to=payload.to, text=payload.text)
        return {"ok": True, "message_id": msg_id}
    except Exception as e:
        log.exception("send_text failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send/flow", response_model=Dict[str, Any], summary="Send a Flow (if supported)")
def send_flow(payload: FlowSendIn):
    try:
        msg_id = wa.send_flow(
            to=payload.to,
            flow_id=payload.flow_id,
            flow_token=payload.flow_token,
            flow_cta=payload.flow_cta,
            flow_action=payload.flow_action,
            screen=payload.screen,
        )
        return {"ok": True, "message_id": msg_id}
    except AttributeError:
        raise HTTPException(
            status_code=400,
            detail="This pywa version does not support send_flow(). Upgrade pywa and ensure Flows are enabled."
        )
    except Exception as e:
        log.exception("send_flow failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/messages", summary="List recently received messages")
def list_messages(limit: int = Query(50, ge=1, le=MAX_BUFFER)):
    return list(list(messages_buffer)[:limit])

@app.get("/statuses", summary="List recent status updates")
def list_statuses(limit: int = Query(50, ge=1, le=MAX_BUFFER)):
    return list(list(statuses_buffer)[:limit])
