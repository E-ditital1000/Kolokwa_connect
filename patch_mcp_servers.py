#!/usr/bin/env python
"""Patch MCP server files to use correct table names"""
import sys
from pathlib import Path

def patch_file(filepath: Path, old_text: str, new_text: str) -> bool:
    """Patch a file by replacing text"""
    try:
        content = filepath.read_text(encoding='utf-8')
        
        if old_text not in content:
            print(f"⚠ Pattern not found in {filepath.name}")
            return False
        
        new_content = content.replace(old_text, new_text)
        filepath.write_text(new_content, encoding='utf-8')
        print(f"✓ Patched {filepath.name}")
        return True
    except Exception as e:
        print(f"✗ Error patching {filepath.name}: {e}")
        return False

def main():
    print("=" * 70)
    print("PATCHING MCP SERVERS FOR CORRECT TABLE NAMES")
    print("=" * 70)
    
    # Find the server files
    base_dir = Path(__file__).resolve().parent
    
    # Look for MCP server files
    server_files = [
        base_dir / "src" / "kolokwa_mcp" / "mcp" / "dictionary_server.py",
        base_dir / "src" / "kolokwa_mcp" / "mcp" / "translation_server.py",
    ]
    
    # Alternative locations
    if not server_files[0].exists():
        server_files = [
            base_dir / "kolokwa_mcp" / "mcp" / "dictionary_server.py",
            base_dir / "kolokwa_mcp" / "mcp" / "translation_server.py",
        ]
    
    # Check if files exist
    for f in server_files:
        if not f.exists():
            print(f"✗ File not found: {f}")
            print("\nPlease provide the correct path to your MCP server files.")
            sys.exit(1)
    
    print(f"\nFound server files:")
    for f in server_files:
        print(f"  • {f.relative_to(base_dir)}")
    
    # Pattern to replace
    old_pattern = """            if 'sqlite' in db_engine:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='dictionary_koloquaentry'"
                )
            elif 'postgresql' in db_engine:
                cursor.execute(
                    "SELECT tablename FROM pg_tables WHERE tablename='dictionary_koloquaentry'"
                )"""
    
    new_pattern = """            if 'sqlite' in db_engine:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='koloqua_entries'"
                )
            elif 'postgresql' in db_engine:
                cursor.execute(
                    "SELECT tablename FROM pg_tables WHERE tablename='koloqua_entries'"
                )"""
    
    print("\n" + "=" * 70)
    print("APPLYING PATCHES...")
    print("=" * 70)
    
    success_count = 0
    for filepath in server_files:
        if patch_file(filepath, old_pattern, new_pattern):
            success_count += 1
    
    print("\n" + "=" * 70)
    if success_count == len(server_files):
        print(f"✅ SUCCESS: Patched {success_count}/{len(server_files)} files")
        print("\nNext steps:")
        print("  1. Test with: python test_db.py")
        print("  2. Restart your MCP servers")
        print("  3. Test server health checks")
    else:
        print(f"⚠ PARTIAL: Patched {success_count}/{len(server_files)} files")
        print("\nSome files may need manual patching.")
    print("=" * 70)

if __name__ == "__main__":
    main()