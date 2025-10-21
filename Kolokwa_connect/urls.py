from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import home, about, health_check_view
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from users.workos_views import workos_callback, workos_login, workos_logout

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Home and general pages
    path('', home, name='home'),
    path('about/', about, name='about'),
    path('health/', health_check_view, name='health_check'),
    
    # WorkOS Authentication (add these BEFORE allauth)
    path('auth/workos/callback', workos_callback, name='workos-callback'),
    path('auth/workos/login', workos_login, name='workos-login'),
    path('auth/workos/logout', workos_logout, name='workos-logout'),
    
    # Traditional Authentication (allauth)
    path('accounts/', include('allauth.urls')),
    
    # API Authentication
    path('api/auth/', include('dj_rest_auth.urls')),
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),
    
    # App URLs
    path('users/', include('users.urls', namespace='users')),
    path('dictionary/', include('dictionary.urls', namespace='dictionary')),
    path('gamification/', include('gamification.urls')),
    path('api/nl/', include('nl_interact.urls')),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
