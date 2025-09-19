# core/analyzer.py

# A list of common words and phrases that can lead to ambiguous requirements.
WEAK_WORDS = [
    "should", "may", "could", "possibly", "as appropriate", "user-friendly",
    "robust", "efficient", "effective", "etc.", "and/or", "minimize",
    "maximize", "support", "seamless", "easy to use", "state-of-the-art",
    "best", "handle", "approximately", "as required", "fast", "strong",
    "high resolution", "high", "low", "long"
]

# A list of common passive voice phrases to detect.
PASSIVE_VOICE_PHRASES = [
    "is provided", "is required", "is developed", "is tested",
    "are provided", "are required", "are developed", "are tested",
    "shall be provided", "shall be required", "shall be developed", "shall be tested",
    "will be provided", "will be required", "will be developed", "will be tested"
]

def check_requirement_ambiguity(requirement_text):
    """Analyzes a requirement string for weak words and returns the findings."""
    found_words = []
    lower_requirement = requirement_text.lower()
    
    for word in WEAK_WORDS:
        if word in lower_requirement:
            found_words.append(word)
            
    return found_words

def check_passive_voice(requirement_text):
    """Analyzes a requirement string for passive voice phrases."""
    found_phrases = []
    lower_requirement = requirement_text.lower()

    for phrase in PASSIVE_VOICE_PHRASES:
        if phrase in lower_requirement:
            found_phrases.append(phrase)
    
    return found_phrases