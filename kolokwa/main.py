"""
Kolokwa MCP Servers - Main Entry Point
Runs both dictionary and translation servers with HTTP/STDIO transport support
Supports: Claude Desktop (stdio), Studio (http dev), Streamable (http prod)
"""

import os
import sys

# Add project to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Kolokwa_connect.settings')

# Setup Django
import django
django.setup()

# Import configuration first
from production_config import Config, logger, run_http_server, print_startup_info

# Import servers (they're already initialized when imported)
from kolokwa_mcp import dictionary_server
from kolokwa_mcp import translation_server

# Expose the dictionary server's mcp instance for `mcp dev` and `uvicorn`
mcp = dictionary_server.mcp

def print_server_info():
    """Print information about loaded servers"""
    logger.info("=" * 60)
    logger.info("Kolokwa MCP Servers - Combined Entry Point")
    logger.info("=" * 60)
    
    # Dictionary server info
    dict_tools = len(dictionary_server.mcp.list_tools())
    dict_resources = len(dictionary_server.mcp.list_resources())
    logger.info(f"Dictionary Server: {dict_tools} tools, {dict_resources} resources")
    
    # Translation server info
    trans_tools = len(translation_server.mcp.list_tools())
    trans_prompts = len(translation_server.mcp.list_prompts())
    logger.info(f"Translation Server: {trans_tools} tools, {trans_prompts} prompts")
    
    logger.info("=" * 60)
    logger.info(f"Transport Mode: {Config.TRANSPORT}")
    
    if Config.TRANSPORT == "http":
        logger.info(f"Server URL: http://{Config.HTTP_HOST}:{Config.HTTP_PORT}")
        logger.info(f"API Documentation: http://{Config.HTTP_HOST}:{Config.HTTP_PORT}/docs")
        logger.info(f"Health Check: http://{Config.HTTP_HOST}:{Config.HTTP_PORT}/health")
    else:
        logger.info("Mode: STDIO (Claude Desktop)")
    
    logger.info("=" * 60)
    logger.info("Ready to serve MCP requests")


def main():
    """Main entry point with transport selection"""
    
    # Print startup information
    print_startup_info()
    print_server_info()
    
    # Determine how to run based on transport configuration
    if Config.TRANSPORT == "http":
        logger.info("Starting in HTTP mode...")
        logger.info("Use Ctrl+C to stop the server")
        run_http_server(mcp, Config.HTTP_PORT, Config.HTTP_HOST)
    else:
        logger.info("Starting in STDIO mode (Claude Desktop)...")
        mcp.run()


# ============================================================================
# DUAL MODE SUPPORT
# ============================================================================

def run_stdio():
    """Run in STDIO mode for Claude Desktop"""
    logger.info("Running in STDIO mode for Claude Desktop")
    mcp.run()


def run_http(port: int = None, host: str = None):
    """Run in HTTP mode for Studio/Streamable"""
    port = port or Config.HTTP_PORT
    host = host or Config.HTTP_HOST
    
    logger.info(f"Running in HTTP mode on {host}:{port}")
    logger.info(f"Access API docs at: http://{host}:{port}/docs")
    
    run_http_server(mcp, port, host)


