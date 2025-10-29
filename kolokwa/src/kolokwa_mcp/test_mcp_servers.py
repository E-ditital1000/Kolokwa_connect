"""
Test script for MCP servers
"""

import asyncio
import asyncpg
import json
import logging
from dotenv import load_dotenv
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DATABASE_HOST', 'localhost'),
    'port': int(os.getenv('DATABASE_PORT', 5432)),
    'user': os.getenv('DATABASE_USER', 'postgres'),
    'password': os.getenv('DATABASE_PASSWORD', ''),
    'database': os.getenv('DATABASE_NAME', 'kolokwa_db')
}


async def test_database_connection():
    """Test database connectivity"""
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        # Test query
        result = await conn.fetchval("SELECT COUNT(*) FROM koloqua_entries WHERE status = 'verified'")
        logger.info(f"✓ Database connection successful")
        logger.info(f"  Found {result} verified entries")
        
        await conn.close()
        return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        return False


async def test_dictionary_search():
    """Test dictionary search functionality"""
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        # Test search
        results = await conn.fetch("""
            SELECT koloqua_text, english_translation
            FROM koloqua_entries
            WHERE status = 'verified'
            LIMIT 5
        """)
        
        logger.info(f"✓ Dictionary search works")
        logger.info(f"  Sample entries:")
        for row in results:
            logger.info(f"    - {row['koloqua_text']}: {row['english_translation']}")
        
        await conn.close()
        return True
    except Exception as e:
        logger.error(f"✗ Dictionary search failed: {e}")
        return False


async def test_openai_connection():
    """Test OpenAI API connectivity"""
    try:
        from openai import AsyncOpenAI
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("⚠ OpenAI API key not configured")
            return False
        
        client = AsyncOpenAI(api_key=api_key)
        
        # Simple test
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'test successful' if you can read this."}],
            max_tokens=10
        )
        
        logger.info(f"✓ OpenAI connection successful")
        logger.info(f"  Response: {response.choices[0].message.content}")
        return True
    except Exception as e:
        logger.error(f"✗ OpenAI connection failed: {e}")
        return False


async def test_mcp_import():
    """Test if MCP server can be imported"""
    try:
        from run_dictionary_mcp import mcp
        logger.info(f"✓ MCP server import successful")
        logger.info(f"  Server name: {mcp.name}")
        
        # Try to get tool list
        if hasattr(mcp, '_tools'):
            logger.info(f"  Tools registered: {len(mcp._tools)}")
            for tool_name in list(mcp._tools.keys())[:5]:
                logger.info(f"    - {tool_name}")
        
        return True
    except Exception as e:
        logger.error(f"✗ MCP server import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("Testing Kolokwa MCP Servers")
    logger.info("=" * 60)
    
    tests = [
        ("MCP Server Import", test_mcp_import),
        ("Database Connection", test_database_connection),
        ("Dictionary Search", test_dictionary_search),
        ("OpenAI Connection", test_openai_connection),
    ]
    
    results = {}
    for test_name, test_func in tests:
        logger.info(f"\nTesting: {test_name}")
        logger.info("-" * 40)
        results[test_name] = await test_func()
    
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    for test_name, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    all_passed = all(results.values())
    logger.info("\n" + ("All tests passed! ✓" if all_passed else "Some tests failed! ✗"))
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)