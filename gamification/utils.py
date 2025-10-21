# gamification/utils.py
from django.utils import timezone
from django.db.models import Count, F
from django.db import transaction
from .models import Badge, UserBadge, PointTransaction, UserStreak


def award_points(user, points, transaction_type, description):
    """Award points to a user and create transaction record"""
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
    """Update user's contribution streak"""
    streak, created = UserStreak.objects.get_or_create(user=user)
    streak.update_streak()
    
    # Award streak bonuses
    if streak.current_streak > 0 and streak.current_streak % 7 == 0:  # Weekly bonus
        award_points(
            user, 
            streak.current_streak * 2, 
            'achievement', 
            f'{streak.current_streak} day streak bonus!'
        )
    
    return streak


def check_and_award_badges(user):
    """Check if user has earned any new badges"""
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
    
    return newly_earned


def check_special_badge_criteria(user, badge):
    """Check criteria for special badges"""
    # Example special badge criteria
    badge_name = badge.name.lower()
    
    if 'first contribution' in badge_name:
        return user.contributions_count >= 1
    
    elif 'helpful verifier' in badge_name:
        return user.verifications_count >= 10
    
    elif 'community hero' in badge_name:
        # Must have contributions AND verifications
        return (user.contributions_count >= 5 and user.verifications_count >= 20)
    
    elif 'streak master' in badge_name:
        streak = UserStreak.objects.filter(user=user).first()
        return streak and streak.longest_streak >= 30
    
    elif 'early adopter' in badge_name:
        # Users who joined in the first month
        from django.utils import timezone
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


def get_user_level_info(points):
    """Get user level information based on points"""
    levels = [
        (0, 'beginner', 'Beginner'),
        (100, 'contributor', 'Contributor'),
        (500, 'expert', 'Expert'), 
        (1000, 'master', 'Master'),
        (2500, 'legend', 'Legend'),
        (5000, 'champion', 'Kolokwa Champion'),
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
            'badge_type': 'streak',
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