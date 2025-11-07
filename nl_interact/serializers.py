# nl_interact/serializers.py
from rest_framework import serializers


class NLQuerySerializer(serializers.Serializer):
    """
    Serializer for natural language query input.
    """
    query = serializers.CharField(
        max_length=5000,
        help_text="Natural language query for translation or dictionary lookup",
        required=True,
        allow_blank=False
    )
    
    include_examples = serializers.BooleanField(
        default=True,
        required=False,
        help_text="Include example sentences in the response"
    )
    
    cultural_context = serializers.BooleanField(
        default=True,
        required=False,
        help_text="Include cultural notes and context in the response"
    )

    def validate_query(self, value):
        """
        Validate that the query is not empty after stripping whitespace.
        """
        if not value.strip():
            raise serializers.ValidationError("Query cannot be empty.")
        return value.strip()


class NLResponseSerializer(serializers.Serializer):
    """
    Serializer for natural language query response.
    """
    response = serializers.CharField(
        help_text="Natural language response from the AI assistant"
    )
    
    # Optional fields for additional metadata
    sources = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Dictionary entries used to generate the response"
    )
    
    confidence = serializers.FloatField(
        required=False,
        help_text="Confidence score of the translation (0.0 to 1.0)"
    )
    
    intent = serializers.CharField(
        required=False,
        help_text="Detected query intent (e.g., 'translate_to_kolokwa', 'definition', 'example')"
    )
    
    entries_found = serializers.IntegerField(
        required=False,
        help_text="Number of dictionary entries found and used in the response"
    )


class PhraseTranslationSerializer(serializers.Serializer):
    """
    Serializer for phrase translation requests.
    """
    phrase = serializers.CharField(
        max_length=2000,
        help_text="Phrase to translate",
        required=True,
        allow_blank=False
    )
    
    from_language = serializers.ChoiceField(
        choices=['english', 'kolokwa'],
        default='english',
        help_text="Source language"
    )
    
    to_language = serializers.ChoiceField(
        choices=['kolokwa', 'english'],
        default='kolokwa',
        help_text="Target language"
    )
    
    def validate_phrase(self, value):
        """Validate phrase is not empty."""
        if not value.strip():
            raise serializers.ValidationError("Phrase cannot be empty.")
        return value.strip()
    
    def validate(self, data):
        """Validate language pair."""
        if data['from_language'] == data['to_language']:
            raise serializers.ValidationError(
                "Source and target languages must be different."
            )
        return data


class ExplainPhraseSerializer(serializers.Serializer):
    """
    Serializer for Kolokwa phrase explanation requests.
    """
    phrase = serializers.CharField(
        max_length=2000,
        help_text="Kolokwa phrase to explain",
        required=True,
        allow_blank=False
    )
    
    def validate_phrase(self, value):
        """Validate phrase is not empty."""
        if not value.strip():
            raise serializers.ValidationError("Phrase cannot be empty.")
        return value.strip()


class DictionaryEntrySerializer(serializers.Serializer):
    """
    Serializer for dictionary entry details in responses.
    """
    id = serializers.IntegerField(
        help_text="Entry ID"
    )
    
    kolokwa_text = serializers.CharField(
        help_text="Kolokwa text"
    )
    
    english_translation = serializers.CharField(
        help_text="English translation"
    )
    
    entry_type = serializers.CharField(
        help_text="Entry type (word, phrase, idiom, proverb)"
    )
    
    pronunciation_guide = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Pronunciation guide"
    )
    
    example_kolokwa = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Example sentence in Kolokwa"
    )
    
    example_english = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Example sentence in English"
    )
    
    context_explanation = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Context and usage explanation"
    )
    
    cultural_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Cultural notes"
    )
    
    relevance_score = serializers.IntegerField(
        required=False,
        help_text="Relevance score for this query"
    )


class EnhancedNLResponseSerializer(serializers.Serializer):
    """
    Enhanced serializer for detailed natural language query responses.
    Includes structured dictionary entries and metadata.
    """
    response = serializers.CharField(
        help_text="Natural language response from the AI assistant"
    )
    
    intent = serializers.CharField(
        required=False,
        help_text="Detected query intent"
    )
    
    entries_found = serializers.IntegerField(
        required=False,
        help_text="Number of dictionary entries found"
    )
    
    dictionary_entries = DictionaryEntrySerializer(
        many=True,
        required=False,
        help_text="Detailed dictionary entries used in response"
    )
    
    target_phrase = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Detected target phrase for construction"
    )
    
    constructed_phrase = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Constructed Kolokwa phrase from entries"
    )
    
    confidence = serializers.FloatField(
        required=False,
        help_text="Confidence score of the response (0.0 to 1.0)"
    )
    
    search_terms = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Search terms extracted from query"
    )