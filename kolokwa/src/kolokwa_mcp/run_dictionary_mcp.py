"""
Kolokwa Dictionary MCP Server using FastMCP
Provides dictionary lookup, search, and contribution tools
"""

import os
import logging
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DATABASE_HOST', 'localhost'),
    'port': int(os.getenv('DATABASE_PORT', '5432')),
    'user': os.getenv('DATABASE_USER', 'postgres'),
    'password': os.getenv('DATABASE_PASSWORD', ''),
    'database': os.getenv('DATABASE_NAME', 'kolokwa_db')
}

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("kolokwa-dictionary")


@mcp.tool()
async def search_kolokwa(query: str, search_type: str = "all", limit: int = 10) -> Dict[str, Any]:
    """Search the Kolokwa dictionary for words, phrases, or translations."""
    # Import asyncpg ONLY when tool is actually called
    import asyncpg
    
    limit = min(limit, 50)
    
    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG['host'], port=DB_CONFIG['port'],
            user=DB_CONFIG['user'], password=DB_CONFIG['password'],
            database=DB_CONFIG['database'], timeout=10
        )
        
        try:
            if search_type == "kolokwa":
                sql = """SELECT id, koloqua_text, english_translation, literal_translation,
                         entry_type, context_explanation, example_sentence_koloqua,
                         example_sentence_english, pronunciation_guide, cultural_notes,
                         upvotes, downvotes FROM koloqua_entries
                         WHERE status = 'verified' AND (koloqua_text ILIKE $1 OR example_sentence_koloqua ILIKE $1)
                         ORDER BY upvotes - downvotes DESC LIMIT $2"""
            elif search_type == "english":
                sql = """SELECT id, koloqua_text, english_translation, literal_translation,
                         entry_type, context_explanation, example_sentence_koloqua,
                         example_sentence_english, pronunciation_guide, cultural_notes,
                         upvotes, downvotes FROM koloqua_entries
                         WHERE status = 'verified' AND (english_translation ILIKE $1 OR example_sentence_english ILIKE $1)
                         ORDER BY upvotes - downvotes DESC LIMIT $2"""
            else:
                sql = """SELECT id, koloqua_text, english_translation, literal_translation,
                         entry_type, context_explanation, example_sentence_koloqua,
                         example_sentence_english, pronunciation_guide, cultural_notes,
                         upvotes, downvotes FROM koloqua_entries
                         WHERE status = 'verified' AND (koloqua_text ILIKE $1 OR english_translation ILIKE $1 OR
                         example_sentence_koloqua ILIKE $1 OR example_sentence_english ILIKE $1 OR
                         context_explanation ILIKE $1) ORDER BY upvotes - downvotes DESC LIMIT $2"""
            
            results = await conn.fetch(sql, f"%{query}%", limit)
            
            entries = [{
                'id': r['id'], 'kolokwa': r['koloqua_text'], 'english': r['english_translation'],
                'literal': r['literal_translation'], 'type': r['entry_type'],
                'context': r['context_explanation'], 'example_kolokwa': r['example_sentence_koloqua'],
                'example_english': r['example_sentence_english'], 'pronunciation': r['pronunciation_guide'],
                'cultural_notes': r['cultural_notes'], 'score': r['upvotes'] - r['downvotes']
            } for r in results]
            
            return {'success': True, 'query': query, 'search_type': search_type, 'count': len(entries), 'entries': entries}
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Search error: {e}")
        return {'success': False, 'error': str(e), 'query': query}


