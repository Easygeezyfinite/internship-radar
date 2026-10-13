"""
End-to-end test against a FAKE Discord webhook running on your own machine.
    python tests/test_with_fake_discord.py <folder with simplify.json and vansh.json>

The fake server answers each incoming message with whatever we queue up: 204 (ok), 429 (rate
limited), 400 (bad card), 404 (deleted webhook), 500 (outage) or "drop" (hang up mid-request).
It proves:
  1. temporary failures are NOT remembered and get retried next run
  2. nothing is ever delivered twice, and order stays oldest -> newest
  3. one invalid card can't block every future ping
  4. a deleted webhook loses nothing
  5. editing the filter doesn't flood you with old postings
  6. a missing secret on GitHub fails loudly instead of silently marking everything as sent
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
from radar import config, discord_notifier
from radar.main import run_once
from radar.sources import normalize_raw_listing, is_open_and_visible, url_without_tracking
from radar.filters import keep_matching_postings

discord_notifier.PAUSE_BETWEEN_MESSAGES_SECONDS = 0  # keep the test fast

delivered_titles = []          # every card the fake Discord ACCEPTED, in arrival order
planned_responses = []         # queue of responses; empty -> 204


class FakeDiscordHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        planned = planned_responses.pop(0) if planned_responses else 204
        if planned == "drop":
            self.close_connection = True
            return  # hang up without answering -> client sees RemoteDisconnected
        if planned == 204:
            delivered_titles.extend(embed["title"] for embed in body["embeds"])
            self.send_response(204)
            self.end_headers()
            return
        self.send_response(planned)
        self.end_headers()
        self.wfile.write(json.dumps({"retry_after": 0.1, "message": "fake"}).encode())

    def log_message(self, *args):
        pass  # silence default request logging


fake_server = HTTPServer(("127.0.0.1", 0), FakeDiscordHandler)
threading.Thread(target=fake_server.serve_forever, daemon=True).start()
fake_webhook_url = f"http://127.0.0.1:{fake_server.server_port}/webhook"

# --- data setup: hold back 4 groups of the newest matches and "post" them one group at a time
local_data_folder = sys.argv[1]
all_raw = {name: json.load(open(f"{local_data_folder}/{name}.json")) for name in config.LISTING_SOURCES}
simplify_open = [normalize_raw_listing(raw, "simplify") for raw in all_raw["simplify"] if is_open_and_visible(raw)]
newest_matches = keep_matching_postings(simplify_open)
group_a = newest_matches[-23:]        # rate limit + outage test
group_b = newest_matches[-26:-23]     # bad-card (400) test
group_c = newest_matches[-29:-26]     # dropped connection, then deleted webhook
hidden_ids = {posting.posting_id for posting in group_a + group_b + group_c}
now_epoch = max(posting.date_posted_epoch for posting in simplify_open)


def card_title(posting):
    return f"{posting.company_name} | {posting.title}"[:256]


def visible_listings(source_name):
    return [raw for raw in all_raw[source_name] if url_without_tracking(raw["url"]) not in hidden_ids]


def reveal(group):
    hidden_ids.difference_update(posting.posting_id for posting in group)


def run(minutes_later, responses=()):
    delivered_titles.clear()
    planned_responses[:] = list(responses)
    return run_once(memory_file, visible_listings, now_epoch + minutes_later * 60, fake_webhook_url)


memory_file = os.path.join(PROJECT_DIR, "test_memory.json")
if os.path.exists(memory_file):
    os.remove(memory_file)

print("=== run 1: first run, Discord healthy")
run(0)

print("\n=== run 2: 23 new -> messages of 10, 10, 3. msg 2 rate limited once, msg 3 hits a 500")
reveal(group_a)
sent = run(15, [204, 429, 204, 500])
assert len(sent) == 20 and delivered_titles == [card_title(p) for p in group_a[:20]]

print("\n=== run 3: healthy -> only the 3 failed ones are sent")
sent = run(30)
assert delivered_titles == [card_title(p) for p in group_a[20:]]

print("\n=== run 4: nothing new -> nothing sent")
assert run(45) == []

print("\n=== run 5: 3 new, Discord rejects the chunk (400); singles: ok, bad card, ok")
reveal(group_b)
sent = run(60, [400, 204, 400, 204])
assert [card_title(p) for p in sent] == [card_title(group_b[0]), card_title(group_b[2])]

print("\n=== run 6: the bad card is skipped for good, it doesn't block anything")
assert run(75) == []

print("\n=== run 7: 3 new, Discord hangs up mid-request (used to crash the whole run)")
reveal(group_c)
assert run(90, ["drop"]) == []

print("\n=== run 8: webhook was deleted (404) -> nothing lost, nothing marked seen")
assert run(105, [404]) == []

print("\n=== run 9: webhook fixed -> the 3 held-back postings finally arrive, in order")
sent = run(120)
assert delivered_titles == [card_title(p) for p in group_c]

print("\n=== run 10: you add 'data science' to config.py -> old postings must NOT flood in")
config.ROLE_KEYWORDS.append("data science")
before_count = len(json.load(open(memory_file))["seen"])
sent = run(135)
after_count = len(json.load(open(memory_file))["seen"])
newly_matching = after_count - before_count
print(f"   newly matching postings: {newly_matching}, pinged: {len(sent)} (only the last {config.FIRST_RUN_BACKFILL_HOURS}h)")
assert newly_matching > 20 and len(sent) < newly_matching
assert all(p.date_posted_epoch >= now_epoch + 135 * 60 - config.FIRST_RUN_BACKFILL_HOURS * 3600 for p in sent)
config.ROLE_KEYWORDS.remove("data science")

os.remove(memory_file)
fake_server.shutdown()

print("\n=== missing secret on GitHub must fail loudly, before touching memory")
guard_check = subprocess.run(
    [sys.executable, "-m", "radar.main"], cwd=PROJECT_DIR, capture_output=True, text=True,
    env={**os.environ, "GITHUB_ACTIONS": "true", "DISCORD_WEBHOOK_URL": ""})
assert guard_check.returncode != 0 and "secret is missing" in guard_check.stderr
assert not os.path.exists(os.path.join(PROJECT_DIR, "seen_postings.json"))
print("   exited with:", guard_check.stderr.strip())

print("\nALL CHECKS PASSED")
