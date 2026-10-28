# bearly

Everything happening around Berkeley in one filterable list: talks, hackathons, parties,
club meetings, free food. A scraper pulls from every place student events get posted,
merges duplicates, tags each event by topic and area, and publishes one JSON file. A static
page lets students filter it.

Live: https://vitgruib.github.io/bearly/

## Sources

| Source | How | Needs |
| --- | --- | --- |
| Luma | discover feed and AI/Tech/Climate/Arts category feeds around campus; ~25 Bay Area tech calendars; plus every org calendar that hosts near campus, **found automatically** | nothing |
| UC Berkeley Events | events.berkeley.edu LiveWhale JSON API (gym hours and daily exhibits filtered out) | nothing |
| Calendar feeds | ~55 feeds in `sources.toml` `[[feeds.list]]`: Law, Haas, Botanical Garden, Simons, iSchool, Cal Athletics home games, ASUC, Graduate Assembly, BAMPFA, Berkeley Public Library, OMCA, Chabot, Funcheap, and 37 public student-org Google Calendars found through CalLink. Types: ics, rss, jsonld, tribe, localist, fullcalendar | nothing |
| Cerebral Valley | its public API, every approved Bay Area event | nothing |
| Eventbrite | search pages for Berkeley and Oakland | nothing |
| Hackathons | Devpost (only hackathons whose window is the event itself, not a month-long submission period), YC events, MLH, AGI House; Bay Area in-person only | nothing |
| Partiful | Bay Area "trending" on `/explore`, plus any `partiful.com/e/…` link seen elsewhere | nothing |
| Instagram | ~850 student-org accounts (`clubs/instagram.txt`, from CalLink) via Apify; captions parsed for date/time/place | `APIFY_TOKEN` |
| Mailing lists | IMAP inbox subscribed to listservs | `IMAP_USER`, `IMAP_PASSWORD` |
| Slack | channels the bot is in, across any number of workspaces | `SLACK_TOKENS` |

Emails, Slack posts, RSS items and Instagram captions go through two passes, both free.
First, every Luma, Partiful, Eventbrite, Cerebral Valley or Meetup link in the text is
fetched as a full event; a Luma *calendar* link expands to all of its upcoming events.
Second, a rule-based parser (`scraper/textparse.py`) reads announcements with no link
("GBM Thursday 10/29 7pm in Soda 306, pizza!"): dates, times, campus buildings, free food.

The same event reached from several places is merged into one record. The structured
platform listing wins, and the card shows every source it came from.

## How it stays running

- **The published site is the database.** Each CI run downloads the last published
  `data/events.json` and `data/state.json`, scrapes, and publishes again. Nothing is
  committed back to the repo, so history stays clean and there is no data merge conflict.
- **Per-source schedules.** The workflow wakes every 3 hours; each source runs only when
  due (`every_hours` in `scraper/registry.py`, overridable in `sources.toml`). Sources not
  due reuse their last events without a single request.
- **Polite HTTP.** One shared client spaces requests per host, retries 429/5xx with
  backoff honouring `Retry-After`, and revalidates calendar feeds with ETag /
  Last-Modified (the cache persists across runs via `actions/cache`).
- **Failure isolation.** A source that errors keeps serving its last good events. One
  broken feed inside a source is a warning, not a failure.
- **Health and alerts.** `state.json` tracks each source's health: `failing`, `down`
  (3+ failures in a row), or `degraded` (far fewer events than usual, the usual sign a page
  changed). Down or degraded sources open a `source-health` GitHub issue, which closes
  itself on recovery.
- **Cost cap.** Instagram is the only paid source. It reads accounts in rotating slices,
  asks only for posts since that slice was last read, and stops for the month at
  `monthly_budget_usd` (Apify also enforces a per-run cap server-side).
- **Keepalive.** GitHub disables cron workflows after 60 days without commits; the
  workflow re-enables itself every run.

## Run it

```sh
uv sync
uv run python -m scraper.run              # every source that is due
uv run python -m scraper.run luma feeds   # force just these; the rest keep last results
python3 -m http.server -d site 8000       # open http://localhost:8000
uv run pytest
```

## Secrets

Add under **Settings → Secrets → Actions** (or `gh secret set NAME`). Every source without
its secret skips itself quietly.

- `APIFY_TOKEN`: Instagram via Apify's Instagram Post Scraper.
- `IMAP_USER` / `IMAP_PASSWORD` (and `IMAP_HOST` if not Gmail): use a dedicated Gmail
  account with a [Gmail app password](https://myaccount.google.com/apppasswords).
  Subscribe it to club and department listservs. Add a filter that labels them `events`,
  the folder named in `sources.toml`.
- `SLACK_TOKENS`: comma-separated bot tokens, one per workspace, with the
  `channels:read` and `channels:history` scopes. Invite the bot to a channel to start
  reading it.

## Adding a source

A club or venue with a calendar: add a `[[feeds.list]]` entry, or a Luma slug under
`[luma] calendars`, or an Instagram handle to `clubs/instagram.txt`.

A new kind of site: add a module under `scraper/sources/` with
`fetch(cfg, ctx) -> list[Event]` (`ctx` carries the run clock, a persistent `memory` dict
and `warn()`), register it in `scraper/registry.py`, and give it a section in
`sources.toml`. Region, topic tags, dedupe and the frontend all work from the normalized
`Event`, so nothing else changes.
