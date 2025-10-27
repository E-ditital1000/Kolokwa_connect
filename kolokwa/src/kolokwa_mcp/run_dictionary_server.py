#!/usr/bin/env python
"""Wrapper script to run the Kolokwa dictionary MCP server with HTTP transport"""
import os
import sys
import traceback
from pathlib import Path

# Redirect stdout to stderr for logging
sys.stdout = sys.stderr

try:
    print("=" * 60, file=sys.stderr)
    print("KOLOKWA DICTIONARY SERVER - STARTUP (HTTP)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    # Get the project root directory - USE CASE-SENSITIVE PATH RESOLUTION
    current_file = Path(__file__).resolve()
    
    # On Windows, Path.resolve() may change case. Get the actual case from the filesystem
    def get_actual_case_path(path: Path) -> Path:
        """Get the actual case-sensitive path on Windows"""
        if not path.exists():
            return path
        
        # Start from root and build up with actual case
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
    
    # Get actual case-sensitive paths
    print(f"Resolving case-sensitive paths...", file=sys.stderr)
    current_file = get_actual_case_path(current_file)
    
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
    
    # Configure Python path
    original_path = sys.path.copy()
    sys.path.clear()
    sys.path.append(str(kolokwa_connect_dir))
    sys.path.append(str(src_dir))
    
    for path in original_path:
        path_lower = path.lower()
        if any(x in path_lower for x in ['python310', 'python3', 'site-packages', '.venv', 'dll', 'lib']):
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
        print("⚠ Using default SECRET_KEY for build/inspection", file=sys.stderr)
    
    # Setup Django
    print("\nSetting up Django...", file=sys.stderr)
    import django
    django.setup()
    print("✓ Django setup complete", file=sys.stderr)
    
    # Detect environment
    IS_PREFLIGHT = os.getenv('FASTMCP_PREFLIGHT_CHECK') == 'true' or \
                   'preflight' in ' '.join(sys.argv).lower() or \
                   os.getenv('FASTMCP_CLOUD_URL') is not None
    
    if IS_PREFLIGHT:
        print("⚠ Pre-flight/Cloud environment detected", file=sys.stderr)
    
    # Import server components
    print("\nImporting server modules...", file=sys.stderr)
    from kolokwa_mcp.production_config import (
        create_server, print_startup_info, 
        handle_errors, handle_errors_sync, 
        track_performance, get_cached_or_compute, 
        metrics, logger, Config
    )
    
    # CRITICAL: Ensure HTTP transport is set before creating server
    os.environ['MCP_TRANSPORT'] = 'http'
    
    # Create server with explicit configuration
    mcp = create_server("kolokwa-dictionary")
    print("✓ MCP server created", file=sys.stderr)
    print(f"✓ Server type: {type(mcp).__name__}", file=sys.stderr)
    print(f"✓ Server module: {type(mcp).__module__}", file=sys.stderr)
    
    # Import Django models
    from dictionary.models import KoloquaEntry, WordCategory, TranslationHistory
    from users.models import User
    from django.db.models import Q, Count
    from django.db import connection
    from django.db.utils import OperationalError
    from asgiref.sync import sync_to_async
    import json
    from datetime import datetime
    
    # Defer database check
    print("⚠ Deferring database check to first request (fast startup)", file=sys.stderr)
    
    # Async version for runtime checks
    async def check_database_available():
        """Check if database is available and has tables - called lazily on demand"""
        @sync_to_async
        def _check():
            try:
                with connection.cursor() as cursor:
                    db_engine = connection.settings_dict['ENGINE']
                    
                    if 'sqlite' in db_engine:
                        cursor.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name='koloqua_entries'"
                        )
                    elif 'postgresql' in db_engine:
                        cursor.execute(
                            "SELECT tablename FROM pg_tables WHERE tablename='koloqua_entries'"
                        )
                    else:
                        cursor.execute("SELECT 1")
                    
                    result = cursor.fetchone()
                    return result is not None
            except Exception as e:
                logger.debug(f"Database check: {type(e).__name__}")
                return False
        
        return await _check()
    
    # Register resources
    @mcp.resource("kolokwa://dictionary/stats")
    @handle_errors_sync
    def get_dictionary_stats() -> str:
        """Get overall statistics about the Kolokwa dictionary"""
        def compute_stats():
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                
                return {
                    "status": "healthy",
                    "database_available": True,
                    "total_entries": KoloquaEntry.objects.filter(status='verified').count(),
                    "pending_entries": KoloquaEntry.objects.filter(status='pending').count(),
                    "total_contributors": User.objects.filter(contributions_count__gt=0).count(),
                    "words": KoloquaEntry.objects.filter(status='verified', entry_type='word').count(),
                    "phrases": KoloquaEntry.objects.filter(status='verified', entry_type='phrase').count(),
                }
            except Exception as e:
                logger.warning(f"Stats unavailable: {e}")
                return {
                    "status": "degraded",
                    "database_available": False,
                    "message": "Database statistics unavailable",
                    "capabilities": ["health_check", "search_dictionary (limited)"]
                }
        
        stats = get_cached_or_compute('dictionary_stats', compute_stats, ttl=60)
        return json.dumps(stats, indent=2)
    
    @mcp.tool()
    @handle_errors
    @track_performance("search_dictionary")
    async def search_dictionary(query: str, search_type: str = "all", limit: int = 10) -> str:
        """Search the Kolokwa dictionary"""
        if not query or not query.strip():
            return json.dumps({
                "error": "Invalid query",
                "message": "Query cannot be empty",
                "query": query
            }, indent=2)
        
        if search_type not in ["kolokwa", "english", "all"]:
            return json.dumps({
                "error": "Invalid search_type",
                "message": "search_type must be 'kolokwa', 'english', or 'all'",
                "query": query
            }, indent=2)
        
        limit = min(max(1, limit), Config.MAX_SEARCH_RESULTS)
        db_available = await check_database_available()
        
        @sync_to_async
        def _search():
            if not db_available:
                return None
            
            try:
                if search_type == "kolokwa":
                    results = KoloquaEntry.objects.filter(
                        status='verified', koloqua_text__icontains=query
                    )
                elif search_type == "english":
                    results = KoloquaEntry.objects.filter(
                        status='verified', english_translation__icontains=query
                    )
                else:
                    results = KoloquaEntry.objects.filter(
                        Q(status='verified'),
                        Q(koloqua_text__icontains=query) | 
                        Q(english_translation__icontains=query)
                    )
                
                results = results.distinct()[:limit]
                
                entries = []
                for entry in results:
                    entries.append({
                        "id": entry.id,
                        "kolokwa": entry.koloqua_text,
                        "english": entry.english_translation,
                        "entry_type": entry.entry_type,
                        "example_kolokwa": entry.example_sentence_koloqua if hasattr(entry, 'example_sentence_koloqua') else None,
                        "example_english": entry.example_sentence_english if hasattr(entry, 'example_sentence_english') else None,
                    })
                return entries
                
            except Exception as e:
                logger.error(f"Search error: {type(e).__name__}: {str(e)}")
                raise
        
        try:
            entries = await _search()
            
            if entries is None:
                return json.dumps({
                    "status": "unavailable",
                    "query": query,
                    "search_type": search_type,
                    "results": 0,
                    "entries": [],
                    "message": "Database not available. Search requires database connection."
                }, indent=2)
            
            return json.dumps({
                "status": "success",
                "query": query,
                "search_type": search_type,
                "results": len(entries),
                "entries": entries,
                "message": f"Found {len(entries)} result(s)" if entries else "No matching entries found"
            }, indent=2)
            
        except Exception as e:
            return json.dumps({
                "status": "error",
                "query": query,
                "error": str(e),
                "message": "An error occurred during search"
            }, indent=2)
    
    @mcp.tool()
    @handle_errors
    async def health_check() -> str:
        """Check if the MCP server is running and healthy"""
        db_available = await check_database_available()
        
        health_info = {
            "status": "healthy",
            "server": "kolokwa-dictionary",
            "version": "1.0.3",
            "transport": "http",
            "database_available": db_available,
            "environment": Config.ENVIRONMENT,
            "capabilities": {
                "search": db_available,
                "statistics": db_available,
                "health_check": True
            },
            "message": "Dictionary MCP server is operational"
        }
        
        if not db_available:
            health_info["status"] = "degraded"
            health_info["warning"] = "Database unavailable - limited functionality"
        
        return json.dumps(health_info, indent=2)
    
    print("✓ All tools and resources registered", file=sys.stderr)
    print_startup_info()
    
    # CRITICAL FIX: Properly expose FastMCP as ASGI app
    # FastMCP has an internal ASGI app that needs to be exposed
    print(f"\n🔍 Configuring ASGI application...", file=sys.stderr)
    
    # Check if FastMCP has a method to get the ASGI app
    if hasattr(mcp, 'get_asgi_app'):
        app = mcp.get_asgi_app()
        print(f"✓ Using mcp.get_asgi_app(): {type(app).__name__}", file=sys.stderr)
    elif hasattr(mcp, '_app'):
        app = mcp._app
        print(f"✓ Using mcp._app: {type(app).__name__}", file=sys.stderr)
    elif hasattr(mcp, 'app'):
        app = mcp.app
        print(f"✓ Using mcp.app: {type(app).__name__}", file=sys.stderr)
    else:
        # FastMCP itself might be callable as ASGI
        app = mcp
        print(f"✓ Using FastMCP instance directly: {type(app).__name__}", file=sys.stderr)
    
    # Verify app is callable
    if callable(app):
        print(f"✓ App is callable (ASGI-compatible)", file=sys.stderr)
    else:
        print(f"⚠ WARNING: App might not be ASGI-compatible!", file=sys.stderr)
        # Try wrapping it
        try:
            from fastmcp import FastMCP
            if isinstance(mcp, FastMCP):
                # Create a simple ASGI wrapper
                async def asgi_app(scope, receive, send):
                    # This is a fallback - FastMCP should handle this internally
                    await mcp(scope, receive, send)
                app = asgi_app
                print(f"✓ Created ASGI wrapper", file=sys.stderr)
        except Exception as e:
            print(f"⚠ Could not create wrapper: {e}", file=sys.stderr)
    
    print(f"\n✓ ASGI app ready: {type(app).__name__}", file=sys.stderr)
    print("✅ Server ready (database checks deferred)", file=sys.stderr)
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