#!/usr/bin/env python
"""Wrapper script to run the Kolokwa translation MCP server with HTTP transport"""
import os
import sys
import traceback
from pathlib import Path

# Redirect stdout to stderr for logging
sys.stdout = sys.stderr

try:
    print("=" * 60, file=sys.stderr)
    print("KOLOKWA TRANSLATION SERVER - STARTUP (HTTP)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    # Get the project root directory
    # This file is at: kolokwa/src/kolokwa_mcp/run_translator_server.py
    # Project root is 3 levels up: /app
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent  # /app
    mcp_src_dir = current_file.parent.parent  # /app/kolokwa/src
    
    # Add BOTH paths - project root first, then MCP src
    sys.path.insert(0, str(project_root))
    sys.path.insert(1, str(mcp_src_dir))
    
    print(f"Project Root: {project_root}", file=sys.stderr)
    print(f"MCP Src Dir: {mcp_src_dir}", file=sys.stderr)
    print(f"Python Version: {sys.version}", file=sys.stderr)
    
    # Set Django settings
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Kolokwa_connect.settings')
    
    # Force HTTP transport for Render deployment
    os.environ['MCP_TRANSPORT'] = 'http'
    
    print(f"Django Settings: {os.environ.get('DJANGO_SETTINGS_MODULE')}", file=sys.stderr)
    print(f"Transport: {os.environ.get('MCP_TRANSPORT')}", file=sys.stderr)
    
    # Import Django first
    print("Setting up Django...", file=sys.stderr)
    import django
    django.setup()
    print("Django setup complete", file=sys.stderr)
    
    # Now import the server components
    print("Importing server modules...", file=sys.stderr)
    
    # Import production config
    from kolokwa_mcp.production_config import create_server, print_startup_info
    from kolokwa_mcp.production_config import handle_errors, handle_errors_sync, track_performance
    from kolokwa_mcp.production_config import get_cached_or_compute, metrics, logger
    
    print("Creating MCP server...", file=sys.stderr)
    mcp = create_server("kolokwa-translator")
    
    # Import and register the tools/resources
    print("Registering tools and resources...", file=sys.stderr)
    from dictionary.models import KoloquaEntry, TranslationHistory
    from asgiref.sync import sync_to_async
    import json
    
    # Register all the translation server functions
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "translator_server_defs",
        current_file.parent / "translator_server.py"
    )
    translator_server_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(translator_server_module)
    
    print("Module imported successfully!", file=sys.stderr)
    print_startup_info()
    print("Starting MCP server with HTTP transport...", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    # Get HTTP configuration from environment or use defaults
    http_host = os.getenv('MCP_HTTP_HOST', '0.0.0.0')
    http_port = int(os.getenv('MCP_HTTP_PORT', '8000'))
    
    print(f"HTTP Server: {http_host}:{http_port}", file=sys.stderr)
    print(f"Visit: http://localhost:{http_port}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    # Run with HTTP transport
    # FastMCP will create a web server and handle HTTP requests
    mcp.run(transport='http', host=http_host, port=http_port)
    
except ImportError as e:
    print("=" * 60, file=sys.stderr)
    print("IMPORT ERROR", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Failed to import module: {e}", file=sys.stderr)
    print("\nFull Traceback:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    print("\nPython Path:", file=sys.stderr)
    for i, path in enumerate(sys.path):
        exists = "✓" if Path(path).exists() else "✗"
        print(f"  [{exists}] {i}: {path}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    sys.exit(1)
    
except Exception as e:
    print("=" * 60, file=sys.stderr)
    print("FATAL ERROR", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Error Type: {type(e).__name__}", file=sys.stderr)
    print(f"Error Message: {str(e)}", file=sys.stderr)
    print("\nFull Traceback:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    sys.exit(1)