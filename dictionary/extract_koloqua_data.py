#!/usr/bin/env python3
"""
Script to extract and process Koloqua dictionary data from the provided text
and prepare it for database import.
"""

import csv
import re
from typing import List, Tuple, Dict
from pathlib import Path

def parse_koloqua_dictionary_text(text_content: str) -> List[Dict[str, str]]:
    """
    Parse the Koloqua dictionary text and extract structured data.
    
    Args:
        text_content: Raw text content from the Koloqua dictionary
        
    Returns:
        List of dictionaries containing structured dictionary entries
    """
    entries = []
    lines = text_content.strip().split('\n')
    
    current_entry = {}
    current_word = None
    
    for line in lines:
        line = line.strip()
        
        # Skip header and empty lines
        if not line or line.startswith('Koloqua Dictionary') or line.startswith('Liberian Word'):
            continue
        
        # Skip section headers (single letters)
        if re.match(r'^[A-Z]\s*$', line):
            continue
        
        # Parse dictionary entries
        # Format: Word/Phrase\tMeaning\tSample Sentence\tEnglish Translation
        parts = line.split('\t')
        
        if len(parts) >= 4:
            koloqua_word = parts[0].strip()
            english_meaning = parts[1].strip()
            sample_koloqua = parts[2].strip()
            sample_english = parts[3].strip()
            
            # Clean up the data
            koloqua_word = clean_text(koloqua_word)
            english_meaning = clean_text(english_meaning)
            sample_koloqua = clean_text(sample_koloqua)
            sample_english = clean_text(sample_english)
            
            # Skip if essential fields are empty
            if not koloqua_word or not english_meaning:
                continue
            
            entry = {
                'koloqua_text': koloqua_word,
                'english_translation': english_meaning,
                'example_sentence_koloqua': sample_koloqua,
                'example_sentence_english': sample_english,
                'entry_type': determine_entry_type(koloqua_word, english_meaning),
                'context_explanation': generate_context_explanation(koloqua_word, english_meaning),
                'tags': generate_tags(koloqua_word, english_meaning),
                'categories': suggest_categories(koloqua_word, english_meaning)
            }
            
            entries.append(entry)
    
    return entries

def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove control characters but keep basic punctuation
    text = re.sub(r'[^\w\s\-\'\"\(\)\[\]\{\}\,\.\!\?\;]', '', text)
    
    return text

def determine_entry_type(koloqua_text: str, english_translation: str) -> str:
    """Determine if entry is word, phrase, idiom, or proverb."""
    word_count = len(koloqua_text.split())
    
    if word_count == 1:
        return 'word'
    elif any(indicator in english_translation.lower() for indicator in 
             ['expression', 'saying', 'proverb', 'oath']):
        return 'proverb'
    elif word_count > 4 or any(word in koloqua_text.lower() for word in 
                               ['when', 'if', 'because', 'since']):
        return 'idiom'
    else:
        return 'phrase'

def generate_context_explanation(koloqua_text: str, english_translation: str) -> str:
    """Generate context explanation for usage."""
    entry_type = determine_entry_type(koloqua_text, english_translation)
    
    if 'insult' in english_translation.lower() or 'ridicule' in english_translation.lower():
        return f"Informal {entry_type} used to express criticism or mockery. Use with caution in formal settings."
    elif any(word in english_translation.lower() for word in ['greeting', 'hello', 'goodbye']):
        return f"Common social {entry_type} used in everyday greetings and farewells."
    elif any(word in english_translation.lower() for word in ['slang', 'informal']):
        return f"Informal {entry_type} commonly used in casual conversation among peers."
    elif any(word in english_translation.lower() for word in ['traditional', 'secret', 'ritual']):
        return f"Traditional {entry_type} with cultural significance. May be used in specific cultural contexts."
    else:
        return f"Common {entry_type} used in everyday Liberian Koloqua conversation."

