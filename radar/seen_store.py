"""
Layer 2: remember which postings we've already pinged, across runs.

Why a file? Every GitHub Actions run starts on a fresh machine with no memory.
So we keep seen_postings.json in the repo itself and commit it back after each run.

File shape:
    {
      "filter_fingerprint": "3f9a...",      # hash of the filter settings in config.py
      "seen": {                              # dict, not list -> O(1) "have I seen this?" lookups
        "https://job-boards.greenhouse.io/memx/jobs/5450442008": 1791843310,   # cleaned link -> first seen (epoch secs)
        ...
      }
    }

Why the fingerprint? If you add a keyword to config.py, hundreds of OLD postings suddenly
match and would all look "new". When the fingerprint changes, main.py treats that run like a
first run: only recent postings ping, the rest are remembered silently.
"""

import json
import os

SECONDS_PER_DAY = 24 * 60 * 60


def load_seen_postings(seen_file_path: str) -> tuple:
    """Returns (seen_postings dict, filter_fingerprint or None)."""
    if not os.path.exists(seen_file_path):
        return {}, None  # no file yet = very first run
    with open(seen_file_path) as seen_file:
        stored = json.load(seen_file)
    if "seen" not in stored:          # older flat format {posting_id: epoch}
        return stored, None
    return stored["seen"], stored.get("filter_fingerprint")


def save_seen_postings(seen_file_path: str, seen_postings: dict, filter_fingerprint: str) -> None:
    with open(seen_file_path, "w") as seen_file:
        # sort_keys + indent -> stable, readable git diffs ("3 lines added" instead of a giant blob)
        json.dump({"filter_fingerprint": filter_fingerprint, "seen": seen_postings}, seen_file, indent=1, sort_keys=True)


def split_new_from_seen(matching_postings: list, seen_postings: dict) -> list:
    # The whole algorithm is one set difference: matches MINUS already-seen.
    return [posting for posting in matching_postings if posting.posting_id not in seen_postings]
    # sanity check: matches={A,B,C}, seen={A,B} -> [C]


def pick_postings_for_first_run(new_postings: list, backfill_hours: int, now_epoch: int) -> list:
    """
    First run problem: EVERYTHING is "new" (~1,250 postings). Pinging all of them is useless.
    So on the first run we only ping postings from the last `backfill_hours`,
    and silently mark the rest as seen. You browse the old backlog on the repos yourself.
    """
    cutoff_epoch = now_epoch - backfill_hours * 60 * 60
    return [posting for posting in new_postings if posting.date_posted_epoch >= cutoff_epoch]


def remember_postings(seen_postings: dict, postings: list, now_epoch: int) -> None:
    for posting in postings:
        seen_postings.setdefault(posting.posting_id, now_epoch)  # setdefault keeps the ORIGINAL first-seen time


def forget_very_old_entries(seen_postings: dict, keep_days: int, now_epoch: int, still_open_ids: set) -> int:
    # Without this the file grows forever. But age ALONE isn't safe: internships stay open
    # for months, and forgetting an id that's still listed makes it look "new" -> pinged again.
    # So an entry is forgotten only if it's old AND no longer in the current listings (closed).
    cutoff_epoch = now_epoch - keep_days * SECONDS_PER_DAY
    stale_ids = [
        posting_id for posting_id, first_seen in seen_postings.items()
        if first_seen < cutoff_epoch and posting_id not in still_open_ids
    ]
    # sanity check: seen={A: day 1, B: day 1}, now=day 40, still_open={A} -> forget [B], keep A
    for posting_id in stale_ids:
        del seen_postings[posting_id]
    return len(stale_ids)
