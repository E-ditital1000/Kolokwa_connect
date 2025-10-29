# users/models.py - Complete Updated User Model with SMS Features

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class User(AbstractUser):
    """Custom User model for Koloqua Connect with SMS notification support"""
    
    CONTRIBUTOR_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
        ('chief', 'Chief Linguist'),
    ]
    
    email = models.EmailField(_('email address'), unique=True)
    phone_number = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        help_text="Phone number for SMS notifications (format: +231770123456)"
    )
    bio = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    
    # Gamification fields
    points = models.IntegerField(default=0)
    level = models.CharField(max_length=20, choices=CONTRIBUTOR_LEVELS, default='beginner')
    contributions_count = models.IntegerField(default=0)
    verifications_count = models.IntegerField(default=0)
    
    # SMS Notification Preferences
    sms_entry_verified = models.BooleanField(
        default=True, 
        verbose_name="Entry verified notifications",
        help_text="Receive SMS when someone verifies your entry"
    )
    sms_badge_earned = models.BooleanField(
        default=True, 
        verbose_name="Badge earned notifications",
        help_text="Receive SMS when you earn a new badge"
    )
    sms_level_up = models.BooleanField(
        default=True, 
        verbose_name="Level up notifications",
        help_text="Receive SMS when you advance to a new level"
    )
    sms_leaderboard = models.BooleanField(
        default=False, 
        verbose_name="Leaderboard change notifications",
        help_text="Receive SMS when your leaderboard rank changes significantly"
    )
    sms_streak_milestone = models.BooleanField(
        default=True, 
        verbose_name="Streak milestone notifications",
        help_text="Receive SMS at streak milestones (3, 7, 14, 30+ days)"
    )
    sms_needs_revision = models.BooleanField(
        default=True, 
        verbose_name="Entry revision notifications",
        help_text="Receive SMS when your entry needs revision"
    )
    sms_daily_challenge = models.BooleanField(
        default=False, 
        verbose_name="Daily challenge notifications",
        help_text="Receive SMS about new daily challenges (opt-in)"
    )
    
    # Track previous rank for leaderboard notifications
    previous_rank = models.IntegerField(
        default=0, 
        help_text="Last known leaderboard rank for change detection"
    )
    
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
            models.Index(fields=['phone_number']),
        ]
        
    def __str__(self):
        return self.email
    
    def has_phone_number(self):
        """Check if user has a valid phone number for SMS"""
        return bool(self.phone_number and len(self.phone_number) > 5)
    
    def can_receive_sms(self, notification_type):
        """
        Check if user can receive SMS for specific notification type
        
        Args:
            notification_type (str): Type of notification
                - 'entry_verified'
                - 'badge_earned'
                - 'level_up'
                - 'leaderboard'
                - 'streak_milestone'
                - 'needs_revision'
                - 'daily_challenge'
        
        Returns:
            bool: True if user can receive SMS, False otherwise
        """
        if not self.has_phone_number():
            return False
        
        # Check if SMS notifications are globally enabled
        if not getattr(settings, 'SMS_NOTIFICATIONS_ENABLED', True):
            return False
        
        preference_map = {
            'entry_verified': self.sms_entry_verified,
            'badge_earned': self.sms_badge_earned,
            'level_up': self.sms_level_up,
            'leaderboard': self.sms_leaderboard,
            'streak_milestone': self.sms_streak_milestone,
            'needs_revision': self.sms_needs_revision,
            'daily_challenge': self.sms_daily_challenge,
        }
        
        return preference_map.get(notification_type, False)
    
    def update_level(self):
        """
        Update user level based on points and send SMS notification if level changes
        
        Returns:
            bool: True if level changed, False otherwise
        """
        old_level = self.level
        
        if self.points >= 1000:
            new_level = 'chief'
        elif self.points >= 500:
            new_level = 'expert'
        elif self.points >= 100:
            new_level = 'intermediate'
        else:
            new_level = 'beginner'
        
        if new_level != old_level:
            self.level = new_level
            self.save(update_fields=['level'])
            
            # Send SMS notification if enabled
            if self.can_receive_sms('level_up'):
                try:
                    from utils.sms_notifications import send_level_up_notification
                    send_level_up_notification(self, old_level, new_level)
                except ImportError:
                    pass  # SMS service not available
            
            return True
        
        return False
    
    def add_points(self, points, reason=''):
        """
        Add points to user, update level, and send notifications
        
        Args:
            points (int): Number of points to add (can be negative)
            reason (str): Reason for point change (for logging and notifications)
        """
        old_points = self.points
        self.points += points
        self.save(update_fields=['points'])
        
        # Update level (handles level-up notification internally)
        level_changed = self.update_level()
        
        # Send points notification for significant gains (5+ points)
        # Don't send if level-up notification was just sent
        if not level_changed and points >= 5 and self.can_receive_sms('entry_verified'):
            try:
                from utils.sms_notifications import send_points_notification
                send_points_notification(self, points, reason)
            except ImportError:
                pass  # SMS service not available
        
        # Log the points change (optional integration with PointTransaction model)
        if reason:
            try:
                from gamification.models import PointTransaction
                PointTransaction.objects.create(
                    user=self,
                    points=points,
                    transaction_type='manual',
                    description=reason
                )
            except ImportError:
                pass  # PointTransaction model not available
    
    def is_workos_user(self):
        """Check if user authenticated via WorkOS"""
        return bool(self.workos_id)
    
    def get_sms_preferences(self):
        """
        Get all SMS notification preferences as a dictionary
        
        Returns:
            dict: Dictionary of notification types and their enabled status
        """
        return {
            'entry_verified': self.sms_entry_verified,
            'badge_earned': self.sms_badge_earned,
            'level_up': self.sms_level_up,
            'leaderboard': self.sms_leaderboard,
            'streak_milestone': self.sms_streak_milestone,
            'needs_revision': self.sms_needs_revision,
            'daily_challenge': self.sms_daily_challenge,
        }
    
    def update_sms_preferences(self, preferences):
        """
        Update SMS notification preferences
        
        Args:
            preferences (dict): Dictionary of notification types to update
                Example: {'entry_verified': True, 'daily_challenge': False}
        """
        valid_preferences = [
            'entry_verified', 'badge_earned', 'level_up', 
            'leaderboard', 'streak_milestone', 'needs_revision', 
            'daily_challenge'
        ]
        
        fields_to_update = []
        
        for pref, value in preferences.items():
            if pref in valid_preferences:
                field_name = f'sms_{pref}'
                setattr(self, field_name, bool(value))
                fields_to_update.append(field_name)
        
        if fields_to_update:
            self.save(update_fields=fields_to_update)
    
    def enable_all_sms_notifications(self):
        """Enable all SMS notifications"""
        self.sms_entry_verified = True
        self.sms_badge_earned = True
        self.sms_level_up = True
        self.sms_leaderboard = True
        self.sms_streak_milestone = True
        self.sms_needs_revision = True
        self.sms_daily_challenge = True
        self.save(update_fields=[
            'sms_entry_verified', 'sms_badge_earned', 'sms_level_up',
            'sms_leaderboard', 'sms_streak_milestone', 'sms_needs_revision',
            'sms_daily_challenge'
        ])
    
    def disable_all_sms_notifications(self):
        """Disable all SMS notifications"""
        self.sms_entry_verified = False
        self.sms_badge_earned = False
        self.sms_level_up = False
        self.sms_leaderboard = False
        self.sms_streak_milestone = False
        self.sms_needs_revision = False
        self.sms_daily_challenge = False
        self.save(update_fields=[
            'sms_entry_verified', 'sms_badge_earned', 'sms_level_up',
            'sms_leaderboard', 'sms_streak_milestone', 'sms_needs_revision',
            'sms_daily_challenge'
        ])
    
    def format_phone_for_display(self):
        """
        Format phone number for display
        
        Returns:
            str: Formatted phone number or empty string
        """
        if not self.phone_number:
            return ''
        number = self.phone_number.strip()
        if number.startswith('+231') and len(number) >= 12:
            return f"{number[:4]} {number[4:6]} {number[6:9]} {number[9:]}"
        return number
    
    @property
    def display_name(self):
        """Get user's display name (username or email)"""
        return self.username or self.email.split('@')[0]
    
    @property
    def sms_enabled(self):
        """Check if user has ANY SMS notifications enabled"""
        return any([
            self.sms_entry_verified,
            self.sms_badge_earned,
            self.sms_level_up,
            self.sms_leaderboard,
            self.sms_streak_milestone,
            self.sms_needs_revision,
            self.sms_daily_challenge,
        ])