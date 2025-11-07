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
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class NLQueryView(views.APIView):
    """
    Enhanced API view to handle natural language queries with Liberian speech patterns.
    Supports Koloqua, Liberian English, and standard English inputs with intelligent
    entry blending and phrase construction.
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

    # Query intent patterns
    INTENT_PATTERNS = {
        'translate_to_kolokwa': [
            r'how.*say.*kolokwa',
            r'translate.*to kolokwa',
            r'kolokwa.*for',
            r'in kolokwa',
            r'how.*you.*say',
            r'how.*i.*say',
        ],
        'translate_to_english': [
            r'what.*mean',
            r'translate.*english',
            r'what is.*in english',
            r'mean in english',
        ],
        'definition': [
            r'what.*is',
            r'define',
            r'meaning of',
            r'definition',
        ],
        'example': [
            r'example',
            r'use.*sentence',
            r'show me.*use',
            r'how.*use',
        ],
        'pronunciation': [
            r'how.*pronounce',
            r'how.*say.*out loud',
            r'pronunciation',
            r'how.*sound',
        ]
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def post(self, request, *args, **kwargs):
        serializer = NLQuerySerializer(data=request.data)
        if not serializer.is_valid():
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        query = serializer.validated_data['query']
        include_examples = serializer.validated_data.get('include_examples', True)
        cultural_context = serializer.validated_data.get('cultural_context', True)
        
        try:
            # Step 1: Classify query intent
            intent = self._classify_query_intent(query)
            
            # Step 2: Normalize the query for Liberian patterns
            normalized_query = self._normalize_liberian_input(query)
            
            # Step 3: Extract search terms using enhanced method
            search_terms = self._extract_search_terms(normalized_query, original_query=query)
            
            # Step 4: Detect if this is a phrase construction request
            target_phrase = self._detect_phrase_construction(query, intent)
            
            # Step 5: Search dictionary with intelligent scoring
            entries = self._search_dictionary(search_terms, intent)
            
            # Step 6: Generate natural language response with blending
            answer = self._generate_response(
                query, 
                entries, 
                search_terms, 
                normalized_query,
                intent,
                target_phrase,
                include_examples,
                cultural_context
            )
            
            # Prepare response data
            response_data = {
                'response': answer,
                'intent': intent,
                'entries_found': len(entries)
            }
            
            # Add optional metadata
            if search_terms:
                response_data['search_terms'] = search_terms
            
            if target_phrase:
                response_data['target_phrase'] = target_phrase
            
            # Return formatted response
            response_serializer = NLResponseSerializer(data=response_data)
            response_serializer.is_valid(raise_exception=True)
            return response.Response(response_serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error processing NL query: {str(e)}", exc_info=True)
            return response.Response(
                {'error': 'An error occurred processing your query. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _classify_query_intent(self, query: str) -> str:
        """
        Classify what the user is trying to do.
        Returns: intent type as string
        """
        query_lower = query.lower()
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            if any(re.search(pattern, query_lower) for pattern in patterns):
                return intent
        
        return 'general'

    def _normalize_liberian_input(self, query: str) -> str:
        """
        Normalize Liberian English/Koloqua patterns to standard English for better LLM understanding.
        """
        normalized = query.lower().strip()
        
        for pattern, replacement in self.LIBERIAN_PATTERNS.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _detect_phrase_construction(self, query: str, intent: str) -> Optional[str]:
        """
        Detect if the query is asking for a phrase that can be built from multiple entries.
        Returns the target phrase to construct, or None.
        """
        if intent != 'translate_to_kolokwa':
            return None
        
        query_lower = query.lower()
        
        # Extract quoted phrases first
        quoted = re.findall(r'["\']([^"\']+)["\']', query)
        if quoted:
            return quoted[0].strip()
        
        # Try to extract after common patterns
        extraction_patterns = [
            (r'how\s+(?:you\s+)?say\s+["\']?([^"\'?]+)["\']?', 1),
            (r'translate\s+["\']?([^"\'?]+)["\']?\s+to\s+kolokwa', 1),
            (r'kolokwa\s+for\s+["\']?([^"\'?]+)["\']?', 1),
            (r'how\s+(?:i\s+)?(?:can\s+)?say\s+["\']?([^"\'?]+)["\']?', 1),
            (r'what\s+is\s+["\']?([^"\'?]+)["\']?\s+in\s+kolokwa', 1),
        ]
        
        for pattern, group in extraction_patterns:
            match = re.search(pattern, query_lower)
            if match:
                phrase = match.group(group).strip(' ?,.:!;')
                if phrase and len(phrase) > 2:
                    return phrase
        
        return None

    def _extract_search_terms(self, query: str, original_query: Optional[str] = None) -> List[str]:
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
If the query asks to translate a phrase, break it into individual words AND keep the phrase.

Examples:
- "How you say 'water'?" -> ["water"]
- "I want to eat" -> ["eat", "want", "want to eat"]
- "I love you" -> ["love", "I love you"]
- "Bro, come, let's go eat" -> ["bro", "brother", "come", "go", "let's go", "eat"]
- "How you say thank you?" -> ["thank you", "thank", "thanks"]

Original query: "{original_query or query}"
Normalized query: "{query}"

Return JSON array of search terms:"""

            completion = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a linguistic assistant that extracts search terms. Always return valid JSON arrays."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=150
            )
            
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

    def _fallback_extraction(self, query: str, original_query: Optional[str] = None) -> List[str]:
        """
        Enhanced fallback extraction that understands Liberian speech patterns.
        """
        text = original_query or query
        text_lower = text.lower().strip()
        
        # First try to extract quoted content
        quoted = re.findall(r'["\']([^"\']+)["\']', text)
        if quoted:
            # Also break down the quoted phrase into words
            phrase = quoted[0]
            words = phrase.lower().split()
            return [phrase] + words[:5]  # Phrase + individual words
        
        # Remove common sentence starters
        for starter in self.SENTENCE_STARTERS:
            text_lower = re.sub(starter, '', text_lower)
        
        # Remove common question/command words
        remove_words = [
            'how', 'what', 'tell', 'me', 'say', 'can', 'you', 'help',
            'the', 'a', 'an', 'is', 'be', 'we', 'i', 'my',
            'kolokwa', 'koloqua', 'english', 'translate', 'translation',
            'word', 'phrase', '?', '!', '.'
        ]
        
        words = text_lower.split()
        filtered = [w.strip('.,!?\'\"') for w in words if w.strip('.,!?\'\"') not in remove_words]
        
        # Return cleaned words
        if filtered:
            if len(filtered) <= 4:
                # Keep as phrase if short
                return [' '.join(filtered)] + filtered
            # Return multiple terms for better matching
            return filtered[:6]
        
        # Last resort
        cleaned = text_lower.strip('.,!?\'"')
        return [cleaned] if cleaned else ['help']

    def _search_dictionary(self, search_terms: List[str], intent: str) -> List[KoloquaEntry]:
        """
        Search the dictionary with intelligent scoring and relevance ranking.
        Returns entries sorted by relevance score.
        """
        entry_scores = {}  # Track entries with relevance scores
        entry_objects = {}  # Cache entry objects
        
        for term in search_terms:
            if not term or len(term) < 2:
                continue
            
            term_lower = term.lower()
            
            # PRIMARY MATCHES (Score: 20) - Exact matches
            primary = KoloquaEntry.objects.filter(
                Q(koloqua_text__iexact=term) | 
                Q(english_translation__iexact=term),
                status='verified'
            ).distinct()
            
            for entry in primary:
                entry_scores[entry.id] = entry_scores.get(entry.id, 0) + 20
                entry_objects[entry.id] = entry
            
            # SECONDARY MATCHES (Score: 10) - Contains in main fields
            secondary = KoloquaEntry.objects.filter(
                Q(koloqua_text__icontains=term) |
                Q(english_translation__icontains=term) |
                Q(literal_translation__icontains=term),
                status='verified'
            ).distinct()
            
            for entry in secondary:
                if entry.id not in entry_scores:  # Don't double-count primary matches
                    entry_scores[entry.id] = entry_scores.get(entry.id, 0) + 10
                    entry_objects[entry.id] = entry
            
            # EXAMPLE MATCHES (Score: 7) - Found in examples
            example_matches = KoloquaEntry.objects.filter(
                Q(example_sentence_koloqua__icontains=term) |
                Q(example_sentence_english__icontains=term),
                status='verified'
            ).distinct()
            
            for entry in example_matches:
                if entry.id not in entry_scores:
                    entry_scores[entry.id] = entry_scores.get(entry.id, 0) + 7
                    entry_objects[entry.id] = entry
            
            # CONTEXTUAL MATCHES (Score: 3) - Found in context/tags
            contextual = KoloquaEntry.objects.filter(
                Q(context_explanation__icontains=term) |
                Q(tags__icontains=term) |
                Q(cultural_notes__icontains=term),
                status='verified'
            ).distinct()
            
            for entry in contextual:
                if entry.id not in entry_scores:
                    entry_scores[entry.id] = entry_scores.get(entry.id, 0) + 3
                    entry_objects[entry.id] = entry
        
        # Sort by relevance score (descending)
        sorted_entries = sorted(entry_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Return top entries (more for phrase construction)
        top_count = 10 if intent == 'translate_to_kolokwa' else 6
        top_ids = [id for id, score in sorted_entries[:top_count]]
        
        # Return entries in order of relevance
        return [entry_objects[id] for id in top_ids if id in entry_objects]

    def _format_entries(self, entries: List[KoloquaEntry], include_examples: bool = True, cultural_context: bool = True) -> str:
        """
        Format dictionary entries for LLM context with rich details.
        """
        formatted = []
        for i, entry in enumerate(entries, 1):
            entry_text = f"""
Entry {i}:
- Kolokwa: {entry.koloqua_text}
- English: {entry.english_translation}
- Type: {entry.get_entry_type_display()}"""
            
            if entry.literal_translation and entry.literal_translation != entry.english_translation:
                entry_text += f"\n- Literal meaning: {entry.literal_translation}"
            
            if entry.pronunciation_guide:
                entry_text += f"\n- Pronunciation: {entry.pronunciation_guide}"
            
            if include_examples and entry.example_sentence_koloqua and entry.example_sentence_english:
                entry_text += f"""
- EXAMPLE: "{entry.example_sentence_koloqua}" = "{entry.example_sentence_english}"
  (IMPORTANT: Always include this example when relevant)"""
            
            if entry.context_explanation:
                entry_text += f"\n- Usage context: {entry.context_explanation[:200]}"
            
            if cultural_context and entry.cultural_notes:
                entry_text += f"\n- Cultural note: {entry.cultural_notes[:150]}"
            
            if entry.tags:
                entry_text += f"\n- Tags: {entry.tags}"
                
            formatted.append(entry_text)
        
        return "\n".join(formatted)

    def _clean_markdown(self, text: str) -> str:
        """
        Remove markdown formatting for plain text display.
        """
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        return text

    def _generate_response(
        self, 
        original_query: str, 
        entries: List[KoloquaEntry], 
        search_terms: List[str], 
        normalized_query: str,
        intent: str,
        target_phrase: Optional[str],
        include_examples: bool,
        cultural_context: bool
    ) -> str:
        """
        Generate a natural, culturally-aware response with intelligent entry blending.
        """
        if not entries:
            return self._generate_not_found_response(original_query, search_terms)
        
        entries_text = self._format_entries(entries, include_examples, cultural_context)
        
        try:
            # Different prompts based on intent
            if intent == 'translate_to_kolokwa' and target_phrase:
                prompt = self._build_phrase_construction_prompt(
                    target_phrase, entries_text, original_query
                )
            elif intent == 'translate_to_english':
                prompt = self._build_translation_to_english_prompt(
                    original_query, entries_text
                )
            elif intent == 'example':
                prompt = self._build_example_prompt(
                    original_query, entries_text
                )
            elif intent == 'pronunciation':
                prompt = self._build_pronunciation_prompt(
                    original_query, entries_text
                )
            else:
                prompt = self._build_general_prompt(
                    original_query, entries_text, include_examples
                )

            completion = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert Kolokwa dictionary assistant. Combine entries intelligently to build phrases. Use plain text only, no markdown. Be accurate and only use verified dictionary data."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=700
            )
            
            response_text = completion.choices[0].message.content.strip()
            return self._clean_markdown(response_text)
            
        except Exception as e:
            logger.error(f"Error generating LLM response: {str(e)}", exc_info=True)
            return self._generate_composite_response(entries, original_query, target_phrase)

    def _build_phrase_construction_prompt(self, target_phrase: str, entries_text: str, original_query: str) -> str:
        """Build prompt for phrase construction queries."""
        return f"""You are a Kolokwa language expert helping construct phrases from dictionary entries.

CRITICAL RULES:
1. Build the translation ONLY from the provided dictionary entries
2. Show how to combine individual word entries into the complete phrase
3. ALWAYS include example sentences from dictionary entries when available
4. Show the construction step-by-step, breaking down each word
5. Use plain text - NO markdown formatting (no **, *, or `)
6. If you cannot build the complete phrase from available entries, say so clearly and show what IS available
7. Include pronunciation guides when available

User wants to say in Kolokwa: "{target_phrase}"

Available verified dictionary entries:
{entries_text}

Instructions:
- If you have entries for all the words needed, show the complete phrase construction
- Break down the phrase: "Word1 + Word2 + Word3 = Complete phrase"
- If some words are missing, show what you CAN translate and explicitly state what's missing
- Always include relevant example sentences from the entries
- Show pronunciation for each component when available
- Explain any cultural context

Response:"""

    def _build_translation_to_english_prompt(self, original_query: str, entries_text: str) -> str:
        """Build prompt for Kolokwa to English translation."""
        return f"""You are a Kolokwa dictionary assistant helping translate Kolokwa to English.

CRITICAL RULES:
1. Use ONLY the verified dictionary entries provided
2. If the Kolokwa phrase has multiple words, break down each component
3. Show literal and contextual meanings when different
4. Include example sentences
5. Use plain text - NO markdown
6. Be honest if entries don't fully match the query

User asked: "{original_query}"

Dictionary entries:
{entries_text}

Provide a clear translation using only these verified entries. If it's a phrase, break down each word.

Response:"""

    def _build_example_prompt(self, original_query: str, entries_text: str) -> str:
        """Build prompt for example sentence requests."""
        return f"""You are a Kolokwa dictionary assistant providing example sentences.

CRITICAL RULES:
1. ONLY use example sentences from the verified dictionary entries
2. DO NOT create new examples - only use what's in the entries
3. Show multiple examples if available
4. Use plain text - NO markdown
5. If no examples exist in the entries, say so clearly

User asked: "{original_query}"

Dictionary entries:
{entries_text}

Show all available example sentences from these entries.

Response:"""

    def _build_pronunciation_prompt(self, original_query: str, entries_text: str) -> str:
        """Build prompt for pronunciation requests."""
        return f"""You are a Kolokwa dictionary assistant helping with pronunciation.

CRITICAL RULES:
1. Use ONLY pronunciation guides from the verified dictionary entries
2. If no pronunciation guide exists, say so
3. Use plain text - NO markdown
4. Break down syllables when possible

User asked: "{original_query}"

Dictionary entries:
{entries_text}

Provide pronunciation information from these entries.

Response:"""

    def _build_general_prompt(self, original_query: str, entries_text: str, include_examples: bool) -> str:
        """Build prompt for general queries."""
        return f"""You are a helpful Kolokwa dictionary assistant.

CRITICAL RULES:
1. Use ONLY the verified dictionary entries provided below
2. DO NOT invent translations or use Nigerian Pidgin patterns
3. Kolokwa is LIBERIAN - use authentic Liberian speech patterns only
4. {"ALWAYS show example sentences when available" if include_examples else "Focus on definitions"}
5. If multiple entries are relevant, show how they relate or can be combined
6. Use plain text - NO markdown (no **, *, or `)
7. Be honest if the entries don't fully answer the question

User asked: "{original_query}"

Dictionary entries:
{entries_text}

Provide a clear, helpful response using ONLY these verified entries.
- Show how different entries might work together if relevant
- {"Always include example sentences" if include_examples else ""}
- Be honest if the entries don't fully answer the question

Response:"""

    def _generate_composite_response(
        self, 
        entries: List[KoloquaEntry], 
        original_query: str, 
        target_phrase: Optional[str] = None
    ) -> str:
        """
        Generate response by intelligently combining multiple entries without LLM.
        This is the fallback when LLM fails.
        """
        if len(entries) == 1:
            return self._generate_template_response(entries[0], original_query)
        
        response_parts = []
        
        if target_phrase:
            response_parts.append(f"To say '{target_phrase}' in Kolokwa, here's what we have:\n")
            
            # Try to build the phrase
            kolokwa_words = []
            english_words = []
            breakdown_parts = []
            
            for i, entry in enumerate(entries[:5], 1):
                kolokwa_words.append(entry.koloqua_text)
                english_words.append(entry.english_translation)
                
                part = f"\n{i}. '{entry.koloqua_text}' = '{entry.english_translation}'"
                
                if entry.pronunciation_guide:
                    part += f" (pronounced: {entry.pronunciation_guide})"
                
                breakdown_parts.append(part)
                
                if entry.example_sentence_koloqua and entry.example_sentence_english:
                    part += f"\n   Example: '{entry.example_sentence_koloqua}' = '{entry.example_sentence_english}'"
                
                if entry.context_explanation:
                    context = entry.context_explanation[:120]
                    part += f"\n   Note: {context}"
            
            # Show the constructed phrase
            if kolokwa_words:
                constructed = ' '.join(kolokwa_words)
                response_parts.append(f"\nConstructed phrase: '{constructed}'\n")
                response_parts.append("Breaking it down:")
                response_parts.extend(breakdown_parts)
        else:
            response_parts.append("Based on your query, here are the relevant Kolokwa entries:\n")
            
            for i, entry in enumerate(entries[:4], 1):
                part = f"\n{i}. '{entry.koloqua_text}' = '{entry.english_translation}'"
                
                if entry.pronunciation_guide:
                    part += f" (pronounced: {entry.pronunciation_guide})"
                
                if entry.example_sentence_koloqua and entry.example_sentence_english:
                    part += f"\n   Example: '{entry.example_sentence_koloqua}' = '{entry.example_sentence_english}'"
                
                if entry.context_explanation:
                    part += f"\n   Usage: {entry.context_explanation[:100]}"
                
                if entry.cultural_notes:
                    part += f"\n   Cultural note: {entry.cultural_notes[:100]}"
                
                response_parts.append(part)
        
        return ''.join(response_parts)

    def _generate_template_response(self, entry: KoloquaEntry, original_query: str) -> str:
        """Generate a simple template response for single entry."""
        response = f"In Kolokwa, '{entry.koloqua_text}' means '{entry.english_translation}'."
        
        if entry.pronunciation_guide:
            response += f"\n\nPronunciation: {entry.pronunciation_guide}"
        
        if entry.example_sentence_koloqua and entry.example_sentence_english:
            response += f"\n\nExample: '{entry.example_sentence_koloqua}' = '{entry.example_sentence_english}'"
        
        if entry.context_explanation:
            response += f"\n\n{entry.context_explanation}"
        
        if entry.cultural_notes:
            response += f"\n\nCultural note: {entry.cultural_notes}"
        
        return response

    def _generate_not_found_response(self, query: str, search_terms: List[str]) -> str:
        """Generate a helpful response when no entries are found."""
        terms_text = ', '.join(f"'{term}'" for term in search_terms[:3])
        
        return (
            f"I couldn't find {terms_text} in our Kolokwa dictionary yet. "
            f"Our dictionary is still growing, and we'd love your help! "
            f"If you know this translation, please consider contributing it to help "
            f"preserve Liberian Kolokwa for everyone."
        )