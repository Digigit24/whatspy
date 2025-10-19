# routers/chat.py
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import FLOW_ID, FLOW_TOKEN, FLOW_CTA, FLOW_ACTION, FLOW_SCREEN
from database import get_db, Message, WebhookLog

log = logging.getLogger("whatspy.chat")

router = APIRouter()
wa_client = None

# ────────────────────────────────
# Helper Functions
# ────────────────────────────────

def save_message_to_db(
    db: Session,
    message_id: Optional[str],
    phone: str,
    contact_name: Optional[str],
    text: Optional[str],
    message_type: Optional[str],
    direction: str,
    metadata: Optional[Dict] = None
):
    """Save message to database"""
    try:
        message = Message(
            message_id=message_id,
            phone=phone,
            contact_name=contact_name,
            text=text,
            message_type=message_type,
            direction=direction,
            meta_data=metadata
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        log.info(f"💾 Saved {direction} message to database: {phone}")
        return message
    except Exception as e:
        log.error(f"❌ Failed to save message to database: {e}")
        db.rollback()
        return None


def save_webhook_log(
    db: Session,
    log_type: str,
    phone: Optional[str] = None,
    message_id: Optional[str] = None,
    status: Optional[str] = None,
    error_message: Optional[str] = None,
    context: Optional[str] = None,
    raw_data: Optional[Dict] = None
):
    """Save webhook log to database"""
    try:
        webhook_log = WebhookLog(
            log_type=log_type,
            phone=phone,
            message_id=message_id,
            status=status,
            error_message=error_message,
            context=context,
            raw_data=raw_data
        )
        db.add(webhook_log)
        db.commit()
        log.info(f"📝 Webhook log saved: {log_type}")
        return webhook_log
    except Exception as e:
        log.error(f"❌ Failed to save webhook log: {e}")
        db.rollback()
        return None


def init_wa_client(client):
    """Initialize WhatsApp client and register handlers"""
    global wa_client
    wa_client = client
    
    log.info(f"🚀 INIT: Registering message handlers...")
    
    # Register message handler
    @wa_client.on_message()
    def on_message(client, message):
        from database import get_db_session
        
        log.info("="*50)
        log.info("📩 MESSAGE HANDLER TRIGGERED!")
        log.info(f"📩 From: {getattr(message, 'from_user', 'unknown')}")
        log.info(f"📩 Text: {getattr(message, 'text', None)}")
        log.info("="*50)
        
        try:
            with get_db_session() as db:
                # Extract message data
                phone = getattr(message, "from_user", None)
                contact_name = None
                if hasattr(message, "contact") and message.contact:
                    contact_name = getattr(message.contact, "name", None)
                
                msg_text = getattr(message, "text", None)
                msg_type = getattr(message, "type", None)
                msg_id = getattr(message, "id", None)
                
                # Save incoming message to database
                save_message_to_db(
                    db=db,
                    message_id=msg_id,
                    phone=phone,
                    contact_name=contact_name,
                    text=msg_text,
                    message_type=msg_type,
                    direction="incoming",
                    metadata={"timestamp": str(getattr(message, "timestamp", None))}
                )
                
                # Log webhook activity
                save_webhook_log(
                    db=db,
                    log_type="message",
                    phone=phone,
                    message_id=msg_id,
                    raw_data={"text": msg_text[:100] if msg_text else None}
                )
                
                # Auto-reply logic
                text = (msg_text or "").strip()
                if not text:
                    reply_text = "I only understand text for now 🙂"
                    reply_msg = message.reply_text(reply_text)
                    
                    # Save bot reply
                    save_message_to_db(
                        db=db,
                        message_id=getattr(reply_msg, "id", None) if reply_msg else None,
                        phone=phone,
                        contact_name=contact_name,
                        text=reply_text,
                        message_type="text",
                        direction="outgoing"
                    )
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
                
                # Send reply and save it
                if reply_text:
                    log.info(f"💬 Sending reply: {reply_text[:50]}...")
                    reply_msg = message.reply_text(reply_text)
                    
                    save_message_to_db(
                        db=db,
                        message_id=getattr(reply_msg, "id", None) if reply_msg else None,
                        phone=phone,
                        contact_name=contact_name,
                        text=reply_text,
                        message_type="text",
                        direction="outgoing"
                    )
                
                log.info("="*50)
                log.info("✅ MESSAGE HANDLER COMPLETED SUCCESSFULLY")
                log.info("="*50)
                
        except Exception as e:
            log.exception(f"❌ on_message failed: {e}")
            try:
                with get_db_session() as db:
                    save_webhook_log(
                        db=db,
                        log_type="error",
                        error_message=str(e),
                        context="on_message"
                    )
            except:
                pass
    
    log.info("✅ INIT: Message handler registered successfully!")
    
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
            from database import get_db_session
            try:
                s = kwargs.get("status")
                if s is None and len(args) >= 2:
                    s = args[1]
                if s is not None:
                    with get_db_session() as db:
                        save_webhook_log(
                            db=db,
                            log_type="status",
                            message_id=getattr(s, "message_id", None),
                            status=getattr(s, "status", None)
                        )
                    log.info("Status update: %s", getattr(s, "status", "unknown"))
            except Exception as e:
                log.exception(f"status callback failed: {e}")
                try:
                    with get_db_session() as db:
                        save_webhook_log(
                            db=db,
                            log_type="error",
                            error_message=str(e),
                            context="status_callback"
                        )
                except:
                    pass


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
def send_text(payload: SendTextIn, db: Session = Depends(get_db)):
    """Send a text message via WhatsApp"""
    try:
        msg_id = wa_client.send_text(to=payload.to, text=payload.text)
        
        # Save to database
        save_message_to_db(
            db=db,
            message_id=msg_id,
            phone=payload.to,
            contact_name=None,
            text=payload.text,
            message_type="text",
            direction="outgoing"
        )
        
        return {"ok": True, "message_id": msg_id}
    except Exception as e:
        log.exception("send_text failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send/flow", summary="Send WhatsApp Flow")
def send_flow(payload: FlowSendIn):
    """Send a WhatsApp Flow"""
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
def list_messages(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get recent messages from database"""
    try:
        messages = db.query(Message).order_by(desc(Message.timestamp)).limit(limit).all()
        return [msg.to_dict() for msg in messages]
    except Exception as e:
        log.exception("list_messages failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations", summary="List all conversations")
def list_conversations(db: Session = Depends(get_db)):
    """Get all conversations with last message preview"""
    try:
        # Get all unique phone numbers with their latest message
        from sqlalchemy import func
        
        subquery = db.query(
            Message.phone,
            func.max(Message.timestamp).label('last_timestamp')
        ).group_by(Message.phone).subquery()
        
        conversations = db.query(Message).join(
            subquery,
            (Message.phone == subquery.c.phone) & (Message.timestamp == subquery.c.last_timestamp)
        ).order_by(desc(Message.timestamp)).all()
        
        result = []
        for msg in conversations:
            # Count total messages for this phone
            msg_count = db.query(Message).filter(Message.phone == msg.phone).count()
            
            result.append({
                "phone": msg.phone,
                "name": msg.contact_name or msg.phone,
                "last_message": msg.text or "(media)",
                "last_timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
                "unread_count": 0,
                "message_count": msg_count
            })
        
        log.info(f"Returning {len(result)} conversations")
        return result
    except Exception as e:
        log.exception("list_conversations failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{phone}", summary="Get conversation with specific number")
def get_conversation(phone: str, db: Session = Depends(get_db)):
    """Get full conversation history with a phone number"""
    try:
        messages = db.query(Message).filter(
            Message.phone == phone
        ).order_by(Message.timestamp).all()
        
        return {
            "phone": phone,
            "messages": [msg.to_dict() for msg in messages]
        }
    except Exception as e:
        log.exception("get_conversation failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs", summary="Get webhook logs")
def get_webhook_logs(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get recent webhook activity logs from Meta"""
    try:
        logs = db.query(WebhookLog).order_by(desc(WebhookLog.timestamp)).limit(limit).all()
        return [log.to_dict() for log in logs]
    except Exception as e:
        log.exception("get_webhook_logs failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug", summary="Debug endpoint")
def debug_info(db: Session = Depends(get_db)):
    """Debug information about current state"""
    try:
        conversations_count = db.query(Message.phone).distinct().count()
        messages_count = db.query(Message).count()
        logs_count = db.query(WebhookLog).count()
        
        # Get recent messages
        recent = db.query(Message).order_by(desc(Message.timestamp)).limit(5).all()
        
        return {
            "database_connected": True,
            "conversations_count": conversations_count,
            "total_messages": messages_count,
            "webhook_logs_count": logs_count,
            "recent_messages": [msg.to_dict() for msg in recent]
        }
    except Exception as e:
        log.exception("debug_info failed")
        return {
            "database_connected": False,
            "error": str(e)
        }