# Kolokwa_connect/dictionary/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from .models import KoloquaEntry, WordCategory, TranslationHistory, EntryVote, EntryVerification
from .serializers import (
    KoloquaEntrySerializer,
    KoloquaEntryDetailSerializer,
    WordCategorySerializer,
    KoloquaEntryCreateSerializer,
    EntryVoteSerializer,
    EntryVerificationSerializer
)
from django.db.models import Q
from gamification.utils import handle_entry_verification, handle_entry_rejection, handle_new_contribution, award_points
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import View, ListView, DetailView
from django.views.generic.edit import UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .forms import KoloquaEntryForm, EntryVerificationForm
import json
from django.db.utils import IntegrityError


class KoloquaEntryListView(ListView):
    """HTML View for listing dictionary entries"""
    model = KoloquaEntry
    template_name = 'dictionary/entry_list.html'
    context_object_name = 'entries'
    paginate_by = 20

    def get_queryset(self):
        queryset = KoloquaEntry.objects.filter(status='verified').select_related('contributor').prefetch_related('categories')
        
        query = self.request.GET.get('q')
        entry_type = self.request.GET.get('type')
        category = self.request.GET.get('category')
        sort = self.request.GET.get('sort')

        if query:
            queryset = queryset.filter(
                Q(koloqua_text__icontains=query) |
                Q(english_translation__icontains=query)
            ).distinct()
            
            # Log the search for analytics
            if self.request.user.is_authenticated:
                TranslationHistory.objects.create(
                    user=self.request.user,
                    search_text=query,
                    search_language='auto',
                    found=queryset.exists()
                )

        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)

        if category:
            queryset = queryset.filter(categories__name=category)
            
        # Sorting
        if sort == 'alphabetical':
            queryset = queryset.order_by('koloqua_text')
        elif sort == 'popular':
            queryset = queryset.extra(
                select={'score': 'upvotes - downvotes + (verification_count * 2)'}
            ).order_by('-score')
        else:
            queryset = queryset.order_by('-created_at')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['category'] = self.request.GET.get('category', '')
        context['categories'] = WordCategory.objects.all()
        context['current_type'] = self.request.GET.get('type', '')
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class PendingEntriesListView(LoginRequiredMixin, ListView):
    """HTML View for listing pending dictionary entries for review"""
    model = KoloquaEntry
    template_name = 'dictionary/pending_list.html'
    context_object_name = 'entries'
    paginate_by = 20

    def get_queryset(self):
        queryset = KoloquaEntry.objects.filter(status='pending').select_related('contributor').prefetch_related('categories')
        query = self.request.GET.get('q')
        entry_type = self.request.GET.get('type')
        category = self.request.GET.get('category')
        sort = self.request.GET.get('sort')

        if query:
            queryset = queryset.filter(
                Q(koloqua_text__icontains=query) |
                Q(english_translation__icontains=query)
            ).distinct()
        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)
        if category:
            queryset = queryset.filter(categories__name=category)
        if sort == 'oldest':
            queryset = queryset.order_by('created_at')
        else:
            queryset = queryset.order_by('-created_at')
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['category'] = self.request.GET.get('category', '')
        context['categories'] = WordCategory.objects.all()
        context['current_type'] = self.request.GET.get('type', '')
        context['entry_types'] = KoloquaEntry.ENTRY_TYPES
        context['current_sort'] = self.request.GET.get('sort', '')
        context['pending_count'] = KoloquaEntry.objects.filter(status='pending').count()
        return context


class KoloquaEntryDetailView(DetailView):
    """HTML View for displaying entry details"""
    model = KoloquaEntry
    template_name = 'dictionary/entry_detail.html'
    context_object_name = 'entry'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entry = self.object
        
        # Get related entries (same category or similar tags)
        related_entries = KoloquaEntry.objects.filter(
            status='verified'
        ).exclude(id=entry.id)
        
        if entry.categories.exists():
            related_entries = related_entries.filter(
                categories__in=entry.categories.all()
            ).distinct()[:5]
        else:
            related_entries = related_entries[:5]
        
        context['related_entries'] = related_entries
        
        # Get verifications
        context['verifications'] = entry.verifications.select_related('verifier')[:10]
        
        # Check if user has voted
        if self.request.user.is_authenticated:
            try:
                user_vote = EntryVote.objects.get(entry=entry, voter=self.request.user)
                context['user_vote'] = user_vote.vote_type
            except EntryVote.DoesNotExist:
                context['user_vote'] = None
        
        return context

