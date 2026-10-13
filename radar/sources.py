"""
Layer 1a: fetch each repo's listings.json and normalize it into one Posting shape.

Why normalize? The two repos store the same idea differently:
    simplify -> {"terms": ["Winter 2027"], "category": "Software", "degrees": [...]}
    vansh    -> {"season": "Winter"}   (no year, no category, no degrees)
Every later layer (filter, scorer, notifier) should only ever see ONE shape.
"""

import json
import urllib.request
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from dataclasses import dataclass, field


@dataclass
class Posting:
    posting_id: str          # stable unique key - later used to remember "already seen"
    source_name: str         # "simplify" or "vansh"
    company_name: str
    title: str
    apply_url: str
    locations: list
    terms: list              # always a list of strings, e.g. ["Winter 2027"] or ["Winter"]
    date_posted_epoch: int   # seconds since 1970 - lets us sort newest first
    sponsorship_flag: str    # e.g. "Other", "U.S. Citizenship is Required"
    degrees: list = field(default_factory=list)


def download_listings_json(url: str) -> list:
    # The Simplify file is ~13 MB. Fine for GitHub Actions; we just read it once per run.
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def normalize_raw_listing(raw_listing: dict, source_name: str) -> Posting:
    # simplify has "terms" (list); vansh has "season" (single string, sometimes None or the text "null").
    raw_season = raw_listing.get("season")
    if raw_listing.get("terms"):
        terms_list = raw_listing["terms"]
    elif raw_season and str(raw_season).strip().lower() != "null":
        terms_list = [str(raw_season).strip()]
    else:
        terms_list = ["N/A"]
    # sanity check: {"season": "Winter"} -> ["Winter"];  {"season": "null"} -> ["N/A"]

    return Posting(
        # Identity = the cleaned apply link, NOT "<repo>:<repo's id>". The same job listed in both
        # repos (or twice in one repo) must count as ONE job, or memory treats copies as new.
        posting_id=url_without_tracking(raw_listing["url"]),
        source_name=source_name,
        company_name=raw_listing["company_name"].strip(),
        title=raw_listing["title"].strip(),
        apply_url=raw_listing["url"],
        locations=raw_listing.get("locations") or [],
        terms=terms_list,
        date_posted_epoch=int(raw_listing.get("date_posted") or 0),
        sponsorship_flag=raw_listing.get("sponsorship") or "Other",
        degrees=raw_listing.get("degrees") or [],
    )


def is_open_and_visible(raw_listing: dict) -> bool:
    # Closed roles stay in the file forever (that's how the README shows the lock icon),
    # so most of the ~17k rows are dead. Only "active" + "is_visible" are applyable.
    # "is not False" so a missing OR None is_visible still counts as visible.
    return raw_listing.get("active") is True and raw_listing.get("is_visible") is not False


def url_without_tracking(url: str) -> str:
    # Same job can appear in both repos with different ?utm_source=... tails, so drop those.
    # But DON'T drop the whole query string: for links like
    #   boards.greenhouse.io/embed/job_app?token=6865687002
    # the query IS the job id. (Bug caught by simulate_three_runs.py.)
    parsed_url = urlsplit(url.strip())
    kept_query_params = [(key, value) for key, value in parse_qsl(parsed_url.query) if not key.lower().startswith("utm_")]
    host = parsed_url.netloc.lower()
    # Greenhouse serves the same job on two hostnames; treat them as one.
    if host == "boards.greenhouse.io":
        host = "job-boards.greenhouse.io"
    cleaned_url = urlunsplit((parsed_url.scheme.lower(), host, parsed_url.path.rstrip("/"), urlencode(kept_query_params), ""))
    return cleaned_url
    # sanity check: ".../jobs/123?utm_source=github" -> ".../jobs/123"
    #               ".../job_app?token=686" -> ".../job_app?token=686"
    #               "boards.greenhouse.io/x/jobs/1" == "job-boards.greenhouse.io/x/jobs/1"


def fetch_all_open_postings(listing_sources: dict, read_local_file=None) -> list:
    """
    Returns one de-duplicated list of open postings across every source.
    read_local_file lets us test offline with already-downloaded JSON files.
    """
    open_postings = []
    already_seen_urls = set()  # dedupe across repos by apply URL

    for source_name, source_url in listing_sources.items():
        raw_listings = read_local_file(source_name) if read_local_file else download_listings_json(source_url)
        skipped_malformed_count = 0

        for raw_listing in raw_listings:
            if not is_open_and_visible(raw_listing):
                continue
            try:
                posting = normalize_raw_listing(raw_listing, source_name)
            except (KeyError, TypeError, ValueError, AttributeError):
                # One broken row upstream (missing url, title=None, ...) must not crash every run.
                skipped_malformed_count += 1
                continue
            if posting.posting_id in already_seen_urls:   # posting_id IS the cleaned url
                continue  # first source wins; simplify is listed first because its data is richer
            already_seen_urls.add(posting.posting_id)
            open_postings.append(posting)

        if skipped_malformed_count:
            print(f"warning: skipped {skipped_malformed_count} malformed rows from {source_name}")

    return open_postings
