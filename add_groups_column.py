# add_groups_column.py
"""Add groups column to contacts table"""
from sqlalchemy import text
from database import engine, test_db_connection

print("🔧 Adding groups column to contacts table...")

if not test_db_connection():
    print("❌ Database connection failed!")
    exit(1)

try:
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='contacts' AND column_name='groups'
        """))
        
        if result.fetchone():
            print("⚠️  Column 'groups' already exists")
        else:
            # Add column
            conn.execute(text("ALTER TABLE contacts ADD COLUMN groups JSONB"))
            conn.commit()
            print("✅ Column 'groups' added successfully")
    
    print("\n✅ Migration completed!")
    
except Exception as e:
    print(f"❌ Migration failed: {e}")
    exit(1)