def generate_tags(koloqua_text: str, english_translation: str) -> List[str]:
    """Generate relevant tags for the entry."""
    tags = ['koloqua', 'liberian']
    
    text_combined = (koloqua_text + ' ' + english_translation).lower()
    
    # Add semantic tags based on content
    tag_keywords = {
        'slang': ['slang', 'informal', 'street'],
        'formal': ['formal', 'official', 'proper'],
        'food': ['eat', 'food', 'cook', 'rice', 'soup', 'meat'],
        'family': ['father', 'mother', 'brother', 'sister', 'aunt', 'uncle', 'child'],
        'emotion': ['angry', 'happy', 'sad', 'love', 'hate', 'excited'],
        'money': ['money', 'dollar', 'buy', 'sell', 'pay', 'business'],
        'social': ['friend', 'greet', 'hello', 'goodbye', 'thank'],
        'body': ['hand', 'foot', 'head', 'eye', 'body', 'heart'],
        'animals': ['monkey', 'bird', 'fish', 'snake', 'chicken', 'cow'],
        'clothing': ['wear', 'dress', 'shirt', 'clothes'],
        'traditional': ['traditional', 'culture', 'secret', 'ritual']
    }
    
    for tag, keywords in tag_keywords.items():
        if any(keyword in text_combined for keyword in keywords):
            tags.append(tag)
    
    return tags

def suggest_categories(koloqua_text: str, english_translation: str) -> List[str]:
    """Suggest appropriate categories for the entry."""
    text_combined = (koloqua_text + ' ' + english_translation).lower()
    
    categories = []
    
    category_mappings = {
        'Greetings & Social': ['hello', 'goodbye', 'thank', 'please', 'welcome', 'friend'],
        'Food & Cooking': ['rice', 'fish', 'cook', 'eat', 'food', 'soup', 'meat', 'drink'],
        'Family & Relationships': ['father', 'mother', 'brother', 'sister', 'aunt', 'uncle', 'child', 'wife', 'husband'],
        'Slang & Informal': ['slang', 'informal', 'street', 'crazy', 'stupid', 'fool'],
        'Animals & Nature': ['monkey', 'bird', 'fish', 'snake', 'elephant', 'tree', 'forest', 'river'],
        'Body & Health': ['head', 'hand', 'foot', 'eye', 'medicine', 'sick', 'pain', 'blood'],
        'Clothing & Appearance': ['clothes', 'wear', 'dress', 'shirt', 'beautiful', 'ugly', 'hair'],
        'Money & Business': ['money', 'dollar', 'buy', 'sell', 'pay', 'business', 'work'],
        'Transportation': ['car', 'taxi', 'road', 'walk', 'travel', 'motorcycle'],
        'Emotions & Feelings': ['happy', 'sad', 'angry', 'love', 'hate', 'fear', 'worry'],
        'Traditional & Cultural': ['traditional', 'culture', 'secret', 'ritual', 'ceremony']
    }
    
    for category, keywords in category_mappings.items():
        if any(keyword in text_combined for keyword in keywords):
            categories.append(category)
    
    # Default category if none found
    if not categories:
        categories.append('Slang & Informal')
    
    return categories

def create_csv_from_dictionary_text(input_file_path: str = None, output_csv_path: str = "koloqua_dictionary.csv") -> None:
    """
    Create a CSV file from the Koloqua dictionary text.
    
    Args:
        input_file_path: Path to input text file (optional, uses hardcoded data if None)
        output_csv_path: Path for output CSV file
    """
    
    # Use the provided dictionary data (hardcoded for reliability)
    dictionary_entries = get_hardcoded_dictionary_data()
    
    # If input file provided, try to parse it
    if input_file_path and Path(input_file_path).exists():
        try:
            with open(input_file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                parsed_entries = parse_koloqua_dictionary_text(content)
                if parsed_entries:
                    dictionary_entries.extend(parsed_entries)
        except Exception as e:
            print(f"Error reading input file: {e}")
    
    # Write to CSV
    csv_headers = [
        'koloqua_text',
        'english_translation', 
        'example_sentence_koloqua',
        'example_sentence_english',
        'entry_type',
        'context_explanation',
        'tags',
        'categories'
    ]
    
    with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_headers)
        writer.writeheader()
        
        for entry in dictionary_entries:
            # Convert lists to comma-separated strings
            entry_copy = entry.copy()
            if isinstance(entry_copy.get('tags'), list):
                entry_copy['tags'] = ','.join(entry_copy['tags'])
            if isinstance(entry_copy.get('categories'), list):
                entry_copy['categories'] = ','.join(entry_copy['categories'])
            
            writer.writerow(entry_copy)
    
    print(f"Created CSV file with {len(dictionary_entries)} entries: {output_csv_path}")

