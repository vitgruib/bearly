# bearly

Everything happening around Berkeley in one filterable list: talks, hackathons, parties,
club meetings, free food. A scraper pulls from every place student events get posted,
merges duplicates, tags each event by topic and area, and writes one JSON file. A static
page lets students filter it.

## Sources

| Source | How | Needs |
| --- | --- | --- |
| Luma | `api.lu.ma` discover feed around campus, plus club calendars listed in `sources.toml` | nothing |
| Eventbrite | search pages for Berkeley and Oakland (embedded `__SERVER_DATA__`) | nothing |
| Cerebral Valley | `/events` JSON-LD | nothing |
| Partiful | Bay Area "trending" on `/explore`, plus any `partiful.com/e/…` link seen elsewhere | nothing |
| UC Berkeley Events | events.berkeley.edu LiveWhale JSON API (gym hours and daily exhibits filtered out) | nothing |
| Club calendars | any public iCal feed, e.g. a club's Google Calendar, listed under `[ics]` | nothing |
| Mailing lists | IMAP inbox subscribed to listservs | `IMAP_USER`, `IMAP_PASSWORD` |
| Slack | channels the bot is in, across any number of workspaces | `SLACK_TOKENS` |

Emails and Slack posts go through two passes. First, every Luma, Partiful, Eventbrite,
Cerebral Valley or Meetup link in the message is fetched as a full event; a Luma
*calendar* link expands to all of that calendar's upcoming events. Second, if
`ANTHROPIC_API_KEY` is set, Claude reads the text for events announced with no link
("GBM Thursday 7pm in Soda 306, pizza!"). Each message is sent once; results are cached in
`data/llm_cache.json`.

The same event reached from several places is merged into one record. The structured
platform listing wins, and the card shows every source it came from.

## Run it

```sh
uv sync
uv run python -m scraper.run              # all sources -> site/data/events.json
uv run python -m scraper.run luma slack   # just these; the rest keep their last results
python3 -m http.server -d site 8000       # open http://localhost:8000
uv run pytest
```

A source that errors keeps its events from the previous run, so one flaky site never
empties the page. Per-source status is written into `events.json` and shown in the footer.

## Deploy

`.github/workflows/scrape.yml` runs every 3 hours. It runs the tests, scrapes, commits the
refreshed data and publishes `site/` to GitHub Pages. To turn it on:

1. Push the repo to GitHub and set **Settings → Pages → Source** to **GitHub Actions**.
2. Add whichever secrets you want under **Settings → Secrets → Actions**:
   - `ANTHROPIC_API_KEY`: reads free-text announcements in emails and Slack.
   - `IMAP_USER` / `IMAP_PASSWORD` (and `IMAP_HOST` if not Gmail): use a dedicated Gmail
     account with a [Gmail app password](https://myaccount.google.com/apppasswords).
     Subscribe it to the listservs (club lists, department lists, `@lists.berkeley.edu`).
     Add a filter that labels them `events`, the folder named in `sources.toml`.
   - `SLACK_TOKENS`: comma-separated bot tokens, one per workspace, with the
     `channels:read` and `channels:history` scopes. Invite the bot to a channel to start
     reading it.

## Adding a source

Add a module under `scraper/sources/` with a `fetch(cfg) -> list[Event]` function, register
it in `SOURCES` in `scraper/run.py`, and give it a section in `sources.toml`. Region, topic
tags, dedupe and the frontend all work from the normalized `Event`, so nothing else
changes.

To add a club, put its Luma slug under `[luma] calendars` or its iCal URL under
`[ics] feeds`.
