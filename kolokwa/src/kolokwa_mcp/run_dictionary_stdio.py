#!/usr/bin/env python
"""Run Kolokwa Dictionary MCP Server with STDIO transport for Claude Desktop"""
import os
import sys
from pathlib import Path

# FORCE development settings BEFORE any imports
os.environ['ENVIRONMENT'] = 'development'
os.environ['MCP_AUTH_ENABLED'] = 'False'
os.environ['CACHE_ENABLED'] = 'False'
os.environ['DEBUG'] = 'True'
os.environ['LOG_LEVEL'] = 'DEBUG'
os.environ['MCP_TRANSPORT'] = 'stdio'

# Redirect stdout to stderr for logging (keep stdin/stdout clean for MCP protocol)
original_stdout = sys.stdout
sys.stdout = sys.stderr

try:
    # Setup paths
    current_file = Path(__file__).resolve()
    # This file is at: kolokwa_connect/kolokwa/src/kolokwa_mcp/run_dictionary_stdio.py
    # Go up 4 levels to reach kolokwa_connect root
    project_root = current_file.parent.parent.parent.parent  # kolokwa_connect
    mcp_src_dir = current_file.parent  # kolokwa_mcp directory
    
    sys.path.insert(0, str(project_root))
    sys.path.insert(1, str(mcp_src_dir))
    
    print(f"Starting Dictionary Server (STDIO)", file=sys.stderr)
    print(f"Project Root: {project_root}", file=sys.stderr)
    print(f"Environment: {os.environ.get('ENVIRONMENT')}", file=sys.stderr)
    print(f"Auth: {os.environ.get('MCP_AUTH_ENABLED')}", file=sys.stderr)
    
    # Setup Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Kolokwa_connect.settings')
    
    import django
    django.setup()
    print("Django setup complete", file=sys.stderr)
    
    # Import the server module - it's in the same directory
    from dictionary_server import mcp as dictionary_mcp
    
    print("Server loaded successfully", file=sys.stderr)
    print("Ready for Claude Desktop", file=sys.stderr)
    
    # Restore stdout for MCP protocol
    sys.stdout = original_stdout
    
    # Run the server
    dictionary_mcp.run(transport='stdio')
    
except Exception as e:
    import traceback
    print(f"FATAL ERROR: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)