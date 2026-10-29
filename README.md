# Bearly Missed

Berkeley's open-source calendar. Everything happening around Berkeley in one filterable
list: talks, hackathons, parties, club meetings, free food. Anyone can add a calendar or
report a listing ([Adding a source](#adding-a-source)), no code needed. A scraper pulls from every place student events get posted,
merges duplicates, tags each event by topic and area, and publishes one JSON file. A static
page lets students filter it.

Live: https://vitgruib.github.io/bearly/

## Sources

| Source | How | Needs |
| --- | --- | --- |
| Luma | discover feed and AI/Tech/Climate/Arts category feeds around campus; ~25 Bay Area tech calendars, ~25 campus org calendars and ~17 org profiles that post from a personal account; plus every org calendar that hosts near campus, **found automatically** | nothing |
| UC Berkeley Events | events.berkeley.edu LiveWhale JSON API (gym hours and daily exhibits filtered out) | nothing |
| Calendar feeds | ~62 feeds in `sources.toml` `[[feeds.list]]`: Law, Haas, Botanical Garden, Simons, iSchool, Cal Athletics home games, ASUC, Graduate Assembly, BAMPFA, Berkeley Public Library, OMCA, Funcheap, the Haas clubs CampusGroups feed (~40 clubs), and ~48 public student-org Google Calendars found through CalLink and OCF club sites. Types: ics, rss, jsonld, tribe, localist, fullcalendar | nothing |
| Cerebral Valley | its public API, every approved Bay Area event | nothing |
| Hackathons | Devpost (only hackathons whose window is the event itself, not a month-long submission period), YC events, MLH, AGI House; Bay Area in-person only | nothing |
| Music & venues | Ashkenaz, Ivy Room (VenuePilot), Fox, Greek, UC Theatre, Resident Advisor, and 17 East Bay venues on DoTheBay | nothing |
| Partiful | Bay Area "trending" on `/explore`, plus any `partiful.com/e/…` link seen elsewhere | nothing |
| Instagram | ~850 student-org accounts (`clubs/instagram.txt`, from CalLink) via Apify; captions parsed for date/time/place | `APIFY_TOKEN` |
| Mailing lists | IMAP inbox subscribed to listservs | `IMAP_USER`, `IMAP_PASSWORD` |
| Added by students | single events sent through the form or an "Add an event" issue, once a maintainer approves them (`contributed/events.toml`) | nothing |
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
- **Nothing broken ships.** Before every deploy, `scraper/smoke.py` loads both pages in
  headless Chromium at desktop and phone width: no uncaught errors, events and every filter
  row render, filters respond, no sideways scroll, and the event count hasn't fallen below
  half the last published one. A failure skips the deploy and the last good site stays up.
  `scraper/stamp.py` versions asset URLs by content hash so no browser mixes old and new files.
- **Keepalive.** GitHub disables cron workflows after 60 days without commits; the
  workflow re-enables itself every run.

## Run it

```sh
uv sync
uv run python -m scraper.run              # every source that is due
uv run python -m scraper.run luma feeds   # force just these; the rest keep last results
python3 -m http.server -d site 8000       # open http://localhost:8000
uv run pytest
uv run playwright install chromium && uv run python -m scraper.smoke   # what CI runs before deploying
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

Anyone, no code, and nothing goes up until a maintainer adds the `approved` label:

- [Add a source](https://github.com/vitgruib/bearly/issues/new?template=add-source.yml): a
  calendar link. `.github/workflows/community.yml` runs `scraper/contribute.py`, which
  recognizes the feed (Google Calendar share links become their iCal address; Luma, .ics, RSS,
  WordPress, Localist and schema.org pages are detected), fetches it once and replies with the
  events it found. Approved, it's saved as `contributed/<name>.toml`, committed, and a scrape
  starts. Only feed types the scraper already parses are accepted, so nothing a stranger
  submits runs as code.
- [Add an event](https://github.com/vitgruib/bearly/issues/new?template=add-event.yml): one
  event link. The bot replies with a preview, or closes the issue if the site already lists it.
  Approved, the link goes in `contributed/events.toml` and is re-read every run.
- **Report**: each event's Report link opens a prefilled issue. Approved, the event's id goes in
  `moderation.toml`, which hides it from then on.

No GitHub account? One Google Form (`[community]` in `sources.toml`) covers all three plus
feedback. Forms can't trigger GitHub, so every 30 minutes the workflow reads the form's
published response sheet and files new rows as the same issues (feedback gets a `feedback`
label), with the bot's check as a comment. The submitter gets no reply, which is why the site
calls GitHub the fast path.

By hand: add a `[[feeds.list]]` entry, or a Luma slug under
`[luma] calendars`, or an Instagram handle to `clubs/instagram.txt`.

A new kind of site: add a module under `scraper/sources/` with
`fetch(cfg, ctx) -> list[Event]` (`ctx` carries the run clock, a persistent `memory` dict
and `warn()`), register it in `scraper/registry.py`, and give it a section in
`sources.toml`. Region, topic tags, dedupe and the frontend all work from the normalized
`Event`, so nothing else changes.
