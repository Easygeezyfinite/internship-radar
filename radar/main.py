"""
One full bot run: fetch -> filter -> diff against memory -> notify -> save memory.
GitHub Actions calls `python -m radar.main` on a schedule.
"""

import os
import sys
import time

from radar import config
from radar.sources import fetch_all_open_postings
from radar.filters import keep_matching_postings, compute_filter_fingerprint
from radar.discord_notifier import send_postings_to_discord
from radar.seen_store import (
    load_seen_postings, save_seen_postings, split_new_from_seen,
    pick_postings_for_first_run, remember_postings, forget_very_old_entries,
)


def print_instead_of_sending(postings: list) -> tuple:
    # Dry-run "notifier" used when no webhook is configured (local testing).
    for posting in postings:
        print(f"PING  {posting.company_name} | {posting.title} | {posting.terms} | {posting.apply_url}")
    return postings, []


def run_once(seen_file_path=config.SEEN_POSTINGS_FILE, read_local_file=None, now_epoch=None,
             webhook_url=None) -> list:
    now_epoch = now_epoch or int(time.time())

    open_postings = fetch_all_open_postings(config.LISTING_SOURCES, read_local_file)
    matching_postings = keep_matching_postings(open_postings)        # sorted oldest -> newest

    seen_postings, stored_fingerprint = load_seen_postings(seen_file_path)
    current_fingerprint = compute_filter_fingerprint()
    is_first_run = len(seen_postings) == 0
    filter_was_edited = not is_first_run and stored_fingerprint != current_fingerprint
    new_postings = split_new_from_seen(matching_postings, seen_postings)

    if is_first_run or filter_was_edited:
        # First run, or you edited config.py: lots of OLD postings look new. Only ping recent ones.
        postings_to_ping = pick_postings_for_first_run(new_postings, config.FIRST_RUN_BACKFILL_HOURS, now_epoch)
        ping_ids = {posting.posting_id for posting in postings_to_ping}
        silently_skipped_postings = [posting for posting in new_postings if posting.posting_id not in ping_ids]
    else:
        postings_to_ping = new_postings
        silently_skipped_postings = []

    if webhook_url:
        sent_postings, rejected_postings = send_postings_to_discord(webhook_url, postings_to_ping)
    else:
        sent_postings, rejected_postings = print_instead_of_sending(postings_to_ping)

    # Remember only what was delivered (+ intentional skips + cards Discord can never display).
    # Anything that hit a temporary failure stays "new" and gets retried on the next run.
    remember_postings(seen_postings, silently_skipped_postings + sent_postings + rejected_postings, now_epoch)

    still_open_ids = {posting.posting_id for posting in matching_postings}
    forgotten_count = forget_very_old_entries(seen_postings, config.FORGET_SEEN_AFTER_DAYS, now_epoch, still_open_ids)
    save_seen_postings(seen_file_path, seen_postings, current_fingerprint)

    failed_count = len(postings_to_ping) - len(sent_postings) - len(rejected_postings)
    print(f"summary: matches={len(matching_postings)} new={len(new_postings)} pinged={len(sent_postings)} "
          f"failed={failed_count} rejected={len(rejected_postings)} first_run={is_first_run} "
          f"filter_edited={filter_was_edited} forgot={forgotten_count} memory_size={len(seen_postings)}")
    return sent_postings


if __name__ == "__main__":
    # The webhook URL is a secret: it comes from an environment variable (a GitHub Actions secret),
    # never from the code, because anyone holding it can post into your channel.
    discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    # On GitHub, a missing secret must be a loud failure. Otherwise the bot would "send" by
    # printing, mark everything as seen, commit that, and those pings would be lost for good.
    if os.environ.get("GITHUB_ACTIONS") == "true" and not discord_webhook_url:
        sys.exit("DISCORD_WEBHOOK_URL secret is missing or empty - add it under Settings > Secrets and variables > Actions")

    run_once(webhook_url=discord_webhook_url or None)
