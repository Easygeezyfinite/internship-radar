"""
Run layer 1 end to end and print what it found.
    python try_layer_one.py               -> downloads live data
    python try_layer_one.py ./local_dir   -> reads <local_dir>/<source>.json (offline testing)
"""

import json
import sys
import time
from collections import Counter

from radar import config
from radar.sources import fetch_all_open_postings
from radar.filters import keep_matching_postings, explain_posting

local_data_folder = sys.argv[1] if len(sys.argv) > 1 else None
read_local_file = (lambda source_name: json.load(open(f"{local_data_folder}/{source_name}.json"))) if local_data_folder else None

open_postings = fetch_all_open_postings(config.LISTING_SOURCES, read_local_file)
matching_postings = keep_matching_postings(open_postings)

print(f"open postings across sources : {len(open_postings)}")
print(f"matching your filters        : {len(matching_postings)}")
print("matches by source            :", dict(Counter(posting.source_name for posting in matching_postings)))
print("matches by term              :", dict(Counter(term for posting in matching_postings for term in posting.terms)))

print("\n10 newest matches (newest at the bottom):")
for posting in matching_postings[-10:]:
    posted_at = time.strftime("%b %d %H:%M UTC", time.gmtime(posting.date_posted_epoch))
    print(f"  {posted_at} | {posting.company_name[:22]:22} | {posting.title[:55]:55} | {posting.terms}")

# Show WHY a few postings were rejected, so the filter isn't a black box.
print("\nwhy some open postings were rejected:")
matching_ids = {posting.posting_id for posting in matching_postings}  # set -> O(1) lookups
rejected_samples = [posting for posting in open_postings if posting.posting_id not in matching_ids][:6]
for posting in rejected_samples:
    first_failure = next(reason for _, passed, reason in explain_posting(posting) if not passed)
    print(f"  {posting.title[:55]:55} -> {first_failure}")
