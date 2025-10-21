from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import TemplateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model
from django.db.models import Q, Count, Sum
from .serializers import UserSerializer, UserRegistrationSerializer, UserProfileSerializer
from .forms import UserProfileForm, UserRegistrationForm
from dictionary.models import KoloquaEntry, EntryVerification
from dictionary.serializers import KoloquaEntrySerializer
from gamification.models import UserBadge

# Import JWT token properly
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

# Template Views
class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'account/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the user to display (could be current user or another user)
        username = self.kwargs.get('username')
        if username:
            profile_user = get_object_or_404(User, username=username)
        else:
            profile_user = self.request.user
        
        context['profile_user'] = profile_user
        
        # Get user's badges
        context['badges'] = UserBadge.objects.filter(user=profile_user).select_related('badge')
        
        # Get recent contributions
        context['recent_contributions'] = KoloquaEntry.objects.filter(
            contributor=profile_user
        ).order_by('-created_at')[:5]
        
        # Calculate statistics
        contributions = KoloquaEntry.objects.filter(contributor=profile_user)
        context['total_words'] = contributions.count()
        context['verified_words'] = contributions.filter(status='verified').count()
        context['pending_words'] = contributions.filter(status='pending').count()
        
        return context


class EditProfileView(LoginRequiredMixin, UpdateView):
    template_name = 'account/edit_profile.html'
    model = User
    form_class = UserProfileForm  # Define this form
    success_url = reverse_lazy('users:me-profile')
    
    def get_object(self):
        return self.request.user
    
    def form_valid(self, form):
        messages.success(self.request, 'Your profile has been updated successfully!')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class UserContributionsTemplateView(LoginRequiredMixin, TemplateView):
    template_name = 'account/user_contributions.html'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get contributions with pagination
        contributions = KoloquaEntry.objects.filter(
            contributor=self.request.user
        ).order_by('-created_at')
        
        # Add filtering
        status_filter = self.request.GET.get('status')
        if status_filter in ['verified', 'pending', 'rejected']:
            contributions = contributions.filter(status=status_filter)
        
        context['contributions'] = contributions
        context['total_count'] = contributions.count()
        context['verified_count'] = contributions.filter(status='verified').count()
        context['pending_count'] = contributions.filter(status='pending').count()
        context['rejected_count'] = contributions.filter(status='rejected').count()
        context['current_filter'] = status_filter
        
        return context


# API Views
class UserRegistrationView(generics.CreateAPIView):
    """Register a new user"""
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'message': 'Registration successful!'
        }, status=status.HTTP_201_CREATED)


class UserProfileView(generics.RetrieveAPIView):
    """View user profile"""
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        # Allow viewing by ID or username
        lookup = self.kwargs.get('pk')
        if lookup:
            if lookup.isdigit():
                return get_object_or_404(User, pk=lookup)
            else:
                return get_object_or_404(User, username=lookup)
        return super().get_object()


class UserListView(generics.ListAPIView):
    """List all users (for leaderboard, etc.)"""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = User.objects.filter(is_active=True)
        
        # Filter by level
        level = self.request.query_params.get('level')
        if level:
            queryset = queryset.filter(level=level)
        
        # Filter by verification status
        verified_only = self.request.query_params.get('verified_only')
        if verified_only and verified_only.lower() == 'true':
            queryset = queryset.filter(is_verified_contributor=True)
        
        # Search functionality
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        
        # Order by points by default, but allow other orderings
        ordering = self.request.query_params.get('ordering', '-points')
        if ordering in ['points', '-points', 'contributions_count', '-contributions_count', 'username', '-username']:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-points')
        
        return queryset


class CurrentUserView(generics.RetrieveAPIView):
    """Get current user's profile"""
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        return self.request.user


class UpdateProfileView(generics.UpdateAPIView):
    """Update current user's profile"""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['put', 'patch']
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response({
            'user': serializer.data,
            'message': 'Profile updated successfully!'
        })


class UserContributionsView(generics.ListAPIView):
    """View user's contributions with detailed filtering"""
    serializer_class = KoloquaEntrySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = KoloquaEntry.objects.filter(contributor=user)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter in ['verified', 'pending', 'rejected']:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        # Search in contributions
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(koloqua_text__icontains=search) |
                Q(english_translation__icontains=search)
            )
        
        return queryset.order_by('-created_at')


class LeaderboardView(LoginRequiredMixin, TemplateView):
    """Template view for leaderboard"""
    template_name = 'account/leaderboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get top contributors and annotate with their contribution count
        context['top_contributors'] = User.objects.annotate(
            num_contributions=Count('contributions')
        ).filter(
            is_active=True,
            num_contributions__gt=0
        ).order_by('-points')[:10]
        
        # Get current user's rank if logged in
        if self.request.user.is_authenticated:
            user_rank = User.objects.filter(
                points__gt=self.request.user.points
            ).count() + 1
            context['user_rank'] = user_rank
        
        # Statistics
        context['total_contributors'] = User.objects.filter(
            contributions_count__gt=0
        ).count()
        context['total_contributions'] = KoloquaEntry.objects.count()
        context['verified_contributions'] = KoloquaEntry.objects.filter(
            status='verified'
        ).count()
        
        return context