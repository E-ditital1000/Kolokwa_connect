# utils/sms_notifications.py
"""
Twilio SMS notification service for Kolokwa Connect
Handles all SMS notifications for user activities
"""
from twilio.rest import Client
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class TwilioSMSService:
    """Service for sending SMS notifications via Twilio"""
    
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_number = settings.TWILIO_PHONE_NUMBER
        self.client = None
        
        # Initialize Twilio client
        try:
            self.client = Client(self.account_sid, self.auth_token)
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")
    
    def send_sms(self, to_number, message):
        """
        Send SMS to a phone number
        
        Args:
            to_number: Recipient phone number (format: +1234567890)
            message: SMS message content
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.client:
            logger.error("Twilio client not initialized")
            return False
        
        if not to_number:
            logger.warning("No phone number provided")
            return False
        
        # Rate limiting: max 1 SMS per user per 5 minutes
        cache_key = f"sms_sent_{to_number}"
        if cache.get(cache_key):
            logger.info(f"SMS rate limit hit for {to_number}")
            return False
        
        try:
            # Send SMS
            message = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )
            
            # Set rate limit cache
            cache.set(cache_key, True, 300)  # 5 minutes
            
            logger.info(f"SMS sent successfully to {to_number}, SID: {message.sid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send SMS to {to_number}: {e}")
            return False
    
    def notify_entry_verified(self, user, entry, verifier_name):
        """Notify user when their entry is verified"""
        if not user.phone_number:
            return False
        
        message = (
            f"🎉 Great news! {verifier_name} verified your Kolokwa word '{entry.koloqua_text}'. "
            f"You earned points! Check your profile at kolokwa.com"
        )
        return self.send_sms(user.phone_number, message)
    
    def notify_points_earned(self, user, points, reason):
        """Notify user when they earn points"""
        if not user.phone_number:
            return False
        
        message = (
            f"💎 You earned {points} points on Kolokwa! "
            f"Reason: {reason}. Total points: {user.points}"
        )
        return self.send_sms(user.phone_number, message)
    
    def notify_badge_earned(self, user, badge):
        """Notify user when they earn a new badge"""
        if not user.phone_number:
            return False
        
        message = (
            f"🏆 Achievement unlocked! You earned the '{badge.name}' badge on Kolokwa. "
            f"Keep contributing to unlock more!"
        )
        return self.send_sms(user.phone_number, message)
    
    def notify_level_up(self, user, old_level, new_level):
        """Notify user when they level up"""
        if not user.phone_number:
            return False
        
        message = (
            f"🚀 Level Up! You've advanced from {old_level} to {new_level} on Kolokwa. "
            f"Great work! Current points: {user.points}"
        )
        return self.send_sms(user.phone_number, message)
    
    def notify_leaderboard_rank(self, user, rank, rank_change):
        """Notify user about leaderboard position change"""
        if not user.phone_number or rank_change == 0:
            return False
        
        if rank_change > 0:
            emoji = "📈"
            direction = f"up {rank_change} positions"
        else:
            emoji = "📉"
            direction = f"down {abs(rank_change)} positions"
        
        message = (
            f"{emoji} Your Kolokwa leaderboard rank moved {direction}! "
            f"Current rank: #{rank}. Keep contributing!"
        )
        return self.send_sms(user.phone_number, message)
    
    def notify_streak_milestone(self, user, streak_days):
        """Notify user about streak milestones"""
        if not user.phone_number:
            return False
        
        message = (
            f"🔥 Amazing! You've maintained a {streak_days}-day contribution streak on Kolokwa! "
            f"Keep it going to earn bonus points!"
        )
        return self.send_sms(user.phone_number, message)
    
    def notify_entry_needs_revision(self, user, entry, comment):
        """Notify user when their entry needs revision"""
        if not user.phone_number:
            return False
        
        message = (
            f"📝 Your Kolokwa entry '{entry.koloqua_text}' needs revision. "
            f"Feedback: {comment[:50]}... Visit kolokwa.com to update it."
        )
        return self.send_sms(user.phone_number, message)
    
    def notify_daily_challenge(self, user, challenge):
        """Notify user about new daily challenge"""
        if not user.phone_number:
            return False
        
        message = (
            f"⚡ New Kolokwa Daily Challenge: {challenge.title}! "
            f"Complete it to earn {challenge.points_reward} points. Visit kolokwa.com"
        )
        return self.send_sms(user.phone_number, message)
    
    def notify_welcome(self, user):
        """Send welcome SMS to new user"""
        if not user.phone_number:
            return False
        
        message = (
            f"👋 Welcome to Kolokwa, {user.username}! "
            f"Start contributing Koloqua words to earn points and badges. Visit kolokwa.com"
        )
        return self.send_sms(user.phone_number, message)


# Initialize global instance
sms_service = TwilioSMSService()


# Convenience functions
def send_verification_notification(user, entry, verifier_name):
    """Send notification when entry is verified"""
    return sms_service.notify_entry_verified(user, entry, verifier_name)


def send_points_notification(user, points, reason):
    """Send notification when user earns points"""
    # Only notify for significant point gains
    if points >= 5:
        return sms_service.notify_points_earned(user, points, reason)
    return False


def send_badge_notification(user, badge):
    """Send notification when user earns badge"""
    return sms_service.notify_badge_earned(user, badge)


def send_level_up_notification(user, old_level, new_level):
    """Send notification when user levels up"""
    return sms_service.notify_level_up(user, old_level, new_level)


def send_leaderboard_notification(user, rank, rank_change):
    """Send notification about leaderboard changes"""
    # Only notify for significant rank changes
    if abs(rank_change) >= 5 or rank <= 10:
        return sms_service.notify_leaderboard_rank(user, rank, rank_change)
    return False


def send_streak_notification(user, streak_days):
    """Send notification for streak milestones"""
    # Notify at meaningful milestones
    milestones = [3, 7, 14, 30, 60, 90, 180, 365]
    if streak_days in milestones:
        return sms_service.notify_streak_milestone(user, streak_days)
    return False


def send_revision_notification(user, entry, comment):
    """Send notification when entry needs revision"""
    return sms_service.notify_entry_needs_revision(user, entry, comment)


def send_daily_challenge_notification(user, challenge):
    """Send notification about daily challenge"""
    return sms_service.notify_daily_challenge(user, challenge)


def send_welcome_notification(user):
    """Send welcome notification to new user"""
    return sms_service.notify_welcome(user)