@mcp.tool()
async def get_entry_details(entry_id: int) -> Dict[str, Any]:
    """Get complete details for a specific dictionary entry."""
    import asyncpg
    
    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG['host'], port=DB_CONFIG['port'],
            user=DB_CONFIG['user'], password=DB_CONFIG['password'],
            database=DB_CONFIG['database'], timeout=10
        )
        
        try:
            row = await conn.fetchrow("""
                SELECT e.id, e.koloqua_text, e.english_translation, e.literal_translation,
                       e.entry_type, e.context_explanation, e.example_sentence_koloqua,
                       e.example_sentence_english, e.pronunciation_guide, e.cultural_notes,
                       e.upvotes, e.downvotes, e.status, e.created_at, e.region_specific,
                       e.verification_count, u.username as contributor_username
                FROM koloqua_entries e LEFT JOIN users u ON e.contributor_id = u.id
                WHERE e.id = $1
            """, entry_id)
            
            if not row:
                return {'success': False, 'error': f'Entry with ID {entry_id} not found'}
            
            return {
                'success': True,
                'entry': {
                    'id': row['id'], 'kolokwa': row['koloqua_text'], 'english': row['english_translation'],
                    'literal': row['literal_translation'], 'type': row['entry_type'],
                    'context': row['context_explanation'], 'example_kolokwa': row['example_sentence_koloqua'],
                    'example_english': row['example_sentence_english'], 'pronunciation': row['pronunciation_guide'],
                    'cultural_notes': row['cultural_notes'], 'region': row['region_specific'],
                    'upvotes': row['upvotes'], 'downvotes': row['downvotes'],
                    'score': row['upvotes'] - row['downvotes'], 'status': row['status'],
                    'verification_count': row['verification_count'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'contributor': row['contributor_username']
                }
            }
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Get entry error: {e}")
        return {'success': False, 'error': str(e)}


@mcp.tool()
async def get_random_entries(count: int = 5, entry_type: Optional[str] = None) -> Dict[str, Any]:
    """Get random dictionary entries for learning or exploration."""
    import asyncpg
    
    count = min(count, 20)
    
    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG['host'], port=DB_CONFIG['port'],
            user=DB_CONFIG['user'], password=DB_CONFIG['password'],
            database=DB_CONFIG['database'], timeout=10
        )
        
        try:
            if entry_type:
                results = await conn.fetch("""
                    SELECT id, koloqua_text, english_translation, entry_type,
                           example_sentence_koloqua, example_sentence_english,
                           pronunciation_guide, upvotes, downvotes
                    FROM koloqua_entries WHERE status = 'verified' AND entry_type = $1
                    ORDER BY RANDOM() LIMIT $2
                """, entry_type, count)
            else:
                results = await conn.fetch("""
                    SELECT id, koloqua_text, english_translation, entry_type,
                           example_sentence_koloqua, example_sentence_english,
                           pronunciation_guide, upvotes, downvotes
                    FROM koloqua_entries WHERE status = 'verified'
                    ORDER BY RANDOM() LIMIT $1
                """, count)
            
            entries = [{
                'id': r['id'], 'kolokwa': r['koloqua_text'], 'english': r['english_translation'],
                'type': r['entry_type'], 'example_kolokwa': r['example_sentence_koloqua'],
                'example_english': r['example_sentence_english'], 'pronunciation': r['pronunciation_guide'],
                'score': r['upvotes'] - r['downvotes']
            } for r in results]
            
            return {'success': True, 'count': len(entries), 'entries': entries}
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Random entries error: {e}")
        return {'success': False, 'error': str(e)}


@mcp.tool()
async def get_dictionary_stats() -> Dict[str, Any]:
    """Get statistics about the dictionary."""
    import asyncpg
    
    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG['host'], port=DB_CONFIG['port'],
            user=DB_CONFIG['user'], password=DB_CONFIG['password'],
            database=DB_CONFIG['database'], timeout=10
        )
        
        try:
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
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return {'success': False, 'error': str(e)}


@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check if the MCP server is running properly."""
    import asyncpg
    
    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG['host'], port=DB_CONFIG['port'],
            user=DB_CONFIG['user'], password=DB_CONFIG['password'],
            database=DB_CONFIG['database'], timeout=10
        )
        
        try:
            await conn.fetchval("SELECT 1")
            return {
                'success': True,
                'status': 'healthy',
                'server': 'kolokwa-dictionary',
                'database': 'connected'
            }
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Health check: {e}")
        return {
            'success': True,
            'status': 'running',
            'server': 'kolokwa-dictionary',
            'database': 'not_connected',
            'note': f'Database connection failed: {str(e)}'
        }