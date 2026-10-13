# internship-radar

Pings a Discord channel within ~15 minutes of a new Summer 2027 / Winter 2027 SWE, backend or ML
internship being posted, so you can apply while you're still in the first batch a recruiter reads.

Runs free on GitHub Actions. Nothing runs on your own computer.

## How it works

```
GitHub Actions (every 15 min)
  └─ radar/main.py
       1. sources.py          download listings.json from SimplifyJobs + vanshb03 repos, normalize, dedupe by link
       2. filters.py          keep: wanted term, SWE/ML title, bachelor's OK, no US-citizenship requirement
       3. seen_store.py       new = matches - already sent   (memory lives in seen_postings.json)
       4. discord_notifier.py send new ones, 10 cards per message, oldest -> newest (newest at bottom)
       5. remember ONLY what Discord confirmed -> failed sends retry next run
  └─ commit seen_postings.json back to the repo
```

## Setup (about 10 minutes)

1. **Discord webhook.** In your own Discord server: Server Settings → Integrations → Webhooks →
   New Webhook → pick a channel (e.g. `#internships`) → Copy Webhook URL.
   On your phone, set that channel's notifications to "All messages".
2. **GitHub repo.** Create a **public** repo named `internship-radar` (public = unlimited free
   Actions minutes) and push this folder to it, including the hidden `.github` folder.
3. **Secret.** In the repo: Settings → Secrets and variables → Actions → New repository secret.
   Name `DISCORD_WEBHOOK_URL`, value = the URL from step 1. Never commit the URL itself.
4. **First run.** Actions tab → internship-radar → Run workflow. You'll get the last 48 hours of
   matches; older open postings are marked as seen silently (browse those on the repos once).
   After that it runs by itself every 15 minutes.

Editing `radar/config.py` later is safe: the bot notices the filter changed and only pings
newly-matching postings from the last 48 hours instead of flooding you with old ones.

If GitHub ever emails you that a scheduled workflow was disabled, re-enable it from the Actions tab.

## Changing what it looks for

Everything is in `radar/config.py`: terms, title keywords, excluded words, memory length.

## Testing locally (no Discord needed)

```
python try_layer_one.py                                   # what matches right now
python tests/test_with_fake_discord.py <data folder>      # failure/retry test with a fake webhook
python -m radar.main                                      # no DISCORD_WEBHOOK_URL set = prints instead of sending
```
