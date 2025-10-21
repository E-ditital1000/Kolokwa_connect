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