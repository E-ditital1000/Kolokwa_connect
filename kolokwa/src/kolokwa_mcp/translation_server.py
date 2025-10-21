"""
Kolokwa Translation MCP Server - Production Ready
Handles Kolokwa↔English translation with dictionary context
"""


import os
import sys
import django

# Get the absolute path to the Django project root
# Adjust the path based on your actual structure
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.join(BASE_DIR, '..')  # Go up to kolokwa_connect directory

# Add the project root to the Python path
sys.path.insert(0, PROJECT_ROOT)

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Kolokwa_connect.settings')

# Setup Django
django.setup()

# Now import our production config and Django models
from production_config import (
    Config, create_server, handle_errors, handle_errors_sync,
    track_performance, logger, print_startup_info
)

from dictionary.models import KoloquaEntry
from django.db.models import Q
from asgiref.sync import sync_to_async
import json

# Create server with production configuration
mcp = create_server("kolokwa-translator")

# Print startup information
print_startup_info()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

@sync_to_async
def _find_relevant_entries_sync(text: str, search_english: bool, limit: int):
    """Find dictionary entries relevant to the given text."""
    words = text.lower().split()
    
    if search_english:
        results = KoloquaEntry.objects.filter(
            status='verified'
        ).filter(
            Q(english_translation__icontains=text) |
            Q(english_translation__in=words)
        ).distinct()[:limit]
    else:
        results = KoloquaEntry.objects.filter(
            status='verified'
        ).filter(
            Q(koloqua_text__icontains=text) |
            Q(koloqua_text__in=words)
        ).distinct()[:limit]
    
    return list(results)


def format_dictionary_context(entries: list) -> str:
    """Format dictionary entries as context for translation."""
    if not entries:
        return "No relevant dictionary entries found."
    
    context = []
    for entry in entries:
        entry_str = f"""
- Kolokwa: {entry.koloqua_text}
  English: {entry.english_translation}
  Entry Type: {entry.entry_type}
"""
        if entry.example_sentence_koloqua:
            entry_str += f"  Example: {entry.example_sentence_koloqua} → {entry.example_sentence_english}\n"
        
        if entry.context_explanation:
            entry_str += f"  Context: {entry.context_explanation}\n"
        
        context.append(entry_str)
    
    return "\n".join(context)


# ============================================================================
# PROMPTS
# ============================================================================

@mcp.prompt()
@handle_errors_sync
def translate_to_kolokwa(text: str) -> str:
    """
    Translate English text to Kolokwa using dictionary context.
    
    Args:
        text: English text to translate
    """
    if not text or len(text.strip()) == 0:
        raise ValueError("Text to translate cannot be empty")
    
    # Note: This is a sync function, so we use the sync version
    import asyncio
    entries = asyncio.run(_find_relevant_entries_sync(text, search_english=True, limit=5))
    context_str = format_dictionary_context(entries)
    
    logger.info(f"Translate to Kolokwa: '{text[:50]}...' ({len(entries)} context entries)")
    
    return f"""You are translating English to Kolokwa, a Liberian language.

DICTIONARY CONTEXT:
{context_str}

TASK: Translate the following English text to Kolokwa:
"{text}"

INSTRUCTIONS:
1. Use the dictionary entries above as reference for accurate translations
2. Maintain the natural flow and meaning of the original text
3. If exact matches aren't available, use similar words and explain your reasoning
4. Provide the Kolokwa translation and explain key word choices
5. If providing a translation for a phrase not in the dictionary, base it on similar entries and linguistic patterns

Provide:
- The Kolokwa translation
- Explanation of word choices
- Any cultural or usage notes"""


@mcp.prompt()
@handle_errors_sync
def translate_to_english(text: str) -> str:
    """
    Translate Kolokwa text to English using dictionary context.
    
    Args:
        text: Kolokwa text to translate
    """
    if not text or len(text.strip()) == 0:
        raise ValueError("Text to translate cannot be empty")
    
    import asyncio
    entries = asyncio.run(_find_relevant_entries_sync(text, search_english=False, limit=5))
    context_str = format_dictionary_context(entries)
    
    logger.info(f"Translate to English: '{text[:50]}...' ({len(entries)} context entries)")
    
    return f"""You are translating Kolokwa (a Liberian language) to English.

DICTIONARY CONTEXT:
{context_str}

TASK: Translate the following Kolokwa text to English:
"{text}"

INSTRUCTIONS:
1. Use the dictionary entries above as reference for accurate translations
2. Provide natural, idiomatic English that preserves the meaning
3. If exact matches aren't available, use context clues from similar entries
4. Explain any cultural nuances or idiomatic expressions

Provide:
- The English translation
- Explanation of key terms
- Any cultural or contextual notes"""


@sync_to_async
def _get_word_usage_sync(word: str):
    """Get word usage information from database"""
    entries = KoloquaEntry.objects.filter(
        status='verified',
        koloqua_text__iexact=word
    )
    
    if entries.exists():
        return entries.first()
    return None


