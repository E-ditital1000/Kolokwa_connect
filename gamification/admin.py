from django.contrib import admin
from .models import Badge, UserBadge, PointTransaction, DailyChallenge, UserStreak

@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'badge_type', 'points_required', 'contributions_required', 'verifications_required')
    list_filter = ('badge_type',)
    search_fields = ('name', 'description')

@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ('user', 'badge', 'earned_at')
    list_filter = ('badge',)
    search_fields = ('user__username', 'badge__name')

@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'points', 'transaction_type', 'created_at')
    list_filter = ('transaction_type',)
    search_fields = ('user__username', 'description')

@admin.register(DailyChallenge)
class DailyChallengeAdmin(admin.ModelAdmin):
    list_display = ('title', 'challenge_date', 'points_reward', 'is_active')
    list_filter = ('is_active', 'challenge_date')
    search_fields = ('title', 'description')

@admin.register(UserStreak)
class UserStreakAdmin(admin.ModelAdmin):
    list_display = ('user', 'current_streak', 'longest_streak', 'last_contribution_date')
    search_fields = ('user__username',)
