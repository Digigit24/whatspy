# database.py
import logging
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from config import DATABASE_URL

log = logging.getLogger("whatspy.database")

# ────────────────────────────────
# SQLAlchemy Setup
# ────────────────────────────────
Base = declarative_base()

# Create engine with connection pooling for production
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,  # Verify connections before using
    echo=False  # Set to True for SQL debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ────────────────────────────────
# Database Models (with tenant_id support)
# ────────────────────────────────

class Message(Base):
    """Store all WhatsApp messages (incoming and outgoing)"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), index=True, nullable=False)  # ⬅️ NEW
    message_id = Column(String(255), unique=True, index=True, nullable=True)
    phone = Column(String(50), index=True, nullable=False)
    contact_name = Column(String(255), nullable=True)
    text = Column(Text, nullable=True)
    message_type = Column(String(50), nullable=True)
    direction = Column(String(20), nullable=False)  # 'incoming' or 'outgoing'
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    meta_data = Column(JSON, nullable=True)
    
    def to_dict(self):
        return {
            "id": self.message_id,
            "from": self.phone if self.direction == "incoming" else "bot",
            "to": self.phone if self.direction == "outgoing" else None,
            "name": self.contact_name,
            "text": self.text,
            "type": self.message_type,
            "direction": self.direction,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.meta_data,
            "tenant_id": self.tenant_id
        }


class WebhookLog(Base):
    """Log all webhook activity from Meta"""
    __tablename__ = "webhook_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), index=True, nullable=False)  # ⬅️ NEW
    log_type = Column(String(50), index=True)  # 'message', 'status', 'error'
    phone = Column(String(50), nullable=True)
    message_id = Column(String(255), nullable=True)
    status = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    context = Column(String(255), nullable=True)
    raw_data = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            "type": self.log_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "from": self.phone,
            "message_id": self.message_id,
            "status": self.status,
            "error": self.error_message,
            "context": self.context,
            "text": self.raw_data.get("text") if self.raw_data else None,
            "tenant_id": self.tenant_id
        }


class Campaign(Base):
    """Store broadcast campaign data"""
    __tablename__ = "campaigns"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), index=True, nullable=False)  # ⬅️ NEW
    campaign_id = Column(String(100), unique=True, index=True, nullable=False)
    campaign_name = Column(String(255), nullable=True)
    message_text = Column(Text, nullable=False)
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    results = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            "campaign_id": self.campaign_id,
            "campaign_name": self.campaign_name,
            "total_recipients": self.total_recipients,
            "sent": self.sent_count,
            "failed": self.failed_count,
            "timestamp": self.created_at.isoformat() if self.created_at else None,
            "results": self.results or [],
            "tenant_id": self.tenant_id
        }


class MessageTemplate(Base):
    """Store message templates"""
    __tablename__ = "message_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), index=True, nullable=False)  # ⬅️ NEW
    name = Column(String(255), index=True, nullable=False)
    content = Column(Text, nullable=False)
    variables = Column(JSON, nullable=True)  # List of variable names
    category = Column(String(100), default="general")
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "name": self.name,
            "content": self.content,
            "variables": self.variables or [],
            "category": self.category,
            "usage_count": self.usage_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tenant_id": self.tenant_id
        }


class AdminUser(Base):
    """Store admin credentials (legacy - keep for backward compatibility)"""
    __tablename__ = "admin_users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class Contact(Base):
    """Store WhatsApp contacts"""
    __tablename__ = "contacts"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), index=True, nullable=False)  # ⬅️ NEW
    phone = Column(String(50), index=True, nullable=False)
    name = Column(String(255), nullable=True)
    profile_pic_url = Column(String(500), nullable=True)
    status = Column(String(500), nullable=True)
    is_business = Column(Boolean, default=False)
    business_description = Column(Text, nullable=True)
    labels = Column(JSON, nullable=True)  # Tags/labels
    groups = Column(JSON, nullable=True) 
    notes = Column(Text, nullable=True)  # Internal notes
    last_seen = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "phone": self.phone,
            "name": self.name,
            "profile_pic_url": self.profile_pic_url,
            "status": self.status,
            "is_business": self.is_business,
            "business_description": self.business_description,
            "labels": self.labels or [],
            "groups": self.groups or [],
            "notes": self.notes,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tenant_id": self.tenant_id
        }


class Group(Base):
    """Store WhatsApp group information"""
    __tablename__ = "groups"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), index=True, nullable=False)  # ⬅️ NEW
    group_id = Column(String(100), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    participants = Column(JSON, nullable=True)  # List of phone numbers
    admins = Column(JSON, nullable=True)  # List of admin phone numbers
    created_by = Column(String(50), nullable=True)
    group_invite_link = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "name": self.name,
            "description": self.description,
            "participants": self.participants or [],
            "admins": self.admins or [],
            "created_by": self.created_by,
            "group_invite_link": self.group_invite_link,
            "is_active": self.is_active,
            "participant_count": len(self.participants) if self.participants else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "tenant_id": self.tenant_id
        }


class MessageReaction(Base):
    """Store message reactions"""
    __tablename__ = "message_reactions"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), index=True, nullable=False)  # ⬅️ NEW
    message_id = Column(String(255), index=True, nullable=False)
    phone = Column(String(50), nullable=False)
    emoji = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "phone": self.phone,
            "emoji": self.emoji,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tenant_id": self.tenant_id
        }


# ────────────────────────────────
# Database Functions
# ────────────────────────────────

def init_db():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        log.info("✅ Database tables created successfully")
    except Exception as e:
        log.error(f"❌ Failed to create database tables: {e}")
        raise


def get_db() -> Session:
    """Get database session - use with FastAPI Depends"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """Get database session - use with context manager"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def test_db_connection() -> bool:
    """Test database connection"""
    try:
        from sqlalchemy import text
        with get_db_session() as db:
            db.execute(text("SELECT 1"))
        log.info("✅ Database connection successful")
        return True
    except Exception as e:
        log.error(f"❌ Database connection failed: {e}")
        return False