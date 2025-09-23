# core/analyzer.py
import spacy
import re
from core.rule_engine import RuleEngine

# Load the small English NLP model from spaCy
nlp = spacy.load("en_core_web_sm")

def check_requirement_ambiguity(requirement_text, rule_engine):
    """Analyzes a requirement string for weak words, based on the loaded rules."""
    if not rule_engine.is_check_enabled("ambiguity"):
        return []
        
    found_words = []
    lower_requirement = requirement_text.lower()
    weak_words = rule_engine.get_ambiguity_words()
    
    for word in weak_words:
        # Using regex with word boundaries (\b) for a more accurate match
        if re.search(r'\b' + re.escape(word) + r'\b', lower_requirement):
            found_words.append(word)
            
    return found_words

def check_passive_voice(requirement_text):
    """Analyzes a requirement string for passive voice using spaCy."""
    # Note: For this version, passive voice check is always on if called,
    # but we could add a rule_engine check here as well.
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
    """
    issues = []
    doc = nlp(requirement_text)
    
    conjunctions = [token.text.lower() for token in doc if token.dep_ == "cc" and token.text.lower() in ["and", "or"]]

    if conjunctions:
        issues.extend(conjunctions)
            
    return list(set(issues))