class KoloquaEntryCreateView(LoginRequiredMixin, View):
    """HTML View for creating new entries with duplicate prevention"""
    template_name = 'dictionary/entry_form.html'
    form_class = KoloquaEntryForm

    def get(self, request, *args, **kwargs):
        form = self.form_class(user=request.user)
        categories = WordCategory.objects.all()
        return render(request, self.template_name, {
            'form': form,
            'categories': categories,
            'is_edit': False
        })

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST, request.FILES, user=request.user)
        
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                entry = form.save(commit=False)
                entry.contributor = request.user
                entry.save()
                form.save_m2m()
                
                # Award points for new contribution
                try:
                    from .utils import handle_new_contribution
                    handle_new_contribution(entry)
                except ImportError:
                    pass  # Function not available
                
                # Return JSON for AJAX, redirect for regular form
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': 'Your contribution has been submitted for review!',
                        'entry_id': entry.pk,
                        'redirect_url': reverse_lazy('dictionary:entry-detail', kwargs={'pk': entry.pk})
                    })
                else:
                    messages.success(request, 'Your contribution has been submitted for review!')
                    return redirect('dictionary:entry-detail', pk=entry.pk)
                    
            except IntegrityError as e:
                error_msg = 'This word/phrase has already been submitted.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'error': error_msg
                    }, status=400)
                else:
                    messages.error(request, error_msg)
        else:
            # Handle form validation errors
            if is_ajax:
                # Extract errors for JSON response
                errors = {}
                for field, error_list in form.errors.items():
                    errors[field] = [str(e) for e in error_list]
                
                # Get specific error message for display
                error_message = 'Please correct the errors in the form.'
                if 'koloqua_text' in errors:
                    error_message = errors['koloqua_text'][0]
                
                return JsonResponse({
                    'success': False,
                    'error': error_message,
                    'errors': errors
                }, status=400)
            else:
                # Show error messages for regular form submission
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')
        
        # Re-render form with errors
        categories = WordCategory.objects.all()
        return render(request, self.template_name, {
            'form': form,
            'categories': categories,
            'is_edit': False
        })


class KoloquaEntryUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """HTML View for updating entries"""
    model = KoloquaEntry
    form_class = KoloquaEntryForm
    template_name = 'dictionary/entry_form.html'

    def test_func(self):
        entry = self.get_object()
        return self.request.user == entry.contributor or self.request.user.is_staff

    def get_form_kwargs(self):
        """Pass user to the form"""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        messages.success(self.request, 'Entry updated successfully!')
        return reverse_lazy('dictionary:entry-detail', kwargs={'pk': self.object.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = WordCategory.objects.all()
        context['is_edit'] = True
        return context


class KoloquaEntryDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """HTML View for deleting entries"""
    model = KoloquaEntry
    template_name = 'dictionary/entry_confirm_delete.html'
    success_url = reverse_lazy('users:user-contributions')

    def test_func(self):
        entry = self.get_object()
        return self.request.user == entry.contributor or self.request.user.is_staff

class EntryVoteView(LoginRequiredMixin, View):
    """Handle voting on entries (AJAX/JSON)"""
    
    def post(self, request, pk):
        entry = get_object_or_404(KoloquaEntry, pk=pk)
        
        # Handle both JSON and form data
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                vote_type = data.get('vote_type')
            except:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
        else:
            vote_type = request.POST.get('vote_type')
        
        if vote_type not in ['1', '-1', 1, -1]:
            return JsonResponse({'error': 'Invalid vote type'}, status=400)
        
        vote_type = int(vote_type)
        
        # Try to get existing vote
        try:
            vote = EntryVote.objects.get(entry=entry, voter=request.user)
            vote_existed = True
            old_vote_type = vote.vote_type
            
            # If clicking the same vote, remove it (toggle off)
            if vote.vote_type == vote_type:
                vote.delete()
                message = 'Vote removed'
                user_vote = None
                
                # Adjust contributor points
                if entry.contributor != request.user:
                    award_points(
                        entry.contributor, 
                        -vote_type, 
                        'vote_removed', 
                        f'Vote removed for your entry: {entry.koloqua_text}'
                    )
            else:
                # Change vote to the opposite
                vote.vote_type = vote_type
                vote.save()
                message = 'Vote changed'
                user_vote = vote_type
                
                # Adjust contributor points (net change is 2x the new vote)
                if entry.contributor != request.user:
                    point_change = vote_type - old_vote_type
                    award_points(
                        entry.contributor, 
                        point_change, 
                        'vote_changed', 
                        f'Vote changed for your entry: {entry.koloqua_text}'
                    )
        
        except EntryVote.DoesNotExist:
            # Create new vote
            vote = EntryVote.objects.create(
                entry=entry,
                voter=request.user,
                vote_type=vote_type
            )
            vote_existed = False
            message = 'Vote recorded'
            user_vote = vote_type
            
            # Award points to the voter for participating
            award_points(
                request.user, 
                1, 
                'vote', 
                f'Voted on entry: {entry.koloqua_text}'
            )
            
            # Award points to the contributor for the vote
            if entry.contributor != request.user:
                award_points(
                    entry.contributor, 
                    vote_type, 
                    'vote_received', 
                    f'Your entry received a vote: {entry.koloqua_text}'
                )
        
        # Refresh entry to get updated counts
        entry.refresh_from_db()
        
        return JsonResponse({
            'status': 'success',
            'message': message,
            'upvotes': entry.upvotes,
            'downvotes': entry.downvotes,
            'user_vote': user_vote
        })

class EntryVerifyView(LoginRequiredMixin, View):
    """Handle verification of entries - FIXED VERSION"""
    
    def post(self, request, pk):
        entry = get_object_or_404(KoloquaEntry, pk=pk)
        
        if request.user == entry.contributor:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Cannot verify your own entry'}, status=400)
            messages.error(request, 'You cannot verify your own entry')
            return redirect('dictionary:entry-detail', pk=pk)
        
        verification_type = request.POST.get('verification_type')
        comments = request.POST.get('comments', '')
        
        if verification_type not in ['accurate', 'needs_revision', 'incorrect']:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Invalid verification type'}, status=400)
            messages.error(request, 'Invalid verification type')
            return redirect('dictionary:entry-detail', pk=pk)
        
        # Create or update verification
        verification, created = EntryVerification.objects.update_or_create(
            entry=entry,
            verifier=request.user,
            defaults={
                'verification_type': verification_type,
                'comments': comments
            }
        )
        
        # Update verification count
        entry.verification_count = entry.verifications.filter(
            verification_type='accurate'
        ).count()
        
        # Handle verification points and status changes
        if verification_type == 'accurate':
            # Check if entry should be auto-verified
            if entry.verification_count >= 3 and entry.status == 'pending':  # Lowered threshold for testing
                entry.status = 'verified'
                entry.save()
                # Use the proper gamification function
                handle_entry_verification(entry, request.user)
                status_message = 'Entry has been verified!'
            else:
                entry.save()
                # Award points for verification activity
                award_points(request.user, 3, 'verification', f'Verified entry: {entry.koloqua_text}')
                # Award points to contributor for positive verification
                award_points(entry.contributor, 2, 'verification_received', f'Your entry received verification: {entry.koloqua_text}')
                status_message = 'Thank you for your verification!'
        
        elif verification_type == 'incorrect':
            # Handle rejection
            if entry.verifications.filter(verification_type='incorrect').count() >= 2:
                entry.status = 'rejected'
                entry.save()
                handle_entry_rejection(entry, request.user)
                status_message = 'Entry has been rejected due to multiple negative verifications.'
            else:
                entry.save()
                # Award points for verification activity
                award_points(request.user, 2, 'verification', f'Reviewed entry: {entry.koloqua_text}')
                status_message = 'Thank you for your verification!'
        
        else:  # needs_revision
            entry.save()
            award_points(request.user, 2, 'verification', f'Reviewed entry: {entry.koloqua_text}')
            status_message = 'Thank you for your verification!'
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'message': status_message,
                'verification_count': entry.verification_count,
                'entry_status': entry.status
            })
        
        messages.success(request, status_message)
        return redirect('dictionary:entry-detail', pk=pk)


