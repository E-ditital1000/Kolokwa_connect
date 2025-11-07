import os
import logging
import asyncpg
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------
# Kolokwa Dictionary MCP Server (Production-Ready)
# ---------------------------------------------------------------
# Provides dictionary lookup, translation, and health monitoring
# for the Liberian Kolokwa Dictionary platform.
# ---------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger("KolokwaMCP")

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DATABASE_HOST", "localhost"),
    "port": int(os.getenv("DATABASE_PORT", "5432")),
    "user": os.getenv("DATABASE_USER", "postgres"),
    "password": os.getenv("DATABASE_PASSWORD", ""),
    "database": os.getenv("DATABASE_NAME", "kolokwa_db"),
}

mcp = FastMCP("kolokwa-dictionary")

async def get_connection():
    try:
        conn = await asyncpg.connect(**DB_CONFIG, timeout=10)
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

@mcp.tool()
async def search_kolokwa(query: str, search_type: str = "all", limit: int = 10):
    """Search the Kolokwa dictionary for words, phrases, or translations."""
    limit = min(limit, 50)
    query = query.strip()
    if not query:
        return {"success": False, "error": "Query cannot be empty."}

    SQL_QUERIES = {
        "kolokwa": """SELECT * FROM koloqua_entries
                        WHERE status='verified' AND (koloqua_text ILIKE $1 OR example_sentence_koloqua ILIKE $1)
                        ORDER BY upvotes - downvotes DESC, created_at DESC LIMIT $2""",
        "english": """SELECT * FROM koloqua_entries
                        WHERE status='verified' AND (english_translation ILIKE $1 OR example_sentence_english ILIKE $1)
                        ORDER BY upvotes - downvotes DESC, created_at DESC LIMIT $2""",
        "all": """SELECT * FROM koloqua_entries
                    WHERE status='verified' AND (
                        koloqua_text ILIKE $1 OR english_translation ILIKE $1 OR
                        example_sentence_koloqua ILIKE $1 OR example_sentence_english ILIKE $1 OR
                        context_explanation ILIKE $1 OR cultural_notes ILIKE $1
                    )
                    ORDER BY upvotes - downvotes DESC, created_at DESC LIMIT $2""",
    }

    sql = SQL_QUERIES.get(search_type, SQL_QUERIES["all"])

    try:
        conn = await get_connection()
        results = await conn.fetch(sql, f"%{query}%", limit)
        await conn.close()

        entries = [
            {
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
                "score": (r["upvotes"] or 0) - (r["downvotes"] or 0),
            }
            for r in results
        ]

        return {"success": True, "count": len(entries), "entries": entries}

    except Exception as e:
        logger.error(f"Search error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def health_check():
    """Check if the MCP server and database are healthy."""
    try:
        conn = await get_connection()
        await conn.fetchval("SELECT 1")
        await conn.close()
        return {"success": True, "status": "healthy", "database": "connected"}
    except Exception as e:
        logger.warning(f"Health check issue: {e}")
        return {"success": True, "status": "running", "database": f"not_connected ({e})"}

@mcp.tool()
async def get_entry_detail(entry_id: int):
    """Retrieve full details for a specific dictionary entry by ID."""
    try:
        conn = await get_connection()
        result = await conn.fetchrow("SELECT * FROM koloqua_entries WHERE id = $1 AND status='verified'", entry_id)
        await conn.close()

        if not result:
            return {"success": False, "error": "Entry not found or not verified."}

        entry = dict(result)
        entry["score"] = (entry.get("upvotes", 0) or 0) - (entry.get("downvotes", 0) or 0)

        return {"success": True, "entry": entry}

    except Exception as e:
        logger.error(f"Error retrieving entry detail: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    logger.info("Starting Kolokwa Dictionary MCP Server...")
    logger.info(f"Database host: {DB_CONFIG['host']}")
    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server stopped manually.")
    except Exception as e:
        logger.critical(f"Fatal server error: {e}")
