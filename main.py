import os
import logging
from collections import deque
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
templates = Jinja2Templates(directory="templates")

from pywa import WhatsApp

# -------------------------------------------------------------------
# Env & logging
# -------------------------------------------------------------------
load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("whatspy")

PHONE_ID: str = os.getenv("WHATSAPP_PHONE_ID", "")
TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
VERIFY_TOKEN: str = os.getenv("VERIFY_TOKEN", "")
CALLBACK_URL: str = os.getenv("CALLBACK_URL", "https://whatsapp.example.com/webhook")
APP_ID: Optional[str] = os.getenv("FB_APP_ID")
APP_SECRET: Optional[str] = os.getenv("FB_APP_SECRET")
WEBHOOK_DELAY: float = float(os.getenv("WEBHOOK_CHALLENGE_DELAY", "0.0"))

if not PHONE_ID or not TOKEN or not VERIFY_TOKEN:
    log.warning("Missing one of WHATSAPP_PHONE_ID / WHATSAPP_TOKEN / VERIFY_TOKEN")

# -------------------------------------------------------------------
# FastAPI app
# -------------------------------------------------------------------
app = FastAPI(title="Whatspy (PyWa + FastAPI)", version="1.0.0")


@app.get("/dashboard", include_in_schema=False)
@app.get("/status", include_in_schema=False)
@app.get("/", include_in_schema=False)  # Override default JSON for homepage
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "phone_id": PHONE_ID,
        "webhook": CALLBACK_URL,
        "verify_token": VERIFY_TOKEN,
        "buffer_size": MAX_BUFFER,
        "messages": list(messages_buffer)[:10],
        "statuses": list(statuses_buffer)[:10],
        "endpoints": [
            "/send/text",
            "/messages",
            "/statuses",
            "/send/flow (if enabled)",
            "/docs (Swagger UI)",
            "/redoc (Redoc UI)"
        ]
    })

# -------------------------------------------------------------------
# PyWa client attach to FastAPI server
# -------------------------------------------------------------------
wa_kwargs: Dict[str, Any] = dict(
    phone_id=PHONE_ID,
    token=TOKEN,
    server=app,                       # attach FastAPI app
    verify_token=VERIFY_TOKEN,        # webhook verification
    callback_url=CALLBACK_URL,        # must be HTTPS & resolvable from Meta
    webhook_challenge_delay=WEBHOOK_DELAY,  # useful on slow boots
)

# Only pass app creds if you actually set them (prevents unexpected kwargs issues)
if APP_ID and APP_SECRET:
    wa_kwargs.update(app_id=APP_ID, app_secret=APP_SECRET)

wa = WhatsApp(**wa_kwargs)

# -------------------------------------------------------------------
# In-memory message store (basic observability)
# -------------------------------------------------------------------
MAX_BUFFER = int(os.getenv("MESSAGE_BUFFER", "200"))
messages_buffer: deque = deque(maxlen=MAX_BUFFER)
statuses_buffer: deque = deque(maxlen=MAX_BUFFER)

def strip_message(m) -> Dict[str, Any]:
    """Safely create a small serializable view of an incoming message."""
    return {
        "id": getattr(m, "id", None),
        "from": getattr(m, "from_user", None),
        "name": getattr(getattr(m, "contact", None), "name", None) if hasattr(m, "contact") else None,
        "type": getattr(m, "type", None),
        "text": getattr(m, "text", None),
        "timestamp": getattr(m, "timestamp", None),
        "raw": getattr(m, "raw", None),
    }

def strip_status(s) -> Dict[str, Any]:
    return {
        "id": getattr(s, "id", None),
        "message_id": getattr(s, "message_id", None),
        "status": getattr(s, "status", None),
        "recipient": getattr(s, "recipient", None),
        "timestamp": getattr(s, "timestamp", None),
        "raw": getattr(s, "raw", None),
    }

# -------------------------------------------------------------------
# Bot: listeners
# -------------------------------------------------------------------
@wa.on_message()
def on_message(client: WhatsApp, message):
    """
    Basic text bot:
      - /help: show commands
      - /echo <text>: echo back
      - hi/hello: quick intro + menu
      - otherwise: simple echo
    """
    try:
        messages_buffer.appendleft(strip_message(message))
        text = (message.text or "").strip()

        if not text:
            return message.reply_text("I only understand text for now 🙂")

        if text.lower() in {"hi", "hello", "hey"}:
            return message.reply_text(
                "👋 Hey! Try:\n"
                "• /help – show commands\n"
                "• /echo <text> – I’ll repeat it\n"
                "• /flow – (if configured) send a sample Flow\n"
            )

        if text.startswith("/help"):
            return message.reply_text(
                "🧰 Commands:\n"
                "• /help – show this\n"
                "• /echo <text>\n"
                "• /flow – send a sample Flow (needs FLOW_ID env)\n"
            )

        if text.startswith("/echo"):
            rest = text.split(" ", 1)
            return message.reply_text(rest[1] if len(rest) > 1 else "(nothing to echo)")

        if text.startswith("/flow"):
            flow_id = os.getenv("FLOW_ID")
            flow_cta = os.getenv("FLOW_CTA", "Open")
            try:
                if not flow_id:
                    return message.reply_text("No FLOW_ID configured on server.")
                # If your PyWa version supports flows, this will work.
                # Otherwise it will raise and we’ll explain how to enable.
                client.send_flow(
                    to=message.from_user,
                    flow_id=flow_id,
                    flow_token=os.getenv("FLOW_TOKEN", None),
                    flow_cta=flow_cta,
                    flow_action="navigate",
                    screen=os.getenv("FLOW_SCREEN", None),
                )
                return
            except Exception as e:
                log.exception("Flow send failed")
                return message.reply_text(
                    "Flow sending not available with current setup/library. "
                    "Make sure your PyWa version & Meta app have Flows enabled."
                )

        # default: echo
        return message.reply_text("Echo: " + text)
    except Exception:
        log.exception("on_message failed")

@wa.on_status()
def on_status(client: WhatsApp, status):
    try:
        statuses_buffer.appendleft(strip_status(status))
        log.info("Status update: %s", getattr(status, "status", "unknown"))
    except Exception:
        log.exception("on_status failed")

# -------------------------------------------------------------------
# API models
# -------------------------------------------------------------------
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
    # You can add "data" for variables if your flow requires it.

# -------------------------------------------------------------------
# HTTP endpoints
# -------------------------------------------------------------------
@app.get("/", summary="Health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "phone_id": PHONE_ID,
        "webhook": CALLBACK_URL,
        "buffer_size": MAX_BUFFER,
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
        # This requires a PyWa version that implements send_flow. If not present, it will fail.
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
            detail="This PyWa version does not support send_flow(). Upgrade pywa and ensure Flows are enabled."
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

# -------------------------------------------------------------------
# Notes:
# - PyWa mounts its webhook route on FastAPI using `server=app` and the given
#   `verify_token` / `callback_url`. You don't need to implement /webhook here.
# - For production, run behind gunicorn/uvicorn worker as you already do.
# - To try locally: uvicorn main:app --reload (but Meta requires HTTPS for webhook).
# -------------------------------------------------------------------
