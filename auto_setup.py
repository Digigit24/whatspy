# auto_setup.py
"""
Complete Whatspy Setup Script
- Creates all database tables
- Creates admin user
- Tests connections
Run once on fresh installation
"""
import os
import sys

def setup():
    print("=" * 60)
    print("🚀 Whatspy Complete Setup - All Tables & Admin User")
    print("=" * 60)
    
    # Import after printing header
    try:
        from database import init_db, test_db_connection, get_db_session, Base, engine
        from auth import create_admin_user
        from config import ADMIN_USERNAME, ADMIN_PASSWORD, DATABASE_URL
    except Exception as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're in the correct directory and .env is configured")
        return 1
    
    # Show configuration
    print(f"\n📋 Configuration:")
    print(f"   Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    print(f"   Admin User: {ADMIN_USERNAME}")
    print()
    
    # Step 1: Test database connection
    print("1️⃣  Testing database connection...")
    if not test_db_connection():
        print("   ❌ Database connection failed!")
        print("   Please check:")
        print("   - PostgreSQL is running")
        print("   - Database exists (CREATE DATABASE whatspy_db;)")
        print("   - DATABASE_URL in .env is correct")
        return 1
    print("   ✅ Database connected successfully")
    
    # Step 2: Create all tables
    print("\n2️⃣  Creating database tables...")
    print("   Creating tables:")
    print("      - messages (all WhatsApp messages)")
    print("      - webhook_logs (Meta webhook activity)")
    print("      - campaigns (broadcast campaigns)")
    print("      - message_templates (reusable templates)")
    print("      - admin_users (authentication)")
    
    try:
        init_db()
        print("   ✅ All tables created successfully")
        
        # Verify tables were created
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"   📊 Tables in database: {len(tables)}")
        for table in tables:
            print(f"      ✓ {table}")
            
    except Exception as e:
        print(f"   ❌ Table creation failed: {e}")
        return 1
    
    # Step 3: Create admin user
    print(f"\n3️⃣  Creating admin user '{ADMIN_USERNAME}'...")
    try:
        with get_db_session() as db:
            user = create_admin_user(ADMIN_USERNAME, ADMIN_PASSWORD, db)
            if user:
                print(f"   ✅ Admin user '{ADMIN_USERNAME}' created successfully")
            else:
                print(f"   ⚠️  User '{ADMIN_USERNAME}' already exists (skipping)")
    except Exception as e:
        print(f"   ❌ Admin user creation failed: {e}")
        return 1
    
    # Step 4: Final verification
    print("\n4️⃣  Verifying setup...")
    try:
        with get_db_session() as db:
            from database import Message, WebhookLog, Campaign, MessageTemplate, AdminUser
            
            # Count records
            admin_count = db.query(AdminUser).count()
            print(f"   ✓ Admin users: {admin_count}")
            
            # Test each table
            db.query(Message).first()
            db.query(WebhookLog).first()
            db.query(Campaign).first()
            db.query(MessageTemplate).first()
            
        print("   ✅ All tables verified and working")
    except Exception as e:
        print(f"   ⚠️  Verification warning: {e}")
    
    # Success!
    print("\n" + "=" * 60)
    print("✅ SETUP COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("\n📌 Login Credentials:")
    print(f"   Username: {ADMIN_USERNAME}")
    print(f"   Password: {ADMIN_PASSWORD}")
    print(f"   🔒 IMPORTANT: Change password after first login!")
    
    print("\n🚀 Next Steps:")
    print("   Local Development:")
    print("      uvicorn main:app --reload --host 0.0.0.0 --port 8000")
    print("      Visit: http://localhost:8000/login")
    print()
    print("   Production Server:")
    print("      sudo systemctl restart whatspy")
    print("      Visit: https://whatsapp.dglinkup.com/login")
    
    print("\n" + "=" * 60)
    return 0

if __name__ == "__main__":
    exit_code = setup()
    sys.exit(exit_code)