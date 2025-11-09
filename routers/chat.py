# routers/chat.py
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from config import FLOW_ID, FLOW_TOKEN, FLOW_CTA, FLOW_ACTION, FLOW_SCREEN
from database import get_db, Message, WebhookLog, Contact, Group

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
) -> Optional[Message]:
    """Save message to database with error handling"""
    try:
        message = Message(
            message_id=message_id,
            phone=phone,
            contact_name=contact_name,
            text=text,
            message_type=message_type or "text",
            direction=direction,
            meta_data=metadata
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        log.info(f"💾 Saved {direction} message to DB: {phone}")
        return message
    except Exception as e:
        log.error(f"❌ Failed to save message: {e}")
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


def extract_phone_from_user(from_user) -> tuple[Optional[str], Optional[str]]:
    """Extract phone number and name from PyWa User object"""
    if not from_user:
        return None, None
    
    try:
        if hasattr(from_user, 'wa_id'):
            phone = from_user.wa_id
            name = getattr(from_user, 'name', None)
            return phone, name
        else:
            return str(from_user), None
    except Exception as e:
        log.error(f"Failed to extract phone: {e}")
        return None, None


def save_or_update_contact(db: Session, phone: str, name: Optional[str] = None):
    """Save or update contact in database"""
    try:
        contact = db.query(Contact).filter(Contact.phone == phone).first()
        if contact:
            if name and contact.name != name:
                contact.name = name
                contact.last_seen = datetime.utcnow()
                db.commit()
        else:
            contact = Contact(phone=phone, name=name)
            db.add(contact)
            db.commit()
    except Exception as e:
        log.error(f"Failed to save contact: {e}")
        db.rollback()


def init_wa_client(client):
    """Initialize WhatsApp client and register handlers"""
    global wa_client
    wa_client = client
    
    log.info("🚀 INIT: Registering message handlers...")
    
    # Register message handler
    @wa_client.on_message()
    def on_message(client, message):
        from database import get_db_session
        
        log.info("="*50)
        log.info("📩 MESSAGE HANDLER TRIGGERED!")
        
        try:
            with get_db_session() as db:
                # Extract sender info
                from_user = getattr(message, "from_user", None)
                phone, contact_name = extract_phone_from_user(from_user)
                
                if not phone:
                    log.error("❌ No phone number extracted from message")
                    return
                
                log.info(f"📱 From: {phone} ({contact_name})")
                
                # Save/update contact
                save_or_update_contact(db, phone, contact_name)
                
                # Extract message data
                msg_text = getattr(message, "text", None)
                msg_type = getattr(message, "type", "text")
                msg_id = getattr(message, "id", None)
                
                log.info(f"📩 Type: {msg_type}, Text: {msg_text}")
                
                # Build metadata
                metadata = {
                    "timestamp": str(getattr(message, "timestamp", None)),
                    "type": msg_type
                }
                
                # Handle different message types
                if msg_type == "image":
                    metadata["media_id"] = getattr(message, "image", {}).get("id")
                    metadata["caption"] = getattr(message, "image", {}).get("caption")
                    msg_text = metadata.get("caption", "(image)")
                elif msg_type == "video":
                    metadata["media_id"] = getattr(message, "video", {}).get("id")
                    metadata["caption"] = getattr(message, "video", {}).get("caption")
                    msg_text = metadata.get("caption", "(video)")
                elif msg_type == "audio":
                    metadata["media_id"] = getattr(message, "audio", {}).get("id")
                    msg_text = "(audio)"
                elif msg_type == "document":
                    metadata["media_id"] = getattr(message, "document", {}).get("id")
                    metadata["filename"] = getattr(message, "document", {}).get("filename")
                    msg_text = metadata.get("filename", "(document)")
                elif msg_type == "location":
                    loc = getattr(message, "location", {})
                    metadata["latitude"] = loc.get("latitude")
                    metadata["longitude"] = loc.get("longitude")
                    msg_text = f"Location: {metadata['latitude']}, {metadata['longitude']}"
                
                # Save incoming message
                saved_msg = save_message_to_db(
                    db=db,
                    message_id=msg_id,
                    phone=phone,
                    contact_name=contact_name,
                    text=msg_text,
                    message_type=msg_type,
                    direction="incoming",
                    metadata=metadata
                )
                
                if saved_msg:
                    log.info(f"✅ Message saved with ID: {saved_msg.id}")
                
                # Log webhook
                save_webhook_log(
                    db=db,
                    log_type="message",
                    phone=phone,
                    message_id=msg_id,
                    raw_data={"text": str(msg_text)[:100] if msg_text else None, "type": msg_type}
                )
                
                # Auto-reply logic (only for text messages)
                if msg_type != "text" or not msg_text:
                    reply_text = "I only respond to text messages 🙂"
                    reply_msg = message.reply_text(reply_text)
                    
                    save_message_to_db(
                        db=db,
                        message_id=getattr(reply_msg, "id", None) if reply_msg else None,
                        phone=phone,
                        contact_name=contact_name,
                        text=reply_text,
                        message_type="text",
                        direction="outgoing",
                        metadata=None
                    )
                    return
                
                text = msg_text.strip()
                low = text.lower()
                reply_text = None
                
                if low in {"hi", "hello", "hey", "start"}:
                    reply_text = (
                        "👋 Welcome to Whatspy!\n\n"
                        "Commands:\n"
                        "• /help - Show all commands\n"
                        "• /echo <text> - Echo your message\n"
                        "• /info - Get your contact info"
                    )
                elif low.startswith("/help"):
                    reply_text = (
                        "🧰 Available Commands:\n\n"
                        "• /help - Show this help\n"
                        "• /echo <text> - Repeat your text\n"
                        "• /info - Show your info\n"
                        "• /ping - Test bot response"
                    )
                elif low.startswith("/echo "):
                    parts = text.split(" ", 1)
                    reply_text = parts[1] if len(parts) > 1 else "(nothing to echo)"
                elif low == "/info":
                    reply_text = f"📋 Your Info:\n\nPhone: {phone}\nName: {contact_name or 'Not set'}"
                elif low == "/ping":
                    reply_text = "🏓 Pong! Bot is working."
                else:
                    reply_text = f"Echo: {text}\n\nSend /help for commands."
                
                # Send reply
                if reply_text:
                    log.info(f"💬 Sending reply: {reply_text[:50]}...")
                    try:
                        reply_msg = message.reply_text(reply_text)
                        
                        save_message_to_db(
                            db=db,
                            message_id=getattr(reply_msg, "id", None) if reply_msg else None,
                            phone=phone,
                            contact_name=contact_name,
                            text=reply_text,
                            message_type="text",
                            direction="outgoing",
                            metadata=None
                        )
                    except Exception as reply_error:
                        log.error(f"Failed to send reply: {reply_error}")
                
                log.info("✅ MESSAGE HANDLER COMPLETED SUCCESSFULLY")
                
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
    
    log.info("✅ Message handler registered successfully!")
    
    # Register status handler
    _status_decorator = None
    if hasattr(wa_client, "on_status"):
        _status_decorator = wa_client.on_status()
    elif hasattr(wa_client, "on_message_status"):
        _status_decorator = wa_client.on_message_status()
    
    if _status_decorator:
        @_status_decorator
        def _status_cb(*args, **kwargs):
            from database import get_db_session
            try:
                s = kwargs.get("status") or (args[1] if len(args) >= 2 else None)
                if s:
                    with get_db_session() as db:
                        save_webhook_log(
                            db=db,
                            log_type="status",
                            message_id=getattr(s, "message_id", None),
                            status=getattr(s, "status", None)
                        )
                    log.info(f"Status update: {getattr(s, 'status', 'unknown')}")
            except Exception as e:
                log.exception(f"Status callback failed: {e}")


# ────────────────────────────────
# Pydantic Models
# ────────────────────────────────

class SendTextIn(BaseModel):
    to: str = Field(..., description="WhatsApp phone (international format, no +)")
    text: str = Field(..., min_length=1, max_length=4096)


class SendMediaIn(BaseModel):
    to: str = Field(..., description="Recipient phone number")
    media_id: str = Field(..., description="Media ID from WhatsApp")
    caption: Optional[str] = Field(None, max_length=1024)
    media_type: str = Field(..., description="Type: image, video, audio, document")


class SendLocationIn(BaseModel):
    to: str
    latitude: float
    longitude: float
    name: Optional[str] = None
    address: Optional[str] = None


class SendTemplateIn(BaseModel):
    to: str
    template_name: str
    language_code: str = "en"
    components: Optional[List[Dict]] = None


class MarkAsReadIn(BaseModel):
    message_id: str


# ────────────────────────────────
# API Endpoints
# ────────────────────────────────

@router.post("/send/text", summary="Send text message")
def send_text(payload: SendTextIn, db: Session = Depends(get_db)):
    """Send a text message via WhatsApp"""
    msg_id = None
    try:
        # Send message
        msg_response = wa_client.send_text(to=payload.to, text=payload.text)
        
        # Extract message ID
        if hasattr(msg_response, 'id'):
            msg_id = msg_response.id
        elif isinstance(msg_response, str):
            msg_id = msg_response
        else:
            msg_id = str(msg_response) if msg_response else None
        
        log.info(f"✅ Message sent: {msg_id} to {payload.to}")
        
    except Exception as send_error:
        log.exception("Failed to send message")
        raise HTTPException(status_code=500, detail=f"Send failed: {str(send_error)}")
    
    # Save to database (non-critical)
    try:
        save_message_to_db(
            db=db,
            message_id=msg_id,
            phone=payload.to,
            contact_name=None,
            text=payload.text,
            message_type="text",
            direction="outgoing",
            metadata={"sent_at": datetime.utcnow().isoformat()}
        )
    except Exception as db_error:
        log.error(f"Failed to save to DB: {db_error}")
    
    return {"ok": True, "message_id": msg_id}


@router.post("/send/media", summary="Send media message")
def send_media(payload: SendMediaIn, db: Session = Depends(get_db)):
    """Send image, video, audio, or document"""
    try:
        if payload.media_type == "image":
            msg_id = wa_client.send_image(
                to=payload.to,
                image=payload.media_id,
                caption=payload.caption
            )
        elif payload.media_type == "video":
            msg_id = wa_client.send_video(
                to=payload.to,
                video=payload.media_id,
                caption=payload.caption
            )
        elif payload.media_type == "audio":
            msg_id = wa_client.send_audio(
                to=payload.to,
                audio=payload.media_id
            )
        elif payload.media_type == "document":
            msg_id = wa_client.send_document(
                to=payload.to,
                document=payload.media_id,
                caption=payload.caption
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid media type")
        
        # Save to DB
        try:
            save_message_to_db(
                db=db,
                message_id=str(msg_id) if msg_id else None,
                phone=payload.to,
                contact_name=None,
                text=payload.caption or f"({payload.media_type})",
                message_type=payload.media_type,
                direction="outgoing",
                metadata={"media_id": payload.media_id}
            )
        except Exception as db_error:
            log.error(f"Failed to save media message: {db_error}")
        
        return {"ok": True, "message_id": str(msg_id)}
        
    except Exception as e:
        log.exception("send_media failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send/location", summary="Send location")
def send_location(payload: SendLocationIn, db: Session = Depends(get_db)):
    """Send location message"""
    try:
        msg_id = wa_client.send_location(
            to=payload.to,
            latitude=payload.latitude,
            longitude=payload.longitude,
            name=payload.name,
            address=payload.address
        )
        
        return {"ok": True, "message_id": str(msg_id)}
    except Exception as e:
        log.exception("send_location failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mark-read", summary="Mark message as read")
def mark_as_read(payload: MarkAsReadIn):
    """Mark a message as read"""
    try:
        wa_client.mark_as_read(message_id=payload.message_id)
        return {"ok": True}
    except Exception as e:
        log.exception("mark_as_read failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages", summary="List recent messages")
def list_messages(
    limit: int = Query(50, ge=1, le=200),
    phone: Optional[str] = None,
    direction: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get recent messages from database with optional filters"""
    try:
        query = db.query(Message)
        
        if phone:
            query = query.filter(Message.phone == phone)
        if direction:
            query = query.filter(Message.direction == direction)
        
        messages = query.order_by(desc(Message.timestamp)).limit(limit).all()
        return [msg.to_dict() for msg in messages]
    except Exception as e:
        log.exception("list_messages failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations", summary="List all conversations")
def list_conversations(db: Session = Depends(get_db)):
    """Get all conversations with last message preview"""
    try:
        # Get latest message for each phone
        subquery = db.query(
            Message.phone,
            func.max(Message.timestamp).label('last_timestamp')
        ).group_by(Message.phone).subquery()
        
        conversations = db.query(Message).join(
            subquery,
            (Message.phone == subquery.c.phone) & 
            (Message.timestamp == subquery.c.last_timestamp)
        ).order_by(desc(Message.timestamp)).all()
        
        result = []
        for msg in conversations:
            msg_count = db.query(Message).filter(Message.phone == msg.phone).count()
            
            result.append({
                "phone": msg.phone,
                "name": msg.contact_name or msg.phone,
                "last_message": msg.text or f"({msg.message_type})",
                "last_timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
                "unread_count": 0,
                "message_count": msg_count
            })
        
        log.info(f"Returning {len(result)} conversations")
        return result
    except Exception as e:
        log.exception("list_conversations failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{phone}", summary="Get conversation")
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

# ────────────────────────────────
# Backward-compatibility aliases for old frontend paths
# Keep until frontend is updated from /api/messages/conversations/* to /api/conversations/*
# ────────────────────────────────
@router.get("/messages/conversations", summary="Alias: List all conversations")
@router.get("/messages/conversations/", summary="Alias: List all conversations (trailing slash)")
def list_conversations_alias(db: Session = Depends(get_db)):
    log.warning("Deprecated endpoint hit: /api/messages/conversations - update frontend to /api/conversations")
    return list_conversations(db=db)

@router.get("/messages/conversations/{phone}", summary="Alias: Get conversation")
@router.get("/messages/conversations/{phone}/", summary="Alias: Get conversation (trailing slash)")
def get_conversation_alias(phone: str, db: Session = Depends(get_db)):
    log.warning("Deprecated endpoint hit: /api/messages/conversations/{phone} - update frontend to /api/conversations/{phone}")
    return get_conversation(phone=phone, db=db)


@router.delete("/conversations/{phone}", summary="Delete conversation")
def delete_conversation(phone: str, db: Session = Depends(get_db)):
    """Delete all messages for a phone number"""
    try:
        deleted = db.query(Message).filter(Message.phone == phone).delete()
        db.commit()
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        log.exception("delete_conversation failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts", summary="List all contacts")
def list_contacts(db: Session = Depends(get_db)):
    """Get all contacts"""
    try:
        contacts = db.query(Contact).order_by(desc(Contact.last_seen)).all()
        return [c.to_dict() for c in contacts]
    except Exception as e:
        log.exception("list_contacts failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs", summary="Get webhook logs")
def get_webhook_logs(
    limit: int = Query(100, ge=1, le=500),
    log_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get recent webhook activity logs"""
    try:
        query = db.query(WebhookLog)
        
        if log_type:
            query = query.filter(WebhookLog.log_type == log_type)
        
        logs = query.order_by(desc(WebhookLog.timestamp)).limit(limit).all()
        return [log.to_dict() for log in logs]
    except Exception as e:
        log.exception("get_webhook_logs failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", summary="Get statistics")
def get_stats(db: Session = Depends(get_db)):
    """Get messaging statistics"""
    try:
        total_messages = db.query(Message).count()
        total_conversations = db.query(Message.phone).distinct().count()
        total_contacts = db.query(Contact).count()
        
        incoming = db.query(Message).filter(Message.direction == "incoming").count()
        outgoing = db.query(Message).filter(Message.direction == "outgoing").count()
        
        # Messages by type
        message_types = db.query(
            Message.message_type,
            func.count(Message.id).label('count')
        ).group_by(Message.message_type).all()
        
        return {
            "total_messages": total_messages,
            "total_conversations": total_conversations,
            "total_contacts": total_contacts,
            "incoming_messages": incoming,
            "outgoing_messages": outgoing,
            "message_types": {mt: count for mt, count in message_types}
        }
    except Exception as e:
        log.exception("get_stats failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug", summary="Debug endpoint")
def debug_info(db: Session = Depends(get_db)):
    """Debug information"""
    try:
        conversations_count = db.query(Message.phone).distinct().count()
        messages_count = db.query(Message).count()
        logs_count = db.query(WebhookLog).count()
        contacts_count = db.query(Contact).count()
        
        recent = db.query(Message).order_by(desc(Message.timestamp)).limit(5).all()
        
        return {
            "database_connected": True,
            "conversations_count": conversations_count,
            "total_messages": messages_count,
            "webhook_logs_count": logs_count,
            "contacts_count": contacts_count,
            "recent_messages": [msg.to_dict() for msg in recent]
        }
    except Exception as e:
        log.exception("debug_info failed")
        return {
            "database_connected": False,
            "error": str(e)
        }