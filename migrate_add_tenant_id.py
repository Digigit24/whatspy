# migrate_add_tenant_id.py
"""
Migration script to add tenant_id column to all tables
Run this once to update existing database schema
"""
from sqlalchemy import text
from database import engine, test_db_connection

print("=" * 60)
print("🔧 Adding tenant_id column to all tables")
print("=" * 60)

if not test_db_connection():
    print("❌ Database connection failed!")
    exit(1)

print("✅ Database connected\n")

# Tables that need tenant_id column
tables = [
    'messages',
    'webhook_logs',
    'campaigns',
    'message_templates',
    'contacts',
    'groups',
    'message_reactions'
]

try:
    with engine.connect() as conn:
        for table in tables:
            print(f"Processing table: {table}")
            
            # Check if column exists
            result = conn.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='{table}' AND column_name='tenant_id'
            """))
            
            if result.fetchone():
                print(f"  ⚠️  Column 'tenant_id' already exists in {table}")
            else:
                # Add column (allow NULL initially for existing data)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN tenant_id VARCHAR(100)"))
                print(f"  ✅ Added 'tenant_id' column to {table}")
                
                # Create index for better query performance
                conn.execute(text(f"CREATE INDEX idx_{table}_tenant_id ON {table}(tenant_id)"))
                print(f"  ✅ Created index on {table}.tenant_id")
            
            print()
        
        conn.commit()
    
    print("=" * 60)
    print("✅ Migration completed successfully!")
    print("=" * 60)
    print("\n⚠️  IMPORTANT NOTES:")
    print("1. Existing records will have NULL tenant_id")
    print("2. You should update existing records with appropriate tenant_id")
    print("3. Future inserts MUST include tenant_id")
    print("4. Consider making tenant_id NOT NULL after data migration")
    print("\nExample update query:")
    print("  UPDATE messages SET tenant_id = 'your-tenant-id' WHERE tenant_id IS NULL;")
    print()
    
except Exception as e:
    print(f"❌ Migration failed: {e}")
    exit(1)