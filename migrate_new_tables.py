# migrate_new_tables.py
"""
Add new tables: contacts, groups, message_reactions
"""
from database import init_db, test_db_connection

print("🔧 Adding new tables...")

if not test_db_connection():
    print("❌ Database connection failed!")
    exit(1)

print("✅ Database connected")
print("📦 Creating new tables...")

init_db()

print("✅ Tables created successfully!")
print("\nNew tables added:")
print("  - contacts")
print("  - groups")
print("  - message_reactions")