# dictionary/serializers.py
from rest_framework import serializers
from .models import KoloquaEntry, EntryVerification, EntryVote, WordCategory
from users.serializers import UserSerializer
from gamification.utils import award_points

class WordCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = WordCategory
        fields = '__all__'


class ContributorSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSerializer.Meta.model
        fields = ('id', 'username', 'level')


class KoloquaEntrySerializer(serializers.ModelSerializer):
    contributor = ContributorSerializer(read_only=True)

    class Meta:
        model = KoloquaEntry
        fields = [
            'id', 'koloqua_text', 'english_translation', 'entry_type',
            'status', 'upvotes', 'downvotes', 'contributor'
        ]
        read_only_fields = ['status', 'upvotes', 'downvotes', 'contributor']


class KoloquaEntryDetailSerializer(KoloquaEntrySerializer):
    categories = WordCategorySerializer(many=True, read_only=True)
    
    class Meta(KoloquaEntrySerializer.Meta):
        fields = KoloquaEntrySerializer.Meta.fields + [
            'literal_translation', 'context_explanation', 'example_sentence_koloqua',
            'example_sentence_english', 'cultural_notes', 'tags',
            'pronunciation_guide', 'audio_pronunciation',
            'region_specific', 'created_at', 'verified_at', 'categories'
        ]


class EntryVerificationSerializer(serializers.ModelSerializer):
    verifier = ContributorSerializer(read_only=True)
    
    class Meta:
        model = EntryVerification
        fields = ['id', 'entry', 'verifier', 'verification_type', 'comments', 'created_at']
        read_only_fields = ['verifier']


class EntryVoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryVote
        fields = ['id', 'entry', 'vote_type']


class KoloquaEntryCreateSerializer(serializers.ModelSerializer):
    categories = serializers.PrimaryKeyRelatedField(queryset=WordCategory.objects.all(), many=True, required=False)

    class Meta:
        model = KoloquaEntry
        fields = [
            'koloqua_text', 'english_translation', 'entry_type',
            'literal_translation', 'context_explanation', 'example_sentence_koloqua',
            'example_sentence_english', 'cultural_notes', 'tags',
            'pronunciation_guide', 'audio_pronunciation', 'region_specific',
            'categories'
        ]