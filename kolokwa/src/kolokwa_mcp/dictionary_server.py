"""
Kolokwa Dictionary MCP Server - Production Ready
Provides structured access to the Kolokwa dictionary database
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
    track_performance, get_cached_or_compute, metrics, logger, print_startup_info
)

from dictionary.models import KoloquaEntry, WordCategory, TranslationHistory
from users.models import User
from django.db.models import Q, Count
from asgiref.sync import sync_to_async
import json

# Create server with production configuration
mcp = create_server("kolokwa-dictionary")

# Print startup information
print_startup_info()

# ============================================================================
# RESOURCES
# ============================================================================

@mcp.resource("kolokwa://dictionary/stats")
@handle_errors_sync
def get_dictionary_stats() -> str:
    """Get overall statistics about the Kolokwa dictionary"""
    
    def compute_stats():
        return {
            "total_entries": KoloquaEntry.objects.filter(status='verified').count(),
            "pending_entries": KoloquaEntry.objects.filter(status='pending').count(),
            "total_contributors": User.objects.filter(contributions_count__gt=0).count(),
            "total_translations": TranslationHistory.objects.count(),
            "entries_with_audio": KoloquaEntry.objects.exclude(audio_pronunciation='').count(),
            "entries_with_examples": KoloquaEntry.objects.exclude(example_sentence_koloqua='').count(),
            "words": KoloquaEntry.objects.filter(status='verified', entry_type='word').count(),
            "phrases": KoloquaEntry.objects.filter(status='verified', entry_type='phrase').count(),
            "idioms": KoloquaEntry.objects.filter(status='verified', entry_type='idiom').count(),
            "proverbs": KoloquaEntry.objects.filter(status='verified', entry_type='proverb').count(),
        }
    
    stats = get_cached_or_compute('dictionary_stats', compute_stats)
    return json.dumps(stats, indent=2)


@mcp.resource("kolokwa://dictionary/categories")
@handle_errors_sync
def get_categories() -> str:
    """List of all word categories in the dictionary"""
    
    def compute_categories():
        return list(WordCategory.objects.values('id', 'name', 'description'))
    
    categories = get_cached_or_compute('dictionary_categories', compute_categories, 3600)
    return json.dumps(categories, indent=2)


@mcp.resource("kolokwa://dictionary/recent")
@handle_errors_sync
def get_recent_entries() -> str:
    """Recently added dictionary entries"""
    recent = KoloquaEntry.objects.filter(
        status='verified'
    ).order_by('-created_at')[:20].values(
        'id', 'koloqua_text', 'english_translation',
        'entry_type', 'created_at', 'upvotes', 'downvotes'
    )
    return json.dumps(list(recent), indent=2, default=str)


# ============================================================================
# TOOLS
# ============================================================================

@sync_to_async
def _search_dictionary_sync(query: str, search_type: str, limit: int):
    """Synchronous database query for search"""
    
    # Input validation
    if not query or len(query.strip()) == 0:
        raise ValueError("Query cannot be empty")
    
    query = query.strip()
    
    if limit > Config.MAX_SEARCH_RESULTS:
        limit = Config.MAX_SEARCH_RESULTS
    
    # Build query based on search type
    if search_type == "kolokwa":
        results = KoloquaEntry.objects.filter(
            status='verified',
            koloqua_text__icontains=query
        )
    elif search_type == "english":
        results = KoloquaEntry.objects.filter(
            status='verified',
            english_translation__icontains=query
        )
    elif search_type == "examples":
        results = KoloquaEntry.objects.filter(
            Q(status='verified'),
            Q(example_sentence_koloqua__icontains=query) |
            Q(example_sentence_english__icontains=query)
        )
    else:  # all
        results = KoloquaEntry.objects.filter(
            Q(status='verified'),
            Q(koloqua_text__icontains=query) |
            Q(english_translation__icontains=query) |
            Q(context_explanation__icontains=query) |
            Q(example_sentence_koloqua__icontains=query) |
            Q(example_sentence_english__icontains=query)
        )
    
    results = results.distinct()[:limit]
    
    entries = []
    for entry in results:
        entries.append({
            "id": entry.id,
            "kolokwa": entry.koloqua_text,
            "english": entry.english_translation,
            "literal_translation": entry.literal_translation,
            "entry_type": entry.entry_type,
            "context": entry.context_explanation,
            "example_kolokwa": entry.example_sentence_koloqua,
            "example_english": entry.example_sentence_english,
            "pronunciation": entry.pronunciation_guide,
            "has_audio": bool(entry.audio_pronunciation),
            "region": entry.region_specific,
            "score": entry.calculate_score(),
        })
    
    return entries


@mcp.tool()
@handle_errors
@track_performance("search_dictionary")
async def search_dictionary(query: str, search_type: str = "all", limit: int = 10) -> str:
    """
    Search the Kolokwa dictionary by text, translation, or tags.
    
    Args:
        query: Search term (can be Kolokwa or English)
        search_type: Type of search - "all", "kolokwa", "english", or "examples"
        limit: Maximum number of results (default: 10, max: 50)
    
    Returns:
        JSON string of matching entries with full details
    """
    
    # Validate search type
    valid_types = ['all', 'kolokwa', 'english', 'examples']
    if search_type not in valid_types:
        raise ValueError(f"Invalid search_type. Must be one of: {', '.join(valid_types)}")
    
    entries = await _search_dictionary_sync(query, search_type, limit)
    
    logger.info(f"Search: query='{query}', type={search_type}, results={len(entries)}")
    
    return json.dumps({
        "query": query,
        "search_type": search_type,
        "total_results": len(entries),
        "entries": entries
    }, indent=2)


@sync_to_async
def _get_entry_details_sync(entry_id: int):
    """Get entry details by ID"""
    try:
        entry = KoloquaEntry.objects.get(id=entry_id, status='verified')
        return {
            "id": entry.id,
            "kolokwa": entry.koloqua_text,
            "english": entry.english_translation,
            "literal_translation": entry.literal_translation,
            "entry_type": entry.entry_type,
            "context": entry.context_explanation,
            "example_kolokwa": entry.example_sentence_koloqua,
            "example_english": entry.example_sentence_english,
            "cultural_notes": entry.cultural_notes,
            "pronunciation": entry.pronunciation_guide,
            "region": entry.region_specific,
            "tags": entry.tags,
            "categories": [cat.name for cat in entry.categories.all()],
            "upvotes": entry.upvotes,
            "downvotes": entry.downvotes,
            "score": entry.calculate_score(),
            "verification_count": entry.verification_count,
            "contributor": entry.contributor.username if entry.contributor else "Anonymous",
            "created_at": str(entry.created_at),
            "verified_at": str(entry.verified_at) if entry.verified_at else None,
        }
    except KoloquaEntry.DoesNotExist:
        return None


@mcp.tool()
@handle_errors
async def get_entry_details(entry_id: int) -> str:
    """
    Get full details of a specific dictionary entry by ID.
    
    Args:
        entry_id: Dictionary entry ID
    
    Returns:
        JSON string with complete entry details
    """
    if entry_id <= 0:
        raise ValueError("Entry ID must be positive")
    
    details = await _get_entry_details_sync(entry_id)
    if details:
        return json.dumps(details, indent=2)
    return json.dumps({"error": f"Entry with ID {entry_id} not found"}, indent=2)


# Add metrics resource in production
if Config.IS_PRODUCTION:
    @mcp.resource("kolokwa://dictionary/metrics")
    def get_metrics() -> str:
        """Get server performance metrics"""
        return json.dumps(metrics.get_stats(), indent=2)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    logger.info("Starting Kolokwa Dictionary MCP Server...")
    mcp.run()