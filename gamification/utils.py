# gamification/utils.py - Updated with SMS notifications

from django.utils import timezone
from django.db.models import Count, F
from django.db import transaction
from django.conf import settings
from .models import Badge, UserBadge, PointTransaction, UserStreak
import logging

logger = logging.getLogger(__name__)


def award_points(user, points, transaction_type, description):
    """Award points to a user and create transaction record with SMS notification"""
    if points == 0:
        return None
    
    with transaction.atomic():
        # Create transaction
        point_transaction = PointTransaction.objects.create(
            user=user,
            points=points,
            transaction_type=transaction_type,
            description=description
        )
        
        # Update user counters based on transaction type
        if transaction_type == 'contribution':
            user.contributions_count = F('contributions_count') + 1
            user.save(update_fields=['contributions_count'])
            user.refresh_from_db(fields=['contributions_count'])
        elif transaction_type == 'verification':
            user.verifications_count = F('verifications_count') + 1
            user.save(update_fields=['verifications_count'])
            user.refresh_from_db(fields=['verifications_count'])
        
        # Update user points
        old_level = user.level
        user.points = F('points') + points
        user.save(update_fields=['points'])
        user.refresh_from_db(fields=['points'])
        
        # Update level and send SMS if level changed
        user.update_level()
        
        # Send SMS notification for significant points (only if not a level-up)
        if (user.level == old_level and 
            getattr(settings, 'SMS_NOTIFICATIONS_ENABLED', False) and 
            points >= getattr(settings, 'SMS_POINTS_THRESHOLD', 5)):
            
            if hasattr(user, 'can_receive_sms') and user.can_receive_sms('entry_verified'):
                try:
                    from utils.sms_notifications import send_points_notification
                    send_points_notification(user, points, description)
                except Exception as e:
                    logger.error(f"Failed to send points SMS to {user.email}: {e}")
        
        # Check for new badges (avoid recursion by checking if it's not an achievement transaction)
        if transaction_type != 'achievement':
            check_and_award_badges(user)
        
        return point_transaction


def handle_entry_verification(entry, verifier):
    """
    Handle the verification of an entry - award points to both verifier and contributor
    This should be called when an entry status changes to 'verified'
    """
    # Award points to the verifier for doing the verification
    verifier_points = 5  # Points for verifying
    award_points(
        verifier, 
        verifier_points, 
        'verification', 
        f'Verified entry: {entry.koloqua_text}'
    )
    
    # Award points to the original contributor whose entry was verified
    contributor_points = 10  # Points for having entry verified
    award_points(
        entry.contributor, 
        contributor_points, 
        'contribution_verified', 
        f'Entry verified: {entry.koloqua_text}'
    )
    
    # Update contributor's streak
    update_user_streak(entry.contributor)
    
    # Store points awarded in the entry (optional - for display purposes)
    if hasattr(entry, 'points_awarded'):
        entry.points_awarded = contributor_points
        entry.save(update_fields=['points_awarded'])
    
    # Send SMS notification to contributor
    if getattr(settings, 'SMS_NOTIFICATIONS_ENABLED', False):
        if hasattr(entry.contributor, 'can_receive_sms') and entry.contributor.can_receive_sms('entry_verified'):
            try:
                from utils.sms_notifications import send_verification_notification
                send_verification_notification(
                    entry.contributor, 
                    entry, 
                    verifier.username
                )
            except Exception as e:
                logger.error(f"Failed to send verification SMS: {e}")
    
    return {
        'verifier_points': verifier_points,
        'contributor_points': contributor_points
    }


def handle_entry_rejection(entry, verifier):
    """
    Handle the rejection of an entry
    This should be called when an entry status changes to 'rejected'
    """
    # Award smaller points to verifier for the review work
    verifier_points = 2  # Smaller reward for rejection
    award_points(
        verifier, 
        verifier_points, 
        'verification', 
        f'Reviewed entry: {entry.koloqua_text}'
    )
    
    # Optionally notify contributor about rejection
    if getattr(settings, 'SMS_NOTIFICATIONS_ENABLED', False):
        if hasattr(entry.contributor, 'can_receive_sms') and entry.contributor.can_receive_sms('needs_revision'):
            try:
                from utils.sms_notifications import sms_service
                message = (
                    f"⚠️ Your Kolokwa entry '{entry.koloqua_text}' was marked as incorrect. "
                    f"Please review and update it at kolokwa.com"
                )
                sms_service.send_sms(entry.contributor.phone_number, message)
            except Exception as e:
                logger.error(f"Failed to send rejection SMS: {e}")
    
    return {
        'verifier_points': verifier_points,
        'contributor_points': 0
    }


def handle_new_contribution(entry):
    """
    Handle a new contribution submission
    This should be called when a new entry is created
    """
    # Award initial points for contributing
    initial_points = 2  # Small initial reward for contributing
    award_points(
        entry.contributor,
        initial_points,
        'contribution',
        f'Contributed new entry: {entry.koloqua_text}'
    )
    
    # Update streak
    update_user_streak(entry.contributor)
    
    return initial_points


