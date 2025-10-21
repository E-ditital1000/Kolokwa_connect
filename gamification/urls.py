from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BadgeViewSet,
    DailyChallengeViewSet,
    LeaderboardViewSet,
    UserStatsViewSet,
    LeaderboardView,
    UserProfileView,
    BadgesView
)

app_name = 'gamification'

# Create a router for the API ViewSets
router = DefaultRouter()
router.register(r'api/badges', BadgeViewSet, basename='badge')
router.register(r'api/challenges', DailyChallengeViewSet, basename='challenge')
router.register(r'api/leaderboard', LeaderboardViewSet, basename='leaderboard-api')
router.register(r'api/user-stats', UserStatsViewSet, basename='user-stats')

# Define urlpatterns for both HTML views and the API router
urlpatterns = [
    # HTML Views
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('profile/', UserProfileView.as_view(), name='gamification-profile'),
    path('badges/', BadgesView.as_view(), name='badge-list'),

    # API Routes
    path('', include(router.urls)),
]