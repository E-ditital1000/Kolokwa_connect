from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    KoloquaEntryListView,
    KoloquaEntryDetailView,
    KoloquaEntryCreateView,
    KoloquaEntryUpdateView,
    KoloquaEntryDeleteView,
    EntryVoteView,
    EntryVerifyView,
    PendingEntriesListView,
    KoloquaEntryViewSet,
    WordCategoryViewSet
)

app_name = 'dictionary'

# Create router for API endpoints
router = DefaultRouter()
router.register(r'api/entries', KoloquaEntryViewSet, basename='api-entry')
router.register(r'api/categories', WordCategoryViewSet, basename='api-category')

urlpatterns = [
    # HTML Template Views
    path('', KoloquaEntryListView.as_view(), name='entry-list'),
    path('review/', PendingEntriesListView.as_view(), name='entry-review-list'),
    path('entry/<int:pk>/', KoloquaEntryDetailView.as_view(), name='entry-detail'),
    path('contribute/', KoloquaEntryCreateView.as_view(), name='entry-contribute'),
    path('entry/<int:pk>/edit/', KoloquaEntryUpdateView.as_view(), name='entry-update'),
    path('entry/<int:pk>/delete/', KoloquaEntryDeleteView.as_view(), name='entry-delete'),
    path('entry/<int:pk>/vote/', EntryVoteView.as_view(), name='entry-vote'),
    path('entry/<int:pk>/verify/', EntryVerifyView.as_view(), name='entry-verify'),
    
    # Include API routes
    path('', include(router.urls)),
]