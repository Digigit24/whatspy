# auth.py
import logging
from datetime import datetime
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import AdminUser, get_db_session

log = logging.getLogger("whatspy.auth")

# ────────────────────────────────
# Password Hashing
# ────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


# ────────────────────────────────
# User Management
# ────────────────────────────────

def create_admin_user(username: str, password: str, db: Session) -> Optional[AdminUser]:
    """Create a new admin user"""
    try:
        # Check if user already exists
        existing_user = db.query(AdminUser).filter(AdminUser.username == username).first()
        if existing_user:
            log.warning(f"User '{username}' already exists")
            return None
        
        # Create new user
        user = AdminUser(
            username=username,
            password_hash=hash_password(password),
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        log.info(f"✅ Admin user '{username}' created successfully")
        return user
    except Exception as e:
        log.error(f"❌ Failed to create admin user: {e}")
        db.rollback()
        return None


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user with username and password - returns user dict"""
    try:
        with get_db_session() as db:
            user = db.query(AdminUser).filter(
                AdminUser.username == username,
                AdminUser.is_active == True
            ).first()
            
            if not user:
                log.warning(f"Authentication failed: User '{username}' not found")
                return None
            
            if not verify_password(password, user.password_hash):
                log.warning(f"Authentication failed: Invalid password for '{username}'")
                return None
            
            # Update last login
            user.last_login = datetime.utcnow()
            db.commit()
            
            log.info(f"✅ User '{username}' authenticated successfully")
            
            # Return user data as dict (not SQLAlchemy object)
            return {
                "id": user.id,
                "username": user.username,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None
            }
    except Exception as e:
        log.error(f"❌ Authentication error: {e}")
        return None


def get_user_by_username(username: str, db: Session) -> Optional[AdminUser]:
    """Get user by username"""
    return db.query(AdminUser).filter(AdminUser.username == username).first()


def update_user_password(username: str, new_password: str, db: Session) -> bool:
    """Update user password"""
    try:
        user = get_user_by_username(username, db)
        if not user:
            return False
        
        user.password_hash = hash_password(new_password)
        db.commit()
        
        log.info(f"✅ Password updated for user '{username}'")
        return True
    except Exception as e:
        log.error(f"❌ Failed to update password: {e}")
        db.rollback()
        return False