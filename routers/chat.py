# routers/chat.py
import logging
import json
import os
from pathlib import Path
from collections import deque
from typing import Optional, Dict, Any, List
from datetime import datetime
from threading import Lock

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import MAX_BUFFER, FLOW_ID, FLOW_TOKEN, FLOW_CTA, FLOW_ACTION, FLOW_SCREEN

log = logging.getLogger("whatspy.chat")

router = APIRouter()
wa_client = None

# ────────────────────────────────
# Shared file-based storage
# ────────────────────────────────
DATA_DIR = Path("/tmp/whatspy_data")
DATA_DIR.mkdir(exist_ok=True)
CONVERSATIONS_FILE = DATA_DIR / "conversations.json"
MESSAGES_FILE = DATA_DIR / "messages.json"
LOGS_FILE = DATA_DIR / "webhook_logs.json"

# Lock for thread-safe file access
file_lock = Lock()

def load_json_file(filepath: Path, default=None):
    """Load JSON from file with lock"""
    if default is None:
        default = {}
    try:
        with file_lock:
            if filepath.exists():
                with open(filepath, 'r') as f:
                    return json.load(f)
    except Exception as e:
        log.error(f"Failed to load {filepath}: {e}")
    return default

def save_json_file(filepath: Path, data):
    """Save JSON to file with lock"""
    try:
        with file_lock:
            with open(filepath, 'w') as f:
                json.dump(data, f)
    except Exception as e:
        log.error(f"Failed to save {filepath}: {e}")

# ────────────────────────────────
# In-memory buffers (for backward compatibility)
# ────────────────────────────────
messages_buffer: deque = deque(maxlen=MAX_BUFFER)
statuses_buffer: deque = deque(maxlen=MAX_BUFFER)
webhook_logs: deque = deque(maxlen=MAX_BUFFER)

# Load persistent data
conversations: Dict[str, List[Dict]] = load_json_file(CONVERSATIONS_FILE, {})

def init_wa_client(client):
    """Initialize WhatsApp client and register handlers"""
    global wa_client
    wa_client = client
    
    # Register message handler
    @wa_client.on_message()
    def on_message(client, message):
        try:
            # Log webhook activity
            webhook_logs.appendleft({
                "type": "message",
                "timestamp": datetime.now().isoformat(),
                "from": getattr(message, "from_user", "unknown"),
                "message_id": getattr(message, "id", None),
                "text": getattr(message, "text", None)[:100] if getattr(message, "text", None) else None
            })
            
            msg_data = strip_message(message)
            messages_buffer.appendleft(msg_data)
            
            # Store in conversations
            phone = msg_data.get("from")
            if phone:
                if phone not in conversations:
                    conversations[phone] = []
                
                msg_entry = {
                    "id": msg_data.get("id"),
                    "from": phone,
                    "name": msg_data.get("name") or phone,
                    "text": msg_data.get("text"),
                    "type": msg_data.get("type"),
                    "direction": "incoming",
                    "timestamp": datetime.now().isoformat()
                }
                conversations[phone].append(msg_entry)
                log.info(f"Message stored for {phone}: {msg_data.get('text', '')[:50]}")
            
            # Auto-reply logic
            text = (message.text or "").strip()
            if not text:
                reply_msg = message.reply_text("I only understand text for now 🙂")
                # Store bot reply
                if phone and phone in conversations:
                    conversations[phone].append({
                        "id": getattr(reply_msg, "id", None) if reply_msg else None,
                        "from": "bot",
                        "to": phone,
                        "text": "I only understand text for now 🙂",
                        "direction": "outgoing",
                        "timestamp": datetime.now().isoformat()
                    })
                return
            
            low = text.lower()
            reply_text = None
            
            if low in {"hi", "hello", "hey"}:
                reply_text = (
                    "👋 Hey! Try:\n"
                    "• /help – show commands\n"
                    "• /echo <text> – I'll repeat it\n"
                    "• /flow – send a sample Flow (if enabled)"
                )
            elif low.startswith("/help"):
                reply_text = (
                    "🧰 Commands:\n"
                    "• /help – show this\n"
                    "• /echo <text>\n"
                    "• /flow – send a sample Flow"
                )
            elif low.startswith("/echo"):
                parts = text.split(" ", 1)
                reply_text = parts[1] if len(parts) > 1 else "(nothing to echo)"
            elif low.startswith("/flow"):
                if not FLOW_ID:
                    reply_text = "No FLOW_ID configured on server."
                else:
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
                        reply_text = "Flow not supported in this PyWa version."
                    except Exception as e:
                        log.exception("Flow send failed")
                        reply_text = f"Flow send failed: {e}"
            else:
                # Default echo
                reply_text = "Echo: " + text
            
            # Send reply and store it
            if reply_text:
                reply_msg = message.reply_text(reply_text)
                if phone and phone in conversations:
                    conversations[phone].append({
                        "id": getattr(reply_msg, "id", None) if reply_msg else None,
                        "from": "bot",
                        "to": phone,
                        "text": reply_text,
                        "direction": "outgoing",
                        "timestamp": datetime.now().isoformat()
                    })
            
        except Exception as e:
            log.exception(f"on_message failed: {e}")
            webhook_logs.appendleft({
                "type": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "context": "on_message"
            })
    
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
                    status_data = strip_status(s)
                    statuses_buffer.appendleft(status_data)
                    
                    # Log webhook activity
                    webhook_logs.appendleft({
                        "type": "status",
                        "timestamp": datetime.now().isoformat(),
                        "status": getattr(s, "status", "unknown"),
                        "message_id": getattr(s, "message_id", None)
                    })
                    
                    log.info("Status update: %s", getattr(s, "status", "unknown"))
            except Exception as e:
                log.exception(f"status callback failed: {e}")
                webhook_logs.appendleft({
                    "type": "error",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                    "context": "status_callback"
                })

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
    try:
        result = []
        for phone, msgs in conversations.items():
            if msgs:
                last_msg = msgs[-1]
                result.append({
                    "phone": phone,
                    "name": last_msg.get("name", phone),
                    "last_message": last_msg.get("text", ""),
                    "last_timestamp": last_msg.get("timestamp", ""),
                    "unread_count": 0,
                    "message_count": len(msgs)
                })
        
        sorted_result = sorted(result, key=lambda x: x["last_timestamp"], reverse=True)
        log.info(f"Returning {len(sorted_result)} conversations")
        return sorted_result
    except Exception as e:
        log.exception(f"list_conversations failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/conversations/{phone}", summary="Get conversation with specific number")
def get_conversation(phone: str):
    """Get full conversation history with a phone number"""
    try:
        if phone not in conversations:
            return {"phone": phone, "messages": []}
        return {
            "phone": phone,
            "messages": conversations[phone]
        }
    except Exception as e:
        log.exception(f"get_conversation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs", summary="Get webhook logs")
def get_webhook_logs(limit: int = Query(100, ge=1, le=MAX_BUFFER)):
    """Get recent webhook activity logs from Meta"""
    return list(webhook_logs)[:limit]

@router.get("/debug", summary="Debug endpoint")
def debug_info():
    """Debug information about current state"""
    return {
        "conversations_count": len(conversations),
        "conversations_keys": list(conversations.keys()),
        "messages_buffer_count": len(messages_buffer),
        "webhook_logs_count": len(webhook_logs),
        "recent_messages": list(messages_buffer)[:5],
        "sample_conversation": {
            phone: msgs[:2] for phone, msgs in list(conversations.items())[:2]
        } if conversations else {}
    }