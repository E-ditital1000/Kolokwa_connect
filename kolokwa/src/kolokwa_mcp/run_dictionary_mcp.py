"""
Kolokwa Dictionary MCP Server using FastMCP
Provides dictionary lookup, search, and contribution tools.
"""

import os
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("KolokwaMCP")

# --- Environment ---
load_dotenv()
DB_CONFIG = {
    "host": os.getenv("DATABASE_HOST", "localhost"),
    "port": int(os.getenv("DATABASE_PORT", "5432")),
    "user": os.getenv("DATABASE_USER", "postgres"),
    "password": os.getenv("DATABASE_PASSWORD", ""),
    "database": os.getenv("DATABASE_NAME", "kolokwa_db"),
}

# --- Initialize MCP ---
mcp = FastMCP("kolokwa-dictionary")

# -------------------------------------------------------------------
# TOOLS
# -------------------------------------------------------------------

@mcp.tool()
async def search_kolokwa(query: str, search_type: str = "all", limit: int = 10) -> Dict[str, Any]:
    """Search the Kolokwa dictionary for words, phrases, or translations."""
    import asyncpg
    limit = min(limit, 50)
    try:
        conn = await asyncpg.connect(**DB_CONFIG, timeout=10)
        try:
            if search_type == "kolokwa":
                sql = """SELECT * FROM koloqua_entries
                         WHERE status='verified' AND (koloqua_text ILIKE $1 OR example_sentence_koloqua ILIKE $1)
                         ORDER BY upvotes - downvotes DESC LIMIT $2"""
            elif search_type == "english":
                sql = """SELECT * FROM koloqua_entries
                         WHERE status='verified' AND (english_translation ILIKE $1 OR example_sentence_english ILIKE $1)
                         ORDER BY upvotes - downvotes DESC LIMIT $2"""
            else:
                sql = """SELECT * FROM koloqua_entries
                         WHERE status='verified' AND (
                            koloqua_text ILIKE $1 OR english_translation ILIKE $1 OR
                            example_sentence_koloqua ILIKE $1 OR example_sentence_english ILIKE $1 OR
                            context_explanation ILIKE $1
                         )
                         ORDER BY upvotes - downvotes DESC LIMIT $2"""
            results = await conn.fetch(sql, f"%{query}%", limit)
            entries = [{
                "id": r["id"],
                "kolokwa": r["koloqua_text"],
                "english": r["english_translation"],
                "literal": r["literal_translation"],
                "type": r["entry_type"],
                "context": r["context_explanation"],
                "example_kolokwa": r["example_sentence_koloqua"],
                "example_english": r["example_sentence_english"],
                "pronunciation": r["pronunciation_guide"],
                "cultural_notes": r["cultural_notes"],
                "score": r["upvotes"] - r["downvotes"],
            } for r in results]
            return {"success": True, "count": len(entries), "entries": entries}
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Search error: {e}")
        return {"success": False, "error": str(e)}        

@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check if the MCP server is running properly."""
    import asyncpg
    try:
        conn = await asyncpg.connect(**DB_CONFIG, timeout=10)
        await conn.fetchval("SELECT 1")
        await conn.close()
        return {"success": True, "status": "healthy", "database": "connected"}
    except Exception as e:
        logger.warning(f"Health check issue: {e}")
        return {"success": True, "status": "running", "database": f"not_connected ({e})"}
