"""
Replays three scheduled runs against real downloaded data, so you can watch the memory work.
    python simulate_three_runs.py <folder with simplify.json and vansh.json>

Trick: for runs 1 and 2 we HIDE the 3 newest matching simplify postings,
pretending they hadn't been posted yet. Run 3 "reveals" them.
"""

import json
import os
import sys

from radar import config
from radar.main import run_once
from radar.sources import normalize_raw_listing, is_open_and_visible, url_without_tracking
from radar.filters import keep_matching_postings

local_data_folder = sys.argv[1]
memory_file = "simulated_seen_postings.json"
if os.path.exists(memory_file):
    os.remove(memory_file)  # start from "never ran before"

all_raw_listings = {name: json.load(open(f"{local_data_folder}/{name}.json")) for name in config.LISTING_SOURCES}

# find the 3 newest simplify postings that pass our filters -> these are the "not yet posted" ones
simplify_open = [normalize_raw_listing(raw, "simplify") for raw in all_raw_listings["simplify"] if is_open_and_visible(raw)]
# hide by URL, not id: Simplify sometimes has two rows (different ids) for the same job link
three_newest_urls = {url_without_tracking(posting.apply_url) for posting in keep_matching_postings(simplify_open)[-3:]}
latest_posted_epoch = max(posting.date_posted_epoch for posting in simplify_open)


def listings_with_newest_hidden(source_name):
    return [raw for raw in all_raw_listings[source_name] if url_without_tracking(raw["url"]) not in three_newest_urls]


def listings_with_everything(source_name):
    return all_raw_listings[source_name]


print("=== RUN 1 (first ever run, 3 newest not posted yet) ===")
run_once(memory_file, listings_with_newest_hidden, now_epoch=latest_posted_epoch)
print("\n=== RUN 2 (20 min later, nothing new) ===")
run_once(memory_file, listings_with_newest_hidden, now_epoch=latest_posted_epoch + 1200)
print("\n=== RUN 3 (40 min later, 3 postings appear) ===")
run_once(memory_file, listings_with_everything, now_epoch=latest_posted_epoch + 2400)
os.remove(memory_file)
