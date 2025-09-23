# core/rule_engine.py
import json

class RuleEngine:
    def __init__(self, rule_filepath="data/default_rules.json"):
        """
        Initializes the Rule Engine by loading a JSON rule file.
        """
        try:
            with open(rule_filepath, 'r') as f:
                self.rules = json.load(f)
            print(f"Successfully loaded rules: {self.rules.get('name')}")
        except FileNotFoundError:
            print(f"ERROR: Rule file not found at {rule_filepath}. Using empty rules.")
            self.rules = {}
        except json.JSONDecodeError:
            print(f"ERROR: Could not parse JSON in {rule_filepath}. Using empty rules.")
            self.rules = {}

    def get_ambiguity_words(self):
        """Returns the list of ambiguous words from the loaded rules."""
        return self.rules.get("rules", {}).get("ambiguity", {}).get("words", [])

    def get_penalty(self, issue_type):
        """Returns the penalty score for a given issue type."""
        return self.rules.get("rules", {}).get(issue_type, {}).get("penalty", 0)

    def is_check_enabled(self, check_name):
        """Checks if a specific analysis is enabled in the rules."""
        return self.rules.get("rules", {}).get(check_name, {}).get("enabled", False)