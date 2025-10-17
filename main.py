import os
import logging
from collections import deque
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pywa import WhatsApp

# ── Env & logging ──────────────────────────────────────────────────────────────
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
MAX_BUFFER = int(os.getenv("MESSAGE_BUFFER", "200"))

if not PHONE_ID or not TOKEN or not VERIFY_TOKEN:
    log.warning("Missing one of WHATSAPP_PHONE_ID / WHATSAPP_TOKEN / VERIFY_TOKEN")

# ── App & Templates ───────────────────────────────────────────────────────────
app = FastAPI(title="Whatspy (PyWa + FastAPI)", version="1.0.0")
templates = Jinja2Templates(directory="templates")

# ── In-memory stores for quick observability ──────────────────────────────────
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

# ── PyWa client (mounts webhook routes on FastAPI) ────────────────────────────
wa_kwargs: Dict[str, Any] = dict(
    phone_id=PHONE_ID,
    token=TOKEN,
    server=app,                      # attach FastAPI app
    verify_token=VERIFY_TOKEN,       # webhook verification
    callback_url=CALLBACK_URL,       # must be public HTTPS in Meta
    webhook_challenge_delay=WEBHOOK_DELAY,
)
if APP_ID and APP_SECRET:
    wa_kwargs.update(app_id=APP_ID, app_secret=APP_SECRET)

wa = WhatsApp(**wa_kwargs)

# ── Bot listeners ─────────────────────────────────────────────────────────────
@wa.on_message()
def on_message(client: WhatsApp, message):
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
                "• /flow – send a sample Flow (needs FLOW_ID)\n"
            )

        if text.startswith("/help"):
            return message.reply_text(
                "🧰 Commands:\n"
                "• /help – show this\n"
                "• /echo <text>\n"
                "• /flow – send a sample Flow (needs FLOW_ID)\n"
            )

        if text.startswith("/echo"):
            parts = text.split(" ", 1)
            return message.reply_text(parts[1] if len(parts) > 1 else "(nothing to echo)")

        if text.startswith("/flow"):
            flow_id = os.getenv("FLOW_ID")
            flow_cta = os.getenv("FLOW_CTA", "Open")
            if not flow_id:
                return message.reply_text("No FLOW_ID configured on server.")
            try:
                client.send_flow(
                    to=message.from_user,
                    flow_id=flow_id,
                    flow_token=os.getenv("FLOW_TOKEN", None),
                    flow_cta=flow_cta,
                    flow_action="navigate",
                    screen=os.getenv("FLOW_SCREEN", None),
                )
                return
            except Exception:
                log.exception("Flow send failed")
                return message.reply_text(
                    "Flow sending not available. Ensure your PyWa version & Meta app support Flows."
                )

        return message.reply_text("Echo: " + text)
    except Exception:
        log.exception("on_message failed")

@wa.on_status()
def on_status(client: WhatsApp, status):
    try:
        statuses_buffer.appendleft(strip_status(status))
        log.info("Status: %s", getattr(status, "status", "unknown"))
    except Exception:
        log.exception("on_status failed")

# ── API models ────────────────────────────────────────────────────────────────
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

# ── HTTP endpoints ────────────────────────────────────────────────────────────
@app.get("/healthz", summary="Health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "phone_id": PHONE_ID, "webhook": CALLBACK_URL, "buffer_size": MAX_BUFFER}

@app.get("/", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "phone_id": PHONE_ID,
            "webhook": CALLBACK_URL,
            "verify_token": VERIFY_TOKEN,
            "buffer_size": MAX_BUFFER,
            "messages": list(messages_buffer)[:10],
            "statuses": list(statuses_buffer)[:10],
            "endpoints": [
                "/send/text",
                "/send/flow",
                "/messages",
                "/statuses",
                "/docs",
                "/redoc",
                "/healthz",
            ],
        },
    )

@app.post("/send/text", summary="Send a text message")
def send_text(payload: SendTextIn):
    try:
        msg_id = wa.send_text(to=payload.to, text=payload.text)
        return {"ok": True, "message_id": msg_id}
    except Exception as e:
        log.exception("send_text failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send/flow", summary="Send a Flow (if supported)")
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
            detail="This PyWa version does not support send_flow(). Upgrade pywa and enable Flows.",
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
