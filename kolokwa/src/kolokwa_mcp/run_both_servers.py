"""
Runner script to start both MCP servers simultaneously
"""

import sys
import os
import asyncio
import logging
from pathlib import Path
import signal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mcp_servers.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_event = asyncio.Event()


async def run_dictionary_server():
    """Run dictionary server"""
    try:
        from dictionary_server import init_db_pool, close_db_pool, mcp as dict_mcp
        
        await init_db_pool()
        logger.info("Dictionary server initialized")
        
        # Run until shutdown
        await dict_mcp.run(transport='stdio')
        
    except Exception as e:
        logger.error(f"Dictionary server error: {e}")
    finally:
        await close_db_pool()


async def run_translation_server():
    """Run translation server"""
    try:
        from translation_server import init_clients, close_clients, mcp as trans_mcp
        
        await init_clients()
        logger.info("Translation server initialized")
        
        # Run until shutdown
        await trans_mcp.run(transport='stdio')
        
    except Exception as e:
        logger.error(f"Translation server error: {e}")
    finally:
        await close_clients()


async def main():
    """Main entry point - run both servers"""
    logger.info("=" * 60)
    logger.info("Starting Both Kolokwa MCP Servers")
    logger.info("=" * 60)
    
    # Create tasks for both servers
    tasks = [
        asyncio.create_task(run_dictionary_server(), name="dictionary"),
        asyncio.create_task(run_translation_server(), name="translation")
    ]
    
    try:
        # Wait for shutdown signal
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        # Cancel all tasks
        for task in tasks:
            task.cancel()
        
        # Wait for cancellation
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All servers stopped")


def handle_shutdown(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    shutdown_event.set()


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")