@mcp.prompt()
@handle_errors_sync
def explain_usage(word: str) -> str:
    """
    Explain how to use a Kolokwa word or phrase in context.
    
    Args:
        word: Kolokwa word or phrase to explain
    """
    if not word or len(word.strip()) == 0:
        raise ValueError("Word cannot be empty")
    
    import asyncio
    entry = asyncio.run(_get_word_usage_sync(word))
    
    if entry:
        context_str = f"""
Entry: {entry.koloqua_text}
Translation: {entry.english_translation}
Entry Type: {entry.entry_type}
Context: {entry.context_explanation or 'No context provided'}
"""
        if entry.example_sentence_koloqua:
            context_str += f"Example (Kolokwa): {entry.example_sentence_koloqua}\n"
            context_str += f"Example (English): {entry.example_sentence_english}\n"
        
        if entry.cultural_notes:
            context_str += f"Cultural Notes: {entry.cultural_notes}\n"
        
        logger.info(f"Explain usage: '{word}' (found)")
        
        return f"""Explain how to use the Kolokwa word "{word}" with practical examples.

DICTIONARY INFORMATION:
{context_str}

Provide:
1. Clear explanation of the meaning and usage
2. Common contexts where this word is used
3. 2-3 additional example sentences (if not already provided)
4. Any cultural notes or nuances
5. Related words or phrases that might be useful"""
    else:
        logger.warning(f"Explain usage: '{word}' (not found)")
        return f"The word '{word}' was not found in the Kolokwa dictionary."


# ============================================================================
# TOOLS
# ============================================================================

@mcp.tool()
@handle_errors
@track_performance("find_translation_context")
async def find_translation_context(text: str, language: str) -> str:
    """
    Find relevant dictionary entries to help with translation.
    
    Args:
        text: Text to find context for
        language: Language of the input text ("kolokwa" or "english")
    
    Returns:
        Relevant dictionary entries for translation context
    """
    if language not in ['kolokwa', 'english']:
        raise ValueError("Language must be 'kolokwa' or 'english'")
    
    if not text or len(text.strip()) == 0:
        raise ValueError("Text cannot be empty")
    
    search_english = (language == "english")
    entries = await _find_relevant_entries_sync(text, search_english, 10)
    context_str = format_dictionary_context(entries)
    
    logger.info(f"Translation context: '{text[:50]}...', lang={language}, found={len(entries)}")
    
    return f"Found {len(entries)} relevant dictionary entries:\n\n{context_str}"


@sync_to_async
def _validate_translation_sync(kolokwa: str, english: str):
    """Synchronous database query for translation validation"""
    matches = KoloquaEntry.objects.filter(
        Q(status='verified'),
        Q(koloqua_text__iexact=kolokwa) |
        Q(koloqua_text__icontains=kolokwa)
    ).filter(
        Q(english_translation__iexact=english) |
        Q(english_translation__icontains=english)
    )
    
    if matches.exists():
        match = matches.first()
        return {
            "verified": True,
            "match": {
                "kolokwa": match.koloqua_text,
                "english": match.english_translation
            }
        }
    else:
        kolokwa_matches = list(KoloquaEntry.objects.filter(
            status='verified',
            koloqua_text__icontains=kolokwa
        )[:3].values('koloqua_text', 'english_translation'))
        
        english_matches = list(KoloquaEntry.objects.filter(
            status='verified',
            english_translation__icontains=english
        )[:3].values('koloqua_text', 'english_translation'))
        
        return {
            "verified": False,
            "kolokwa_matches": kolokwa_matches,
            "english_matches": english_matches
        }


@mcp.tool()
@handle_errors
@track_performance("validate_translation")
async def validate_translation(kolokwa: str, english: str) -> str:
    """
    Check if a proposed translation exists in the dictionary.
    
    Args:
        kolokwa: Kolokwa text
        english: English text
    
    Returns:
        Validation result with confidence level
    """
    if not kolokwa or not english:
        raise ValueError("Both Kolokwa and English text must be provided")
    
    result = await _validate_translation_sync(kolokwa, english)
    
    logger.info(f"Validate translation: verified={result['verified']}")
    
    if result["verified"]:
        match = result["match"]
        return (f"✓ Translation verified in dictionary:\n"
                f"Kolokwa: {match['kolokwa']}\n"
                f"English: {match['english']}\n"
                f"Confidence: High")
    else:
        output = "⚠ Exact translation not found in dictionary\n\n"
        
        if result["kolokwa_matches"]:
            output += "Similar Kolokwa entries:\n"
            for entry in result["kolokwa_matches"]:
                output += f"- {entry['koloqua_text']} → {entry['english_translation']}\n"
        
        if result["english_matches"]:
            output += "\nSimilar English entries:\n"
            for entry in result["english_matches"]:
                output += f"- {entry['koloqua_text']} → {entry['english_translation']}\n"
        
        return output


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    logger.info("Starting Kolokwa Translation MCP Server...")
    mcp.run()