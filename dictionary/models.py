import os
from django.db import models
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.postgres.fields import ArrayField



class WordCategory(models.Model):
    """Categories for organizing words/phrases"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'word_categories'
        verbose_name_plural = 'Word Categories'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class KoloquaEntry(models.Model):
    """Main model for Koloqua words and phrases"""
    
    ENTRY_TYPES = [
        ('word', 'Word'),
        ('phrase', 'Phrase'),
        ('idiom', 'Idiom'),
        ('proverb', 'Proverb'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('needs_revision', 'Needs Revision'),
    ]
    embedding = ArrayField(
        models.FloatField(),
        size=1536,
        null=True,
        blank=True,
        help_text="Vector embedding for semantic search"
    )
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    # Core fields
    koloqua_text = models.CharField(max_length=255, db_index=True)
    english_translation = models.TextField()
    literal_translation = models.TextField(blank=True, help_text="Word-for-word translation if different from meaning")
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='word')
    
    # Context and usage
    context_explanation = models.TextField(help_text="Explain when and how this is used")
    example_sentence_koloqua = models.TextField()
    example_sentence_english = models.TextField()
    cultural_notes = models.TextField(blank=True, help_text="Any cultural context or significance")
    
    # Classification
    categories = models.ManyToManyField(WordCategory, related_name='entries', blank=True)
    tags = models.JSONField(default=list, blank=True, help_text="List of tags for easier searching")
    
    # Metadata
    contributor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='contributions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    verification_count = models.IntegerField(default=0)
    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Additional fields
    pronunciation_guide = models.CharField(max_length=255, blank=True)
    audio_pronunciation = models.FileField(upload_to='pronunciations/', blank=True, null=True)
    region_specific = models.CharField(max_length=100, blank=True, help_text="Specific region where this is used")
    
    class Meta:
        db_table = 'koloqua_entries'
        verbose_name = 'Koloqua Entry'
        verbose_name_plural = 'Koloqua Entries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['koloqua_text', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
        unique_together = [['koloqua_text', 'contributor']]


    
    def __str__(self):
        return f"{self.koloqua_text} - {self.english_translation[:50]}"
    
    def calculate_score(self):
        """Calculate entry score for ranking"""
        return self.upvotes - self.downvotes + (self.verification_count * 2)
    
    def verify(self):
        """Mark entry as verified after enough community validation"""
        if self.verification_count >= 5:
            self.status = 'verified'
            self.verified_at = timezone.now()
            self.save(update_fields=['status', 'verified_at'])
            return True
        return False


class EntryVerification(models.Model):
    """Track user verifications of entries"""
    
    VERIFICATION_TYPES = [
        ('accurate', 'Accurate'),
        ('needs_revision', 'Needs Revision'),
        ('incorrect', 'Incorrect'),
    ]
    
    entry = models.ForeignKey(KoloquaEntry, on_delete=models.CASCADE, related_name='verifications')
    verifier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='verifications')
    verification_type = models.CharField(max_length=20, choices=VERIFICATION_TYPES)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'entry_verifications'
        unique_together = [['entry', 'verifier']]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.verifier} verified {self.entry}"


class EntryVote(models.Model):
    """Track upvotes and downvotes for entries"""
    
    VOTE_TYPES = [
        (1, 'Upvote'),
        (-1, 'Downvote'),
    ]
    
    entry = models.ForeignKey(KoloquaEntry, on_delete=models.CASCADE, related_name='votes')
    voter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='votes')
    vote_type = models.SmallIntegerField(choices=VOTE_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'entry_votes'
        unique_together = [['entry', 'voter']]
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_vote = None
        
        if not is_new:
            old_vote = EntryVote.objects.get(pk=self.pk).vote_type
        
        super().save(*args, **kwargs)
        
        # Update entry vote counts
        if is_new:
            if self.vote_type == 1:
                self.entry.upvotes += 1
            else:
                self.entry.downvotes += 1
        elif old_vote != self.vote_type:
            if old_vote == 1:
                self.entry.upvotes -= 1
                self.entry.downvotes += 1
            else:
                self.entry.downvotes -= 1
                self.entry.upvotes += 1
        
        self.entry.save(update_fields=['upvotes', 'downvotes'])


class TranslationHistory(models.Model):
    """Track translation searches for analytics and AI training"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    search_text = models.CharField(max_length=255)
    search_language = models.CharField(max_length=10, choices=[('en', 'English'), ('ko', 'Koloqua')])
    result_entry = models.ForeignKey(KoloquaEntry, on_delete=models.SET_NULL, null=True, blank=True)
    found = models.BooleanField(default=False)
    searched_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'translation_history'
        verbose_name_plural = 'Translation Histories'
        ordering = ['-searched_at']




from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

@receiver(post_save, sender=KoloquaEntry)
def generate_embedding_on_save(sender, instance, created, **kwargs):
    """Automatically generate embedding when entry is created or updated."""
    
    # Skip if OpenAI API key is not available (e.g., during fixtures loading)
    if not os.getenv('OPENAI_API_KEY'):
        return
    
    try:
        from nl_interact.utils import generate_entry_embedding
    except Exception as e:
        # Silently skip if import fails (e.g., during migration/restore)
        return
    
    # Only generate if content changed or no embedding exists
    should_generate = (
        not instance.embedding or
        created or
        instance.embedding_updated_at is None or
        instance.updated_at > instance.embedding_updated_at
    )
    
    if should_generate and instance.status == 'verified':
        # Run async in production (use Celery or similar)
        try:
            generate_entry_embedding(instance)
        except Exception as e:
            # Log error but don't fail the save operation
            print(f"Warning: Could not generate embedding: {e}")