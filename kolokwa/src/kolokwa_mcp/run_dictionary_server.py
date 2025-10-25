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
    
    # Create server
    mcp = create_server("kolokwa-dictionary")
    print("✓ MCP server created", file=sys.stderr)
    
    # Import Django models
    from dictionary.models import KoloquaEntry, WordCategory, TranslationHistory
    from users.models import User
    from django.db.models import Q, Count
    from django.db import connection
    from django.db.utils import OperationalError
    from asgiref.sync import sync_to_async
    import json
    
    # IMPROVED: Better database availability check
    def check_database_available():
        """Check if database is available and has tables"""
        # Allow database access in production even during preflight
        # Only skip if explicitly told to or if database doesn't exist
        try:
            with connection.cursor() as cursor:
                # Check for both SQLite and PostgreSQL
                db_engine = connection.settings_dict['ENGINE']
                if 'sqlite' in db_engine:
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='dictionary_koloquaentry'"
                    )
                elif 'postgresql' in db_engine:
                    cursor.execute(
                        "SELECT tablename FROM pg_tables WHERE tablename='dictionary_koloquaentry'"
                    )
                else:
                    # Generic check
                    cursor.execute("SELECT 1")
                
                result = cursor.fetchone()
                available = result is not None
                if available:
                    print(f"✓ Database available ({db_engine})", file=sys.stderr)
                return available
        except Exception as e:
            print(f"⚠ Database unavailable: {type(e).__name__}: {str(e)}", file=sys.stderr)
            return False
    
    # Check database at startup
    DB_AVAILABLE = check_database_available()
    
    # Register resources
    @mcp.resource("kolokwa://dictionary/stats")
    @handle_errors_sync
    def get_dictionary_stats() -> str:
        """Get overall statistics about the Kolokwa dictionary"""
        def compute_stats():
            if not DB_AVAILABLE:
                return {
                    "status": "healthy",
                    "mode": "limited",
                    "database_available": False,
                    "message": "Server is running. Database statistics unavailable.",
                    "capabilities": [
                        "health_check available",
                        "search_dictionary available (demo mode)",
                        "Database required for full functionality"
                    ]
                }
            
            try:
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
                logger.error(f"Stats error: {e}")
                return {
                    "status": "degraded",
                    "database_available": False,
                    "error": "Could not retrieve statistics",
                    "message": str(e)
                }
        
        stats = get_cached_or_compute('dictionary_stats', compute_stats, ttl=60)
        return json.dumps(stats, indent=2)
    
    @mcp.tool()
    @handle_errors
    @track_performance("search_dictionary")
    async def search_dictionary(query: str, search_type: str = "all", limit: int = 10) -> str:
        """Search the Kolokwa dictionary
        
        Args:
            query: The search term to look for
            search_type: Type of search - "kolokwa", "english", or "all"
            limit: Maximum number of results to return (default: 10, max: 50)
            
        Returns:
            JSON string with search results
        """
        # Validate inputs
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
        
        @sync_to_async
        def _search():
            if not DB_AVAILABLE:
                return None  # Signal database unavailable
            
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
                    "message": "Database not available. Search requires database connection.",
                    "suggestion": "Check database configuration and ensure tables are created."
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
    def health_check() -> str:
        """Check if the MCP server is running and healthy"""
        db_available = check_database_available()
        
        health_info = {
            "status": "healthy",
            "server": "kolokwa-dictionary",
            "version": "1.0.0",
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
    
    # Expose server instance
    app = mcp
    
    if DB_AVAILABLE:
        print("\n✅ Server ready with full database access", file=sys.stderr)
    else:
        print("\n⚠️  Server ready in limited mode (no database)", file=sys.stderr)
    
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