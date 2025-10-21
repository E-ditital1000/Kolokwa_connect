
# gamification/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone


class Badge(models.Model):
    """Badges that users can earn"""
    
    BADGE_TYPES = [
        ('contribution', 'Contribution'),
        ('verification', 'Verification'),
        ('streak', 'Streak'),
        ('special', 'Special'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    badge_type = models.CharField(max_length=20, choices=BADGE_TYPES)
    icon = models.ImageField(upload_to='badges/', blank=True, null=True)
    points_required = models.IntegerField(default=0)
    contributions_required = models.IntegerField(default=0)
    verifications_required = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'badges'
        ordering = ['points_required']
    
    def __str__(self):
        return self.name


class UserBadge(models.Model):
    """Track which badges users have earned"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    earned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_badges'
        unique_together = [['user', 'badge']]
        ordering = ['-earned_at']
    
    def __str__(self):
        return f"{self.user} - {self.badge}"


class PointTransaction(models.Model):
    """Track point awards and deductions"""
    
    TRANSACTION_TYPES = [
        ('contribution', 'New Contribution'),
        ('verification', 'Verification'),
        ('vote', 'Vote Cast'),
        ('vote_received', 'Vote Received'),
        ('vote_changed', 'Vote Changed'),
        ('vote_removed', 'Vote Removed'),
        ('daily_bonus', 'Daily Bonus'),
        ('achievement', 'Achievement'),
        ('penalty', 'Penalty'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='point_transactions')
    points = models.IntegerField()
    transaction_type = models.CharField(max_length=50, choices=TRANSACTION_TYPES)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'point_transactions'
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        # Check if this is a new transaction
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            # Update user's total points
            from django.db.models import F
            self.user.points = F('points') + self.points
            self.user.save(update_fields=['points'])
            # Refresh to get the actual value
            self.user.refresh_from_db(fields=['points'])
            # Update user level
            self.user.update_level()


class DailyChallenge(models.Model):
    """Daily challenges for users to complete"""
    title = models.CharField(max_length=200)
    description = models.TextField()
    points_reward = models.IntegerField(default=10)
    target_count = models.IntegerField(default=1)
    challenge_date = models.DateField(unique=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'daily_challenges'
        ordering = ['-challenge_date']
    
    def __str__(self):
        return f"{self.title} - {self.challenge_date}"


class UserStreak(models.Model):
    """Track user contribution streaks"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='streak')
    current_streak = models.IntegerField(default=0)
    longest_streak = models.IntegerField(default=0)
    last_contribution_date = models.DateField(null=True, blank=True)
    
    # Challenge tracking
    accepted_challenge = models.ForeignKey(DailyChallenge, on_delete=models.SET_NULL, null=True, blank=True, related_name='accepted_by')
    accepted_challenge_date = models.DateField(null=True, blank=True)
    completed_challenge = models.ForeignKey(DailyChallenge, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_by')
    completed_challenge_date = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'user_streaks'
    
    def update_streak(self):
        """Update streak based on contribution date"""
        today = timezone.now().date()
        
        if self.last_contribution_date:
            days_diff = (today - self.last_contribution_date).days
            
            if days_diff == 0:
                return  # Already contributed today
            elif days_diff == 1:
                self.current_streak += 1
            else:
                self.current_streak = 1
        else:
            self.current_streak = 1
        
        self.last_contribution_date = today
        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak
        self.save()
    
    def __str__(self):
        return f"{self.user.username} - {self.current_streak} day streak"