def get_hardcoded_dictionary_data() -> List[Dict[str, str]]:
    """Return hardcoded dictionary data extracted from the provided document."""
    
    raw_entries = [
        # A
        ("Abuse", "To insult, ridicule", "Buh you na abuse the man bad way oh!", "You shouldn't insult the man badly!"),
        ("Argo Oil", "Vegetable oil", "Wheh play ley argo oy (eh)?", "Where is the vegetable oil?"),
        ("Air cool", "Air conditioning", "", ""),
        ("All two", "both", "Take all two to the papay deh", "Take both to the old man"),
        ("Ants bear", "The pangolin", "", ""),
        ("Antay", "Aunt", "La ma antay (deh)", "That's my aunt (there)"),
        
        # B
        ("Ba", "A friend, buddy, peer", "Ba, come leh go", "Friend, come let's go"),
        ("bamboo", "The raffia palm tree", "", ""),
        ("baboon", "chimpanzee", "", ""),
        ("Baf fence", "An outdoor shower area", "", ""),
        ("Bamboo wine", "Palm wine", "", ""),
        ("Bamboo worm", "Beetle grubs", "", ""),
        ("banjo", "To sell something at a discount; cheap", "All de tinnen you selling yeh, la banjo?", "Everything you sell, are they cheap?"),
        ("Barbing saloon", "Barber shop", "We coming go to lay barbing saloon jessna", "We are going to the barbershop right now"),
        ("Beard-beard", "A longer beard on a man", "See beard-beard oh!", "Look at his beard!"),
        ("Bend-bend", "Crooked, twisted, not straight", "", ""),
        ("Bend de elbow", "To get drunk", "I no longer bend de elbow", "I no longer drink alcohol"),
        ("Behind you", "To bother someone, to nag", "Buh what you behind me for again?", "Why are you harassing me again?"),
        ("belle", "Big stomach; pregnancy", "The woman geh belle for da man", "The woman was impregnated by that man"),
        ("Bessa", "A busybody, gossip, rumors", "Do na believe dat ting, dat bessa", "Don't believe that, that's gossip"),
        ("Bessa body", "busy body; to be a gossip", "It na good to be bessa body oh", "It's not good to be a gossip"),
        ("Big Book", "educated English, big words", "La your big book, don't bring it to me oh", "Don't speak to me using big words I don't understand"),
        ("Biggor boy", "A big shot (usually young person)", "See biggor boy oh", "Look at the big shot"),
        ("Big cold", "Very cold temperature", "", ""),
        ("Big heart", "To be arrogant, boastful, brave", "You tink say you geh big heart?", "Do you think you're that bold and arrogant?"),
        ("Big man", "A big shot, government official", "", ""),
        ("Billhook", "A small cutting tool for harvesting rice", "", ""),
        ("biskeh", "Biscuit or cookies", "La how much you buy dih biskeh?", "How much were these biscuits?"),
        ("Bite an blow", "To take advantage of someone by fooling them", "", ""),
        ("Blance", "To hit the football against something", "", ""),
        ("Blast", "Yelling, reprimanding", "I will blast you jessna", "I will reprimand you immediately"),
        ("Blay", "Stylish or fashionable clothing", "See blay oh!", "This person is very fashionable"),
        ("Blinger", "A cell phone", "", ""),
        ("Blood fish", "Atlantic blue fin tuna", "", ""),
        ("Blood tableh", "Vitamin pills/tablets", "", ""),
        ("Blood wasting", "Bleeding", "", ""),
        ("Bluff", "To show off, to flaunt", "Oh? So la me you bluffing so?", "Are you showing off for me?"),
        ("Bluffuh-joe", "Someone who is a showoff", "Looka this other bluffuh-joe", "Look at this showoff"),
        ("Bobo", "A deaf mute person; ignorant person", "Small more, you will be bobo", "Keep this up and you'll be senseless"),
        ("Body bra", "A one-piece women's swimsuit", "", ""),
        ("Body Man", "A body builder; muscular man", "", ""),
        ("Boiling", "Going out, having fun", "Today we boil!", "Today we're having fun!"),
        ("Boke", "I see you; I catch you", "I boke you!", "I caught you!"),
        ("Boney", "Dried herring fish", "The dry boney sweet in this food yeh", "The dried herring is tasty in this dish"),
        ("Book", "A general term for education", "Book see book, book hide", "When educated meets more educated, the less educated defers"),
        ("Book people", "The educated class", "The book people na come oh", "The educated people are here"),
        ("Boid", "Bird", "How they can call da blah bweh?", "What is the name of that black bird?"),
        ("Born town", "Birthplace; hometown", "", ""),
        ("Bounder", "A rascal", "", ""),
        ("Brabee", "An older brother", "Brabee you know you de bossman now", "Big bro, you're the boss now"),
        ("Brackeh", "To meet up with someone", "Where can we brackeh?", "Where can we meet?"),
        ("Bread nut", "Jack fruit", "", ""),
        ("Break word", "To state an opinion", "", ""),
        ("Bright", "Light skinned/complexion", "Wheh play breh Fatu eh?", "Where is fair-skinned Fatu?"),
        ("Brutha", "Male sibling, close friend", "", ""),
        ("Buba", "A long robe associated with Muslims", "", ""),
        ("Bufeh", "To seize or takeaway quickly", "", ""),
        ("Bugumaa", "Imaginary evil spirits or genies", "", ""),
        ("Bug-a-bug", "termites", "", ""),
        ("Bug-a-bug eat your brain", "Are you stupid?", "Bug-a-bug eat yor brain?", "Are you stupid?"),
        ("Bumpay", "To hit a target", "ah bumpay!", "I hit the target!"),
        ("Bunga", "The buttocks", "", ""),
        ("Bush-school", "Traditional school; Sande and Poro", "", ""),
        ("Bush cat", "The palm civet or golden cat", "", ""),
        ("Bush chicken", "The partridge", "", ""),
        ("Bush cow", "West African dwarf buffalo", "", ""),
        ("Bush dog", "The river otter; mongoose", "", ""),
        ("Bush road", "A foot path in the forest", "", ""),
        ("Bush taxi", "To travel by foot", "", ""),
        ("Bush wife", "Country wife; native woman", "", ""),
        ("Butta rice", "Starchy imported rice from China", "", ""),
        ("Butt up with", "Bump into someone unexpectedly", "I na butt up with my brother today oh!", "I ran into my brother today!"),
        
        # C
        ("Call me dog", "An oath to hold someone in contempt", "If I don't put one slap in your ear, call me dog!", "I'd rather be called a dog than let you do that!"),
        ("Calopay", "To knock down; turn over flat", "", ""),
        ("Cahmo", "Commode; toilet", "I am going to use the cahmo", "I'm going to use the toilet"),
        ("Cane juice", "Sugarcane liquor", "", ""),
        ("Carboy", "Conductor driver assistant", "I cant drive dis truck without a carboy", "I can't drive this truck without an assistant"),
        ("Car pay", "Taxi or bus fare", "", ""),
        ("Cassava snake", "The Gaboon viper", "", ""),
        ("Cat eye", "Light colored eyes; road reflectors", "", ""),
        ("Catoon", "A cardboard box or carton", "Y'all muh bust la catoon in the back", "Please break that box in the backyard"),
        ("Cavalla fish", "An Atlantic horse mackerel fish", "", ""),
        ("Chakla", "To destroy, mess up", "The how y'all now chakla this room", "Look how you've messed up this room"),
        ("Charged", "To be intoxicated", "", ""),
        ("Chant", "To recite a magical spell", "", ""),
        ("Chap", "To cut with a knife", "", ""),
        ("Che", "An expression of surprise", "Che! So this whole pot of rice y'all na swallow all?", "So you ate all this rice?"),
        ("Che-che", "Gossip, slander", "", ""),
        ("Che-che-polay", "a gossip", "Chechepolay move from behind me oh!", "Gossip, get away from me!"),
        ("Chuck rice", "Rice with greens and gravy", "I coming eat my chuck rice", "I'm going to eat my chuck rice"),
        ("Chek", "A girlfriend or lover", "", ""),
        ("Chicken rogue", "A chicken thief", "", ""),
        ("Chicken soup", "Bullion cubes", "How you will fix this palm butter without chicken soup?", "How will you make palm butter without bullion cubes?"),
        ("chiklet", "Bubble gum", "This chicklet sweet oh!", "This gum is sweet!"),
        ("Chinee leh", "Cheap Chinese battery lamp", "Lih ullur Chinee leh na geh nattin inside", "The Chinese light has nothing inside"),
        ("Chinee man", "Any Asian-looking man", "Go to ley chinee man on broad street", "Go to the Chinese man on Broad Street"),
        ("chop", "To misuse money wrongfully", "You na chop the man schoo fees", "You misused the man's school fees"),
        ("Church motha", "An older church lady leader", "", ""),
        ("Civilize", "Westernized, Christian, educated", "", ""),
        ("Coe tar ro", "A paved road", "Ley pull na fix the coe tar ro", "The people have fixed the road"),
        ("Coat suit", "A two or three piece men's suit", "See the man coat suit seh", "Look at his nice suit"),
        ("Coe bo", "Cheap street food", "I jeh eating my small coe bo", "I'm eating a small meal"),
        ("Coe bo shop", "A small cook shop", "I to the coe bo shop", "I'm at the cook shop"),
        ("Coffee bag fall in de wuhtuh", "Someone has gone crazy", "", ""),
        ("Coh-pa", "A charcoal stove", "", ""),
        ("Cook spoon", "A large metal cooking spoon", "", ""),
        ("Colloma", "Fake or imitation", "", ""),
        ("Come leh eat", "Polite invitation to eat", "", ""),
        ("Common", "Well known, ordinary", "", ""),
        ("Comping", "A rotational savings club", "", ""),
        ("Con", "Crook", "", ""),
        ("Correh", "Something of good quality", "Da man correh oh", "That man is good/upstanding"),
        ("Cattah", "Cloth used to balance head load", "", ""),
        ("Cotton tree", "The silk cotton tree", "", ""),
        ("Country bread", "Pounced rice meal", "", ""),
        ("Country chalk", "White clay for medicine/ritual", "", ""),
        ("Country chicken", "Free-range village chicken", "", ""),
        ("Country chop", "Stew with various meats over rice", "", ""),
        ("Country guitar", "Homemade stringed instrument", "", ""),
        ("Country medicine", "Traditional herbal remedies", "", ""),
        ("Country money", "Thin iron rods used as currency", "", ""),
        ("Country ray", "The country is economically hard", "Since this man take the country, the country ray", "Since this president took office, times are tough"),
        ("Country rope", "Forest vines for tying", "", ""),
        ("Country salt", "Potash made from palm ashes", "", ""),
        ("Country soap", "Traditional village-made soap", "", ""),
        ("Cow spirit", "Egret (white bird)", "", ""),
        ("Co wator", "Bribe; welcome liquor", "", ""),
        ("Crackay", "Stubborn, argumentative person", "", ""),
        ("Craw-craw", "An itchy skin disease", "", ""),
        ("Craw-craw frog", "A toad", "", ""),
        ("Credih", "An advance loan, cell phone units", "", ""),
        ("Crushing", "Having romantic feelings", "", ""),
        ("Cruss", "Rice crust from pot bottom", "", ""),
        ("Culture", "Traditional secret societies", "", ""),
        ("Cup", "A can used to measure rice", "", ""),
        ("Currenn", "Electricity", "", ""),
        ("Cutlax", "A machete", "", ""),
        ("cycle", "A bicycle", "", ""),
        
        # D
        ("Da lie", "Not true; false", "Da ting you sayin da lie", "What you're saying is a lie"),
        ("Dat ha", "That's how", "", ""),
        ("Dan", "Ten Liberian dollars", "", ""),
        ("Day bor", "Casual daily laborer", "", ""),
        ("Dealin", "Using witchcraft/sorcery", "", ""),
        ("Dear", "Expensive, costly", "This thing dear oh", "This is expensive"),
        ("Deer", "The duiker antelope", "", ""),
        ("Dux", "To ace something, top performer", "", ""),
        ("Dey few days", "Recently", "", ""),
        ("Dorfa", "A duck", "", ""),
        ("Different different", "Several varieties", "", ""),
        ("Direct code", "Straight talk, bold speech", "", ""),
        ("Deeshcloth", "Eczema, skin rash", "You have deeshcloth on your hand", "You have eczema on your hand"),
        ("Dite", "Garbage, trash", "", ""),
        ("Dog baby", "Puppy", "", ""),
        ("Dokafleh", "Used clothes from abroad", "Please bi me dokafleh sneakor", "Please buy me used sneakers"),
        ("Dolphin fish", "The mahi-mahi fish", "", ""),
        ("Dooji", "Heroin", "", ""),
        ("Door mouf", "A doorway", "", ""),
        ("Dragon", "A malevolent reptilian spirit", "", ""),
        ("Drappay", "To give a small gift", "", ""),
        ("Dress", "Move closer together, scoot over", "", ""),
        ("Drill", "To march in military parade", "", ""),
        ("Drunk you", "To get someone drunk", "", ""),
        ("Druss", "Western medicine", "", ""),
        ("Dry", "To be skinny or malnourished", "", ""),
        ("Drah face", "To be unashamed; bold", "", ""),
        ("Dry meat", "Dried bush meat", "", ""),
        ("Dry monkey", "Severe malnutrition", "", ""),
        ("Du", "The kusimanse mongoose", "", ""),
        ("Dukor", "Monrovia", "", ""),
        ("Dumboy", "Thick cassava dough to swallow", "", ""),
        ("Dunkin", "Ignorant; fooled easily", "", ""),
        ("Dusta", "A blackboard eraser", "", ""),
        ("Dumpile", "A garbage dump", "", ""),
        ("Dusty road", "A dirt/unpaved road", "", ""),
        ("Dwah", "Small mythical creatures", "", ""),
        ("Dynamo", "A diesel generator", "", ""),
        
        # E
        ("Ee mah eyeball", "To rip someone off", "The man really eat my eyeball", "The man really cheated me"),
        ("Een de butto", "To be drunk", "", ""),
        ("Eh yah", "Expression of sympathy", "", ""),
        ("Eye turning", "To be dizzy or drunk", "", ""),
        ("Elda", "Title of respect for older person", "", ""),
        
        # F
        ("Face cap", "Baseball hat", "", ""),
        ("Fall off", "To fall apart, break", "", ""),
        ("Fanga", "Small two-head pressure drum", "", ""),
        ("Fanner", "Flat basket to winnow rice", "", ""),
        ("Fanti cloth", "Brightly colored African cloth", "", ""),
        ("Farina", "Dried cassava flakes cereal", "", ""),
        ("Farm ro far", "To be deaf; distance is far", "", ""),
        ("Fever grass", "Lemongrass", "", ""),
        ("Fever leaf", "Wild basil plant", "", ""),
        ("Fek-fek", "Fake, not true, worthless", "", ""),
        ("Fine", "Beautiful, attractive", "This girl fine oh!", "This girl is beautiful!"),
        ("Too Fine", "Too beautiful", "", ""),
        ("Fish cup", "Tin of cooked fish in oil", "", ""),
        ("Fiya", "To shoot at with weapon", "", ""),
        ("Fiya behine", "To pressure; force someone", "", ""),
        ("Flakajay", "Foolish; senseless; substandard", "I do na like dat flakajay talk", "I don't like that foolish talk"),
        ("Flash", "Call and hang up after one ring", "", ""),
        ("Flask", "A thermos for hot water", "", ""),
        ("Flexing", "To party, go nightclubbing", "", ""),
        ("Flok", "To beat as punishment", "", ""),
        ("For common", "Commonly, often", "", ""),
        ("For nating", "Worthless, good for nothing", "", ""),
        ("Fooly tongor", "The gray duiker antelope", "", ""),
        ("Foot", "The entire leg including foot", "", ""),
        ("Fox", "The slender mongoose", "", ""),
        ("Freak ah", "To love or be attracted to", "", ""),
        ("Film sho", "A movie, video, or film", "", ""),
        ("Fresh", "To be beautiful or fine", "", ""),
        ("Fresh co", "Common cold, runny nose", "", ""),
        ("Friskay", "Wild, rude, overactive", "Dis boy friskay-o", "This boy is wild!"),
        ("Frog baby", "A tadpole", "", ""),
        ("Forstor", "Slang for food or to eat", "", ""),
        ("Fuan-fuan", "Trouble; problem; headache", "I do na wan any fuan-fuan", "I don't want any trouble"),
        ("Fuel oil", "Diesel fuel/gas oil", "", ""),
        ("Full-uh", "Something that is very full", "", ""),
        ("Funny", "Doing something foolish or stupid", "Look a aye, you funny, ehn?", "Look at you, are you being stupid?"),
        ("Fufu", "Food made from cassava", "", ""),
        
        # G
        ("Gallon", "Plastic container for liquids", "", ""),
        ("Galovant", "To walk around", "", ""),
        ("Gamble seed", "Cowrie shells for divination", "", ""),
        ("Gapping", "To be hungry; suffering", "The gapping rate is high", "The hunger rate is high"),
        ("Gate", "Checkpoint on highway", "", ""),
        ("gavay", "Someone who died; escaped", "", ""),
        ("GB", "Cassava dough dumpling", "", ""),
        ("Gbana", "Mischievous, unruly", "", ""),
        ("Gbapleh", "Small finger-sized saltwater fish", "", ""),
        ("Gbassa jamba", "Cassava leaf sauce", "", ""),
        ("Gbelleh", "Foolish, stupid", "Dey gar dah gbelleh", "This guy is stupid"),
        ("Gbehma", "Traditional music with electronic beats", "", ""),
        ("Gborku", "Plenty; surplus; many", "We have ri gborku", "We have plenty of rice"),
        ("Gboyo", "Part of secret society", "", ""),
        ("Geez", "Gossip, salacious rumors", "", ""),
        ("Geh mouf", "People who talk too much", "", ""),
        ("Genah", "A forest spirit", "", ""),
        ("German plum", "Large variety of mango", "", ""),
        ("Ghetto", "Drug hideout location", "", ""),
        ("Give belly", "To impregnate a woman", "", ""),
        ("Go slow", "A labor strike", "", ""),
        ("Gobbachop official", "Corrupt government person", "", ""),
        ("Gohfada", "Sugar-daddy older man", "", ""),
        ("Golden plum", "The Ambarella fruit", "", ""),
        ("Gone weekend", "This past weekend", "", ""),
        ("Gorilla", "Old, very large chimpanzee", "", ""),
        ("Grass", "", "", ""),
        ("Grasscutta", "", "", ""),
        ("Gravy", "sauce", "", ""),
        ("Grebo-bush", "Bush/traditional school", "", ""),
        ("Gree-gree", "Charms or amulets", "", ""),
        ("Green monkey", "Callithrix monkey", "", ""),
        ("Greens", "Leafy vegetable cooked with oil", "", ""),
        ("Grip", "A suitcase", "", ""),
        ("Grumbo pekin", "Person who likes trouble", "", ""),
        ("Gronna", "Rebellious, disrespectful", "", ""),
        ("Gronna boy", "Juvenile delinquent, gangster", "", ""),
        ("Ground pea", "A peanut", "", ""),
        ("Ground pea candy", "Peanut brittle", "", ""),
        ("Gunshot", "A bullet", "", ""),
        ("Gun sound", "Report of gun firing", "", ""),
        ("Gut", "Big stomach", "", ""),
        ("Gutta", "A ditch", "", ""),
        ("Gwana", "The Nile monitor lizard", "", ""),
    ]
    
    processed_entries = []
    for koloqua_text, english_translation, example_koloqua, example_english in raw_entries:
        if not koloqua_text or not english_translation:
            continue
            
        entry = {
            'koloqua_text': clean_text(koloqua_text),
            'english_translation': clean_text(english_translation),
            'example_sentence_koloqua': clean_text(example_koloqua),
            'example_sentence_english': clean_text(example_english),
            'entry_type': determine_entry_type(koloqua_text, english_translation),
            'context_explanation': generate_context_explanation(koloqua_text, english_translation),
            'tags': generate_tags(koloqua_text, english_translation),
            'categories': suggest_categories(koloqua_text, english_translation)
        }
        processed_entries.append(entry)
    
    return processed_entries

if __name__ == "__main__":
    # Create CSV file with extracted data
    create_csv_from_dictionary_text()
    print("Dictionary extraction completed!")