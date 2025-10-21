# nl_interact/utils.py
"""
Utility functions for RAG operations with rate limit protection.
"""
from openai import OpenAI
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
import logging
import numpy as np
import time

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)


def is_rate_limited():
    """Check if we're currently rate limited."""
    return cache.get('openai_rate_limited', False)


def set_rate_limited(duration_seconds=3600):
    """Mark as rate limited for specified duration."""
    cache.set('openai_rate_limited', True, timeout=duration_seconds)
    logger.warning(f"Rate limited - embeddings disabled for {duration_seconds}s")


def get_embedding(text, model="text-embedding-3-small"):
    """
    Get OpenAI embedding for text with caching and rate limit handling.
    
    Args:
        text: String to embed
        model: OpenAI embedding model to use
    
    Returns:
        List of floats (embedding vector) or None on error
    """
    if not text or not text.strip():
        return None
    
    # Check rate limit first
    if is_rate_limited():
        logger.info("Skipping embedding - rate limited")
        return None
    
    # Create cache key (30 day cache)
    cache_key = f"emb_v1_{hash(text.strip().lower())}_{model}"
    cached = cache.get(cache_key)
    
    if cached:
        return cached
    
    try:
        response = client.embeddings.create(
            model=model,
            input=text.strip()
        )
        embedding = response.data[0].embedding
        
        # Cache for 30 days
        cache.set(cache_key, embedding, timeout=86400 * 30)
        return embedding
        
    except Exception as e:
        error_str = str(e)
        
        # Handle rate limiting
        if '429' in error_str or 'quota' in error_str.lower():
            set_rate_limited(3600)  # 1 hour
        
        logger.error(f"Error generating embedding: {error_str}")
        return None


def create_entry_text(entry):
    """
    Create searchable text representation of a dictionary entry.
    """
    parts = [
        f"Kolokwa: {entry.koloqua_text}",
        f"English: {entry.english_translation}",
    ]
    
    if entry.literal_translation and entry.literal_translation != entry.english_translation:
        parts.append(f"Literal: {entry.literal_translation}")
    
    if entry.context_explanation:
        parts.append(f"Context: {entry.context_explanation}")
    
    if entry.example_sentence_english:
        parts.append(f"Example: {entry.example_sentence_english}")
    
    if entry.example_sentence_koloqua:
        parts.append(f"Example Kolokwa: {entry.example_sentence_koloqua}")
    
    if entry.cultural_notes:
        parts.append(f"Cultural: {entry.cultural_notes}")
    
    if entry.tags and isinstance(entry.tags, list):
        parts.append(f"Tags: {', '.join(entry.tags)}")
    
    return " | ".join(parts)


def generate_entry_embedding(entry, force=False):
    """
    Generate and store embedding for a dictionary entry.
    
    Args:
        entry: KoloquaEntry instance
        force: If True, regenerate even if embedding exists
    
    Returns:
        Boolean indicating success
    """
    # Skip if rate limited
    if is_rate_limited():
        logger.info(f"Skipping embedding for entry {entry.id} - rate limited")
        return False
    
    # Skip if embedding exists and is current
    if not force and entry.embedding and entry.embedding_updated_at:
        if entry.embedding_updated_at >= entry.updated_at:
            return True
    
    try:
        # Create searchable text
        entry_text = create_entry_text(entry)
        
        # Generate embedding
        embedding = get_embedding(entry_text)
        
        if embedding:
            entry.embedding = embedding
            entry.embedding_updated_at = timezone.now()
            entry.save(update_fields=['embedding', 'embedding_updated_at'])
            logger.info(f"Generated embedding for entry {entry.id}: {entry.koloqua_text}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error generating embedding for entry {entry.id}: {str(e)}")
        return False


def cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors."""
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


def semantic_search_entries(query_text, top_k=5, threshold=0.5):
    """
    Perform semantic search using stored embeddings.
    Only generates embedding for the query (1 API call).
    """
    from dictionary.models import KoloquaEntry
    
    # Get query embedding (ONLY API call per search)
    query_embedding = get_embedding(query_text)
    
    if not query_embedding:
        logger.warning("Failed to generate query embedding")
        return []
    
    # Get entries with pre-computed embeddings (NO API calls)
    entries = KoloquaEntry.objects.filter(
        status='verified',
        embedding__isnull=False
    ).select_related('contributor')
    
    # Calculate similarities
    scored_entries = []
    for entry in entries:
        if entry.embedding:
            similarity = cosine_similarity(query_embedding, entry.embedding)
            if similarity >= threshold:
                scored_entries.append((entry, similarity))
    
    # Sort by similarity
    scored_entries.sort(key=lambda x: x[1], reverse=True)
    
    return scored_entries[:top_k]


def batch_generate_embeddings(entries, batch_size=10, delay=1.0, force=False):
    """
    Generate embeddings for multiple entries with rate limit protection.
    
    Args:
        entries: QuerySet or list of KoloquaEntry instances
        batch_size: Entries to process before pausing
        delay: Seconds to wait between batches
        force: Regenerate even if exists
    
    Returns:
        Dict with counts: {'success': int, 'failed': int, 'skipped': int}
    """
    results = {'success': 0, 'failed': 0, 'skipped': 0}
    
    for i, entry in enumerate(entries, 1):
        # Stop if rate limited
        if is_rate_limited():
            logger.warning(f"Stopped at entry {i} due to rate limit")
            break
        
        # Skip if already has current embedding
        if not force and entry.embedding and entry.embedding_updated_at:
            if entry.embedding_updated_at >= entry.updated_at:
                results['skipped'] += 1
                continue
        
        # Generate embedding
        if generate_entry_embedding(entry, force=force):
            results['success'] += 1
        else:
            results['failed'] += 1
            
            # If failed due to rate limit, stop
            if is_rate_limited():
                logger.warning(f"Hit rate limit at entry {i}")
                break
        
        # Pause between batches
        if i % batch_size == 0:
            logger.info(f"Processed {i} entries, pausing {delay}s...")
            time.sleep(delay)
    
    return results


def get_rag_stats():
    """Get statistics about embedding coverage."""
    from dictionary.models import KoloquaEntry
    
    total_entries = KoloquaEntry.objects.filter(status='verified').count()
    entries_with_embeddings = KoloquaEntry.objects.filter(
        status='verified',
        embedding__isnull=False
    ).count()
    
    rate_limited = is_rate_limited()
    
    return {
        'total_entries': total_entries,
        'entries_with_embeddings': entries_with_embeddings,
        'coverage_percentage': (entries_with_embeddings / total_entries * 100) if total_entries > 0 else 0,
        'entries_needing_embeddings': total_entries - entries_with_embeddings,
        'rate_limited': rate_limited
    }


def extract_keywords(text):
    """Extract keywords from text for keyword search fallback."""
    import re
    
    stop_words = {
        'how', 'what', 'tell', 'me', 'say', 'can', 'you', 'help',
        'the', 'a', 'an', 'is', 'be', 'we', 'i', 'my', 'your',
        'kolokwa', 'koloqua', 'english', 'translate', 'word', 'phrase'
    }
    
    # Check for quoted phrases
    quoted = re.findall(r'["\']([^"\']+)["\']', text)
    if quoted:
        return quoted
    
    # Tokenize and filter
    text_lower = text.lower().strip()
    words = re.findall(r'\b\w+\b', text_lower)
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    
    return keywords[:5]