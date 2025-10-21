from rest_framework import views, response, status
from rest_framework.permissions import AllowAny
from .serializers import NLQuerySerializer, NLResponseSerializer
from dictionary.models import KoloquaEntry
from django.db.models import Q
from openai import OpenAI
from django.conf import settings
import json
import logging
import re

logger = logging.getLogger(__name__)


class NLQueryView(views.APIView):
    """
    Enhanced API view to handle natural language queries with Liberian speech patterns.
    Supports Koloqua, Liberian English, and standard English inputs.
    """
    permission_classes = [AllowAny]

    # Common Liberian Kolokwa patterns (NOT Nigerian Pidgin)
    LIBERIAN_PATTERNS = {
        r'\bna\b': 'not/don\'t',
        r'\bba\b': 'friend/person',
        r'\bpekin\b': 'child/little one',
        r'\bda\b': 'that/the',
        r'\boh+\b': '',
        r'\bya+h?\b': '',
        r'\bsmall\s+small\b': 'little/small',
        r'\bfine\s+fine\b': 'very nice',
        r'\bplenty\b': 'many/much',
        r'\bself\b': 'even/also',
        r'\bhow\s+you\s+say\b': 'what do you mean',
        r'\byou\s+say\b': 'what do you mean',
    }

    SENTENCE_STARTERS = [
        r'^how\s+you\s+',
        r'^you\s+say\s+',
        r'^my\s+people\s+',
        r'^my\s+pekin\s+',
        r'^my\s+ba\s+',
        r'^i\s+want\s+(to\s+)?know\s+',
        r'^tell\s+me\s+',
        r'^how\s+i\s+can\s+',
        r'^can\s+you\s+help\s+',
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize OpenAI client with API key from settings
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def post(self, request, *args, **kwargs):
        serializer = NLQuerySerializer(data=request.data)
        if not serializer.is_valid():
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        query = serializer.validated_data['query']
        
        try:
            # Normalize the query for Liberian patterns
            normalized_query = self._normalize_liberian_input(query)
            
            # Extract search terms using enhanced method
            search_terms = self._extract_search_terms(normalized_query, original_query=query)
            
            # Search dictionary database
            entries = self._search_dictionary(search_terms)
            
            # Generate natural language response
            answer = self._generate_response(query, entries, search_terms, normalized_query)
            
            # Return formatted response
            response_serializer = NLResponseSerializer(data={'response': answer})
            response_serializer.is_valid(raise_exception=True)
            return response.Response(response_serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error processing NL query: {str(e)}", exc_info=True)
            return response.Response(
                {'error': 'An error occurred processing your query. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _normalize_liberian_input(self, query):
        """
        Normalize Liberian English/Koloqua patterns to standard English for better LLM understanding.
        """
        normalized = query.lower().strip()
        
        for pattern, replacement in self.LIBERIAN_PATTERNS.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _extract_search_terms(self, query, original_query=None):
        """
        Extract key dictionary search terms with enhanced support for Liberian patterns.
        """
        try:
            prompt = f"""You are a linguistic assistant for the Kolokwa-English dictionary (Liberian Kolokwa language).
Your task: extract key search terms from user queries.

IMPORTANT: Kolokwa is LIBERIAN, NOT Nigerian. Do not confuse with Nigerian Pidgin.

Common LIBERIAN Kolokwa patterns:
- "I na know" = "I don't know" (na = not/don't)
- "How you say..." = "What do you mean..."
- "My pekin" = "My child/little one"
- "My ba" = "My friend"
- "Da one" = "That one"

Return ONLY a valid JSON array of the most relevant search terms (words or short phrases).
Focus on content words (nouns, verbs, adjectives), not grammar words.

Examples:
- "How you say 'water'?" -> ["water"]
- "I want to eat" -> ["eat", "want to eat"]
- "I love you" -> ["love", "I love you"]
- "How you say thank you?" -> ["thank you"]

Original query: "{original_query or query}"
Normalized query: "{query}"

Return JSON array of search terms:"""

            # CORRECTED: Use chat.completions.create (not responses.create)
            completion = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a linguistic assistant that extracts search terms. Always return valid JSON arrays."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=150
            )
            
            # CORRECTED: Access response correctly
            result = completion.choices[0].message.content.strip()

            # Try parsing JSON safely
            try:
                parsed = json.loads(result)
                if isinstance(parsed, list) and parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

            # Try extracting inside brackets
            match = re.search(r"\[(.*?)\]", result)
            if match:
                terms = [i.strip(" \"'") for i in match.group(1).split(",") if i.strip()]
                if terms:
                    return terms
            
            # If result is a single word/phrase, return it
            if result and not any(c in '[]{}' for c in result):
                return [result]

            # Fallback
            return self._fallback_extraction(query, original_query)

        except Exception as e:
            logger.warning(f"LLM extraction failed, using fallback: {e}")
            return self._fallback_extraction(query, original_query)

    def _fallback_extraction(self, query, original_query=None):
        """
        Enhanced fallback extraction that understands Liberian speech patterns.
        """
        text = original_query or query
        text_lower = text.lower().strip()
        
        # Remove common sentence starters
        for starter in self.SENTENCE_STARTERS:
            text_lower = re.sub(starter, '', text_lower)
        
        # Remove common question/command words
        remove_words = [
            'how', 'what', 'tell', 'me', 'say', 'can', 'you', 'help',
            'the', 'a', 'an', 'is', 'be', 'we', 'i', 'my',
            'kolokwa', 'koloqua', 'english', 'translate', 'translation',
            'word', 'phrase', 'pekin', 'ba', 'people', '?', '!', '.'
        ]
        
        words = text_lower.split()
        filtered = [w.strip('.,!?\'\"') for w in words if w.strip('.,!?\'\"') not in remove_words]
        
        # Try to capture quoted phrases
        quoted = re.findall(r'["\']([^"\']+)["\']', text)
        if quoted:
            return quoted
        
        # Return cleaned words or the whole phrase if short
        if filtered:
            if len(filtered) <= 4:
                return [' '.join(filtered)]
            return filtered[:3]
        
        # Last resort
        cleaned = text_lower.strip('.,!?\'"')
        return [cleaned] if cleaned else ['help']

    def _search_dictionary(self, search_terms):
        """
        Search the dictionary with fuzzy matching and Liberian pattern awareness.
        """
        entries = []
        
        for term in search_terms:
            if not term or len(term) < 2:
                continue
                
            # Search English translations
            english_matches = KoloquaEntry.objects.filter(
                Q(english_translation__icontains=term) |
                Q(literal_translation__icontains=term) |
                Q(example_sentence_english__icontains=term),
                status='verified'
            ).distinct()[:3]
            entries.extend(english_matches)
            
            # Search Kolokwa text
            kolokwa_matches = KoloquaEntry.objects.filter(
                Q(koloqua_text__icontains=term) |
                Q(example_sentence_koloqua__icontains=term),
                status='verified'
            ).distinct()[:3]
            entries.extend(kolokwa_matches)
            
            # Search in tags and context
            context_matches = KoloquaEntry.objects.filter(
                Q(tags__icontains=term) |
                Q(context_explanation__icontains=term),
                status='verified'
            ).distinct()[:2]
            entries.extend(context_matches)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_entries = []
        for entry in entries:
            if entry.id not in seen:
                seen.add(entry.id)
                unique_entries.append(entry)
        
        return unique_entries[:5]

    def _clean_markdown(self, text):
        """
        Remove markdown formatting for plain text display.
        """
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        return text

    def _generate_response(self, original_query, entries, search_terms, normalized_query):
        """
        Generate a natural, culturally-aware response using ONLY verified dictionary entries.
        """
        if not entries:
            return self._generate_not_found_response(original_query, search_terms)
        
        entries_text = self._format_entries(entries)
        
        try:
            prompt = f"""You are a helpful assistant for the Kolokwa language dictionary.

CRITICAL RULES:
1. Use ONLY the dictionary entries provided below - DO NOT invent translations
2. If the dictionary doesn't have the exact phrase, say so honestly
3. DO NOT use Nigerian Pidgin patterns (no "fo", "hala", "wetin dey", etc.)
4. Kolokwa is LIBERIAN - keep responses authentic to Liberian speech
5. ALWAYS show example sentences if they exist in the dictionary entries
6. Use plain text formatting - NO markdown (no **, *, or ` characters)

User asked: "{original_query}"

Dictionary entries found:
{entries_text}

Provide a helpful response using ONLY these dictionary entries in PLAIN TEXT format.
- If example sentences exist, ALWAYS include them
- If these entries don't fully answer the question, be honest about it
- Use simple quotes ("") for emphasis, not markdown

Response:"""

            # CORRECTED: Use chat.completions.create
            completion = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful Kolokwa dictionary assistant. Use plain text only, no markdown."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            # CORRECTED: Access response correctly
            response_text = completion.choices[0].message.content.strip()
            return self._clean_markdown(response_text)
            
        except Exception as e:
            logger.error(f"Error generating LLM response: {str(e)}", exc_info=True)
            return self._generate_template_response(entries[0], original_query)

    def _format_entries(self, entries):
        """Format dictionary entries for LLM context."""
        formatted = []
        for entry in entries:
            entry_text = f"""
Entry {len(formatted) + 1}:
- Kolokwa: {entry.koloqua_text}
- English: {entry.english_translation}
- Type: {entry.get_entry_type_display()}"""
            
            if entry.example_sentence_koloqua and entry.example_sentence_english:
                entry_text += f"""
- EXAMPLE: "{entry.example_sentence_koloqua}" = "{entry.example_sentence_english}"
  (Always include this example if relevant)"""
            
            if entry.context_explanation:
                entry_text += f"""
- Usage: {entry.context_explanation[:150]}"""
            
            if entry.pronunciation_guide:
                entry_text += f"""
- Pronunciation: {entry.pronunciation_guide}"""
            
            if entry.literal_translation and entry.literal_translation != entry.english_translation:
                entry_text += f"""
- Literal: {entry.literal_translation}"""
            
            if entry.cultural_notes:
                entry_text += f"""
- Cultural note: {entry.cultural_notes[:100]}"""
                
            formatted.append(entry_text)
        
        return "\n".join(formatted)

    def _generate_template_response(self, entry, original_query):
        """Generate a simple template response as fallback."""
        response = f"In Kolokwa, '{entry.koloqua_text}' means '{entry.english_translation}'."
        
        if entry.example_sentence_koloqua and entry.example_sentence_english:
            response += f"\n\nExample: '{entry.example_sentence_koloqua}' = '{entry.example_sentence_english}'."
        
        if entry.pronunciation_guide:
            response += f"\n\nPronunciation: {entry.pronunciation_guide}"
        
        if entry.context_explanation:
            response += f"\n\n{entry.context_explanation}"
        
        return response

    def _generate_not_found_response(self, query, search_terms):
        """Generate a helpful response when no entries are found."""
        terms_text = ', '.join(f"'{term}'" for term in search_terms[:3])
        
        return f"I couldn't find '{terms_text}' in our Kolokwa dictionary yet. Our dictionary is still growing, and we'd love your help! If you know this translation, please consider contributing it to help preserve Liberian Kolokwa for everyone."