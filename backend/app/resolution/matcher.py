"""Entity resolution: decide whether two account records are the same client.

Deterministic code, no AI. Every decision returns a confidence and a plain-English reason
so the review queue and the demo can show *why* records were (or were not) merged.

Rules, strongest first:
  1. Same email domain and similar name        -> 0.97  (merge)
  2. Same email domain, different-looking name  -> 0.90  (merge)
  3. Different domains                          -> <= 0.30 (never merge, however similar the names)
  4. Domain missing on one side: name only      -> at most 0.85 (never auto-merge; review if >= 0.70)
"""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app import config

# Common abbreviations seen in source systems, expanded before comparing.
ABBREVIATIONS = {
    "fds": "foods", "grp": "group", "hldgs": "holdings", "hldg": "holdings", "intl": "international",
    "log": "logistics", "med": "medical", "eng": "engineering", "mfg": "manufacturing", "svcs": "services",
}
# Legal-form words that say nothing about which company it is.
LEGAL_SUFFIXES = {"ltd", "limited", "plc", "pvt", "inc", "llc", "co", "corp", "holdings"}


def normalize_name(name: str) -> str:
    """'KESTREL FDS LTD' -> 'kestrel foods';  'Halden Medical Grp.' -> 'halden medical group'."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    words = [ABBREVIATIONS.get(w, w) for w in words]
    return " ".join(w for w in words if w not in LEGAL_SUFFIXES)


def normalize_domain(domain: str | None) -> str:
    d = (domain or "").strip().lower()
    return d[4:] if d.startswith("www.") else d


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


@dataclass
class Match:
    confidence: float
    method: str
    reason: str

    @property
    def decision(self) -> str:
        if self.confidence >= config.AUTO_MERGE_THRESHOLD:
            return "merge"
        if self.confidence >= config.REVIEW_THRESHOLD:
            return "review"
        return "no_match"


def score(rec_name: str, rec_domain: str | None, cand_name: str, cand_domains: set[str]) -> Match:
    """Score one source record against one known client."""
    sim = name_similarity(rec_name, cand_name)
    sim_txt = f"names {sim:.0%} similar after cleaning ('{normalize_name(rec_name)}' vs '{normalize_name(cand_name)}')"
    dom = normalize_domain(rec_domain)

    if dom and cand_domains:
        if dom in cand_domains:
            if sim >= 0.80:
                return Match(0.97, "domain+name", f"Same domain {dom}; {sim_txt}")
            return Match(0.90, "domain", f"Same domain {dom}; {sim_txt}")
        return Match(round(min(0.30, sim * 0.30), 2), "domain_conflict",
                     f"Different domains ({dom} vs {', '.join(sorted(cand_domains))}); {sim_txt}. "
                     "Treated as different companies.")

    # No domain to confirm: a name alone is never enough to merge automatically.
    return Match(round(min(0.85, 0.50 + 0.40 * sim), 2), "name_only",
                 f"No domain to confirm; {sim_txt}. Needs a person to check.")
