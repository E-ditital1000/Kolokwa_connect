"""
Static Files Verification Script for Kolokwa Connect
Run this to check which static files are missing
"""

import os
from pathlib import Path

# Get the base directory (where manage.py is)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / 'Kolokwa_connect' / 'static'

# Required static files from your templates
required_files = [
    'lib/owlcarousel/assets/owl.carousel.min.css',
    'css/style.css',
    'lib/easing/easing.min.js',
    'lib/waypoints/waypoints.min.js',
    'lib/counterup/counterup.min.js',
    'lib/owlcarousel/owl.carousel.min.js',
    'js/main.js',
    'img/logo.png',
]

print("Checking static files...")
print("=" * 70)
print(f"Static directory: {STATIC_DIR}")
print(f"Static directory exists: {STATIC_DIR.exists()}")
print("=" * 70)

if not STATIC_DIR.exists():
    print(f"\n❌ ERROR: Static directory not found at {STATIC_DIR}")
    print("\nPlease create the directory structure:")
    print(f"  mkdir {STATIC_DIR}")
    exit(1)

missing_files = []
found_files = []

for file_path in required_files:
    full_path = STATIC_DIR / file_path
    if full_path.exists():
        found_files.append(file_path)
        file_size = full_path.stat().st_size
        print(f"✓ Found: {file_path} ({file_size:,} bytes)")
    else:
        missing_files.append(file_path)
        print(f"✗ Missing: {file_path}")

print("=" * 70)
print(f"\nSummary:")
print(f"Found: {len(found_files)}/{len(required_files)}")
print(f"Missing: {len(missing_files)}/{len(required_files)}")

if missing_files:
    print("\n⚠️  Missing files:")
    for f in missing_files:
        print(f"  - {f}")
        # Suggest directory creation
        dir_path = STATIC_DIR / Path(f).parent
        if not dir_path.exists():
            print(f"    Create directory: {dir_path}")
    
    print("\n📝 Next steps:")
    print("1. Create missing directories")
    print("2. Download/add the missing files")
    print("3. Run: python manage.py collectstatic")
else:
    print("\n✅ All static files found!")
    print("\nYou can now run:")
    print("  python manage.py collectstatic")
    print("  python manage.py runserver 127.0.0.1:3000")

# Run it with:
# python check_static_files.py