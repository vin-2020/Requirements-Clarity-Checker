# core/rule_engine.py
import json, re, os
from typing import List, Dict, Any

class RuleEngine:
    def __init__(self, rule_filepath: str = "data/default_rules.json"):
        self._rule_filepath = rule_filepath
        self.rules: Dict[str, Any] = {}
        try:
            path = rule_filepath
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)
            with open(path, "r", encoding="utf-8") as f:
                self.rules = json.load(f)
        except Exception:
            self.rules = {}

    def get_ambiguity_words(self) -> List[str]:
        return self.rules.get("rules", {}).get("ambiguity", {}).get("words", []) or []

    def get_penalty(self, issue_type: str) -> int:
        try:
            return int(self.rules.get("rules", {}).get(issue_type, {}).get("penalty", 0))
        except Exception:
            return 0

    def is_check_enabled(self, check_name: str) -> bool:
        return bool(self.rules.get("rules", {}).get(check_name, {}).get("enabled", False))

    # NEW: JSON-driven ambiguity
    def check_ambiguity(self, text: str) -> List[str]:
        findings: List[str] = []
        t = text or ""
        r = self.rules.get("rules", {}) if isinstance(self.rules, dict) else {}

        # 1) classic weak-word hits
        amb = r.get("ambiguity", {}) or {}
        if amb.get("enabled", False):
            words = amb.get("words", []) or []
            if words:
                rx = re.compile(r"\b(" + "|".join(map(re.escape, sorted(set(words), key=len, reverse=True))) + r")\b", re.IGNORECASE)
                findings += [m.group(1).lower() for m in rx.finditer(t)]

        # 2) binding modal (will/may/should…)
        bm = r.get("binding_modal", {}) or {}
        if bm.get("enabled", False):
            modals = bm.get("non_binding_words", []) or []
            if modals:
                rx = re.compile(r"\b(" + "|".join(map(re.escape, modals)) + r")\b", re.IGNORECASE)
                if rx.search(t):
                    findings.append("Non-binding modal (use 'shall' instead)")

        # 3) measurability (weak verb but no number/unit)
        meas = r.get("measurability", {}) or {}
        if meas.get("enabled", False):
            weak = meas.get("weak_verbs", []) or []
            num = meas.get("number_unit_regex",
                           r"\b\d+(?:\.\d+)?\s*(ms|s|min|h|%|m|km|ft|nm|Hz|kHz|MHz|GHz|°C|C|K|V|A|W|g|kg|MB|GB|dB|bps|kbps|Mbps|ppm)\b")
            if weak:
                wx = re.compile(r"\b(" + "|".join(map(re.escape, weak)) + r")\b", re.IGNORECASE)
                nx = re.compile(num, re.IGNORECASE)
                if wx.search(t) and not nx.search(t):
                    findings.append("No measurable criterion (add number/unit/timing)")

        # 4) alert words without trigger
        alert = r.get("alert_triggers", {}) or {}
        if alert.get("enabled", False):
            aw = alert.get("alert_words", []) or []
            tw = alert.get("trigger_words", []) or []
            ax = re.compile(r"\b(" + "|".join(map(re.escape, aw)) + r")\b", re.IGNORECASE) if aw else None
            tx = re.compile(r"\b(" + "|".join(map(re.escape, tw)) + r")\b", re.IGNORECASE) if tw else None
            if ax and ax.search(t) and (not tx or not tx.search(t)):
                findings.append("Alert without trigger/condition (add when/if/upon/within/after/…)")

        # dedupe, preserve order
        seen, out = set(), []
        for x in findings:
            if x not in seen:
                out.append(x); seen.add(x)
        return out
