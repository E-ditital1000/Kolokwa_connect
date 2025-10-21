"""
users/workos_views.py
WorkOS AuthKit integration views - Updated for WorkOS SDK v5.x
"""

from django.shortcuts import redirect
from django.contrib.auth import login, logout as django_logout
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth import get_user_model
from workos import WorkOSClient
import logging
import json

logger = logging.getLogger(__name__)

User = get_user_model()

# Initialize WorkOS client (v5.x syntax)
workos = WorkOSClient(
    api_key=settings.WORKOS_API_KEY,
    client_id=settings.WORKOS_CLIENT_ID
)


@csrf_exempt
def workos_callback(request):
    """
    Handle WorkOS authentication callback
    URL: /auth/workos/callback
    """
    
    code = request.GET.get('code')
    state = request.GET.get('state', '{}')
    
    if not code:
        logger.error("No authorization code received from WorkOS")
        return JsonResponse({
            'error': 'No authorization code received'
        }, status=400)
    
    try:
        # Exchange the code for user profile (v5.x API)
        auth_response = workos.sso.get_profile_and_token(code)
        
        # Extract user profile information
        profile = auth_response.profile
        access_token = auth_response.access_token
        
        logger.info(f"WorkOS authentication successful for: {profile.email}")
        
        # Get or create user in your database
        user, created = User.objects.get_or_create(
            email=profile.email,
            defaults={
                'username': profile.email.split('@')[0],
                'first_name': profile.first_name or '',
                'last_name': profile.last_name or '',
                'workos_id': profile.id,
                'is_verified_contributor': True,
            }
        )
        
        # Update user info if not created
        if not created:
            user.first_name = profile.first_name or user.first_name
            user.last_name = profile.last_name or user.last_name
            user.workos_id = profile.id
            user.save()
        else:
            logger.info(f"New user created via WorkOS: {user.username}")
        
        # Log the user into Django session
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        
        # Store WorkOS access token in session
        request.session['workos_access_token'] = access_token
        request.session['workos_profile_id'] = profile.id
        
        # Get redirect URL from state or default to profile
        try:
            state_data = json.loads(state) if isinstance(state, str) else state
            next_url = state_data.get('next', '/users/profile/')
        except Exception as e:
            logger.warning(f"Failed to parse state: {e}")
            next_url = '/users/profile/'
        
        logger.info(f"Redirecting authenticated user {user.username} to: {next_url}")
        return redirect(next_url)
        
    except Exception as e:
        logger.error(f"WorkOS authentication failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Authentication failed',
            'message': str(e) if settings.DEBUG else 'Authentication error'
        }, status=400)


def workos_login(request):
    """
    Initiate WorkOS authentication using OAuth provider
    URL: /auth/workos/login
    """
    
    next_url = request.GET.get('next', '/users/profile/')
    redirect_uri = f"{settings.SITE_URL}/auth/workos/callback"
    provider = request.GET.get('provider', 'GoogleOAuth')
    
    try:
        # Use provider-based authentication (v5.x API)
        authorization_url = workos.sso.get_authorization_url(
            provider=provider,
            redirect_uri=redirect_uri,
            state=json.dumps({'next': next_url})
        )
        
        logger.info(f"Initiating WorkOS login with provider: {provider}")
        logger.info(f"Redirect URI: {redirect_uri}")
        
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"Error initiating WorkOS login: {str(e)}")
        return JsonResponse({
            'error': 'Failed to initiate authentication',
            'message': str(e) if settings.DEBUG else 'Authentication error'
        }, status=500)


def workos_logout(request):
    """
    Log out user and clear WorkOS session
    URL: /auth/workos/logout
    """
    
    # Clear Django session
    request.session.flush()
    
    # Django logout
    django_logout(request)
    
    # Redirect to home
    return redirect('/')


# API View for WorkOS authentication (for frontend apps)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status as http_status
from rest_framework_simplejwt.tokens import RefreshToken


@api_view(['POST'])
@permission_classes([AllowAny])
def workos_api_callback(request):
    """
    API endpoint for WorkOS authentication (for React/Vue frontends)
    URL: /api/auth/workos/callback
    
    POST data:
    {
        "code": "authorization_code_from_workos"
    }
    
    Returns:
    {
        "user": {...},
        "access": "jwt_token",
        "refresh": "jwt_refresh_token"
    }
    """
    
    code = request.data.get('code')
    
    if not code:
        return Response({
            'error': 'No authorization code provided'
        }, status=http_status.HTTP_400_BAD_REQUEST)
    
    try:
        # Exchange code for profile (v5.x API)
        auth_response = workos.sso.get_profile_and_token(code)
        profile = auth_response.profile
        
        # Get or create user
        user, created = User.objects.get_or_create(
            email=profile.email,
            defaults={
                'username': profile.email.split('@')[0],
                'first_name': profile.first_name or '',
                'last_name': profile.last_name or '',
                'workos_id': profile.id,
                'is_verified_contributor': True,
            }
        )
        
        # Update existing user
        if not created:
            user.first_name = profile.first_name or user.first_name
            user.last_name = profile.last_name or user.last_name
            user.workos_id = profile.id
            user.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        # Import serializer
        from users.serializers import UserSerializer
        
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'message': 'Authentication successful'
        }, status=http_status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Unexpected error in WorkOS API callback: {str(e)}", exc_info=True)
        return Response({
            'error': 'Internal server error',
            'message': str(e) if settings.DEBUG else 'Authentication error'
        }, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)