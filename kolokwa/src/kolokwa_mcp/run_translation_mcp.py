"""
Kolokwa Translation MCP Server using FastMCP
Provides AI-powered natural language translation with Liberian context
"""

import os
import sys
import logging
import json
from typing import Optional, Dict, Any, List
import asyncpg
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DB_CONFIG = {
    'host': os.getenv('DATABASE_HOST', 'localhost'),
    'port': int(os.getenv('DATABASE_PORT', 5432)),
    'user': os.getenv('DATABASE_USER', 'postgres'),
    'password': os.getenv('DATABASE_PASSWORD', ''),
    'database': os.getenv('DATABASE_NAME', 'kolokwa_db')
}

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

# Import FastMCP
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("kolokwa-translator")

# Global clients
db_pool = None
openai_client = None


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


async def get_openai_client():
    """Get or create OpenAI client"""
    global openai_client
    if openai_client is None and OPENAI_API_KEY:
        openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized")
    return openai_client


async def search_dictionary(search_terms: List[str]) -> List[Dict[str, Any]]:
    """Search the dictionary for matching entries"""
    entries = []
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            for term in search_terms[:5]:
                if not term or len(term) < 2:
                    continue
                
                results = await conn.fetch("""
                    SELECT 
                        id, koloqua_text, english_translation, literal_translation,
                        entry_type, context_explanation, example_sentence_koloqua,
                        example_sentence_english, pronunciation_guide, cultural_notes,
                        upvotes, downvotes
                    FROM koloqua_entries
                    WHERE status = 'verified'
                    AND (
                        koloqua_text ILIKE $1
                        OR english_translation ILIKE $1
                        OR example_sentence_koloqua ILIKE $1
                        OR example_sentence_english ILIKE $1
                    )
                    ORDER BY upvotes - downvotes DESC
                    LIMIT 3
                """, f"%{term}%")
                
                for row in results:
                    if row['id'] not in [e['id'] for e in entries]:
                        entries.append(dict(row))
        
        return entries[:5]
        
    except Exception as e:
        logger.error(f"Dictionary search error: {e}")
        return []