# ============================================================================
# CLI SUPPORT (Optional)
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    # Check if being run via uvicorn, mcp dev, or fastmcp inspect
    # If so, just do initialization without running the server
    inspection_keywords = ['uvicorn', 'mcp', 'fastmcp', 'inspect']
    is_being_inspected = any(keyword in ' '.join(sys.argv).lower() for keyword in inspection_keywords)
    
    if is_being_inspected:
        print_startup_info()
        print_server_info()
        logger.info("✓ Server initialized (not starting - will be run by external tool)")
    else:
        # Parse command line arguments for direct execution
        parser = argparse.ArgumentParser(
            description='Kolokwa MCP Servers',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # STDIO mode (Claude Desktop)
  python __main__.py
  
  # HTTP mode (Studio/Streamable)
  python __main__.py --http
  python __main__.py --http --port 8000
  
  # Using uvicorn (recommended for HTTP)
  uvicorn kolokwa_mcp.__main__:mcp --port 8000 --reload
  
  # Using mcp dev command
  mcp dev kolokwa_mcp.__main__:mcp
            """
        )
        
        parser.add_argument(
            '--http',
            action='store_true',
            help='Run in HTTP mode instead of STDIO'
        )
        
        parser.add_argument(
            '--port',
            type=int,
            default=Config.HTTP_PORT,
            help=f'Port for HTTP mode (default: {Config.HTTP_PORT})'
        )
        
        parser.add_argument(
            '--host',
            default=Config.HTTP_HOST,
            help=f'Host for HTTP mode (default: {Config.HTTP_HOST})'
        )
        
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug mode'
        )
        
        args = parser.parse_args()
        
        # Override config if debug specified
        if args.debug:
            Config.DEBUG = True
            Config.LOG_LEVEL = 'DEBUG'
            import logging
            logger.setLevel(logging.DEBUG)
        
        # Override transport if --http specified
        if args.http:
            Config.TRANSPORT = 'http'
        
        # Run main entry point
        if Config.TRANSPORT == 'http':
            run_http(args.port, args.host)
        else:
            run_stdio()


# ============================================================================
# HEALTH CHECK ENDPOINT (for HTTP mode)
# ============================================================================

@mcp.resource("kolokwa://health")
def health_check() -> str:
    """Health check endpoint for load balancers and monitoring"""
    from production_config import check_database_health, check_redis_health
    import json
    
    db_healthy, db_msg = check_database_health()
    redis_healthy, redis_msg = check_redis_health()
    
    health_status = {
        "status": "healthy" if (db_healthy and redis_healthy) else "degraded",
        "services": {
            "database": {
                "status": "healthy" if db_healthy else "unhealthy",
                "message": db_msg
            },
            "redis": {
                "status": "healthy" if redis_healthy else "unhealthy",
                "message": redis_msg
            },
            "dictionary_server": {
                "status": "healthy",
                "tools": len(dictionary_server.mcp.list_tools()),
                "resources": len(dictionary_server.mcp.list_resources())
            },
            "translation_server": {
                "status": "healthy",
                "tools": len(translation_server.mcp.list_tools()),
                "prompts": len(translation_server.mcp.list_prompts())
            }
        },
        "transport": Config.TRANSPORT,
        "version": "1.0.0"
    }
    
    return json.dumps(health_status, indent=2)


# ============================================================================
# COMBINED SERVER INFO RESOURCE
# ============================================================================

@mcp.resource("kolokwa://servers/info")
def server_info() -> str:
    """Get information about all loaded MCP servers"""
    import json
    
    info = {
        "servers": [
            {
                "name": "dictionary",
                "type": "Dictionary & Language Database",
                "tools": [tool.name for tool in dictionary_server.mcp.list_tools()],
                "resources": [res.name for res in dictionary_server.mcp.list_resources()],
                "description": "Search and manage Kolokwa dictionary entries"
            },
            {
                "name": "translator",
                "type": "Translation Services",
                "tools": [tool.name for tool in translation_server.mcp.list_tools()],
                "prompts": [prompt.name for prompt in translation_server.mcp.list_prompts()],
                "description": "Translate between Kolokwa and English"
            }
        ],
        "configuration": {
            "transport": Config.TRANSPORT,
            "debug": Config.DEBUG,
            "auth_enabled": Config.AUTH_ENABLED,
            "cache_enabled": Config.CACHE_ENABLED,
            "cors_enabled": Config.CORS_ENABLED
        }
    }
    
    return json.dumps(info, indent=2)


# ============================================================================
# EXPORT FOR DIFFERENT USE CASES
# ============================================================================

# For uvicorn: uvicorn kolokwa_mcp.__main__:mcp
app = mcp

# For programmatic access
def get_dictionary_server():
    """Get the dictionary server instance"""
    return dictionary_server.mcp

def get_translation_server():
    """Get the translation server instance"""
    return translation_server.mcp

def get_combined_server():
    """Get the combined server instance"""
    return mcp