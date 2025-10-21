from rest_framework import serializers
from django.contrib.auth import get_user_model
from gamification.models import UserBadge
from gamification.serializers import UserBadgeSerializer
from dictionary.models import KoloquaEntry
# KoloquaEntrySerializer will be imported locally to avoid circular import


User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    badges_count = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'bio', 'profile_picture', 'points', 'level', 
            'contributions_count', 'verifications_count',
            'is_verified_contributor', 'badges_count', 'joined_date'
        ]
        read_only_fields = [
            'points', 'level', 'contributions_count', 
            'verifications_count', 'is_verified_contributor'
        ]
    
    def get_badges_count(self, obj):
        return obj.badges.count()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name'
        ]
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    badges = UserBadgeSerializer(many=True, read_only=True)
    recent_contributions = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'bio', 'profile_picture', 'phone_number', 'points', 
            'level', 'contributions_count', 'verifications_count',
            'is_verified_contributor', 'badges', 'recent_contributions',
            'joined_date', 'last_active'
        ]
        read_only_fields = [
            'points', 'level', 'contributions_count', 
            'verifications_count', 'is_verified_contributor',
            'joined_date', 'last_active'
        ]
    
    def get_recent_contributions(self, obj):
        from dictionary.serializers import KoloquaEntrySerializer
        recent = KoloquaEntry.objects.filter(
            contributor=obj
        ).order_by('-created_at')[:5]
        return KoloquaEntrySerializer(recent, many=True, context=self.context).data