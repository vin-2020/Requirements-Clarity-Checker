# core/scoring.py
"""
Scoring utilities for ReqCheck.

This module provides functions to compute quality metrics
for analyzed requirements documents.
"""


def calculate_clarity_score(total_reqs, flagged_reqs):
    """
    Calculate a clarity score based on the percentage of requirements
    that contain no detected issues.

    Parameters
    ----------
    total_reqs : int
        The total number of requirements analyzed.
    flagged_reqs : int
        The number of requirements flagged with issues
        (e.g., ambiguity, passive voice, incompleteness).

    Returns
    -------
    int
        Clarity score on a scale of 0–100, rounded down to an integer.
        A higher score indicates a clearer requirements set.

    Notes
    -----
    - If no requirements are provided (`total_reqs == 0`),
      the function defaults to returning 100.
    """
    if total_reqs == 0:
        return 100

    clear_reqs = total_reqs - flagged_reqs

    # Percentage of requirements without issues
    score = (clear_reqs / total_reqs) * 100

    return int(score)

