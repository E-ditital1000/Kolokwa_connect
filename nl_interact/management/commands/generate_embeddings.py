# nl_interact/management/commands/generate_embeddings.py
"""
Management command to pre-compute embeddings for all dictionary entries.
Stores embeddings in database, not cache.

Usage: 
  python manage.py generate_embeddings
  python manage.py generate_embeddings --force
  python manage.py generate_embeddings --batch-size 5 --delay 2
"""

from django.core.management.base import BaseCommand
from dictionary.models import KoloquaEntry
from nl_interact.utils import batch_generate_embeddings, get_rag_stats, is_rate_limited
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Pre-generate embeddings for dictionary entries (stores in database)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force regeneration of all embeddings',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Number of entries to process before pausing (default: 10)',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Seconds to wait between batches (default: 1.0)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of entries to process',
        )

    def handle(self, *args, **options):
        force = options['force']
        batch_size = options['batch_size']
        delay = options['delay']
        limit = options['limit']
        
        # Show current stats
        stats = get_rag_stats()
        self.stdout.write(self.style.WARNING('\n=== Current Stats ==='))
        self.stdout.write(f"Total verified entries: {stats['total_entries']}")
        self.stdout.write(f"Entries with embeddings: {stats['entries_with_embeddings']}")
        self.stdout.write(f"Coverage: {stats['coverage_percentage']:.1f}%")
        self.stdout.write(f"Need embeddings: {stats['entries_needing_embeddings']}")
        
        if stats['rate_limited']:
            self.stdout.write(
                self.style.ERROR('\n⚠️  Currently rate limited! Wait before generating.')
            )
            return
        
        # Get entries to process
        if force:
            entries = KoloquaEntry.objects.filter(status='verified')
            self.stdout.write(
                self.style.WARNING(f"\n🔄 Force mode: Processing all {entries.count()} entries")
            )
        else:
            entries = KoloquaEntry.objects.filter(
                status='verified',
                embedding__isnull=True
            )
            self.stdout.write(
                self.style.SUCCESS(f"\n✨ Processing {entries.count()} entries without embeddings")
            )
        
        if limit:
            entries = entries[:limit]
            self.stdout.write(f"Limited to {limit} entries")
        
        if entries.count() == 0:
            self.stdout.write(self.style.SUCCESS('\n✅ All entries already have embeddings!'))
            return
        
        # Confirm for large batches
        if entries.count() > 50:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  Processing {entries.count()} entries will make ~{entries.count()} API calls."
                )
            )
            confirm = input("Continue? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write("Cancelled.")
                return
        
        # Process embeddings
        self.stdout.write(
            self.style.SUCCESS(
                f"\n🚀 Starting generation (batch_size={batch_size}, delay={delay}s)...\n"
            )
        )
        
        results = batch_generate_embeddings(
            entries,
            batch_size=batch_size,
            delay=delay,
            force=force
        )
        
        # Show results
        self.stdout.write(self.style.SUCCESS('\n=== Results ==='))
        self.stdout.write(f"✅ Success: {results['success']}")
        self.stdout.write(f"⏭️  Skipped: {results['skipped']}")
        self.stdout.write(f"❌ Failed: {results['failed']}")
        
        if is_rate_limited():
            self.stdout.write(
                self.style.ERROR(
                    '\n⚠️  Hit rate limit! Run again later to continue.'
                )
            )
        
        # Show updated stats
        stats = get_rag_stats()
        self.stdout.write(self.style.SUCCESS('\n=== Updated Stats ==='))
        self.stdout.write(f"Coverage: {stats['coverage_percentage']:.1f}%")
        self.stdout.write(f"Remaining: {stats['entries_needing_embeddings']}")