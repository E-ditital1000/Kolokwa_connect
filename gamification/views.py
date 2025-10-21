# gamification/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Badge, DailyChallenge, UserStreak, UserBadge, PointTransaction
from .serializers import (
    BadgeSerializer, DailyChallengeSerializer, UserStreakSerializer,
    UserBadgeSerializer, PointTransactionSerializer, LeaderboardSerializer
)
from .utils import award_points, update_user_streak, check_and_award_badges

User = get_user_model()


# HTML Views
class LeaderboardView(TemplateView):
    """HTML view for displaying leaderboard"""
    template_name = 'gamification/leaderboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get top users by points
        top_users = User.objects.annotate(
            contributions_count=Count('koloqua_entries', filter=Q(koloqua_entries__status='verified')),
            verifications_count=Count('verifications'),
            badges_count=Count('badges')
        ).order_by('-points')[:50]
        
        # Add rank to each user
        for i, user in enumerate(top_users):
            user.rank = i + 1
        
        context['top_users'] = top_users
        context['user_rank'] = None
        
        # Get current user's rank if authenticated
        if self.request.user.is_authenticated:
            user_rank = User.objects.filter(
                points__gt=self.request.user.points
            ).count() + 1
            context['user_rank'] = user_rank
        
        return context


class UserProfileView(LoginRequiredMixin, TemplateView):
    """HTML view for user's gamification profile"""
    template_name = 'gamification/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # User stats
        context['user_badges'] = UserBadge.objects.filter(user=user).select_related('badge')
        context['recent_transactions'] = PointTransaction.objects.filter(
            user=user
        ).order_by('-created_at')[:20]
        
        # Streak info
        streak, _ = UserStreak.objects.get_or_create(user=user)
        context['user_streak'] = streak
        
        # Today's challenge
        today = timezone.now().date()
        today_challenge = DailyChallenge.objects.filter(
            challenge_date=today,
            is_active=True
        ).first()
        context['today_challenge'] = today_challenge
        context['challenge_accepted'] = (
            streak.accepted_challenge == today_challenge and 
            streak.accepted_challenge_date == today
        ) if today_challenge else False
        
        return context


class BadgesView(TemplateView):
    """HTML view for displaying all badges"""
    template_name = 'gamification/badges.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['badges'] = Badge.objects.all().order_by('badge_type', 'points_required')
        
        if self.request.user.is_authenticated:
            user_badge_ids = UserBadge.objects.filter(
                user=self.request.user
            ).values_list('badge_id', flat=True)
            context['user_badge_ids'] = list(user_badge_ids)
        else:
            context['user_badge_ids'] = []
        
        return context


