import spacy

# Load the small English NLP model from spaCy
nlp = spacy.load("en_core_web_sm")

# A list of common words and phrases that can lead to ambiguous requirements.
WEAK_WORDS = [
    "should", "may", "could", "possibly", "as appropriate", "user-friendly",
    "robust", "efficient", "effective", "etc.", "and/or", "minimize",
    "maximize", "support", "seamless", "easy to use", "state-of-the-art",
    "best", "handle", "approximately", "as required", "fast", "strong",
    "high resolution", "high", "low", "long"
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
    """Analyzes a requirement string for passive voice using spaCy."""
    found_phrases = []
    doc = nlp(requirement_text)
    
    for token in doc:
        if token.dep_ == "auxpass":
            verb_phrase = [child.text for child in token.head.children]
            verb_phrase.append(token.head.text)
            found_phrases.append(" ".join(sorted(verb_phrase, key=lambda x: doc.text.find(x))))
            
    return found_phrases

# --- NEW FUNCTION ---
def check_incompleteness(requirement_text):
    """
    Checks if a requirement is a full sentence by looking for a verb.
    Returns True if the requirement is likely incomplete (no verb found).
    """
    doc = nlp(requirement_text)
    # Check for the presence of a root verb or an auxiliary verb.
    has_verb = any([token.pos_ in ["VERB", "AUX"] for token in doc])
    return not has_verb
