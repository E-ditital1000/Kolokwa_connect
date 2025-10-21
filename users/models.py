from django.db import models

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    """Custom User model for Koloqua Connect"""
    
    CONTRIBUTOR_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
        ('chief', 'Chief Linguist'),
    ]
    
    email = models.EmailField(_('email address'), unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    
    # Gamification fields
    points = models.IntegerField(default=0)
    level = models.CharField(max_length=20, choices=CONTRIBUTOR_LEVELS, default='beginner')
    contributions_count = models.IntegerField(default=0)
    verifications_count = models.IntegerField(default=0)
    
    # Authentication fields
    workos_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="WorkOS user ID for SSO authentication"
    )
    
    # Metadata
    is_verified_contributor = models.BooleanField(default=False)
    joined_date = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    class Meta:
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['workos_id']),
            models.Index(fields=['points']),
        ]
        
    def __str__(self):
        return self.email
    
    def update_level(self):
        """Update user level based on points"""
        if self.points >= 1000:
            self.level = 'chief'
        elif self.points >= 500:
            self.level = 'expert'
        elif self.points >= 100:
            self.level = 'intermediate'
        else:
            self.level = 'beginner'
        self.save(update_fields=['level'])
    
    def add_points(self, points, reason=''):
        """Add points and update level"""
        self.points += points
        self.save(update_fields=['points'])
        self.update_level()
        
        # Log the points change (optional)
        if reason:
            from django.utils import timezone
            # You can create a PointsHistory model to track this
            pass
    
    def is_workos_user(self):
        """Check if user authenticated via WorkOS"""
        return bool(self.workos_id)