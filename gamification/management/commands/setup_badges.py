from django.core.management.base import BaseCommand
from gamification.utils import create_sample_badges


class Command(BaseCommand):
    help = 'Create sample badges for the gamification system'

    def handle(self, *args, **options):
        create_sample_badges()
        self.stdout.write(
            self.style.SUCCESS('Successfully created sample badges')
        )