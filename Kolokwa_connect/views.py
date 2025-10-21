# Kolokwa_connect/Kolokwa_connect/views.py
from django.shortcuts import render
from dictionary.models import KoloquaEntry, WordCategory, TranslationHistory
from users.models import User
from django.db.models import Q
from django.http import HttpResponse

def home(request):
    """
    Home view with dictionary search and AI translator integration.
    Displays search results, statistics, and recent words.
    """
    query = request.GET.get('q')
    search_results = None

    if query:
        # Search dictionary entries
        search_results = KoloquaEntry.objects.filter(
            Q(status='verified'),
            Q(koloqua_text__icontains=query) |
            Q(english_translation__icontains=query) |
            Q(entry_type__icontains=query) |
            Q(tags__icontains=query) |
            Q(example_sentence_koloqua__icontains=query) |
            Q(example_sentence_english__icontains=query)
        ).distinct().order_by('-created_at')[:20]  # Limit to 20 results

    # Get statistics for the dashboard
    word_count = KoloquaEntry.objects.filter(status='verified').count()
    contributor_count = User.objects.filter(is_active=True, contributions_count__gt=0).count()
    translation_count = TranslationHistory.objects.filter(found=True).count()
    example_count = KoloquaEntry.objects.exclude(example_sentence_koloqua='').count()
    
    # Get recently added words
    recent_words = KoloquaEntry.objects.filter(status='verified').order_by('-created_at')[:6]

    context = {
        'word_count': word_count,
        'contributor_count': contributor_count,
        'translation_count': translation_count,
        'example_count': example_count,
        'recent_words': recent_words,
        'search_results': search_results,
        'query': query,
    }
    return render(request, 'index.html', context)


def about(request):
    """
    About page view with platform statistics.
    """
    word_count = KoloquaEntry.objects.filter(status='verified').count()
    contributor_count = User.objects.filter(is_active=True, contributions_count__gt=0).count()
    translation_count = TranslationHistory.objects.filter(found=True).count()
    example_count = KoloquaEntry.objects.exclude(example_sentence_koloqua='').count()

    context = {
        'word_count': word_count,
        'contributor_count': contributor_count,
        'translation_count': translation_count,
        'example_count': example_count,
    }
    return render(request, 'about.html', context)


def health_check_view(request):
    return HttpResponse("OK", status=200)