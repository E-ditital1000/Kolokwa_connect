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
            # Get actual directory listing to find correct case
            parent = current.parent
            if parent.exists():
                try:
                    # List directory contents to get actual case
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
    
    mcp_dir = current_file.parent  # kolokwa_mcp
    src_dir = mcp_dir.parent  # src
    kolokwa_dir = src_dir.parent  # kolokwa
    kolokwa_connect_dir = kolokwa_dir.parent  # kolokwa_connect
    
    # Get actual case for kolokwa_connect directory
    kolokwa_connect_dir = get_actual_case_path(kolokwa_connect_dir)
    
    print(f"Current file: {current_file}", file=sys.stderr)
    print(f"MCP dir: {mcp_dir}", file=sys.stderr)
    print(f"Src dir: {src_dir}", file=sys.stderr)
    print(f"Kolokwa dir: {kolokwa_dir}", file=sys.stderr)
    print(f"Kolokwa_connect dir: {kolokwa_connect_dir}", file=sys.stderr)
    
    # Verify it's a Django project
    manage_py = kolokwa_connect_dir / 'manage.py'
    if not manage_py.exists():
        print(f"ERROR: manage.py not found at {manage_py}", file=sys.stderr)
        
        # Search for Django root
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
    
    print(f"\nDjango root verified: {kolokwa_connect_dir}", file=sys.stderr)
    
    # Clear sys.path and rebuild with actual case-sensitive paths
    original_path = sys.path.copy()
    sys.path.clear()
    
    # 1. Django project root - WITH ACTUAL CASE
    sys.path.append(str(kolokwa_connect_dir))
    
    # 2. MCP source directory
    sys.path.append(str(src_dir))
    
    # 3. Add back standard library paths
    for path in original_path:
        path_lower = path.lower()
        if any(x in path_lower for x in ['python310', 'python3', 'site-packages', '.venv', 'dll', 'lib']):
            if path not in sys.path:
                sys.path.append(path)
    
    print(f"\nPython Version: {sys.version}", file=sys.stderr)
    print(f"\nConfigured Python Path:", file=sys.stderr)
    for i, path in enumerate(sys.path[:6]):
        exists = "✓" if Path(path).exists() else "✗"
        print(f"  [{exists}] {i}: {path}", file=sys.stderr)
    
    # Find Django settings module - check actual directory structure
    print(f"\nLooking for Django settings...", file=sys.stderr)
    settings_module = None
    settings_path = None
    
    # Look for directories containing settings.py
    for item in kolokwa_connect_dir.iterdir():
        if item.is_dir():
            settings_file = item / 'settings.py'
            if settings_file.exists():
                # Use the ACTUAL directory name (with correct case)
                actual_dirname = item.name
                settings_module = f"{actual_dirname}.settings"
                settings_path = settings_file
                print(f"✓ Found settings module: {settings_module}", file=sys.stderr)
                print(f"  at: {settings_path}", file=sys.stderr)
                break
    
    if not settings_module:
        print("ERROR: Could not find Django settings.py!", file=sys.stderr)
        print(f"\nSearched in: {kolokwa_connect_dir}", file=sys.stderr)
        print("Contents:", file=sys.stderr)
        for item in kolokwa_connect_dir.iterdir():
            marker = "📁" if item.is_dir() else "📄"
            print(f"  {marker} {item.name}", file=sys.stderr)
        sys.exit(1)
    
    # Set Django settings with ACTUAL case
    os.environ['DJANGO_SETTINGS_MODULE'] = settings_module
    os.environ['MCP_TRANSPORT'] = 'http'
    
    # Ensure SECRET_KEY is set for Django (use a default for build/inspection)
    if not os.environ.get('SECRET_KEY'):
        # This is safe because it's only used during build/inspection, not in production runtime
        os.environ['SECRET_KEY'] = 'django-insecure-build-time-key-for-inspection-only-not-used-in-production'
        print("⚠ Using default SECRET_KEY for build/inspection phase", file=sys.stderr)
    
    print(f"\n✓ Django Settings Module: {settings_module}", file=sys.stderr)
    print(f"✓ Transport: http", file=sys.stderr)
    
    # Import and setup Django
    print("\nSetting up Django...", file=sys.stderr)
    import django
    django.setup()
    print("✓ Django setup complete", file=sys.stderr)
    
    # Detect pre-flight check or inspection environment
    IS_PREFLIGHT = os.getenv('FASTMCP_PREFLIGHT_CHECK') == 'true' or \
                   'preflight' in ' '.join(sys.argv).lower() or \
                   os.getenv('FASTMCP_CLOUD_URL') is not None
    
    if IS_PREFLIGHT:
        print("⚠ Pre-flight/Cloud environment detected - using safe mode", file=sys.stderr)
    
    # Import server components
    print("\nImporting server modules...", file=sys.stderr)
    from kolokwa_mcp.production_config import (
        create_server, print_startup_info, 
        handle_errors, handle_errors_sync, 
        track_performance, get_cached_or_compute, 
        metrics, logger, Config
    )
    
    print("✓ Production config imported", file=sys.stderr)
    
    # Create MCP server
    print("Creating MCP server...", file=sys.stderr)
    mcp = create_server("kolokwa-dictionary")
    print("✓ MCP server created", file=sys.stderr)
    
    # Import Django models
    print("Importing Django models...", file=sys.stderr)
    from dictionary.models import KoloquaEntry, WordCategory, TranslationHistory
    from users.models import User
    from django.db.models import Q, Count
    from django.db import connection
    from django.db.utils import OperationalError
    from asgiref.sync import sync_to_async
    import json
    print("✓ Django models imported", file=sys.stderr)
    
    # Helper function to check database availability
    def check_database_available():
        """Check if database is available and has tables"""
        if IS_PREFLIGHT:
            return False
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='dictionary_koloquaentry'"
                )
                return cursor.fetchone() is not None
        except Exception as e:
            print(f"Database check failed: {e}", file=sys.stderr)
            return False
    
    # Register resources and tools
    print("Registering resources and tools...", file=sys.stderr)
    
    @mcp.resource("kolokwa://dictionary/stats")
    @handle_errors_sync
    def get_dictionary_stats() -> str:
        """Get overall statistics about the Kolokwa dictionary"""
        def compute_stats():
            # Check if in pre-flight mode or database unavailable
            if not check_database_available():
                return {
                    "status": "healthy",
                    "mode": "preflight" if IS_PREFLIGHT else "no_database",
                    "message": "Server is running and ready to accept requests",
                    "note": "Database statistics will be available when connected to production database"
                }
            
            try:
                return {
                    "total_entries": KoloquaEntry.objects.filter(status='verified').count(),
                    "pending_entries": KoloquaEntry.objects.filter(status='pending').count(),
                    "total_contributors": User.objects.filter(contributions_count__gt=0).count(),
                    "words": KoloquaEntry.objects.filter(status='verified', entry_type='word').count(),
                    "phrases": KoloquaEntry.objects.filter(status='verified', entry_type='phrase').count(),
                }
            except Exception as e:
                return {
                    "error": "Database unavailable",
                    "message": str(e),
                    "note": "This is expected in demo/inspection environments"
                }
        
        stats = get_cached_or_compute('dictionary_stats', compute_stats)
        return json.dumps(stats, indent=2)
    
    @mcp.tool()
    @handle_errors
    @track_performance("search_dictionary")
    async def search_dictionary(query: str, search_type: str = "all", limit: int = 10) -> str:
        """Search the Kolokwa dictionary
        
        Args:
            query: The search term to look for
            search_type: Type of search - "kolokwa", "english", or "all"
            limit: Maximum number of results to return (default: 10)
            
        Returns:
            JSON string with search results
        """
        
        @sync_to_async
        def _search():
            # Check if database is available
            if not check_database_available():
                return []
            
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
                
                results = results.distinct()[:min(limit, Config.MAX_SEARCH_RESULTS)]
                
                entries = []
                for entry in results:
                    entries.append({
                        "id": entry.id,
                        "kolokwa": entry.koloqua_text,
                        "english": entry.english_translation,
                        "entry_type": entry.entry_type,
                    })
                return entries
                
            except Exception as e:
                print(f"Search error: {e}", file=sys.stderr)
                return []
        
        entries = await _search()
        
        if not entries:
            return json.dumps({
                "query": query,
                "search_type": search_type,
                "results": 0,
                "entries": [],
                "note": "No results found. Database may need initialization or no matching entries exist."
            }, indent=2)
        
        return json.dumps({
            "query": query,
            "search_type": search_type,
            "results": len(entries),
            "entries": entries
        }, indent=2)
    
    @mcp.tool()
    def health_check() -> str:
        """Check if the MCP server is running and healthy"""
        db_available = check_database_available()
        
        health_info = {
            "status": "healthy",
            "server": "kolokwa-dictionary",
            "transport": "http",
            "database_available": db_available,
            "environment": "preflight" if IS_PREFLIGHT else "production",
            "message": "MCP server is running and ready to accept requests"
        }
        
        if not db_available:
            health_info["note"] = "Database not available - using safe mode"
        
        return json.dumps(health_info, indent=2)
    
    print("✓ Registration complete", file=sys.stderr)
    print_startup_info()
    
    # Check if we're being inspected (this check happens at module level)
    # The 'fastmcp inspect' command will import this module to get the mcp object
    is_inspection = 'fastmcp' in sys.argv[0].lower() or 'inspect' in ' '.join(sys.argv).lower()
    
    if is_inspection:
        # During inspection, just expose the mcp object
        print("\n✓ MCP server initialized and ready for inspection", file=sys.stderr)
    else:
        # This is not inspection - it's actual runtime
        # The FastMCP cloud runtime will handle starting the server
        # We just need to expose the mcp object
        print("\n✓ MCP server initialized and ready for runtime", file=sys.stderr)
    
    # NOTE: We do NOT call mcp.run() here anymore!
    # FastMCP Cloud will handle running the server when it imports this module
    # The mcp object is exposed at module level for FastMCP to use
    
    # For FastMCP Cloud compatibility, also expose as 'app'
    app = mcp
    
except ImportError as e:
    print("\n" + "=" * 60, file=sys.stderr)
    print("❌ IMPORT ERROR", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Module: {e}", file=sys.stderr)
    print("\nTraceback:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    print("\nWorking Directory:", file=sys.stderr)
    print(f"  {os.getcwd()}", file=sys.stderr)
    print("\nPython Path (first 10):", file=sys.stderr)
    for i, path in enumerate(sys.path[:10]):
        exists = "✓" if Path(path).exists() else "✗"
        print(f"  [{exists}] {i}: {path}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    sys.exit(1)
    
except Exception as e:
    print("\n" + "=" * 60, file=sys.stderr)
    print("❌ FATAL ERROR", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Type: {type(e).__name__}", file=sys.stderr)
    print(f"Message: {str(e)}", file=sys.stderr)
    print("\nTraceback:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    sys.exit(1)