@mcp.tool()
async def translate_query(
    query: str,
    include_examples: bool = True,
    cultural_context: bool = True
) -> Dict[str, Any]:
    """
    Translate natural language queries using AI and dictionary context.
    Understands Liberian Kolokwa patterns and provides culturally aware responses.
    
    Args:
        query: Natural language question or phrase to translate
        include_examples: Include example sentences in response (default True)
        cultural_context: Include cultural notes when available (default True)
    
    Returns:
        Translation response with dictionary entries and AI-generated explanation
    """
    client = await get_openai_client()
    
    if not client:
        return {
            'success': False,
            'error': 'Translation service unavailable - OpenAI client not initialized'
        }
    
    try:
        # Extract search terms using AI
        extraction_prompt = f"""You are a linguistic assistant for the Kolokwa-English dictionary (Liberian Kolokwa language).
Extract key search terms from this user query. Return ONLY a JSON array of search terms.

IMPORTANT: Kolokwa is LIBERIAN, NOT Nigerian.

Query: "{query}"

Return JSON array of 1-5 key search terms:"""

        extraction_response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Extract search terms. Return valid JSON array only."},
                {"role": "user", "content": extraction_prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        
        result_text = extraction_response.choices[0].message.content.strip()
        
        try:
            search_terms = json.loads(result_text)
            if not isinstance(search_terms, list):
                search_terms = [query]
        except json.JSONDecodeError:
            search_terms = [query]
        
        # Search dictionary
        entries = await search_dictionary(search_terms)
        
        # Generate response
        if entries:
            entries_context = "\n\n".join([
                f"Entry {i+1}:\n"
                f"- Kolokwa: {e['koloqua_text']}\n"
                f"- English: {e['english_translation']}\n"
                f"- Type: {e['entry_type']}\n"
                + (f"- Example: \"{e['example_sentence_koloqua']}\" = \"{e['example_sentence_english']}\"\n" 
                   if include_examples and e['example_sentence_koloqua'] else "")
                + (f"- Usage: {e['context_explanation']}\n" if e['context_explanation'] else "")
                for i, e in enumerate(entries)
            ])
            
            response_prompt = f"""You are a helpful assistant for the Kolokwa language dictionary.

CRITICAL RULES:
1. Use ONLY the dictionary entries provided below
2. DO NOT invent translations
3. Kolokwa is LIBERIAN - no Nigerian Pidgin patterns
4. Use plain text - NO markdown

User asked: "{query}"

Dictionary entries:
{entries_context}

Provide a helpful response using ONLY these entries in plain text."""

            translation_response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a Kolokwa dictionary assistant. Use plain text only."},
                    {"role": "user", "content": response_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            answer = translation_response.choices[0].message.content.strip()
            
            return {
                'success': True,
                'query': query,
                'response': answer,
                'dictionary_matches': len(entries),
                'entries': [
                    {
                        'id': e['id'],
                        'kolokwa': e['koloqua_text'],
                        'english': e['english_translation'],
                        'type': e['entry_type']
                    }
                    for e in entries
                ]
            }
        else:
            return {
                'success': True,
                'query': query,
                'response': f"I couldn't find '{', '.join(search_terms[:3])}' in our Kolokwa dictionary yet. "
                           f"Our dictionary is still growing!",
                'dictionary_matches': 0,
                'entries': []
            }
    
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return {
            'success': False,
            'error': str(e),
            'query': query
        }


@mcp.tool()
async def translate_phrase(
    phrase: str,
    from_language: str = "english",
    to_language: str = "kolokwa"
) -> Dict[str, Any]:
    """
    Translate a specific phrase between English and Kolokwa.
    
    Args:
        phrase: The phrase to translate
        from_language: Source language - 'english' or 'kolokwa' (default 'english')
        to_language: Target language - 'kolokwa' or 'english' (default 'kolokwa')
    
    Returns:
        Translation with dictionary matches
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            if from_language == "english":
                results = await conn.fetch("""
                    SELECT 
                        id, koloqua_text, english_translation, example_sentence_koloqua,
                        example_sentence_english, pronunciation_guide, context_explanation
                    FROM koloqua_entries
                    WHERE status = 'verified'
                    AND english_translation ILIKE $1
                    ORDER BY upvotes - downvotes DESC
                    LIMIT 5
                """, f"%{phrase}%")
            else:
                results = await conn.fetch("""
                    SELECT 
                        id, koloqua_text, english_translation, example_sentence_koloqua,
                        example_sentence_english, pronunciation_guide, context_explanation
                    FROM koloqua_entries
                    WHERE status = 'verified'
                    AND koloqua_text ILIKE $1
                    ORDER BY upvotes - downvotes DESC
                    LIMIT 5
                """, f"%{phrase}%")
        
        matches = [dict(row) for row in results]
        
        if matches:
            return {
                'success': True,
                'phrase': phrase,
                'from_language': from_language,
                'to_language': to_language,
                'dictionary_matches': len(matches),
                'translations': [
                    {
                        'id': m['id'],
                        'kolokwa': m['koloqua_text'],
                        'english': m['english_translation'],
                        'pronunciation': m['pronunciation_guide'],
                        'context': m['context_explanation']
                    }
                    for m in matches
                ]
            }
        else:
            return {
                'success': True,
                'phrase': phrase,
                'from_language': from_language,
                'to_language': to_language,
                'dictionary_matches': 0,
                'message': f"No direct translation found for '{phrase}' in the dictionary."
            }
    
    except Exception as e:
        logger.error(f"Phrase translation error: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@mcp.tool()
async def explain_kolokwa_phrase(phrase: str) -> Dict[str, Any]:
    """
    Get detailed explanation of a Kolokwa phrase including cultural context.
    
    Args:
        phrase: Kolokwa phrase to explain
    
    Returns:
        Detailed explanation with cultural and usage context
    """
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT 
                    id, koloqua_text, english_translation, literal_translation,
                    entry_type, context_explanation, example_sentence_koloqua,
                    example_sentence_english, pronunciation_guide, cultural_notes,
                    region_specific
                FROM koloqua_entries
                WHERE status = 'verified'
                AND koloqua_text ILIKE $1
                ORDER BY upvotes - downvotes DESC
                LIMIT 3
            """, f"%{phrase}%")
            
            if not results:
                return {
                    'success': False,
                    'phrase': phrase,
                    'error': 'Phrase not found in dictionary'
                }
            
            explanations = []
            for row in results:
                explanation = {
                    'id': row['id'],
                    'kolokwa': row['koloqua_text'],
                    'english': row['english_translation'],
                    'literal': row['literal_translation'],
                    'type': row['entry_type'],
                    'pronunciation': row['pronunciation_guide'],
                    'context': row['context_explanation'],
                    'cultural_notes': row['cultural_notes'],
                    'region': row['region_specific'],
                    'example': {
                        'kolokwa': row['example_sentence_koloqua'],
                        'english': row['example_sentence_english']
                    } if row['example_sentence_koloqua'] else None
                }
                explanations.append(explanation)
            
            return {
                'success': True,
                'phrase': phrase,
                'matches': len(explanations),
                'explanations': explanations
            }
    
    except Exception as e:
        logger.error(f"Explanation error: {e}")
        return {
            'success': False,
            'error': str(e)
        }


if __name__ == "__main__":
    # Run with stdio transport for Claude Desktop
    logger.info("Starting Kolokwa Translation MCP Server with stdio transport...")
    mcp.run(transport="stdio")