# API ViewSets
class WordCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API ViewSet for WordCategories"""
    queryset = WordCategory.objects.all()
    serializer_class = WordCategorySerializer
    permission_classes = [permissions.AllowAny]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]


class KoloquaEntryViewSet(viewsets.ModelViewSet):
    """API ViewSet for Koloqua dictionary entries"""
    queryset = KoloquaEntry.objects.filter(status='verified')
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return KoloquaEntryDetailSerializer
        elif self.action == 'create':
            return KoloquaEntryCreateSerializer
        return KoloquaEntrySerializer
    
    def perform_create(self, serializer):
        entry = serializer.save(contributor=self.request.user)
        handle_new_contribution(entry)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def vote(self, request, pk=None):
        """API endpoint for voting"""
        entry = self.get_object()
        vote_type = request.data.get('vote_type')
        
        if vote_type not in [1, -1, '1', '-1']:
            return Response({'error': 'Invalid vote type'}, status=status.HTTP_400_BAD_REQUEST)
        
        vote_type = int(vote_type)
        
        vote, created = EntryVote.objects.get_or_create(
            entry=entry,
            voter=request.user,
            defaults={'vote_type': vote_type}
        )
        
        if not created:
            if vote.vote_type == vote_type:
                vote.delete()
                # Adjust contributor points
                if entry.contributor != request.user:
                    award_points(entry.contributor, -vote_type, 'vote_removed', f'Vote removed for your entry: {entry.koloqua_text}')
                entry.refresh_from_db()
                return Response({
                    'status': 'vote removed',
                    'upvotes': entry.upvotes,
                    'downvotes': entry.downvotes
                }, status=status.HTTP_200_OK)
            else:
                old_vote = vote.vote_type
                vote.vote_type = vote_type
                vote.save()
                # Adjust contributor points
                if entry.contributor != request.user:
                    award_points(entry.contributor, vote_type - old_vote, 'vote_changed', f'Vote changed for your entry: {entry.koloqua_text}')
        else:
            # Award points to voter and contributor
            award_points(request.user, 1, 'vote', f'Voted on entry: {entry.koloqua_text}')
            if entry.contributor != request.user:
                award_points(entry.contributor, vote_type, 'vote_received', f'Your entry received a vote: {entry.koloqua_text}')
        
        entry.refresh_from_db()
        return Response({
            'status': 'vote recorded' if created else 'vote updated',
            'upvotes': entry.upvotes,
            'downvotes': entry.downvotes,
            'user_vote': vote_type
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """API endpoint for searching"""
        query = request.query_params.get('q', '')
        language = request.query_params.get('lang', 'auto')
        
        if not query:
            return Response({'results': []}, status=status.HTTP_200_OK)
        
        # Determine search field based on language
        if language == 'en':
            results = self.queryset.filter(
                english_translation__icontains=query
            ).distinct()[:20]
        elif language == 'ko':
            results = self.queryset.filter(
                koloqua_text__icontains=query
            ).distinct()[:20]
        else:  # auto-detect
            results = self.queryset.filter(
                Q(koloqua_text__icontains=query) |
                Q(english_translation__icontains=query)
            ).distinct()[:20]
        
        # Log search
        if request.user.is_authenticated:
            TranslationHistory.objects.create(
                user=request.user,
                search_text=query,
                search_language=language,
                found=results.exists()
            )
        
        serializer = self.get_serializer(results, many=True)
        return Response({
            'query': query,
            'language': language,
            'count': results.count(),
            'results': serializer.data
        })

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def verify(self, request, pk=None):
        """API endpoint for verification - FIXED VERSION"""
        entry = self.get_object()
        
        if request.user == entry.contributor:
            return Response({'error': 'Cannot verify your own entry'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = EntryVerificationSerializer(data=request.data)
        if serializer.is_valid():
            verification_type = serializer.validated_data.get('verification_type')
            
            verification, created = EntryVerification.objects.update_or_create(
                entry=entry,
                verifier=request.user,
                defaults=serializer.validated_data
            )
            
            # Update verification count
            entry.verification_count = entry.verifications.filter(
                verification_type='accurate'
            ).count()
            
            # Handle verification points and status changes
            if verification_type == 'accurate':
                # Check if entry should be auto-verified
                if entry.verification_count >= 3 and entry.status == 'pending':
                    entry.status = 'verified'
                    entry.save()
                    handle_entry_verification(entry, request.user)
                    message = 'Entry has been verified!'
                else:
                    entry.save()
                    # Award points for verification activity
                    award_points(request.user, 3, 'verification', f'Verified entry: {entry.koloqua_text}')
                    # Award points to contributor for positive verification
                    award_points(entry.contributor, 2, 'verification_received', f'Your entry received verification: {entry.koloqua_text}')
                    message = 'Thank you for your verification!'
            
            elif verification_type == 'incorrect':
                # Handle rejection
                if entry.verifications.filter(verification_type='incorrect').count() >= 2:
                    entry.status = 'rejected'
                    entry.save()
                    handle_entry_rejection(entry, request.user)
                    message = 'Entry has been rejected.'
                else:
                    entry.save()
                    award_points(request.user, 2, 'verification', f'Reviewed entry: {entry.koloqua_text}')
                    message = 'Thank you for your verification!'
            
            else:  # needs_revision
                entry.save()
                award_points(request.user, 2, 'verification', f'Reviewed entry: {entry.koloqua_text}')
                message = 'Thank you for your verification!'

            return Response({
                'status': 'success',
                'message': message,
                'verification_count': entry.verification_count,
                'entry_status': entry.status
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)