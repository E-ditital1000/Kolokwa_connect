from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from dictionary.models import KoloquaEntry
from gamification.models import EntryVerification

User = get_user_model()


class Command(BaseCommand):
    help = 'Update user contribution and verification counts'

    def handle(self, *args, **options):
        users = User.objects.all()
        
        for user in users:
            # Update contributions count
            contributions_count = KoloquaEntry.objects.filter(
                contributor=user,
                status='verified'
            ).count()
            
            # Update verifications count  
            try:
                verifications_count = EntryVerification.objects.filter(
                    verifier=user
                ).count()
            except:
                verifications_count = user.verifications.count()
            
            # Update user
            user.contributions_count = contributions_count
            user.verifications_count = verifications_count
            user.save(update_fields=['contributions_count', 'verifications_count'])
            user.update_level()
            
            self.stdout.write(f'Updated {user.username}: {contributions_count} contributions, {verifications_count} verifications')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated {users.count()} users')
        )