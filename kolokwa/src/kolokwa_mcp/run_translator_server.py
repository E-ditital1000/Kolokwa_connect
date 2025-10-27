#!/usr/bin/env python
"""Wrapper script to run the Kolokwa translation MCP server with HTTP transport"""
import os
import sys
import traceback
from pathlib import Path

# Redirect stdout to stderr for logging
sys.stdout = sys.stderr

# Module-level variable for ASGI server
app = None

try:
    print("=" * 60, file=sys.stderr)
    print("KOLOKWA TRANSLATION SERVER - STARTUP (HTTP)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
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
        
        result = Path(current)
        for part in parts:
            result = result / part
        
        return result
    
    # Setup paths
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
    
    # Configure Python path
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
                settings_module = f"{item.name}.settings"
                print(f"✓ Found settings: {settings_module}", file=sys.stderr)
                break
    
    if not settings_module:
        print("ERROR: Could not find Django settings.py!", file=sys.stderr)
        sys.exit(1)
    
    # Set environment
    os.environ['DJANGO_SETTINGS_MODULE'] = settings_module
    os.environ['MCP_TRANSPORT'] = 'http'
    
    if not os.environ.get('SECRET_KEY'):
        os.environ['SECRET_KEY'] = 'django-insecure-build-time-key-for-inspection-only'
        print("⚠ Using default SECRET_KEY", file=sys.stderr)
    
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
    print("✓ Production config imported", file=sys.stderr)
    
    # Create server
    mcp = create_server("kolokwa-translator")
    print("✓ MCP server created", file=sys.stderr)
    print(f"✓ Server type: {type(mcp).__name__}", file=sys.stderr)
    
    # Import Django models
    print("Importing Django models...", file=sys.stderr)
    from dictionary.models import KoloquaEntry, TranslationHistory
    from django.db.models import Q
    from django.db import connection
    from asgiref.sync import sync_to_async
    import json
    print("✓ Django models imported", file=sys.stderr)
    
    print("⚠ Deferring database check to first request (fast startup)", file=sys.stderr)
    
    # Helper functions
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
    
    @sync_to_async
    def _find_relevant_entries_sync(text: str, search_english: bool, limit: int):
        """Find dictionary entries relevant to the given text."""
        try:
            words = text.lower().split()
            
            if search_english:
                results = KoloquaEntry.objects.filter(
                    status='verified'
                ).filter(
                    Q(english_translation__icontains=text) |
                    Q(english_translation__in=words)
                ).distinct()[:limit]
            else:
                results = KoloquaEntry.objects.filter(
                    status='verified'
                ).filter(
                    Q(koloqua_text__icontains=text) |
                    Q(koloqua_text__in=words)
                ).distinct()[:limit]
            
            return list(results)
        except Exception as e:
            logger.error(f"Error finding entries: {e}")
            return []
    
    def format_dictionary_context(entries: list, db_available: bool = True) -> str:
        """Format dictionary entries as context for translation."""
        if not db_available:
            return "Database unavailable - no dictionary context available."
        
        if not entries:
            return "No relevant dictionary entries found."
        
        context = ["Relevant dictionary entries:"]
        for entry in entries:
            entry_str = f"- {entry.koloqua_text} → {entry.english_translation}"
            if hasattr(entry, 'example_sentence_koloqua') and entry.example_sentence_koloqua:
                entry_str += f"\n  Example: {entry.example_sentence_koloqua}"
            context.append(entry_str)
        
        return "\n".join(context)
    
    # Register prompts
    print("Registering prompts...", file=sys.stderr)
    
    @mcp.prompt()
    @handle_errors_sync
    def translate_to_kolokwa(text: str) -> str:
        """Translate English text to Kolokwa using dictionary context.
        
        Args:
            text: English text to translate to Kolokwa
            
        Returns:
            A prompt with dictionary context for translation
        """
        if not text or not text.strip():
            return "Error: Translation text cannot be empty."
        
        import asyncio
        db_available = asyncio.run(check_database_available())
        
        if not db_available:
            return f"""Translation Unavailable

⚠️ Database not available - cannot provide translation context.

Text requested: "{text}"

Error: The Kolokwa dictionary database is currently unavailable. Translation requires access to the verified dictionary entries for accurate context.

Please ensure:
1. Database connection is established
2. Dictionary tables exist
3. Server has proper database credentials

Translation cannot proceed without database access."""
        
        entries = asyncio.run(_find_relevant_entries_sync(text, search_english=True, limit=5))
        
        if not entries:
            return f"""Translation Context Not Found

No dictionary entries found for: "{text}"

The Kolokwa dictionary does not contain relevant entries for the words in your text. Translation requires verified dictionary entries for accuracy.

Suggestion: Check if the words exist in the dictionary using the search_dictionary tool, or contribute new entries to the dictionary."""
        
        context_str = format_dictionary_context(entries, db_available)
        
        return f"""Translate English to Kolokwa using dictionary context.

{context_str}

Text to translate: "{text}"

Instructions:
1. Use ONLY the dictionary entries above for translation
2. Provide the Kolokwa translation based on verified entries
3. If any words are not in the dictionary, state that they cannot be translated
4. Do not guess or invent translations - only use verified dictionary data"""
    
    @mcp.prompt()
    @handle_errors_sync
    def translate_to_english(text: str) -> str:
        """Translate Kolokwa text to English using dictionary context.
        
        Args:
            text: Kolokwa text to translate to English
            
        Returns:
            A prompt with dictionary context for translation
        """
        if not text or not text.strip():
            return "Error: Translation text cannot be empty."
        
        import asyncio
        db_available = asyncio.run(check_database_available())
        
        if not db_available:
            return f"""Translation Unavailable

⚠️ Database not available - cannot provide translation context.

Text requested: "{text}"

Error: The Kolokwa dictionary database is currently unavailable. Translation requires access to the verified dictionary entries for accurate context.

Please ensure:
1. Database connection is established
2. Dictionary tables exist
3. Server has proper database credentials

Translation cannot proceed without database access."""
        
        entries = asyncio.run(_find_relevant_entries_sync(text, search_english=False, limit=5))
        
        if not entries:
            return f"""Translation Context Not Found

No dictionary entries found for: "{text}"

The Kolokwa dictionary does not contain relevant entries for the words in your text. Translation requires verified dictionary entries for accuracy.

Suggestion: Check if the words exist in the dictionary using the search_dictionary tool, or contribute new entries to the dictionary."""
        
        context_str = format_dictionary_context(entries, db_available)
        
        return f"""Translate Kolokwa to English using dictionary context.

{context_str}

Text to translate: "{text}"

Instructions:
1. Use ONLY the dictionary entries above for translation
2. Provide the English translation based on verified entries
3. If any words are not in the dictionary, state that they cannot be translated
4. Do not guess or invent translations - only use verified dictionary data"""
    
    print("✓ Prompts registered", file=sys.stderr)
    
    # Register tools
    print("Registering tools...", file=sys.stderr)
    
    @mcp.tool()
    @handle_errors
    @track_performance("find_translation_context")
    async def find_translation_context(text: str, language: str) -> str:
        """Find relevant dictionary entries to help with translation.
        
        Args:
            text: The text to find context for
            language: The language of the text - "kolokwa" or "english"
            
        Returns:
            JSON string with relevant dictionary entries
        """
        if not text or not text.strip():
            return json.dumps({
                "status": "error",
                "error": "Invalid input",
                "message": "Text cannot be empty"
            }, indent=2)
        
        if language not in ['kolokwa', 'english']:
            return json.dumps({
                "status": "error",
                "error": "Invalid language",
                "message": "Language must be 'kolokwa' or 'english'"
            }, indent=2)
        
        db_available = await check_database_available()
        
        if not db_available:
            return json.dumps({
                "status": "unavailable",
                "text": text,
                "language": language,
                "entries": [],
                "context": "Database not available",
                "message": "Translation context requires database connection.",
                "suggestion": "Translations will work but without dictionary context"
            }, indent=2)
        
        search_english = (language == "english")
        entries = await _find_relevant_entries_sync(text, search_english, 10)
        
        context_str = format_dictionary_context(entries, db_available)
        
        entry_list = []
        for entry in entries:
            entry_list.append({
                "kolokwa": entry.koloqua_text,
                "english": entry.english_translation,
                "type": entry.entry_type
            })
        
        return json.dumps({
            "status": "success",
            "text": text,
            "language": language,
            "found": len(entries),
            "entries": entry_list,
            "context": context_str,
            "message": f"Found {len(entries)} relevant entries" if entries else "No relevant entries found"
        }, indent=2)
    
    @mcp.tool()
    @handle_errors
    async def health_check() -> str:
        """Check if the translation MCP server is running and healthy"""
        db_available = await check_database_available()
        
        health_info = {
            "status": "healthy" if db_available else "degraded",
            "server": "kolokwa-translator",
            "version": "1.0.0",
            "transport": "http",
            "database_available": db_available,
            "environment": Config.ENVIRONMENT,
            "capabilities": {
                "translate_to_kolokwa": db_available,
                "translate_to_english": db_available,
                "find_context": db_available,
                "health_check": True
            },
            "message": "Translation MCP server is operational" if db_available else "Translation unavailable - database required"
        }
        
        if not db_available:
            health_info["warning"] = "All translation features require database access"
            health_info["note"] = "This server provides dictionary-based translations only"
        
        return json.dumps(health_info, indent=2)
    
    print("✓ Tools registered", file=sys.stderr)
    print("✓ All prompts and tools registered", file=sys.stderr)
    print_startup_info()
    
    # Extract the ASGI application from FastMCP
    print(f"\n🔍 Setting up ASGI application...", file=sys.stderr)
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

    