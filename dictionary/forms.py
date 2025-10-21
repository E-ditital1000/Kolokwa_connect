from django import forms
from django.urls import reverse
from .models import KoloquaEntry, WordCategory, EntryVerification

class KoloquaEntryForm(forms.ModelForm):
    """Form for submitting new Koloqua entries"""
    
    categories = forms.ModelMultipleChoiceField(
        queryset=WordCategory.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )
    
    tags = forms.CharField(
        required=False,
        help_text="Enter tags separated by commas",
        widget=forms.TextInput(attrs={'placeholder': 'e.g., slang, informal, greeting'})
    )
    
    class Meta:
        model = KoloquaEntry
        fields = [
            'koloqua_text',
            'english_translation',
            'literal_translation',
            'entry_type',
            'context_explanation',
            'example_sentence_koloqua',
            'example_sentence_english',
            'cultural_notes',
            'categories',
            'pronunciation_guide',
            'region_specific',
            'audio_pronunciation',
        ]
        widgets = {
            'koloqua_text': forms.TextInput(attrs={
                'class': 'form-control p-4',
                'placeholder': 'Enter Koloqua word or phrase'
            }),
            'english_translation': forms.TextInput(attrs={
                'class': 'form-control p-4',
                'placeholder': 'English translation'
            }),
            'literal_translation': forms.TextInput(attrs={
                'class': 'form-control p-4',
                'placeholder': 'Literal word-for-word translation (optional)'
            }),
            'entry_type': forms.Select(attrs={'class': 'custom-select p-4'}),
            'context_explanation': forms.Textarea(attrs={
                'class': 'form-control p-4',
                'rows': 3,
                'placeholder': 'Explain when and how this is used'
            }),
            'example_sentence_koloqua': forms.TextInput(attrs={
                'class': 'form-control p-4',
                'placeholder': 'Example sentence in Koloqua'
            }),
            'example_sentence_english': forms.TextInput(attrs={
                'class': 'form-control p-4',
                'placeholder': 'Translation of example sentence'
            }),
            'cultural_notes': forms.Textarea(attrs={
                'class': 'form-control p-4',
                'rows': 3,
                'placeholder': 'Any cultural context or significance (optional)'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'form-control p-4',
                'placeholder': 'Tags (comma-separated, Optional)'
            }),
            'pronunciation_guide': forms.TextInput(attrs={
                'class': 'form-control p-4',
                'placeholder': 'How to pronounce (optional)'
            }),
            'audio_pronunciation': forms.URLInput(attrs={
                'class': 'form-control p-4',
                'placeholder': 'Audio URL (Optional)'
            }),
            'region_specific': forms.TextInput(attrs={
                'class': 'form-control p-4',
                'placeholder': 'Specific region where used (optional)'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
    
    def clean_koloqua_text(self):
        """Prevent duplicate word entries in the system"""
        koloqua_text = self.cleaned_data.get('koloqua_text')
        
        if koloqua_text and not self.instance.pk:  # Only check for new entries (not edits)
            # Check if this word already exists (case-insensitive)
            existing_entry = KoloquaEntry.objects.filter(
                koloqua_text__iexact=koloqua_text
            ).exclude(
                status='rejected'  # Allow re-submission if previous was rejected
            ).first()
            
            if existing_entry:
                # Build a helpful error message based on the entry status
                if existing_entry.status == 'verified':
                    raise forms.ValidationError(
                        f'The word "{koloqua_text}" already exists in the dictionary. '
                        f'Please search for it to view the existing entry.'
                    )
                elif existing_entry.status == 'pending':
                    if self.user and existing_entry.contributor == self.user:
                        raise forms.ValidationError(
                            f'You have already submitted "{koloqua_text}" and it is currently pending review. '
                            f'Please wait for verification before submitting again.'
                        )
                    else:
                        raise forms.ValidationError(
                            f'The word "{koloqua_text}" has already been submitted and is pending review. '
                            f'Please check back later.'
                        )
        
        return koloqua_text
    
    def clean_tags(self):
        """Convert comma-separated tags to list"""
        tags_str = self.cleaned_data.get('tags', '')
        if tags_str:
            return [tag.strip() for tag in tags_str.split(',') if tag.strip()]
        return []
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
            self.save_m2m()
            if self.cleaned_data.get('tags'):
                instance.tags = self.cleaned_data['tags']
                instance.save(update_fields=['tags'])
        return instance


class EntryVerificationForm(forms.ModelForm):
    """Form for verifying entries"""
    
    class Meta:
        model = EntryVerification
        fields = ['verification_type', 'comments']
        widgets = {
            'verification_type': forms.RadioSelect(),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional comments or suggestions (optional)'
            })
        }


class SearchForm(forms.Form):
    """Form for searching translations"""
    
    LANGUAGE_CHOICES = [
        ('auto', 'Auto-detect'),
        ('en', 'English to Kolokwa'),
        ('ko', 'Koloqua to English'),
    ]
    
    query = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter word or phrase to translate...'
        })
    )
    
    language = forms.ChoiceField(
        choices=LANGUAGE_CHOICES,
        initial='auto',
        widget=forms.Select(attrs={'class': 'form-control'})
    )