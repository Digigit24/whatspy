# routers/chat.py
import logging
from collections import deque
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import MAX_BUFFER, FLOW_ID, FLOW_TOKEN, FLOW_CTA, FLOW_ACTION, FLOW_SCREEN

log = logging.getLogger("whatspy.chat")

router = APIRouter()
wa_client = None

# ────────────────────────────────
# In-memory storage
# ────────────────────────────────
messages_buffer: deque = deque(maxlen=MAX_BUFFER)
statuses_buffer: deque = deque(maxlen=MAX_BUFFER)
webhook_logs: deque = deque(maxlen=MAX_BUFFER)  # Store all webhook activity

# Store conversations grouped by phone number
conversations: Dict[str, List[Dict]] = {}

def init_wa_client(client):
    """Initialize WhatsApp client and register handlers"""
    global wa_client
    wa_client = client
    
    # Register message handler
    @wa_client.on_message()
    def on_message(client, message):
        try:
            msg_data = strip_message(message)
            messages_buffer.appendleft(msg_data)
            
            # Store in conversations
            phone = msg_data.get("from")
            if phone:
                if phone not in conversations:
                    conversations[phone] = []
                conversations[phone].append({
                    **msg_data,
                    "direction": "incoming",
                    "timestamp": datetime.now().isoformat()
                })
            
            # Auto-reply logic
            text = (message.text or "").strip()
            if not text:
                return message.reply_text("I only understand text for now 🙂")
            
            low = text.lower()
            if low in {"hi", "hello", "hey"}:
                return message.reply_text(
                    "👋 Hey! Try:\n"
                    "• /help – show commands\n"
                    "• /echo <text> – I'll repeat it\n"
                    "• /flow – send a sample Flow (if enabled)"
                )
            
            if low.startswith("/help"):
                return message.reply_text(
                    "🧰 Commands:\n"
                    "• /help – show this\n"
                    "• /echo <text>\n"
                    "• /flow – send a sample Flow"
                )
            
            if low.startswith("/echo"):
                parts = text.split(" ", 1)
                return message.reply_text(parts[1] if len(parts) > 1 else "(nothing to echo)")
            
            if low.startswith("/flow"):
                if not FLOW_ID:
                    return message.reply_text("No FLOW_ID configured on server.")
                
                try:
                    client.send_flow(
                        to=message.from_user,
                        flow_id=FLOW_ID,
                        flow_token=FLOW_TOKEN,
                        flow_cta=FLOW_CTA,
                        flow_action=FLOW_ACTION,
                        screen=FLOW_SCREEN,
                    )
                    return
                except AttributeError:
                    return message.reply_text("Flow not supported in this PyWa version.")
                except Exception as e:
                    log.exception("Flow send failed")
                    return message.reply_text(f"Flow send failed: {e}")
            
            # Default echo
            return message.reply_text("Echo: " + text)
        except Exception:
            log.exception("on_message failed")
    
    # Register status handler
    _status_decorator = None
    if hasattr(wa_client, "on_status"):
        _status_decorator = wa_client.on_status()
    elif hasattr(wa_client, "on_message_status"):
        _status_decorator = wa_client.on_message_status()
    elif hasattr(wa_client, "on_statuses"):
        _status_decorator = wa_client.on_statuses()
    
    if _status_decorator:
        @_status_decorator
        def _status_cb(*args, **kwargs):
            try:
                s = kwargs.get("status")
                if s is None and len(args) >= 2:
                    s = args[1]
                if s is not None:
                    statuses_buffer.appendleft(strip_status(s))
                    log.info("Status update: %s", getattr(s, "status", "unknown"))
            except Exception:
                log.exception("status callback failed")

def strip_message(m) -> Dict[str, Any]:
    """Extract message data"""
    return {
        "id": getattr(m, "id", None),
        "from": getattr(m, "from_user", None),
        "name": getattr(getattr(m, "contact", None), "name", None) if hasattr(m, "contact") else None,
        "type": getattr(m, "type", None),
        "text": getattr(m, "text", None),
        "timestamp": getattr(m, "timestamp", None),
    }

def strip_status(s) -> Dict[str, Any]:
    """Extract status data"""
    return {
        "id": getattr(s, "id", None),
        "message_id": getattr(s, "message_id", None),
        "status": getattr(s, "status", None),
        "recipient": getattr(s, "recipient", None),
        "timestamp": getattr(s, "timestamp", None),
    }

# ────────────────────────────────
# Models
# ────────────────────────────────
class SendTextIn(BaseModel):
    to: str = Field(..., description="WhatsApp phone (international format, no +)")
    text: str = Field(..., min_length=1, max_length=4096)

class FlowSendIn(BaseModel):
    to: str
    flow_id: str
    flow_token: Optional[str] = None
    flow_cta: Optional[str] = "Open"
    flow_action: Optional[str] = "navigate"
    screen: Optional[str] = None

# ────────────────────────────────
# Endpoints
# ────────────────────────────────
@router.post("/send/text", summary="Send text message")
def send_text(payload: SendTextIn):
    try:
        msg_id = wa_client.send_text(to=payload.to, text=payload.text)
        
        # Store in conversations
        if payload.to not in conversations:
            conversations[payload.to] = []
        conversations[payload.to].append({
            "id": msg_id,
            "from": "bot",
            "to": payload.to,
            "text": payload.text,
            "direction": "outgoing",
            "timestamp": datetime.now().isoformat()
        })
        
        return {"ok": True, "message_id": msg_id}
    except Exception as e:
        log.exception("send_text failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send/flow", summary="Send WhatsApp Flow")
def send_flow(payload: FlowSendIn):
    try:
        msg_id = wa_client.send_flow(
            to=payload.to,
            flow_id=payload.flow_id,
            flow_token=payload.flow_token,
            flow_cta=payload.flow_cta,
            flow_action=payload.flow_action,
            screen=payload.screen,
        )
        return {"ok": True, "message_id": msg_id}
    except AttributeError:
        raise HTTPException(status_code=400, detail="Flow not supported in this PyWa version")
    except Exception as e:
        log.exception("send_flow failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages", summary="List recent messages")
def list_messages(limit: int = Query(50, ge=1, le=MAX_BUFFER)):
    return list(messages_buffer)[:limit]

@router.get("/statuses", summary="List status updates")
def list_statuses(limit: int = Query(50, ge=1, le=MAX_BUFFER)):
    return list(statuses_buffer)[:limit]

@router.get("/conversations", summary="List all conversations")
def list_conversations():
    """Get all conversations with last message preview"""
    result = []
    for phone, msgs in conversations.items():
        if msgs:
            last_msg = msgs[-1]
            result.append({
                "phone": phone,
                "name": last_msg.get("name", phone),
                "last_message": last_msg.get("text", ""),
                "last_timestamp": last_msg.get("timestamp", ""),
                "unread_count": 0,  # TODO: implement unread tracking
                "message_count": len(msgs)
            })
    return sorted(result, key=lambda x: x["last_timestamp"], reverse=True)

@router.get("/conversations/{phone}", summary="Get conversation with specific number")
def get_conversation(phone: str):
    """Get full conversation history with a phone number"""
    if phone not in conversations:
        return {"phone": phone, "messages": []}
    return {
        "phone": phone,
        "messages": conversations[phone]
    }