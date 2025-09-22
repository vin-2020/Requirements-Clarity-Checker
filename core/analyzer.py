import spacy
import re

# Load the small English NLP model from spaCy once at import time
nlp = spacy.load("en_core_web_sm")

# -------------------------------------------------------------------
# Reference word list
# Based on INCOSE guidance, weak/ambiguous terms that should be avoided
# in requirements engineering. These are considered "red flag" words.
# -------------------------------------------------------------------
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
    """
    Detect ambiguous / weak words in a requirement.

    Parameters
    ----------
    requirement_text : str
        Requirement statement to analyze.

    Returns
    -------
    list[str]
        List of weak words found in the text.
    """
    found_words = []
    lower_requirement = requirement_text.lower()

    for word in WEAK_WORDS:
        # Regex with word boundaries to avoid partial matches
        if re.search(r'\b' + re.escape(word) + r'\b', lower_requirement):
            found_words.append(word)

    return found_words


def check_passive_voice(requirement_text):
    """
    Detect possible passive voice constructions in a requirement.

    Uses spaCy dependency parsing to find auxiliary passive verbs.

    Parameters
    ----------
    requirement_text : str
        Requirement statement to analyze.

    Returns
    -------
    list[str]
        List of verb phrases flagged as passive.
    """
    found_phrases = []
    doc = nlp(requirement_text)

    for token in doc:
        if token.dep_ == "auxpass":  # Auxiliary passive marker
            # Collect children of the head verb plus the head itself
            verb_phrase = [child.text for child in token.head.children]
            verb_phrase.append(token.head.text)

            # Preserve phrase order by using text position
            ordered = sorted(verb_phrase, key=lambda x: doc.text.find(x))
            found_phrases.append(" ".join(ordered))

    return found_phrases


def check_incompleteness(requirement_text):
    """
    Check if a requirement appears incomplete.

    Heuristic: if no verb or auxiliary verb is present,
    the requirement is considered incomplete.

    Parameters
    ----------
    requirement_text : str

    Returns
    -------
    bool
        True if requirement is incomplete, False otherwise.
    """
    doc = nlp(requirement_text)
    has_verb = any(token.pos_ in ["VERB", "AUX"] for token in doc)
    return not has_verb


def check_singularity(requirement_text):
    """
    Check if a requirement violates the 'singularity' principle
    (i.e., expresses multiple actions in one statement).

    Parameters
    ----------
    requirement_text : str

    Returns
    -------
    list[str]
        List of conjunctions ("and", "or") or extra verbs that suggest
        multiple actions. Returns an empty list if the requirement is singular.
    """
    issues = []
    doc = nlp(requirement_text)

    # Count root verbs (main actions in the sentence)
    root_verbs = [token for token in doc if token.dep_ == "ROOT" and token.pos_ == "VERB"]

    # Find conjunctions that indicate compound actions
    conjunctions = [
        token.text.lower()
        for token in doc
        if token.dep_ in ["cc", "conj"] and token.text.lower() in ["and", "or"]
    ]

    if len(root_verbs) > 1 or conjunctions:
        issues.extend(conjunctions)
        if not conjunctions and len(root_verbs) > 1:
            # Flag extra verbs beyond the first root verb
            issues.extend([verb.text for verb in root_verbs[1:]])

    return list(set(issues))  # Ensure unique issue markers
