from rest_framework import serializers
from .models import Badge, UserBadge, PointTransaction, DailyChallenge, UserStreak

class BadgeSerializer(serializers.ModelSerializer):
    """Serializer for Badge"""
    class Meta:
        model = Badge
        fields = ['id', 'name', 'description', 'badge_type', 'icon', 'points_required']

class UserBadgeSerializer(serializers.ModelSerializer):
    """Serializer for UserBadge"""
    badge = BadgeSerializer(read_only=True)
    class Meta:
        model = UserBadge
        fields = ['id', 'user', 'badge', 'earned_at']

class PointTransactionSerializer(serializers.ModelSerializer):
    """Serializer for PointTransaction"""
    class Meta:
        model = PointTransaction
        fields = ['id', 'user', 'points', 'transaction_type', 'description', 'created_at']

class DailyChallengeSerializer(serializers.ModelSerializer):
    """Serializer for DailyChallenge"""
    class Meta:
        model = DailyChallenge
        fields = ['id', 'title', 'description', 'points_reward', 'target_count', 'challenge_date', 'is_active']

class UserStreakSerializer(serializers.ModelSerializer):
    """Serializer for UserStreak"""
    class Meta:
        model = UserStreak
        fields = ['id', 'user', 'current_streak', 'longest_streak', 'last_contribution_date']


class LeaderboardSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    points = serializers.IntegerField()
    level = serializers.CharField()
    contributions_count = serializers.IntegerField()
    rank = serializers.IntegerField()