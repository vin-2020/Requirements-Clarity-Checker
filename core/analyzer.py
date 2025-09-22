import spacy
import re 

# Load the small English NLP model from spaCy
nlp = spacy.load("en_core_web_sm")

# --- ENHANCED: More comprehensive list based on INCOSE guidance ---
WEAK_WORDS = [
    "about", "adequate", "and/or", "appropriate", "approximately", "as a minimum",
    "as applicable", "as required", "be able to", "be capable of", "best",
    "better", "could", "easy", "effective", "efficient", "etc.", "fast", "flexible",
    "frequently", "good", "high", "handle", "if practical", "if possible",
    "including but not limited to", "instead of", "large", "latest", "long",
    "low", "maximize", "may", "minimize", "modern", "normal", "optimize",
    "possibly", "provide for", "rapid", "recent", "robust", "seamless", "should",
    "significant", "small", "state-of-the-art", "strong", "support", "timely",
    "user-friendly"
]

def check_requirement_ambiguity(requirement_text):
    """Analyzes a requirement string for weak words and returns the findings."""
    found_words = []
    lower_requirement = requirement_text.lower()
    
    for word in WEAK_WORDS:
        # Using regex with word boundaries (\b) for a more accurate match
        if re.search(r'\b' + re.escape(word) + r'\b', lower_requirement):
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

def check_incompleteness(requirement_text):
    """Checks if a requirement is a full sentence by looking for a verb."""
    doc = nlp(requirement_text)
    has_verb = any([token.pos_ in ["VERB", "AUX"] for token in doc])
    return not has_verb

def check_singularity(requirement_text):
    """
    Checks if a requirement contains multiple actions, violating the 'singular' principle.
    Returns a list of conjunctions or extra verbs found.
    """
    issues = []
    doc = nlp(requirement_text)
    
    # Count root verbs (main actions)
    root_verbs = [token for token in doc if token.dep_ == "ROOT" and token.pos_ == "VERB"]
    
    # Find conjunctions connecting clauses or verbs
    conjunctions = [token.text.lower() for token in doc if token.dep_ in ["cc", "conj"] and token.text.lower() in ["and", "or"]]

    if len(root_verbs) > 1 or conjunctions:
        issues.extend(conjunctions)
        if not conjunctions and len(root_verbs) > 1:
            issues.extend([verb.text for verb in root_verbs[1:]])
            
    return list(set(issues)) # Return unique issues