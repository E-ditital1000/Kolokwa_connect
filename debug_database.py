#!/usr/bin/env python
"""Comprehensive database debugging script"""
import os
import sys
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Kolokwa_connect.settings')

import django
django.setup()

from django.db import connection
from django.conf import settings

print("=" * 70)
print("COMPREHENSIVE DATABASE DEBUG")
print("=" * 70)

# 1. Check settings
print("\n1️⃣  SETTINGS.PY DATABASE CONFIG:")
db_settings = settings.DATABASES['default']
for key, value in db_settings.items():
    if key == 'PASSWORD':
        print(f"   {key}: {'*' * len(str(value))}")
    else:
        print(f"   {key}: {value}")

# 2. Check environment variables
print("\n2️⃣  ENVIRONMENT VARIABLES:")
env_vars = [
    'DATABASE_ENGINE', 'DATABASE_NAME', 'DATABASE_HOST', 
    'DATABASE_PORT', 'DATABASE_USER', 'DATABASE_PASSWORD'
]
for var in env_vars:
    value = os.getenv(var)
    if value:
        if 'PASSWORD' in var:
            print(f"   {var}: {'*' * len(value)}")
        else:
            print(f"   {var}: {value}")
    else:
        print(f"   {var}: NOT SET")

# 3. Test actual connection
print("\n3️⃣  ACTUAL DATABASE CONNECTION:")
try:
    with connection.cursor() as cursor:
        # Get database name being used
        cursor.execute("SELECT current_database()")
        db_name = cursor.fetchone()[0]
        print(f"   ✓ Connected to database: {db_name}")
        
        # Get connection info
        cursor.execute("""
            SELECT 
                inet_server_addr() as host,
                inet_server_port() as port,
                current_user as user,
                version() as version
        """)
        row = cursor.fetchone()
        print(f"   ✓ Host: {row[0] or 'localhost'}")
        print(f"   ✓ Port: {row[1] or 'default'}")
        print(f"   ✓ User: {row[2]}")
        print(f"   ✓ Version: {row[3][:50]}...")
        
except Exception as e:
    print(f"   ✗ Connection failed: {e}")
    sys.exit(1)

# 4. List all tables
print("\n4️⃣  ALL TABLES IN DATABASE:")
try:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        tables = cursor.fetchall()
        
        if tables:
            print(f"   Found {len(tables)} tables:")
            for table in tables:
                print(f"   • {table[0]}")
        else:
            print("   ✗ NO TABLES FOUND!")
            print("   This means migrations ran on a DIFFERENT database!")
except Exception as e:
    print(f"   ✗ Error listing tables: {e}")

# 5. Check for dictionary tables specifically
print("\n5️⃣  DICTIONARY APP TABLES:")
dictionary_tables = [
    'dictionary_koloquaentry',
    'dictionary_wordcategory',
    'dictionary_entryverification',
    'dictionary_entryvote',
    'dictionary_translationhistory'
]

try:
    with connection.cursor() as cursor:
        for table in dictionary_tables:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            """, [table])
            exists = cursor.fetchone()[0] > 0
            
            if exists:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"   ✓ {table}: {count} rows")
            else:
                print(f"   ✗ {table}: NOT FOUND")
except Exception as e:
    print(f"   ✗ Error checking tables: {e}")

# 6. Check django_migrations table
print("\n6️⃣  MIGRATION HISTORY IN THIS DATABASE:")
try:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT app, name 
            FROM django_migrations 
            WHERE app IN ('dictionary', 'users', 'gamification')
            ORDER BY app, id
        """)
        migrations = cursor.fetchall()
        
        if migrations:
            current_app = None
            for app, name in migrations:
                if app != current_app:
                    print(f"\n   {app}:")
                    current_app = app
                print(f"     • {name}")
        else:
            print("   ✗ NO MIGRATIONS RECORDED!")
            print("   This confirms migrations ran elsewhere!")
except Exception as e:
    print(f"   ✗ Error reading migrations: {e}")

# 7. Recommendation
print("\n" + "=" * 70)
print("🔍 DIAGNOSIS:")
print("=" * 70)

try:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'dictionary_koloquaentry'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM django_migrations 
            WHERE app = 'dictionary'
        """)
        migrations_exist = cursor.fetchone()[0] > 0
        
        if not table_exists and migrations_exist:
            print("❌ PROBLEM: Migrations exist but tables don't!")
            print("   This is unusual and suggests:")
            print("   1. Tables were manually deleted")
            print("   2. Database was restored from backup without tables")
            print("   3. Migration files don't match recorded migrations")
            print("\n💡 SOLUTION:")
            print("   python manage.py migrate --fake-initial")
            print("   python manage.py migrate dictionary --run-syncdb")
            
        elif not table_exists and not migrations_exist:
            print("❌ PROBLEM: Connected to WRONG database!")
            print("   Migrations show as applied locally, but this database is empty.")
            print("\n💡 SOLUTION:")
            print("   1. Run migrations on THIS database:")
            print("      python manage.py migrate")
            print("   2. Or check if you have multiple databases")
            
        elif table_exists:
            print("✅ Tables exist! MCP servers should work.")
            print("\n🧪 TEST:")
            print("   python test_db.py")
            
        else:
            print("⚠️  Unexpected state - manual investigation needed")
            
except Exception as e:
    print(f"Error during diagnosis: {e}")

print("=" * 70)