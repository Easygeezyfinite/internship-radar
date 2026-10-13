"""
Layer 4: send postings to your own Discord channel through a webhook.

A webhook is just a secret URL. POST some JSON to it and a message appears in the channel.
No bot account, no login, nothing against Discord's rules (it's YOUR server).

Design choices:
  - One Discord message can hold up to 10 "embeds" (cards). We pack postings 10 per message,
    oldest -> newest, so the newest posting is always the last card at the bottom of the feed.
  - We return ONLY the postings Discord confirmed. main.py remembers just those, so anything
    that failed to send is retried automatically on the next run instead of being lost.
"""

import http.client
import json
import time
import urllib.error
import urllib.request

MAX_EMBEDS_PER_MESSAGE = 10        # Discord's limit
MAX_RATE_LIMIT_RETRIES = 3
PAUSE_BETWEEN_MESSAGES_SECONDS = 0.6  # webhooks allow ~5 requests / 2 seconds

# Color-code cards by term so you can scan the feed at a glance.
SUMMER_COLOR = 0x1D9E75    # teal
WINTER_COLOR = 0x378ADD    # blue
UNKNOWN_TERM_COLOR = 0x888780  # gray


def pick_card_color(terms: list) -> int:
    joined_terms = " ".join(terms)
    if "Summer" in joined_terms:
        return SUMMER_COLOR
    if "Winter" in joined_terms:
        return WINTER_COLOR
    return UNKNOWN_TERM_COLOR


def build_embed_for_posting(posting) -> dict:
    location_text = ", ".join(posting.locations[:3]) or "Not listed"
    if len(posting.locations) > 3:
        location_text += f" +{len(posting.locations) - 3} more"

    # <t:EPOCH:R> is Discord's own timestamp syntax: it renders as "12 minutes ago"
    # in YOUR timezone, and keeps counting up live. No timezone math needed on our side.
    posted_text = f"<t:{posting.date_posted_epoch}:R>" if posting.date_posted_epoch else "unknown"

    description_lines = [
        f"**Term:** {', '.join(posting.terms)}",
        f"**Where:** {location_text}",
        f"**Posted:** {posted_text}",
    ]
    if posting.sponsorship_flag == "Does Not Offer Sponsorship":
        description_lines.append("**Heads up:** says it does not offer sponsorship")

    return {
        "title": f"{posting.company_name} | {posting.title}"[:256],  # Discord caps titles at 256 chars
        "url": posting.apply_url,                                   # clicking the title opens the application
        "description": "\n".join(description_lines),
        "color": pick_card_color(posting.terms),
        "footer": {"text": f"via {posting.source_name}"},
    }


def post_json_to_webhook(webhook_url: str, payload: dict) -> tuple:
    """Returns (status_code, response_body_text). Never raises on HTTP errors."""
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            # Discord's firewall rejects Python's default "Python-urllib" user agent with a 403.
            "User-Agent": "internship-radar (personal job alert bot, 1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as http_error:
        return http_error.code, http_error.read().decode("utf-8", "replace")
    except (OSError, http.client.HTTPException) as network_error:
        # OSError covers URLError, timeouts, connection resets; HTTPException covers
        # RemoteDisconnected (Discord hanging up mid-response). Never let these crash the run.
        return 0, str(network_error)  # 0 = never reached Discord at all


# Three possible outcomes for one message:
SENT = "sent"            # Discord accepted it
REJECTED = "rejected"    # 400: Discord says THIS payload is invalid -> retrying the same thing never helps
FAILED = "failed"        # network, 5xx, rate limit exhausted, or a broken/deleted webhook (401/403/404) -> retry next run


def send_one_message_with_retries(webhook_url: str, payload: dict) -> str:
    for attempt_number in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        status_code, response_text = post_json_to_webhook(webhook_url, payload)

        if 200 <= status_code < 300:
            return SENT  # Discord answers 204 No Content on success

        if status_code == 429:
            # Rate limited. Discord tells us exactly how long to wait in "retry_after" (seconds).
            try:
                wait_seconds = float(json.loads(response_text).get("retry_after", 2))
            except (ValueError, AttributeError):
                wait_seconds = 2
            print(f"rate limited, waiting {wait_seconds:.1f}s (attempt {attempt_number})")
            time.sleep(min(wait_seconds, 30) + 0.25)
            continue

        print(f"discord send failed: status={status_code} body={response_text[:200]}")
        if status_code == 400:
            return REJECTED
        if status_code in (401, 403, 404):
            print("the webhook URL looks invalid or deleted - check the DISCORD_WEBHOOK_URL secret")
        return FAILED

    return FAILED


def send_postings_to_discord(webhook_url: str, postings: list) -> tuple:
    """
    Sends postings in chunks of 10, in the order given (oldest -> newest).
    Returns (sent_postings, rejected_postings).
      sent      -> Discord accepted them
      rejected  -> Discord said that posting's card is invalid (400); main.py remembers these too,
                   so one bad card can't block every future ping
    Anything in neither list hit a temporary failure and is retried next run.
    """
    sent_postings = []
    rejected_postings = []

    for chunk_start in range(0, len(postings), MAX_EMBEDS_PER_MESSAGE):
        posting_chunk = postings[chunk_start: chunk_start + MAX_EMBEDS_PER_MESSAGE]
        # sanity check: 23 postings -> chunks of 10, 10, 3

        chunk_outcome = send_one_message_with_retries(
            webhook_url, {"embeds": [build_embed_for_posting(posting) for posting in posting_chunk]})

        if chunk_outcome == SENT:
            sent_postings.extend(posting_chunk)
        elif chunk_outcome == REJECTED:
            # Something in this chunk is invalid. Send the cards one at a time to find which.
            for posting in posting_chunk:
                single_outcome = send_one_message_with_retries(webhook_url, {"embeds": [build_embed_for_posting(posting)]})
                if single_outcome == SENT:
                    sent_postings.append(posting)
                elif single_outcome == REJECTED:
                    print(f"skipping a posting Discord can't display: {posting.company_name} | {posting.title}")
                    rejected_postings.append(posting)
                else:
                    return sent_postings, rejected_postings
                time.sleep(PAUSE_BETWEEN_MESSAGES_SECONDS)
        else:
            # Stop here instead of skipping ahead: if chunk 2 failed and chunk 3 succeeded,
            # the retry next run would land ABOVE chunk 3 and break newest-at-the-bottom order.
            break

        time.sleep(PAUSE_BETWEEN_MESSAGES_SECONDS)

    return sent_postings, rejected_postings
