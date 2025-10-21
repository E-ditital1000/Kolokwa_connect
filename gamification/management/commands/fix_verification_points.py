# gamification/management/commands/fix_verification_points.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from dictionary.models import KoloquaEntry
from gamification.models import PointTransaction
from gamification.utils import handle_entry_verification, award_points, check_and_award_badges
from django.db.models import Count, F, Q

User = get_user_model()

class Command(BaseCommand):
    help = 'Fix verification points for entries that were verified but contributors didn\'t receive points'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without actually making changes',
        )
        parser.add_argument(
            '--entry-id',
            type=int,
            help='Fix points for a specific entry ID only',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        entry_id = options.get('entry_id')
        
        self.stdout.write(
            self.style.WARNING(f'Running in {"DRY RUN" if dry_run else "LIVE"} mode')
        )
        
        # Get verified entries
        queryset = KoloquaEntry.objects.filter(
            status='verified',
            verifications__isnull=False
        ).select_related('contributor').prefetch_related('verifications__verifier')
        
        if entry_id:
            queryset = queryset.filter(id=entry_id)
            
        if not queryset.exists():
            self.stdout.write(
                self.style.WARNING('No verified entries found matching criteria')
            )
            # Even if no entries, still ensure user verification counts are correct
            self._recalculate_all_user_verification_counts(dry_run)
            self._recalculate_all_user_contributions_counts(dry_run)
            return
        
        fixed_count = 0
        skipped_count = 0
        
        for entry in queryset:
            # Iterate through verifications for each entry to find the verifier
            for verification in entry.verifications.all():
                verifier = verification.verifier
                
                # Check if the verifier has already received points for this specific verification
                verifier_already_awarded = PointTransaction.objects.filter(
                    user=verifier,
                    transaction_type='verification',
                    description__icontains=entry.koloqua_text # Or a more specific identifier if available
                ).exists()

                # Check if the contributor has already received points for their contribution being verified
                contributor_already_awarded = PointTransaction.objects.filter(
                    user=entry.contributor,
                    transaction_type__in=['contribution_verified', 'verification_received'],
                    description__icontains=entry.koloqua_text
                ).exists()

                # Only proceed if either the verifier or the contributor needs points
                if verifier_already_awarded and contributor_already_awarded:
                    self.stdout.write(
                        f'SKIP: {entry.koloqua_text} - Both verifier ({verifier.username}) and contributor ({entry.contributor.username}) already awarded points'
                    )
                    skipped_count += 1
                    continue
                
                if dry_run:
                    action_taken = []
                    if not verifier_already_awarded:
                        action_taken.append(f'WOULD AWARD VERIFIER ({verifier.username}) POINTS')
                    if not contributor_already_awarded:
                        action_taken.append(f'WOULD AWARD CONTRIBUTOR ({entry.contributor.username}) POINTS')

                    self.stdout.write(
                        self.style.SUCCESS(
                            f'WOULD FIX: {entry.koloqua_text} by {entry.contributor.username} '
                            f'(verified by {verifier.username}). Actions: {", ".join(action_taken)}'
                        )
                    )
                    fixed_count += 1
                else:
                    try:
                        # Award points if not already awarded
                        if not verifier_already_awarded or not contributor_already_awarded:
                            # handle_entry_verification awards points to both verifier and contributor
                            # It also updates verifications_count for the verifier and potentially contributor_points for the entry.
                            # Since we are re-running, it is safe to call it if either is missing
                            handle_entry_verification(entry, verifier)
                            
                            log_message = f'FIXED: {entry.koloqua_text}. '
                            if not verifier_already_awarded:
                                log_message += f'Awarded points to verifier {verifier.username}. '
                            if not contributor_already_awarded:
                                log_message += f'Awarded points to contributor {entry.contributor.username}. '
                            self.stdout.write(self.style.SUCCESS(log_message.strip()))
                            fixed_count += 1
                            
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'ERROR fixing {entry.koloqua_text} for verifier {verifier.username}: {str(e)}'
                            )
                        )
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f'\n=== SUMMARY ===\n'
                f'{"Would fix" if dry_run else "Fixed"}: {fixed_count} entries\n'
                f'Skipped: {skipped_count} entries\n'
                f'Total processed: {fixed_count + skipped_count} entries'
            )
        )
        
        # Always recalculate all user verification counts to ensure accuracy
        self._recalculate_all_user_verification_counts(dry_run)
        self._recalculate_all_user_contributions_counts(dry_run)
        
        if dry_run and fixed_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    '\nRun without --dry-run to actually apply the fixes'
                )
            )

    def _recalculate_all_user_verification_counts(self, dry_run):
        from dictionary.models import EntryVerification  # Import here to avoid circular dependency
        self.stdout.write(self.style.MIGRATE_HEADING('\nRecalculating all user verification counts...'))
        
        users_to_update = User.objects.annotate(
            actual_verifications_count=Count('verifications')
        ).filter(~Q(actual_verifications_count=F('verifications_count')))

        if not users_to_update.exists():
            self.stdout.write(self.style.SUCCESS('All user verification counts are already accurate.'))
            return

        for user in users_to_update:
            old_count = user.verifications_count
            new_count = user.actual_verifications_count
            
            if dry_run:
                self.stdout.write(
                    f'WOULD UPDATE VERIFICATIONS COUNT for {user.username}: {old_count} -> {new_count}'
                )
            else:
                user.verifications_count = new_count
                user.save(update_fields=['verifications_count'])
                self.stdout.write(
                    self.style.SUCCESS(
                        f'UPDATED VERIFICATIONS COUNT for {user.username}: {old_count} -> {new_count}'
                    )
                )
                # After updating counts, re-check for badges
                check_and_award_badges(user)
        self.stdout.write(self.style.SUCCESS('User verification counts recalculation complete.'))

    def _recalculate_all_user_contributions_counts(self, dry_run):
        from dictionary.models import KoloquaEntry  # Import here to avoid circular dependency
        self.stdout.write(self.style.MIGRATE_HEADING('\nRecalculating all user contributions counts...'))
        
        users_to_update = User.objects.annotate(
            actual_contributions_count=Count('contributions')
        ).filter(~Q(actual_contributions_count=F('contributions_count')))

        if not users_to_update.exists():
            self.stdout.write(self.style.SUCCESS('All user contributions counts are already accurate.'))
            return

        for user in users_to_update:
            old_count = user.contributions_count
            new_count = user.actual_contributions_count
            
            if dry_run:
                self.stdout.write(
                    f'WOULD UPDATE CONTRIBUTIONS COUNT for {user.username}: {old_count} -> {new_count}'
                )
            else:
                user.contributions_count = new_count
                user.save(update_fields=['contributions_count'])
                self.stdout.write(
                    self.style.SUCCESS(
                        f'UPDATED CONTRIBUTIONS COUNT for {user.username}: {old_count} -> {new_count}'
                    )
                )
                # After updating counts, re-check for badges
                check_and_award_badges(user)
        self.stdout.write(self.style.SUCCESS('User contributions counts recalculation complete.'))