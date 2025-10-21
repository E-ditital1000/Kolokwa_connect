from django.core.management.base import BaseCommand
from django.utils import timezone
from gamification.utils import create_daily_challenge


class Command(BaseCommand):
    help = 'Create daily challenge'

    def add_arguments(self, parser):
        parser.add_argument('--title', type=str, help='Challenge title')
        parser.add_argument('--description', type=str, help='Challenge description') 
        parser.add_argument('--points', type=int, default=10, help='Points reward')
        parser.add_argument('--date', type=str, help='Challenge date (YYYY-MM-DD)')

    def handle(self, *args, **options):
        date = None
        if options['date']:
            try:
                date = timezone.datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR('Invalid date format. Use YYYY-MM-DD')
                )
                return

        challenge, created = create_daily_challenge(
            date=date,
            title=options['title'],
            description=options['description'],
            points_reward=options['points']
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created challenge: {challenge.title}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Challenge already exists for {challenge.challenge_date}')
            )
