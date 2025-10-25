#!/usr/bin/env python
"""
Quick test to diagnose why database check is failing
Run this from: kolokwa_connect/
"""
import os
import sys
from pathlib import Path

# Add project to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Load environment
from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Kolokwa_connect.settings')

print("=" * 70)
print("QUICK DATABASE CONNECTION TEST")
print("=" * 70)
print()

# Check environment variables
print("1️⃣  Environment Variables:")
print(f"   DATABASE_ENGINE: {os.getenv('DATABASE_ENGINE', 'NOT SET')}")
print(f"   DATABASE_NAME: {os.getenv('DATABASE_NAME', 'NOT SET')}")
print(f"   DATABASE_HOST: {os.getenv('DATABASE_HOST', 'NOT SET')}")
print(f"   DATABASE_PORT: {os.getenv('DATABASE_PORT', 'NOT SET')}")
print(f"   DATABASE_USER: {os.getenv('DATABASE_USER', 'NOT SET')}")
print(f"   DATABASE_PASSWORD: {'***' if os.getenv('DATABASE_PASSWORD') else 'NOT SET'}")
print()

# Setup Django
print("2️⃣  Setting up Django...")
try:
    import django
    django.setup()
    print("   ✓ Django setup complete")
except Exception as e:
    print(f"   ✗ Django setup failed: {e}")
    sys.exit(1)

print()

# Test database connection
print("3️⃣  Testing database connection...")
try:
    from django.db import connection
    from django.conf import settings
    
    db_settings = settings.DATABASES['default']
    print(f"   Engine: {db_settings['ENGINE']}")
    print(f"   Name: {db_settings['NAME']}")
    print(f"   Host: {db_settings['HOST']}")
    print(f"   Port: {db_settings['PORT']}")
    print()
    
    # Try to connect
    print("   Attempting connection...")
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print("   ✓ Basic connection: SUCCESS")
        
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"   ✓ PostgreSQL version: {version[0][:60]}...")
        
except Exception as e:
    print(f"   ✗ Connection FAILED: {type(e).__name__}")
    print(f"   ✗ Error: {str(e)}")
    print()
    print("COMMON FIXES:")
    print("  1. Check if Railway database is running")
    print("  2. Verify credentials in .env file")
    print("  3. Check if your IP is whitelisted (Railway usually allows all)")
    print("  4. Test with: psql postgresql://postgres:PASSWORD@metro.proxy.rlwy.net:28643/railway")
    sys.exit(1)

print()

# Check for tables
print("4️⃣  Checking for dictionary tables...")
try:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename = 'dictionary_koloquaentry'
        """)
        result = cursor.fetchone()
        
        if result:
            print(f"   ✓ Table 'dictionary_koloquaentry' found!")
            
            # Count entries
            cursor.execute("SELECT COUNT(*) FROM dictionary_koloquaentry")
            count = cursor.fetchone()
            print(f"   ✓ Total entries: {count[0]}")
            
            cursor.execute("SELECT COUNT(*) FROM dictionary_koloquaentry WHERE status='verified'")
            verified = cursor.fetchone()
            print(f"   ✓ Verified entries: {verified[0]}")
            
        else:
            print(f"   ✗ Table 'dictionary_koloquaentry' NOT FOUND")
            print()
            print("   FIX: Run migrations")
            print("   Command: python manage.py migrate")
            
except Exception as e:
    print(f"   ✗ Table check failed: {str(e)}")

print()

# Test the EXACT check used in MCP server
print("5️⃣  Testing MCP server database check (exact replica)...")
try:
    with connection.cursor() as cursor:
        db_engine = connection.settings_dict['ENGINE']
        print(f"   Engine detected: {db_engine}")
        
        if 'sqlite' in db_engine:
            print("   Using SQLite query...")
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dictionary_koloquaentry'"
            )
        elif 'postgresql' in db_engine:
            print("   Using PostgreSQL query...")
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE tablename='dictionary_koloquaentry'"
            )
        else:
            print("   Using generic query...")
            cursor.execute("SELECT 1")
        
        result = cursor.fetchone()
        available = result is not None
        
        if available:
            print(f"   ✓ MCP check result: AVAILABLE")
            print()
            print("=" * 70)
            print("✅ SUCCESS! Database should work with MCP server")
            print("=" * 70)
        else:
            print(f"   ✗ MCP check result: NOT AVAILABLE")
            print(f"   ✗ Query returned: {result}")
            print()
            print("=" * 70)
            print("❌ PROBLEM: Table not found")
            print("=" * 70)
            print()
            print("FIX:")
            print("  python manage.py migrate")
            
except Exception as e:
    print(f"   ✗ MCP check failed: {type(e).__name__}")
    print(f"   ✗ Error: {str(e)}")
    print()
    print("=" * 70)
    print("❌ PROBLEM: Database query failed")
    print("=" * 70)

print()