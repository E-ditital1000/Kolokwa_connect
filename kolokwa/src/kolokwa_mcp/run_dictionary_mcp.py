"""
Kolokwa Dictionary MCP Server using FastMCP
Provides dictionary lookup, search, and contribution tools.
"""

import os
import logging
from typing import Optional, Dict, Any

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Load environment variables ---
from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DATABASE_HOST", "localhost"),
    "port": int(os.getenv("DATABASE_PORT", "5432")),
    "user": os.getenv("DATABASE_USER", "postgres"),
    "password": os.getenv("DATABASE_PASSWORD", ""),
    "database": os.getenv("DATABASE_NAME", "kolokwa_db"),
}

# --- MCP Setup ---
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("kolokwa-dictionary")

# -------------------------------------------------------------------
#  TOOL DEFINITIONS
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
                "score": r["upvotes"] - r["downvotes"]
            } for r in results]
            return {"success": True, "query": query, "search_type": search_type, "count": len(entries), "entries": entries}
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Search error: {e}")
        return {"success": False, "error": str(e), "query": query}


@mcp.tool()
async def get_entry_details(entry_id: int) -> Dict[str, Any]:
    """Get full details for a specific dictionary entry."""
    import asyncpg
    try:
        conn = await asyncpg.connect(**DB_CONFIG, timeout=10)
        try:
            row = await conn.fetchrow("""
                SELECT e.*, u.username AS contributor_username
                FROM koloqua_entries e LEFT JOIN users u ON e.contributor_id = u.id
                WHERE e.id = $1
            """, entry_id)
            if not row:
                return {"success": False, "error": f"Entry with ID {entry_id} not found"}
            return {
                "success": True,
                "entry": {
                    "id": row["id"],
                    "kolokwa": row["koloqua_text"],
                    "english": row["english_translation"],
                    "literal": row["literal_translation"],
                    "type": row["entry_type"],
                    "context": row["context_explanation"],
                    "example_kolokwa": row["example_sentence_koloqua"],
                    "example_english": row["example_sentence_english"],
                    "pronunciation": row["pronunciation_guide"],
                    "cultural_notes": row["cultural_notes"],
                    "region": row["region_specific"],
                    "upvotes": row["upvotes"],
                    "downvotes": row["downvotes"],
                    "score": row["upvotes"] - row["downvotes"],
                    "status": row["status"],
                    "verification_count": row["verification_count"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "contributor": row["contributor_username"]
                }
            }
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Get entry error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_random_entries(count: int = 5, entry_type: Optional[str] = None) -> Dict[str, Any]:
    """Get random dictionary entries."""
    import asyncpg
    count = min(count, 20)
    try:
        conn = await asyncpg.connect(**DB_CONFIG, timeout=10)
        try:
            if entry_type:
                results = await conn.fetch("""
                    SELECT * FROM koloqua_entries WHERE status='verified' AND entry_type=$1
                    ORDER BY RANDOM() LIMIT $2
                """, entry_type, count)
            else:
                results = await conn.fetch("""
                    SELECT * FROM koloqua_entries WHERE status='verified'
                    ORDER BY RANDOM() LIMIT $1
                """, count)
            entries = [{
                "id": r["id"],
                "kolokwa": r["koloqua_text"],
                "english": r["english_translation"],
                "type": r["entry_type"],
                "example_kolokwa": r["example_sentence_koloqua"],
                "example_english": r["example_sentence_english"],
                "pronunciation": r["pronunciation_guide"],
                "score": r["upvotes"] - r["downvotes"]
            } for r in results]
            return {"success": True, "count": len(entries), "entries": entries}
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Random entries error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_dictionary_stats() -> Dict[str, Any]:
    """Get statistics about the dictionary."""
    import asyncpg
    try:
        conn = await asyncpg.connect(**DB_CONFIG, timeout=10)
        try:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE status='verified') AS verified_entries,
                    COUNT(*) FILTER (WHERE status='pending') AS pending_entries,
                    COUNT(DISTINCT contributor_id) AS total_contributors,
                    COUNT(*) FILTER (WHERE entry_type='word') AS total_words,
                    COUNT(*) FILTER (WHERE entry_type='phrase') AS total_phrases,
                    COUNT(*) FILTER (WHERE entry_type='idiom') AS total_idioms,
                    COUNT(*) FILTER (WHERE entry_type='proverb') AS total_proverbs
                FROM koloqua_entries
            """)
            return {
                "success": True,
                "stats": {
                    "verified_entries": stats["verified_entries"],
                    "pending_entries": stats["pending_entries"],
                    "total_contributors": stats["total_contributors"],
                    "breakdown": {
                        "words": stats["total_words"],
                        "phrases": stats["total_phrases"],
                        "idioms": stats["total_idioms"],
                        "proverbs": stats["total_proverbs"]
                    }
                }
            }
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check if the MCP server is healthy."""
    import asyncpg
    try:
        conn = await asyncpg.connect(**DB_CONFIG, timeout=10)
        await conn.fetchval("SELECT 1")
        await conn.close()
        return {"success": True, "status": "healthy", "database": "connected"}
    except Exception as e:
        logger.warning(f"Health check warning: {e}")
        return {"success": True, "status": "running", "database": f"not_connected ({e})"}

# -------------------------------------------------------------------
#  ENTRY POINT (GUARDED)
# -------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    try:
        logger.info("Starting Kolokwa Dictionary MCP Server...")
        asyncio.run(mcp.run())
    except RuntimeError as e:
        if "already running" in str(e).lower():
            logger.warning("Async event loop already running — skipping duplicate run.")
        else:
            raise
