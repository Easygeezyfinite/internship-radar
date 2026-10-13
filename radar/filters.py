"""
Layer 1b: decide which normalized postings are worth your attention.

Each rule is its own small function returning (passed: bool, reason: str).
Keeping the reason makes it easy to debug "why didn't X show up?" later.
"""

import hashlib
import json
import re
from radar import config


def title_contains_whole_word(title: str, keyword: str) -> bool:
    # \b = word boundary, so "ai" matches "AI Intern" but not "Maintenance Intern".
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, title, flags=re.IGNORECASE) is not None
    # sanity check: ("Applied AI Intern", "ai") -> True ; ("Maintenance Intern", "ai") -> False


def passes_term_rule(posting) -> tuple:
    for term in posting.terms:
        if term in config.WANTED_TERMS:
            return True, f"term {term}"
        # vansh seasons have no year and can be combined ("Spring/Summer"), so split on "/".
        # Without a year we can't tell this cycle from last cycle, so we also require a recent post date.
        bare_seasons = {season.strip() for season in term.split("/")}
        if bare_seasons & config.WANTED_SEASONS_WITHOUT_YEAR:
            if posting.date_posted_epoch >= config.BARE_SEASON_POSTED_AFTER_EPOCH:
                return True, f"season {term} (year not given)"
            return False, f"season {term} but posted before this recruiting cycle"
        if term == "N/A" and config.KEEP_POSTINGS_WITH_UNKNOWN_TERM:
            return True, "term unknown"
    return False, f"terms {posting.terms} not wanted"
    # sanity check: "Spring/Summer" -> {"Spring","Summer"} & {"Summer","Winter"} = {"Summer"} -> passes if recent


def passes_role_rule(posting) -> tuple:
    for excluded_keyword in config.EXCLUDED_TITLE_KEYWORDS:
        if title_contains_whole_word(posting.title, excluded_keyword):
            return False, f"title has excluded word '{excluded_keyword}'"
    for role_keyword in config.ROLE_KEYWORDS:
        if title_contains_whole_word(posting.title, role_keyword):
            return True, f"title matched '{role_keyword}'"
    return False, "title matched no role keyword"


def passes_degree_rule(posting) -> tuple:
    # vansh rows have no degrees -> empty list -> give it the benefit of the doubt.
    if not posting.degrees or "Bachelor's" in posting.degrees:
        return True, "bachelor's ok"
    return False, f"needs {posting.degrees}"


def passes_sponsorship_rule(posting) -> tuple:
    if posting.sponsorship_flag in config.DEALBREAKER_SPONSORSHIP_FLAGS:
        return False, posting.sponsorship_flag
    return True, posting.sponsorship_flag


ALL_RULES = [passes_term_rule, passes_role_rule, passes_degree_rule, passes_sponsorship_rule]


def compute_filter_fingerprint() -> str:
    # Any change to these settings changes the hash -> main.py knows the filter was edited.
    filter_settings = {
        "terms": sorted(config.WANTED_TERMS),
        "seasons": sorted(config.WANTED_SEASONS_WITHOUT_YEAR),
        "bare_season_after": config.BARE_SEASON_POSTED_AFTER_EPOCH,
        "keep_unknown": config.KEEP_POSTINGS_WITH_UNKNOWN_TERM,
        "role_keywords": sorted(config.ROLE_KEYWORDS),
        "excluded": sorted(config.EXCLUDED_TITLE_KEYWORDS),
        "dealbreakers": sorted(config.DEALBREAKER_SPONSORSHIP_FLAGS),
    }
    return hashlib.sha256(json.dumps(filter_settings, sort_keys=True).encode()).hexdigest()[:16]


def explain_posting(posting) -> list:
    """Runs every rule and returns [(rule_name, passed, reason), ...] - handy for debugging."""
    return [(rule.__name__, *rule(posting)) for rule in ALL_RULES]


def keep_matching_postings(postings: list) -> list:
    matching_postings = []
    for posting in postings:
        if all(rule(posting)[0] for rule in ALL_RULES):  # all() stops at the first failing rule
            matching_postings.append(posting)
    # oldest -> newest, so when we send them one by one the NEWEST lands at the bottom of the
    # Discord feed (chat apps stack later messages underneath earlier ones).
    matching_postings.sort(key=lambda posting: posting.date_posted_epoch)
    return matching_postings
