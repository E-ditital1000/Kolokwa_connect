from django.urls import path

from django.urls import path
from .views import (
    UserRegistrationView, UserProfileView, UserListView,
    CurrentUserView, UpdateProfileView, UserContributionsView,
    ProfileView, EditProfileView, UserContributionsTemplateView,
    LeaderboardView, SMSPreferencesView, sms_preferences_api, test_sms_notification
)
from .workos_views import workos_api_callback

app_name = 'users'

urlpatterns = [
    # Template-based views
    path('profile/', ProfileView.as_view(), name='me-profile'),
    path('profile/edit/', EditProfileView.as_view(), name='me-edit'),
    path('profile/contributions/', UserContributionsTemplateView.as_view(), name='me-contributions'),
    path('profile/<str:username>/', ProfileView.as_view(), name='user-profile'),
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),

    path('sms-preferences/', SMSPreferencesView.as_view(), name='sms-preferences'),
    path('api/sms-preferences/', sms_preferences_api, name='api-sms-preferences'),
    path('api/test-sms/', test_sms_notification, name='api-test-sms'),
    
    # API endpoints
    path('api/register/', UserRegistrationView.as_view(), name='api-register'),
    path('api/users/', UserListView.as_view(), name='api-user-list'),
    path('api/users/me/', CurrentUserView.as_view(), name='api-me'),
    path('api/users/me/update/', UpdateProfileView.as_view(), name='api-update-profile'),
    path('api/users/me/contributions/', UserContributionsView.as_view(), name='api-me-contributions'),
    path('api/users/<int:pk>/', UserProfileView.as_view(), name='api-user-detail'),
    
    # WorkOS API endpoint (for frontend apps)
    path('api/workos/callback/', workos_api_callback, name='api-workos-callback'),
]
