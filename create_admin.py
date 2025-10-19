# create_admin.py
from database import get_db_session, AdminUser
from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD

print("Creating admin user...")

with get_db_session() as db:
    # Check if user exists
    existing = db.query(AdminUser).filter(AdminUser.username == ADMIN_USERNAME).first()
    
    if existing:
        print(f"User '{ADMIN_USERNAME}' already exists. Updating password...")
        existing.password_hash = hash_password(ADMIN_PASSWORD)
        db.commit()
        print(f"✅ Password updated for '{ADMIN_USERNAME}'")
    else:
        print(f"Creating new user '{ADMIN_USERNAME}'...")
        user = AdminUser(
            username=ADMIN_USERNAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            is_active=True
        )
        db.add(user)
        db.commit()
        print(f"✅ User '{ADMIN_USERNAME}' created successfully")

print(f"\nLogin credentials:")
print(f"Username: {ADMIN_USERNAME}")
print(f"Password: {ADMIN_PASSWORD}")