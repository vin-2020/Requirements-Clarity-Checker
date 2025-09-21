# core/scoring.py

def calculate_clarity_score(total_reqs, flagged_reqs):
    """
    Calculates a clarity score based on the percentage of clear requirements.
    """
    if total_reqs == 0:
        return 100

    clear_reqs = total_reqs - flagged_reqs
    
    # The score is the percentage of requirements that are clear.
    score = (clear_reqs / total_reqs) * 100
    
    return int(score)
