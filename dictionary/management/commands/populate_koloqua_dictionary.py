# management/commands/populate_koloqua_dictionary.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from dictionary.models import KoloquaEntry, WordCategory
from gamification.models import Badge, UserBadge, PointTransaction
import csv
import io

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate the Koloqua dictionary with initial data and auto-verify entries'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            type=str,
            choices=['csv', 'hardcoded'],
            default='hardcoded',
            help='Data source: csv file or hardcoded dictionary data'
        )
        parser.add_argument(
            '--csv-file',
            type=str,
            help='Path to CSV file containing dictionary data'
        )
        parser.add_argument(
            '--create-admin',
            action='store_true',
            help='Create admin user for contributions'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of entries to process in each batch'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Koloqua Dictionary population...'))
        
        # Clear existing entries
        self.stdout.write(self.style.WARNING('Deleting all existing Koloqua entries...'))
        count, _ = KoloquaEntry.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} existing entries.'))
        
        # Create or get admin user for contributions
        admin_user = self.get_or_create_admin_user(options['create_admin'])
        
        # Create categories
        self.create_categories()
        
        # Create initial badges
        self.create_initial_badges()
        
        # Import dictionary data
        if options['source'] == 'csv':
            self.import_from_csv(options['csv_file'], admin_user, options['batch_size'])
        else:
            self.import_hardcoded_data(admin_user, options['batch_size'])
        
        self.stdout.write(self.style.SUCCESS('Dictionary population completed!'))
    
    def get_or_create_admin_user(self, create_admin):
        """Get or create admin user for contributions"""
        try:
            admin_user = User.objects.get(username='koloqua_admin')
            self.stdout.write(f"Using existing admin user: {admin_user.username}")
        except User.DoesNotExist:
            if create_admin:
                admin_user = User.objects.create_user(
                    username='koloqua_admin',
                    email='admin@koloqua.com',
                    password='secure_admin_password_2024',
                    is_staff=True,
                    is_superuser=True
                )
                self.stdout.write(self.style.SUCCESS(f"Created admin user: {admin_user.username}"))
            else:
                # Use the first superuser or create one
                admin_user = User.objects.filter(is_superuser=True).first()
                if not admin_user:
                    admin_user = User.objects.create_user(
                        username='koloqua_system',
                        email='system@koloqua.com',
                        is_staff=True,
                        is_superuser=True
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created system user: {admin_user.username}"))
        
        return admin_user
    
    def create_categories(self):
        """Create word categories"""
        categories_data = [
            ('Greetings & Social', 'Common greetings and social expressions'),
            ('Food & Cooking', 'Food, cooking, and dining related terms'),
            ('Family & Relationships', 'Family members and relationship terms'),
            ('Slang & Informal', 'Informal language and slang expressions'),
            ('Animals & Nature', 'Animals, plants, and natural phenomena'),
            ('Body & Health', 'Body parts, health, and medical terms'),
            ('Clothing & Appearance', 'Clothing, accessories, and appearance'),
            ('Money & Business', 'Financial and business-related terms'),
            ('Transportation', 'Vehicles and transportation'),
            ('Technology & Modern', 'Modern technology and contemporary terms'),
            ('Traditional & Cultural', 'Traditional practices and cultural terms'),
            ('Emotions & Feelings', 'Expressions of emotions and feelings'),
            ('Time & Weather', 'Time expressions and weather terms'),
            ('Colors & Descriptions', 'Colors and descriptive adjectives'),
            ('Actions & Verbs', 'Common actions and verbs'),
        ]
        
        created_count = 0
        for name, description in categories_data:
            category, created = WordCategory.objects.get_or_create(
                name=name,
                defaults={'description': description}
            )
            if created:
                created_count += 1
        
        self.stdout.write(f"Created {created_count} new categories")
    
    def create_initial_badges(self):
        """Create initial gamification badges"""
        badges_data = [
            {
                'name': 'Dictionary Founder',
                'description': 'Contributed to the initial dictionary population',
                'badge_type': 'special',
                'icon': 'trophy',
                'points_required': 0,
                'contributions_required': 1,
            },
            {
                'name': 'First Steps',
                'description': 'Made your first contribution',
                'badge_type': 'contribution',
                'icon': 'star',
                'points_required': 0,
                'contributions_required': 1,
            },
            {
                'name': 'Word Collector',
                'description': 'Contributed 10 verified entries',
                'badge_type': 'contribution',
                'icon': 'collection',
                'points_required': 0,
                'contributions_required': 10,
            },
        ]
        
        created_count = 0
        for badge_data in badges_data:
            badge, created = Badge.objects.get_or_create(
                name=badge_data['name'],
                defaults=badge_data
            )
            if created:
                created_count += 1
        
        self.stdout.write(f"Created {created_count} new badges")
    
    def categorize_entry(self, koloqua_text, english_translation):
        """Automatically categorize entries based on content"""
        text_lower = (koloqua_text + ' ' + english_translation).lower()
        
        # Define keyword mappings
        category_keywords = {
            'Greetings & Social': ['morning', 'hello', 'goodbye', 'thank', 'please', 'sorry', 'welcome'],
            'Food & Cooking': ['rice', 'fish', 'cook', 'eat', 'food', 'soup', 'meat', 'drink', 'palm', 'cassava'],
            'Family & Relationships': ['father', 'mother', 'brother', 'sister', 'aunt', 'uncle', 'child', 'wife', 'husband', 'friend'],
            'Animals & Nature': ['monkey', 'bird', 'fish', 'snake', 'elephant', 'tree', 'forest', 'river', 'mountain'],
            'Body & Health': ['head', 'hand', 'foot', 'eye', 'medicine', 'sick', 'pain', 'blood', 'heart'],
            'Clothing & Appearance': ['clothes', 'wear', 'dress', 'shirt', 'beautiful', 'ugly', 'hair', 'skin'],
            'Money & Business': ['money', 'dollar', 'buy', 'sell', 'pay', 'business', 'work', 'job'],
            'Transportation': ['car', 'taxi', 'road', 'walk', 'travel', 'motorcycle', 'bicycle'],
            'Emotions & Feelings': ['happy', 'sad', 'angry', 'love', 'hate', 'fear', 'worry', 'excited'],
            'Slang & Informal': ['crazy', 'stupid', 'fool', 'bluff', 'joke', 'tease'],
        }
        
        # Find matching categories
        matching_categories = []
        for category_name, keywords in category_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                try:
                    category = WordCategory.objects.get(name=category_name)
                    matching_categories.append(category)
                except WordCategory.DoesNotExist:
                    continue
        
        # Default to general if no specific category found
        if not matching_categories:
            try:
                general_category = WordCategory.objects.get(name='Slang & Informal')
                matching_categories.append(general_category)
            except WordCategory.DoesNotExist:
                pass
        
        return matching_categories
    
    def determine_entry_type(self, koloqua_text, english_translation):
        """Determine if entry is word, phrase, idiom, or proverb"""
        if len(koloqua_text.split()) == 1:
            return 'word'
        elif any(word in english_translation.lower() for word in ['expression', 'saying', 'proverb']):
            return 'proverb'
        elif len(koloqua_text.split()) > 4 or any(word in koloqua_text.lower() for word in ['when', 'if', 'because']):
            return 'idiom'
        else:
            return 'phrase'
    
    def import_hardcoded_data(self, admin_user, batch_size):
        """Import hardcoded dictionary data"""
        
        # Sample of the dictionary data - you can expand this with the full dataset
        dictionary_data = [
            # A
            ("Abuse", "To insult, ridicule", "Buh you na abuse the man bad way oh!", "You shouldn't insult the man badly!"),
            ("Argo Oil", "Vegetable oil", "Wheh play ley argo oy (eh)?", "Where is the vegetable oil?"),
            ("All two", "both", "Take all two to the papay deh", "Take both to the old man"),
            ("Antay", "Aunt", "La ma antay (deh)", "That's my aunt (there)"),
            
            # B  
            ("Ba", "A friend, buddy, peer", "Ba, come leh go", "Friend, come let's go"),
            ("banjo", "To sell cheap, discount", "All de tinnen you selling yeh, la banjo?", "Everything you sell, are they cheap?"),
            ("Beard-beard", "A longer beard on a man", "See beard-beard oh!", "Look at his beard!"),
            ("Behind you", "To bother someone, nag", "Buh what you behind me for again?", "Why are you harassing me again?"),
            ("belle", "Big stomach, pregnancy", "The woman geh belle for da man", "The woman was impregnated by that man"),
            ("Bessa", "Busybody, gossip", "Do na believe dat ting, dat bessa", "Don't believe that, that's gossip"),
            ("Big heart", "Arrogant, boastful", "You tink say you geh big heart?", "Do you think you're that bold?"),
            ("Bluff", "To show off, flaunt", "Oh? So la me you bluffing so?", "Are you showing off for me?"),
            ("Boiling", "Going out, having fun", "Today we boil!", "Today we're having fun!"),
            ("Book people", "Educated class", "The book people na come oh", "The educated people are here"),
            
            # C
            ("Call me dog", "Oath of contempt", "If I don't put one slap in your ear, call me dog!", "I would rather be called a dog than let you do that!"),
            ("Che", "Expression of surprise", "Che! So this whole pot of rice y'all swallow all?", "So you mean you ate all this rice?"),
            ("Chuck rice", "Rice with greens", "I coming eat my chuck rice", "I'm going to eat my chuck rice"),
            ("Country ray", "Times are hard", "Since this man take the country, the country ray", "Since this president took office, times are tough"),
            
            # D
            ("Da lie", "Not true, false", "Da ting you sayin da lie", "What you're saying is false"),
            ("Dear", "Expensive, costly", "This thing too dear", "This is too expensive"),
            ("Dokafleh", "Used clothes", "Please bi me dokafleh sneakor", "Please buy me used sneakers"),
            
            # F
            ("Fine", "Beautiful, attractive", "This girl fine oh!", "This girl is beautiful!"),
            ("Flakajay", "Foolish, stupid", "I do na like dat flakajay talk", "I don't like that foolish talk"),
            ("Friskay", "Wild, rude", "Dis boy friskay-o", "This boy is wild!"),
            
            # G
            ("Gapping", "Hungry, suffering", "The gapping rate is high", "The hunger rate is high"),
            ("Gbelleh", "Foolish, stupid", "Dey gar dah gbelleh", "This guy is stupid"),
            ("Gborku", "Plenty, many", "We have ri gborku", "We have plenty of rice"),
            
            # H  
            ("Hala", "To shout, yell", "Why you hala so?", "Why are you shouting like that?"),
            ("Haat clean", "Honest, good intentions", "This man haat clean", "This man has good intentions"),
            ("Hellaba", "Stubborn", "This pekin hellaba", "This child is stubborn"),
            
            # J
            ("Junk", "Inexperienced, ignorant", "This guy a junk", "This guy is inexperienced"),
            ("Jus na", "Right away", "Come jus na", "Come right away"),
            
            # K
            ("Kubba", "Cunning, experienced", "This girl da kuba", "This girl is cunning"),
            ("Kwi", "Educated, modern", "Only kwi people live in the city", "Only educated people live in the city"),
            
            # L
            ("La lie", "That's a lie", "La lie! I never say that", "That's a lie! I never said that"),
            ("Level", "Empty talk, excuse", "Don't put me en level", "Don't give me empty talk"),
            
            # M
            ("Make mouf", "To boast", "He like make mouf", "He likes to boast"),
            ("Mean", "Selfish, stingy", "This man mean oh", "This man is stingy"),
            
            # N
            ("Now-now", "Right now", "Come now-now", "Come right now"),
            ("Nyan", "Naive, foolish", "Don't be nyan", "Don't be naive"),
            
            # P
            ("Palava", "Argument, problem", "We get palava", "We have a problem"),
            ("Papay", "Wealthy older man", "Go to the papay", "Go to the wealthy man"),
            ("Pekin", "Young boy", "This pekin smart", "This boy is smart"),
            ("Play low", "Forget about it", "Just play it low", "Just forget about it"),
            
            # R
            ("Ray", "Red", "See the ray car", "See the red car"),
            ("Rogue", "Thief", "That man is rogue", "That man is a thief"),
            
            # S
            ("Sabi", "Cunning, crafty", "He sabi oh", "He's crafty"),
            ("Small-small", "Gradually", "We go do it small-small", "We'll do it gradually"),
            ("Sweet", "Delicious", "This food sweet", "This food is delicious"),
            
            # T
            ("Today person", "Modern person", "She's a today person", "She's a modern person"),
            ("Tote", "To carry", "Tote this bag", "Carry this bag"),
            
            # V
            ("Vex", "Angry", "I vex with you", "I'm angry with you"),
            ("Voke", "To tease", "Don't voke me", "Don't tease me"),
            
            # W
            ("Wahala", "Problem, trouble", "We get wahala", "We have trouble"),
            ("Woking", "Food", "I want woking", "I want food"),
            
            # Y
            ("Yana", "Street vendor", "Go to the yana boy", "Go to the street vendor"),
            ("Yute", "Youth, young person", "All the yute dem", "All the young people"),
            
            # Z
            ("Zoko", "Young criminal", "That boy is zoko", "That boy is a petty thief"),
            ("Zepsay", "Crazy, insane", "He zepsay oh", "He's crazy"),
        ]
        
        self.stdout.write(f"Processing {len(dictionary_data)} entries...")
        
        created_count = 0
        updated_count = 0
        
        # Process in batches
        for i in range(0, len(dictionary_data), batch_size):
            batch = dictionary_data[i:i + batch_size]
            
            with transaction.atomic():
                for koloqua_text, english_translation, example_koloqua, example_english in batch:
                    try:
                        # Check if entry already exists
                        existing_entry = KoloquaEntry.objects.filter(
                            koloqua_text__iexact=koloqua_text.strip()
                        ).first()
                        
                        if existing_entry:
                            # Update if not verified
                            if existing_entry.status != 'verified':
                                existing_entry.english_translation = english_translation.strip()
                                existing_entry.example_sentence_koloqua = example_koloqua.strip()
                                existing_entry.example_sentence_english = example_english.strip()
                                existing_entry.status = 'verified'
                                existing_entry.verification_count = 5
                                existing_entry.verified_at = timezone.now()
                                existing_entry.save()
                                updated_count += 1
                        else:
                            # Create new entry
                            entry_type = self.determine_entry_type(koloqua_text, english_translation)
                            
                            entry = KoloquaEntry.objects.create(
                                koloqua_text=koloqua_text.strip(),
                                english_translation=english_translation.strip(),
                                example_sentence_koloqua=example_koloqua.strip(),
                                example_sentence_english=example_english.strip(),
                                entry_type=entry_type,
                                context_explanation=f"Common {entry_type} used in Liberian Koloqua",
                                contributor=admin_user,
                                status='verified',  # Auto-verify initial data
                                verification_count=5,  # Set high verification count
                                verified_at=timezone.now(),
                                upvotes=3,  # Give initial positive votes
                                tags=['initial-data', 'verified']
                            )
                            
                            # Add categories
                            categories = self.categorize_entry(koloqua_text, english_translation)
                            if categories:
                                entry.categories.set(categories)
                            
                            created_count += 1
                            
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"Error processing '{koloqua_text}': {str(e)}")
                        )
                        continue
            
            # Show progress
            self.stdout.write(f"Processed batch {i//batch_size + 1}/{len(dictionary_data)//batch_size + 1}")
        
        # Award badge to admin user
        try:
            founder_badge = Badge.objects.get(name='Dictionary Founder')
            UserBadge.objects.get_or_create(user=admin_user, badge=founder_badge)
        except Badge.DoesNotExist:
            pass
        
        # Update admin user points
        admin_user.points += created_count * 10  # 10 points per contribution
        admin_user.save()
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Import completed! Created: {created_count}, Updated: {updated_count}"
            )
        )
    
    def import_from_csv(self, csv_file_path, admin_user, batch_size):
        """Import from CSV file"""
        if not csv_file_path:
            self.stdout.write(self.style.ERROR("CSV file path required for CSV import"))
            return
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                # Try to detect CSV format
                sample = file.read(1024)
                file.seek(0)
                
                # Assume CSV format: Koloqua,English,Example_Koloqua,Example_English
                reader = csv.DictReader(file)
                
                entries_data = []
                for row in reader:
                    entries_data.append((
                        row.get('koloqua_text', '').strip(),
                        row.get('english_translation', '').strip(),
                        row.get('example_sentence_koloqua', '').strip(),
                        row.get('example_sentence_english', '').strip()
                    ))
                
                self.stdout.write(f"Found {len(entries_data)} entries in CSV")
                
                # Process similar to hardcoded data
                created_count = 0
                for i in range(0, len(entries_data), batch_size):
                    batch = entries_data[i:i + batch_size]
                    
                    with transaction.atomic():
                        for koloqua_text, english_translation, example_koloqua, example_english in batch:
                            if not koloqua_text or not english_translation:
                                continue
                                
                            entry, created = KoloquaEntry.objects.update_or_create(
                                koloqua_text__iexact=koloqua_text,
                                defaults={
                                    'koloqua_text': koloqua_text,
                                    'english_translation': english_translation,
                                    'example_sentence_koloqua': example_koloqua,
                                    'example_sentence_english': example_english,
                                    'entry_type': self.determine_entry_type(koloqua_text, english_translation),
                                    'context_explanation': f"Imported from CSV data",
                                    'contributor': admin_user,
                                    'status': 'verified',
                                    'verification_count': 5,
                                    'verified_at': timezone.now(),
                                    'upvotes': 2,
                                    'tags': ['csv-import', 'verified']
                                }
                            )
                            
                            if created:
                                categories = self.categorize_entry(koloqua_text, english_translation)
                                if categories:
                                    entry.categories.set(categories)
                                created_count += 1
                
                self.stdout.write(self.style.SUCCESS(f"CSV import completed! Created: {created_count} entries"))
                
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"CSV file not found: {csv_file_path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing CSV: {str(e)}"))