# API ViewSets
class BadgeViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing Badges."""
    queryset = Badge.objects.all()
    serializer_class = BadgeSerializer
    permission_classes = [permissions.AllowAny]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]


class DailyChallengeViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for the daily challenge."""
    queryset = DailyChallenge.objects.filter(is_active=True)
    serializer_class = DailyChallengeSerializer
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]

    @action(detail=True, methods=['post'])
    def accept_challenge(self, request, pk=None):
        challenge = self.get_object()
        user = request.user
        today = timezone.now().date()

        # Check if user has already accepted this challenge today
        user_streak, created = UserStreak.objects.get_or_create(user=user)
        if (user_streak.accepted_challenge_date == today and 
            user_streak.accepted_challenge == challenge):
            return Response({
                'detail': 'You have already accepted this challenge today.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user_streak.accepted_challenge = challenge
        user_streak.accepted_challenge_date = today
        user_streak.save()

        return Response({
            'detail': f'Challenge "{challenge.title}" accepted!',
            'challenge': self.get_serializer(challenge).data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def complete_challenge(self, request, pk=None):
        challenge = self.get_object()
        user = request.user
        today = timezone.now().date()

        user_streak, created = UserStreak.objects.get_or_create(user=user)

        if (user_streak.accepted_challenge != challenge or 
            user_streak.accepted_challenge_date != today):
            return Response({
                'detail': 'You have not accepted this challenge today.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if already completed (need to add this field to model)
        if hasattr(user_streak, 'completed_challenge_date') and user_streak.completed_challenge_date == today:
            return Response({
                'detail': 'You have already completed this challenge today.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Award points and update streak
        award_points(
            user, 
            challenge.points_reward, 
            'achievement', 
            f'Completed daily challenge: {challenge.title}'
        )
        update_user_streak(user)

        return Response({
            'detail': f'Challenge "{challenge.title}" completed! Points awarded.',
            'points_awarded': challenge.points_reward
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's challenge"""
        today = timezone.now().date()
        challenge = DailyChallenge.objects.filter(
            challenge_date=today,
            is_active=True
        ).first()
        
        if not challenge:
            return Response({
                'detail': 'No challenge available for today.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user has accepted/completed
        user_streak = UserStreak.objects.filter(user=request.user).first()
        accepted = (
            user_streak and 
            user_streak.accepted_challenge == challenge and 
            user_streak.accepted_challenge_date == today
        )
        
        data = self.get_serializer(challenge).data
        data['accepted'] = accepted
        
        return Response(data)


class LeaderboardViewSet(viewsets.ViewSet):
    """ViewSet for leaderboard data"""
    permission_classes = [permissions.AllowAny]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    
    def list(self, request):
        """Get top users leaderboard"""
        limit = int(request.query_params.get('limit', 50))
        
        top_users = User.objects.annotate(
            contributions_count=Count('koloqua_entries', filter=Q(koloqua_entries__status='verified'))
        ).order_by('-points')[:limit]
        
        leaderboard_data = []
        for i, user in enumerate(top_users):
            leaderboard_data.append({
                'user_id': user.id,
                'username': user.username,
                'points': user.points,
                'level': user.level,
                'contributions_count': user.contributions_count,
                'rank': i + 1
            })
        
        serializer = LeaderboardSerializer(leaderboard_data, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def user_rank(self, request):
        """Get current user's rank"""
        if not request.user.is_authenticated:
            return Response({
                'detail': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        user_rank = User.objects.filter(
            points__gt=request.user.points
        ).count() + 1
        
        return Response({
            'rank': user_rank,
            'points': request.user.points,
            'level': request.user.level
        })


class UserStatsViewSet(viewsets.ViewSet):
    """ViewSet for user statistics"""
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    
    def list(self, request):
        """Get current user's stats"""
        user = request.user
        
        # Get user badges
        user_badges = UserBadge.objects.filter(user=user).select_related('badge')
        
        # Get recent transactions
        recent_transactions = PointTransaction.objects.filter(
            user=user
        ).order_by('-created_at')[:20]
        
        # Get streak info
        streak, _ = UserStreak.objects.get_or_create(user=user)
        
        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'points': user.points,
                'level': user.level,
            },
            'badges': UserBadgeSerializer(user_badges, many=True).data,
            'recent_transactions': PointTransactionSerializer(recent_transactions, many=True).data,
            'streak': UserStreakSerializer(streak).data
        })


# gamification/utils.py
from django.utils import timezone
from django.db.models import Count
from .models import Badge, UserBadge, PointTransaction, UserStreak


def award_points(user, points, transaction_type, description):
    """Award points to a user and create transaction record"""
    if points == 0:
        return
    
    # Create transaction
    transaction = PointTransaction.objects.create(
        user=user,
        points=points,
        transaction_type=transaction_type,
        description=description
    )
    
    # Check for new badges after awarding points
    check_and_award_badges(user)
    
    return transaction


def update_user_streak(user):
    """Update user's contribution streak"""
    streak, created = UserStreak.objects.get_or_create(user=user)
    streak.update_streak()
    
    # Award streak bonuses
    if streak.current_streak > 0 and streak.current_streak % 7 == 0:  # Weekly bonus
        award_points(
            user, 
            streak.current_streak * 2, 
            'achievement', 
            f'{streak.current_streak} day streak bonus!'
        )
    
    return streak


def check_badges(user):
    """Check if user has earned any new badges"""
    # Get user stats
    total_points = user.points
    contributions_count = user.koloqua_entries.filter(status='verified').count()
    verifications_count = user.verifications.count()
    
    # Get badges user doesn't have
    earned_badge_ids = UserBadge.objects.filter(user=user).values_list('badge_id', flat=True)
    available_badges = Badge.objects.exclude(id__in=earned_badge_ids)
    
    newly_earned = []
    
    for badge in available_badges:
        earned = False
        
        # Check point requirements
        if badge.points_required > 0 and total_points >= badge.points_required:
            earned = True
        
        # Check contribution requirements
        if badge.contributions_required > 0 and contributions_count >= badge.contributions_required:
            earned = True
        
        # Check verification requirements  
        if badge.verifications_required > 0 and verifications_count >= badge.verifications_required:
            earned = True
        
        # Special badge logic can be added here
        if badge.badge_type == 'special':
            earned = check_special_badge_criteria(user, badge)
        
        if earned:
            user_badge = UserBadge.objects.create(user=user, badge=badge)
            newly_earned.append(user_badge)
            
            # Award bonus points for earning badge
            award_points(
                user, 
                badge.points_required // 10 or 5,  # 10% of requirement or 5 points minimum
                'achievement', 
                f'Earned badge: {badge.name}'
            )
    
    return newly_earned


def check_special_badge_criteria(user, badge):
    """Check criteria for special badges"""
    # Example special badge criteria
    if badge.name == "First Contribution":
        return user.koloqua_entries.filter(status='verified').count() >= 1
    
    elif badge.name == "Helpful Verifier":
        return user.verifications.count() >= 10
    
    elif badge.name == "Community Hero":
        # Must have contributions AND verifications
        return (user.koloqua_entries.filter(status='verified').count() >= 5 and 
                user.verifications.count() >= 20)
    
    elif badge.name == "Streak Master":
        streak = UserStreak.objects.filter(user=user).first()
        return streak and streak.longest_streak >= 30
    
    return False


def get_user_level(points):
    """Calculate user level based on points"""
    if points < 100:
        return "Beginner"
    elif points < 500:
        return "Contributor"
    elif points < 1000:
        return "Expert"
    elif points < 2500:
        return "Master"
    elif points < 5000:
        return "Legend"
    else:
        return "Kolokwa Champion"


# Add this method to your User model
def update_level(self):
    """Update user's level based on current points"""
    self.level = get_user_level(self.points)
    self.save(update_fields=['level'])


# gamification/serializers.py  
from rest_framework import serializers
from .models import Badge, UserBadge, PointTransaction, DailyChallenge, UserStreak


class BadgeSerializer(serializers.ModelSerializer):
    """Serializer for Badge"""
    class Meta:
        model = Badge
        fields = ['id', 'name', 'description', 'badge_type', 'icon', 'points_required', 
                 'contributions_required', 'verifications_required']


class UserBadgeSerializer(serializers.ModelSerializer):
    """Serializer for UserBadge"""
    badge = BadgeSerializer(read_only=True)
    
    class Meta:
        model = UserBadge
        fields = ['id', 'badge', 'earned_at']


class PointTransactionSerializer(serializers.ModelSerializer):
    """Serializer for PointTransaction"""
    class Meta:
        model = PointTransaction
        fields = ['id', 'points', 'transaction_type', 'description', 'created_at']


class DailyChallengeSerializer(serializers.ModelSerializer):
    """Serializer for DailyChallenge"""
    class Meta:
        model = DailyChallenge
        fields = ['id', 'title', 'description', 'points_reward', 'target_count', 
                 'challenge_date', 'is_active']


class UserStreakSerializer(serializers.ModelSerializer):
    """Serializer for UserStreak"""
    class Meta:
        model = UserStreak
        fields = ['current_streak', 'longest_streak', 'last_contribution_date']


class LeaderboardSerializer(serializers.Serializer):
    """Serializer for leaderboard data"""
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    points = serializers.IntegerField()
    level = serializers.CharField()
    contributions_count = serializers.IntegerField()
    rank = serializers.IntegerField()