def update_user_streak(user):
    """Update user's contribution streak with SMS notifications"""
    streak, created = UserStreak.objects.get_or_create(user=user)
    old_streak = streak.current_streak
    streak.update_streak()
    
    # Award streak bonuses
    if streak.current_streak > 0 and streak.current_streak % 7 == 0:  # Weekly bonus
        award_points(
            user, 
            streak.current_streak * 2, 
            'achievement', 
            f'{streak.current_streak} day streak bonus!'
        )
    
    # Send streak milestone notification
    if getattr(settings, 'SMS_NOTIFICATIONS_ENABLED', False):
        if hasattr(user, 'can_receive_sms') and user.can_receive_sms('streak_milestone'):
            milestones = [3, 7, 14, 30, 60, 90, 180, 365]
            if streak.current_streak in milestones and streak.current_streak != old_streak:
                try:
                    from utils.sms_notifications import send_streak_notification
                    send_streak_notification(user, streak.current_streak)
                except Exception as e:
                    logger.error(f"Failed to send streak SMS to {user.email}: {e}")
    
    return streak


def check_and_award_badges(user):
    """Check if user has earned any new badges with SMS notifications"""
    # Get user's current stats
    user.refresh_from_db()  # Ensure we have latest data
    
    # Get badges user doesn't have
    earned_badge_ids = UserBadge.objects.filter(user=user).values_list('badge_id', flat=True)
    available_badges = Badge.objects.exclude(id__in=earned_badge_ids)
    
    newly_earned = []
    
    for badge in available_badges:
        earned = False
        
        # Check point requirements
        if badge.points_required > 0 and user.points >= badge.points_required:
            earned = True
        
        # Check contribution requirements
        elif badge.contributions_required > 0 and user.contributions_count >= badge.contributions_required:
            earned = True
        
        # Check verification requirements  
        elif badge.verifications_required > 0 and user.verifications_count >= badge.verifications_required:
            earned = True
        
        # Special badge logic
        elif badge.badge_type == 'special':
            earned = check_special_badge_criteria(user, badge)
        
        if earned:
            user_badge = UserBadge.objects.create(user=user, badge=badge)
            newly_earned.append(user_badge)
            
            # Award bonus points for earning badge (prevent recursion)
            bonus_points = max(badge.points_required // 10, 5)  # 10% of requirement or 5 points minimum
            PointTransaction.objects.create(
                user=user,
                points=bonus_points,
                transaction_type='achievement',
                description=f'Earned badge: {badge.name}'
            )
            # Update user points directly
            user.points = F('points') + bonus_points
            user.save(update_fields=['points'])
            user.refresh_from_db(fields=['points'])
            user.update_level()
            
            # Send SMS notification for badge
            if getattr(settings, 'SMS_NOTIFICATIONS_ENABLED', False):
                if hasattr(user, 'can_receive_sms') and user.can_receive_sms('badge_earned'):
                    try:
                        from utils.sms_notifications import send_badge_notification
                        send_badge_notification(user, badge)
                    except Exception as e:
                        logger.error(f"Failed to send badge SMS to {user.email}: {e}")
    
    return newly_earned


def check_special_badge_criteria(user, badge):
    """Check criteria for special badges"""
    # Example special badge criteria
    badge_name = badge.name.lower()
    
    if 'first contribution' in badge_name or 'first steps' in badge_name:
        return user.contributions_count >= 1
    
    elif 'helpful verifier' in badge_name:
        return user.verifications_count >= 10 or user.verifications_count >= 25
    
    elif 'community hero' in badge_name:
        # Must have contributions AND verifications
        return (user.contributions_count >= 5 and user.verifications_count >= 20)
    
    elif 'streak master' in badge_name:
        streak = UserStreak.objects.filter(user=user).first()
        return streak and streak.longest_streak >= 30
    
    elif 'early adopter' in badge_name:
        # Users who joined in the first month
        from datetime import timedelta
        early_date = timezone.now() - timedelta(days=365)  # Adjust as needed
        return user.date_joined <= early_date
    
    elif 'popular contributor' in badge_name:
        # Check if user has entries with high upvotes
        try:
            from dictionary.models import KoloquaEntry
            popular_entries = KoloquaEntry.objects.filter(
                contributor=user, 
                upvotes__gte=10
            ).count()
            return popular_entries >= 3
        except ImportError:
            return False
    
    return False


def update_leaderboard_ranks():
    """
    Update user ranks and send notifications for significant changes
    Should be called periodically (e.g., daily via Celery task)
    """
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Get all users ordered by points
    users = User.objects.filter(is_active=True).order_by('-points')
    
    notifications_sent = 0
    
    for rank, user in enumerate(users, start=1):
        old_rank = getattr(user, 'previous_rank', 0) or 0
        rank_change = old_rank - rank  # Positive means moved up
        
        # Update rank
        if hasattr(user, 'previous_rank'):
            user.previous_rank = rank
            user.save(update_fields=['previous_rank'])
        
        # Send notification for significant changes
        if old_rank > 0:  # Only notify if user had a previous rank
            if getattr(settings, 'SMS_NOTIFICATIONS_ENABLED', False):
                if hasattr(user, 'can_receive_sms') and user.can_receive_sms('leaderboard'):
                    # Notify if moved up 5+ positions or in top 10
                    if abs(rank_change) >= 5 or rank <= 10:
                        try:
                            from utils.sms_notifications import send_leaderboard_notification
                            if send_leaderboard_notification(user, rank, rank_change):
                                notifications_sent += 1
                        except Exception as e:
                            logger.error(f"Failed to send leaderboard SMS to {user.email}: {e}")
    
    logger.info(f"Leaderboard ranks updated. Sent {notifications_sent} notifications.")
    return {
        'total_users': users.count(),
        'notifications_sent': notifications_sent
    }


def send_revision_notification(entry, comment):
    """Send SMS notification when entry needs revision"""
    user = entry.contributor
    
    if getattr(settings, 'SMS_NOTIFICATIONS_ENABLED', False):
        if hasattr(user, 'can_receive_sms') and user.can_receive_sms('needs_revision'):
            try:
                from utils.sms_notifications import send_revision_notification
                send_revision_notification(user, entry, comment)
            except Exception as e:
                logger.error(f"Failed to send revision SMS to {user.email}: {e}")


def get_user_level_info(points):
    """Get user level information based on points"""
    levels = [
        (0, 'beginner', 'Beginner'),
        (100, 'intermediate', 'Intermediate'),
        (500, 'expert', 'Expert'), 
        (1000, 'chief', 'Chief Linguist'),
    ]
    
    current_level = levels[0]
    next_level = None
    
    for i, (threshold, key, name) in enumerate(levels):
        if points >= threshold:
            current_level = (threshold, key, name)
            if i < len(levels) - 1:
                next_level = levels[i + 1]
        else:
            break
    
    progress = 0
    if next_level:
        level_range = next_level[0] - current_level[0]
        current_progress = points - current_level[0] 
        progress = (current_progress / level_range) * 100 if level_range > 0 else 0
    
    return {
        'current': {
            'key': current_level[1],
            'name': current_level[2],
            'threshold': current_level[0]
        },
        'next': {
            'key': next_level[1] if next_level else None,
            'name': next_level[2] if next_level else None,
            'threshold': next_level[0] if next_level else None
        },
        'progress': min(progress, 100)
    }


def get_leaderboard_data(limit=50):
    """Get leaderboard data with rankings"""
    from django.contrib.auth import get_user_model
    from django.db import models
    User = get_user_model()
    
    top_users = User.objects.annotate(
        total_contributions=Count('koloqua_entries', filter=models.Q(koloqua_entries__status='verified')),
        badges_count=Count('user_badges')
    ).order_by('-points')[:limit]
    
    leaderboard_data = []
    for i, user in enumerate(top_users):
        leaderboard_data.append({
            'rank': i + 1,
            'user': user,
            'points': user.points,
            'level': user.get_level_display(),
            'contributions_count': user.total_contributions,
            'badges_count': user.badges_count
        })
    
    return leaderboard_data


def create_sample_badges():
    """Create sample badges for the system"""
    sample_badges = [
        {
            'name': 'First Steps',
            'description': 'Contributed your first word to the dictionary',
            'badge_type': 'contribution',
            'contributions_required': 1,
        },
        {
            'name': 'Word Smith', 
            'description': 'Contributed 10 words to the dictionary',
            'badge_type': 'contribution',
            'contributions_required': 10,
        },
        {
            'name': 'Dictionary Builder',
            'description': 'Contributed 50 words to the dictionary', 
            'badge_type': 'contribution',
            'contributions_required': 50,
        },
        {
            'name': 'Helpful Verifier',
            'description': 'Verified 25 dictionary entries',
            'badge_type': 'verification', 
            'verifications_required': 25,
        },
        {
            'name': 'Point Collector',
            'description': 'Earned 100 points',
            'badge_type': 'contribution',
            'points_required': 100,
        },
        {
            'name': 'Rising Star',
            'description': 'Earned 500 points', 
            'badge_type': 'contribution',
            'points_required': 500,
        },
        {
            'name': 'Community Hero',
            'description': 'Made significant contributions to the community',
            'badge_type': 'special',
        },
        {
            'name': 'Streak Master', 
            'description': 'Maintained a 30-day contribution streak',
            'badge_type': 'special',
        },
    ]
    
    for badge_data in sample_badges:
        Badge.objects.get_or_create(
            name=badge_data['name'],
            defaults=badge_data
        )


def create_daily_challenge(date=None, title=None, description=None, points_reward=10, target_count=1):
    """Create a daily challenge"""
    from .models import DailyChallenge
    if date is None:
        date = timezone.now().date()
    
    if title is None:
        title = f"Daily Challenge - {date.strftime('%B %d, %Y')}"
    
    if description is None:
        description = "Contribute a new word or verify an existing entry today!"
    
    challenge, created = DailyChallenge.objects.get_or_create(
        challenge_date=date,
        defaults={
            'title': title,
            'description': description,
            'points_reward': points_reward,
            'target_count': target_count,
            'is_active': True
        }
    )
    
    return challenge, created