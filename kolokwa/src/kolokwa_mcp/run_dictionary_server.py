#!/usr/bin/env python
"""Wrapper script to run the Kolokwa dictionary MCP server with HTTP transport"""
import os
import sys
import traceback
from pathlib import Path

# Redirect stdout to stderr for logging
sys.stdout = sys.stderr

def get_actual_case_path(path: Path) -> Path:
    """Get the actual case-sensitive path on Windows"""
    if not path.exists():
        return path
    
    parts = []
    current = path
    
    while current != current.parent:
        parent = current.parent
        if parent.exists():
            try:
                actual_name = None
                for item in parent.iterdir():
                    if item.name.lower() == current.name.lower():
                        actual_name = item.name
                        break
                
                if actual_name:
                    parts.insert(0, actual_name)
                else:
                    parts.insert(0, current.name)
            except:
                parts.insert(0, current.name)
        else:
            parts.insert(0, current.name)
        
        current = parent
    
    # Reconstruct path with actual case
    result = Path(current)
    for part in parts:
        result = result / part
    
    return result

# Module-level variable for ASGI server
app = None

try:
    print("=" * 60, file=sys.stderr)
    print("KOLOKWA DICTIONARY SERVER - STARTUP (HTTP)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    # Get paths
    print(f"Resolving case-sensitive paths...", file=sys.stderr)
    current_file = get_actual_case_path(Path(__file__).resolve())
    
    mcp_dir = current_file.parent
    src_dir = mcp_dir.parent
    kolokwa_dir = src_dir.parent
    kolokwa_connect_dir = kolokwa_dir.parent
    kolokwa_connect_dir = get_actual_case_path(kolokwa_connect_dir)
    
    print(f"Current file: {current_file}", file=sys.stderr)
    print(f"Django root: {kolokwa_connect_dir}", file=sys.stderr)
    
    # Verify Django project
    manage_py = kolokwa_connect_dir / 'manage.py'
    if not manage_py.exists():
        print(f"ERROR: manage.py not found at {manage_py}", file=sys.stderr)
        search_dir = current_file.parent
        found = False
        for _ in range(5):
            search_dir = search_dir.parent
            test_manage = search_dir / 'manage.py'
            if test_manage.exists():
                kolokwa_connect_dir = get_actual_case_path(search_dir)
                print(f"Found Django root at: {kolokwa_connect_dir}", file=sys.stderr)
                found = True
                break
        
        if not found:
            print("ERROR: Could not find Django project root!", file=sys.stderr)
            sys.exit(1)
    
    # Configure Python path FIRST
    original_path = sys.path.copy()
    sys.path.clear()
    sys.path.insert(0, str(kolokwa_connect_dir))
    sys.path.insert(1, str(src_dir))
    
    for path in original_path:
        path_lower = path.lower()
        if any(x in path_lower for x in ['python310', 'python311', 'python312', 'python3', 'site-packages', '.venv', 'dll', 'lib']):
            if path not in sys.path:
                sys.path.append(path)
    
    print(f"\nPython Path configured:", file=sys.stderr)
    for i, path in enumerate(sys.path[:6]):
        exists = "✓" if Path(path).exists() else "✗"
        print(f"  [{exists}] {i}: {path}", file=sys.stderr)
    
    # Find Django settings
    print(f"\nLooking for Django settings...", file=sys.stderr)
    settings_module = None
    
    for item in kolokwa_connect_dir.iterdir():
        if item.is_dir():
            settings_file = item / 'settings.py'
            if settings_file.exists():
                actual_dirname = item.name
                settings_module = f"{actual_dirname}.settings"
                print(f"✓ Found settings module: {settings_module}", file=sys.stderr)
                break
    
    if not settings_module:
        print("ERROR: Could not find Django settings.py!", file=sys.stderr)
        sys.exit(1)
    
    # Set environment
    os.environ['DJANGO_SETTINGS_MODULE'] = settings_module
    os.environ['MCP_TRANSPORT'] = 'http'
    
    if not os.environ.get('SECRET_KEY'):
        os.environ['SECRET_KEY'] = 'django-insecure-build-time-key-for-inspection-only'
    
    # Setup Django
    print("\nSetting up Django...", file=sys.stderr)
    import django
    django.setup()
    print("✓ Django setup complete", file=sys.stderr)
    
    # Import server components
    print("\nImporting server modules...", file=sys.stderr)
    from kolokwa_mcp.production_config import (
        create_server, print_startup_info, 
        handle_errors, handle_errors_sync, 
        track_performance, get_cached_or_compute, 
        metrics, logger, Config
    )
    
    # Create server
    mcp = create_server("kolokwa-dictionary")
    print("✓ MCP server created", file=sys.stderr)
    print(f"✓ Server type: {type(mcp).__name__}", file=sys.stderr)
    
    # Import Django models
    from dictionary.models import KoloquaEntry, WordCategory, TranslationHistory
    from users.models import User
    from django.db.models import Q, Count
    from django.db import connection
    from django.db.utils import OperationalError
    from asgiref.sync import sync_to_async
    import json
    from datetime import datetime
    
    print("⚠ Deferring database check to first request (fast startup)", file=sys.stderr)
    
    async def check_database_available():
        """Check if database is available"""
        @sync_to_async
        def _check():
            try:
                with connection.cursor() as cursor:
                    db_engine = connection.settings_dict['ENGINE']
                    if 'sqlite' in db_engine:
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='koloqua_entries'")
                    elif 'postgresql' in db_engine:
                        cursor.execute("SELECT tablename FROM pg_tables WHERE tablename='koloqua_entries'")
                    else:
                        cursor.execute("SELECT 1")
                    return cursor.fetchone() is not None
            except Exception as e:
                logger.debug(f"Database check: {type(e).__name__}")
                return False
        return await _check()
    
    # Register resources
    @mcp.resource("kolokwa://dictionary/stats")
    @handle_errors_sync
    def get_dictionary_stats() -> str:
        """Get dictionary statistics"""
        def compute_stats():
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                return {
                    "status": "healthy",
                    "database_available": True,
                    "total_entries": KoloquaEntry.objects.filter(status='verified').count(),
                    "pending_entries": KoloquaEntry.objects.filter(status='pending').count(),
                    "total_contributors": User.objects.filter(contributions_count__gt=0).count(),
                }
            except Exception as e:
                return {"status": "degraded", "database_available": False}
        return json.dumps(get_cached_or_compute('dictionary_stats', compute_stats, ttl=60), indent=2)
    
    @mcp.tool()
    @handle_errors
    @track_performance("search_dictionary")
    async def search_dictionary(query: str, search_type: str = "all", limit: int = 10) -> str:
        """Search the Kolokwa dictionary"""
        if not query or not query.strip():
            return json.dumps({"error": "Invalid query"}, indent=2)
        
        if search_type not in ["kolokwa", "english", "all"]:
            return json.dumps({"error": "Invalid search_type"}, indent=2)
        
        limit = min(max(1, limit), Config.MAX_SEARCH_RESULTS)
        db_available = await check_database_available()
        
        @sync_to_async
        def _search():
            if not db_available:
                return None
            try:
                if search_type == "kolokwa":
                    results = KoloquaEntry.objects.filter(status='verified', koloqua_text__icontains=query)
                elif search_type == "english":
                    results = KoloquaEntry.objects.filter(status='verified', english_translation__icontains=query)
                else:
                    results = KoloquaEntry.objects.filter(
                        Q(status='verified'),
                        Q(koloqua_text__icontains=query) | Q(english_translation__icontains=query)
                    )
                
                entries = []
                for entry in results.distinct()[:limit]:
                    entries.append({
                        "id": entry.id,
                        "kolokwa": entry.koloqua_text,
                        "english": entry.english_translation,
                        "entry_type": entry.entry_type,
                    })
                return entries
            except Exception as e:
                logger.error(f"Search error: {e}")
                raise
        
        try:
            entries = await _search()
            if entries is None:
                return json.dumps({"status": "unavailable"}, indent=2)
            return json.dumps({"status": "success", "results": len(entries), "entries": entries}, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)}, indent=2)
    
    @mcp.tool()
    @handle_errors
    async def health_check() -> str:
        """Check server health"""
        db_available = await check_database_available()
        return json.dumps({
            "status": "healthy" if db_available else "degraded",
            "server": "kolokwa-dictionary",
            "database_available": db_available,
        }, indent=2)
    
    print("✓ All tools and resources registered", file=sys.stderr)
    print_startup_info()
    
    # Extract the correct ASGI application from FastMCP
    print(f"\n🔍 Setting up ASGI application...", file=sys.stderr)
    
    # FastMCP exposes http_app for HTTP transport
    app = mcp.http_app
    
    print(f"✅ ASGI app ready: {type(app).__name__}", file=sys.stderr)
    print("✅ Server initialized successfully", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
except ImportError as e:
    print("\n" + "=" * 60, file=sys.stderr)
    print("❌ IMPORT ERROR", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Module: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
    
except Exception as e:
    print("\n" + "=" * 60, file=sys.stderr)
    print("❌ FATAL ERROR", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Type: {type(e).__name__}", file=sys.stderr)
    print(f"Message: {str(e)}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)