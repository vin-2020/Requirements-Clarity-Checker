# core/scoring.py

# Define the penalty weights for each type of issue.
# We can make these customizable later (from Module 6).
PENALTY_WEIGHTS = {
    "ambiguity": 15,
    "passive_voice": 10,
    "incompleteness": 25
}

def calculate_clarity_score(total_reqs, issue_counts):
    """
    Calculates an overall clarity score for a document.
    
    The score starts at 100 and deducts points based on the number and type of issues found.
    """
    if total_reqs == 0:
        return 100

    total_penalty = 0
    total_penalty += issue_counts.get("Ambiguity", 0) * PENALTY_WEIGHTS["ambiguity"]
    total_penalty += issue_counts.get("Passive Voice", 0) * PENALTY_WEIGHTS["passive_voice"]
    total_penalty += issue_counts.get("Incompleteness", 0) * PENALTY_WEIGHTS["incompleteness"]
    
    # Calculate the average penalty per requirement
    average_penalty = total_penalty / total_reqs
    
    # The final score is 100 minus the average penalty, with a floor of 0.
    score = max(0, 100 - average_penalty)
    
    return int(score)
