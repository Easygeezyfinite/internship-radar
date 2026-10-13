"""
Everything you'd want to tweak lives here, so the rest of the code never changes
when your targets do.
"""

import calendar

# Each source is a GitHub repo whose listings.json is kept fresh by its maintainers.
# raw.githubusercontent.com serves the file directly - no API key, no scraping.
LISTING_SOURCES = {
    "simplify": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    "vansh": "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json",
}

# Simplify tags terms with a year ("Winter 2027"); vansh only gives a season ("Winter").
# So we match on BOTH the exact term and the bare season word.
WANTED_TERMS = {"Summer 2027", "Winter 2027"}
WANTED_SEASONS_WITHOUT_YEAR = {"Summer", "Winter"}
# A bare "Winter" could be last cycle's job, so bare-season rows must be posted on/after this date.
BARE_SEASON_POSTED_AFTER_EPOCH = calendar.timegm((2026, 5, 1, 0, 0, 0))
KEEP_POSTINGS_WITH_UNKNOWN_TERM = True  # Simplify uses "N/A" a lot (e.g. big-tech research interns)

# A title must hit at least one of these to count as "my kind of role".
# Matched as WHOLE words (see filters.py), so "ai" won't fire on "maintenance".
ROLE_KEYWORDS = [
    # general SWE / backend
    "software", "swe", "backend", "back-end", "back end", "full stack", "full-stack", "fullstack",
    "frontend", "developer", "platform", "infrastructure", "distributed systems", "cloud",
    "forward deployed", "compiler", "mobile engineer", "ios", "android",
    "database engineer", "performance engineer", "linux engineer",
    # ML / AI
    "machine learning", "ml", "ai", "artificial intelligence", "llm", "computer vision",
    "deep learning", "research engineer", "applied scientist", "mlops",
    # data + automation
    "data engineer", "data engineering", "automation",
]

# ...and must NOT hit any of these (roles that match a keyword above but aren't SWE/ML).
EXCLUDED_TITLE_KEYWORDS = [
    # hardware
    "analog", "mixed-signal", "mixed signal", "ic design", "asic", "fpga", "rf", "pcb", "rtl",
    # other engineering disciplines (full phrases, so "Manufacturing Software Developer" still passes)
    "mechanical", "electrical", "civil engineer", "civil engineering", "chemical",
    "manufacturing engineer", "manufacturing engineering", "process automation",
    # non-engineering roles that sneak in through "ai" / "platform"
    "product manager", "product management", "product operations",
    "phd", "ph.d", "mba", "marketing", "sales", "recruiting", "accounting",
]

# Layer 2 (memory) settings
SEEN_POSTINGS_FILE = "seen_postings.json"
FIRST_RUN_BACKFILL_HOURS = 48      # first run pings the last 2 days (Simplify rounds many dates to midnight)
FORGET_SEEN_AFTER_DAYS = 30        # forget closed postings after this; open ones are always kept

# Postings flagged this way are a hard no for a Canadian applicant.
DEALBREAKER_SPONSORSHIP_FLAGS = {"U.S. Citizenship is Required"}
