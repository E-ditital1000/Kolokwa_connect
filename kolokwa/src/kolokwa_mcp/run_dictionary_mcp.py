"""
Kolokwa Dictionary MCP Server using FastMCP
Provides dictionary lookup, search, and contribution tools
"""

import os
import sys
import logging
from typing import Optional, List, Dict, Any
import asyncpg
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DATABASE_HOST', 'localhost'),
    'port': int(os.getenv('DATABASE_PORT', 5432)),
    'user': os.getenv('DATABASE_USER', 'postgres'),
    'password': os.getenv('DATABASE_PASSWORD', ''),
    'database': os.getenv('DATABASE_NAME', 'kolokwa_db')
}

# Import FastMCP
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("kolokwa-dictionary")

# Database connection pool
db_pool = None


async def get_db_pool():
    """Get or create database connection pool"""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            min_size=2,
            max_size=10
        )
        logger.info("Database connection pool initialized")
    return db_pool


@mcp.tool()
async def search_kolokwa(
    query: str,
    search_type: str = "all",
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search the Kolokwa dictionary for words, phrases, or translations.
    
    Args:
        query: Search term (Kolokwa word, English translation, or phrase)
        search_type: Type of search - 'kolokwa', 'english', or 'all' (default)
        limit: Maximum number of results to return (default 10, max 50)
    
    Returns:
        Dictionary containing search results with entry details
    """
    limit = min(limit, 50)
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            if search_type == "kolokwa":
                results = await conn.fetch("""
                    SELECT 
                        id, koloqua_text, english_translation, literal_translation,
                        entry_type, context_explanation, example_sentence_koloqua,
                        example_sentence_english, pronunciation_guide, cultural_notes,
                        upvotes, downvotes, status
                    FROM koloqua_entries
                    WHERE status = 'verified'
                    AND (koloqua_text ILIKE $1 OR example_sentence_koloqua ILIKE $1)
                    ORDER BY upvotes - downvotes DESC
                    LIMIT $2
                """, f"%{query}%", limit)
            
            elif search_type == "english":
                results = await conn.fetch("""
                    SELECT 
                        id, koloqua_text, english_translation, literal_translation,
                        entry_type, context_explanation, example_sentence_koloqua,
                        example_sentence_english, pronunciation_guide, cultural_notes,
                        upvotes, downvotes, status
                    FROM koloqua_entries
                    WHERE status = 'verified'
                    AND (english_translation ILIKE $1 OR example_sentence_english ILIKE $1)
                    ORDER BY upvotes - downvotes DESC
                    LIMIT $2
                """, f"%{query}%", limit)
            
            else:  # search_type == "all"
                results = await conn.fetch("""
                    SELECT 
                        id, koloqua_text, english_translation, literal_translation,
                        entry_type, context_explanation, example_sentence_koloqua,
                        example_sentence_english, pronunciation_guide, cultural_notes,
                        upvotes, downvotes, status
                    FROM koloqua_entries
                    WHERE status = 'verified'
                    AND (
                        koloqua_text ILIKE $1 
                        OR english_translation ILIKE $1
                        OR example_sentence_koloqua ILIKE $1
                        OR example_sentence_english ILIKE $1
                        OR context_explanation ILIKE $1
                    )
                    ORDER BY upvotes - downvotes DESC
                    LIMIT $2
                """, f"%{query}%", limit)
            
            entries = []
            for row in results:
                entries.append({
                    'id': row['id'],
                    'kolokwa': row['koloqua_text'],
                    'english': row['english_translation'],
                    'literal': row['literal_translation'],
                    'type': row['entry_type'],
                    'context': row['context_explanation'],
                    'example_kolokwa': row['example_sentence_koloqua'],
                    'example_english': row['example_sentence_english'],
                    'pronunciation': row['pronunciation_guide'],
                    'cultural_notes': row['cultural_notes'],
                    'score': row['upvotes'] - row['downvotes']
                })
            
            return {
                'success': True,
                'query': query,
                'search_type': search_type,
                'count': len(entries),
                'entries': entries
            }
    
    except Exception as e:
        logger.error(f"Search error: {e}")
        return {
            'success': False,
            'error': str(e),
            'query': query
        }


@mcp.tool()
async def get_entry_details(entry_id: int) -> Dict[str, Any]:
    """
    Get complete details for a specific dictionary entry.
    
    Args:
        entry_id: The database ID of the entry
    
    Returns:
        Complete entry details including metadata and examples
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    e.id, e.koloqua_text, e.english_translation, e.literal_translation,
                    e.entry_type, e.context_explanation, e.example_sentence_koloqua,
                    e.example_sentence_english, e.pronunciation_guide, e.cultural_notes,
                    e.upvotes, e.downvotes, e.status, e.created_at, e.updated_at,
                    e.region_specific, e.verification_count,
                    u.username as contributor_username,
                    u.email as contributor_email
                FROM koloqua_entries e
                LEFT JOIN users u ON e.contributor_id = u.id
                WHERE e.id = $1
            """, entry_id)
            
            if not row:
                return {
                    'success': False,
                    'error': f'Entry with ID {entry_id} not found'
                }
            
            return {
                'success': True,
                'entry': {
                    'id': row['id'],
                    'kolokwa': row['koloqua_text'],
                    'english': row['english_translation'],
                    'literal': row['literal_translation'],
                    'type': row['entry_type'],
                    'context': row['context_explanation'],
                    'example_kolokwa': row['example_sentence_koloqua'],
                    'example_english': row['example_sentence_english'],
                    'pronunciation': row['pronunciation_guide'],
                    'cultural_notes': row['cultural_notes'],
                    'region': row['region_specific'],
                    'upvotes': row['upvotes'],
                    'downvotes': row['downvotes'],
                    'score': row['upvotes'] - row['downvotes'],
                    'status': row['status'],
                    'verification_count': row['verification_count'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'contributor': row['contributor_username']
                }
            }
    
    except Exception as e:
        logger.error(f"Get entry error: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@mcp.tool()
async def get_random_entries(count: int = 5, entry_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Get random dictionary entries for learning or exploration.
    
    Args:
        count: Number of random entries to return (default 5, max 20)
        entry_type: Filter by type - 'word', 'phrase', 'idiom', 'proverb' (optional)
    
    Returns:
        List of random verified entries
    """
    count = min(count, 20)
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            if entry_type:
                results = await conn.fetch("""
                    SELECT 
                        id, koloqua_text, english_translation, entry_type,
                        example_sentence_koloqua, example_sentence_english,
                        pronunciation_guide, upvotes, downvotes
                    FROM koloqua_entries
                    WHERE status = 'verified' AND entry_type = $1
                    ORDER BY RANDOM()
                    LIMIT $2
                """, entry_type, count)
            else:
                results = await conn.fetch("""
                    SELECT 
                        id, koloqua_text, english_translation, entry_type,
                        example_sentence_koloqua, example_sentence_english,
                        pronunciation_guide, upvotes, downvotes
                    FROM koloqua_entries
                    WHERE status = 'verified'
                    ORDER BY RANDOM()
                    LIMIT $1
                """, count)
            
            entries = []
            for row in results:
                entries.append({
                    'id': row['id'],
                    'kolokwa': row['koloqua_text'],
                    'english': row['english_translation'],
                    'type': row['entry_type'],
                    'example_kolokwa': row['example_sentence_koloqua'],
                    'example_english': row['example_sentence_english'],
                    'pronunciation': row['pronunciation_guide'],
                    'score': row['upvotes'] - row['downvotes']
                })
            
            return {
                'success': True,
                'count': len(entries),
                'entries': entries
            }
    
    except Exception as e:
        logger.error(f"Random entries error: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@mcp.tool()
async def get_dictionary_stats() -> Dict[str, Any]:
    """
    Get statistics about the dictionary.
    
    Returns:
        Dictionary statistics including total entries, contributors, and categories
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'verified') as verified_entries,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_entries,
                    COUNT(DISTINCT contributor_id) as total_contributors,
                    COUNT(*) FILTER (WHERE entry_type = 'word') as total_words,
                    COUNT(*) FILTER (WHERE entry_type = 'phrase') as total_phrases,
                    COUNT(*) FILTER (WHERE entry_type = 'idiom') as total_idioms,
                    COUNT(*) FILTER (WHERE entry_type = 'proverb') as total_proverbs
                FROM koloqua_entries
            """)
            
            return {
                'success': True,
                'stats': {
                    'verified_entries': stats['verified_entries'],
                    'pending_entries': stats['pending_entries'],
                    'total_contributors': stats['total_contributors'],
                    'breakdown': {
                        'words': stats['total_words'],
                        'phrases': stats['total_phrases'],
                        'idioms': stats['total_idioms'],
                        'proverbs': stats['total_proverbs']
                    }
                }
            }
    
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return {
            'success': False,
            'error': str(e)
        }


if __name__ == "__main__":
    # Run with stdio transport for Claude Desktop
    logger.info("Starting Kolokwa Dictionary MCP Server with stdio transport...")
    mcp.run(transport="stdio")