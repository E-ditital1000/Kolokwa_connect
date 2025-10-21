#!/usr/bin/env python
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

original_stdout = sys.stdout
sys.stdout = sys.stderr

try:
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent.parent
    mcp_src_dir = current_file.parent.parent
    
    sys.path.insert(0, str(project_root))
    sys.path.insert(1, str(mcp_src_dir))
    
    print(f"Starting Translation Server (STDIO)", file=sys.stderr)
    print(f"Project Root: {project_root}", file=sys.stderr)
    print(f"Environment: {os.environ.get('ENVIRONMENT')}", file=sys.stderr)
    print(f"Auth: {os.environ.get('MCP_AUTH_ENABLED')}", file=sys.stderr)
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Kolokwa_connect.settings')
    
    import django
    django.setup()
    print("Django setup complete", file=sys.stderr)
    
    from kolokwa_mcp import translation_server
    
    print(f"Tools: {len(translation_server.mcp.list_tools())}", file=sys.stderr)
    print(f"Prompts: {len(translation_server.mcp.list_prompts())}", file=sys.stderr)
    print("Ready for Claude Desktop", file=sys.stderr)
    
    sys.stdout = original_stdout
    translation_server.mcp.run()
    
except Exception as e:
    import traceback
    print(f"ERROR: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)