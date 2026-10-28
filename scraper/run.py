"""Scrape every enabled source, normalize, dedupe, and write site/data/events.json.

    uv run python -m scraper.run            # all sources in sources.toml
    uv run python -m scraper.run luma ics   # just these
"""

import json
import logging
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import extract
from .dedupe import dedupe
from .enrich import REGIONS, TOPICS, enrich
from .models import Event, parse_dt
from .sources import (
    berkeley_calendar,
    cerebral_valley,
    email_inbox,
    eventbrite,
    ics,
    luma,
    partiful,
    slack,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data" / "events.json"
log = logging.getLogger("scraper")

SOURCES = {
    "luma": ("Luma", luma),
    "eventbrite": ("Eventbrite", eventbrite),
    "cerebral_valley": ("Cerebral Valley", cerebral_valley),
    "partiful": ("Partiful", partiful),
    "berkeley_calendar": ("UC Berkeley Events", berkeley_calendar),
    "ics": ("Club calendars", ics),
    "email": ("Mailing lists", email_inbox),
    "slack": ("Slack", slack),
}


def _run_one(name: str, cfg: dict) -> tuple[str, list[Event], dict]:
    t0 = time.monotonic()
    try:
        events = SOURCES[name][1].fetch(cfg)
        status = {"ok": True, "count": len(events)}
    except Exception as exc:  # noqa: BLE001 -- a broken source is reported, not fatal
        msg = str(exc)
        skipped = msg.startswith("not configured")
        (log.info if skipped else log.exception)("%s: %s", name, msg)
        events, status = [], {"ok": False, "skipped": skipped, "error": msg[:200]}
    status["seconds"] = round(time.monotonic() - t0, 1)
    return name, events, status


def _previous(name: str) -> list[Event]:
    """Last run's events from a source, so one flaky scrape doesn't empty the site."""
    try:
        old = json.loads(OUT.read_text())["events"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return []
    keep = []
    for d in old:
        if d["source"] != name:
            continue
        keep.append(Event(**{k: v for k, v in d.items() if k not in ("id", "start", "end")},
                          start=parse_dt(d["start"]),
                          end=parse_dt(d["end"]) if d.get("end") else None))
    return keep


def build(events: list[Event], days_ahead: int, now: datetime) -> list[Event]:
    horizon = now + timedelta(days=days_ahead)
    upcoming = []
    for e in events:
        ends = e.end or e.start + timedelta(hours=2)
        # Multi-week "events" (programs, exhibits, month-long hackathons) aren't plans.
        if ends < now or e.start > horizon or (ends - e.start) > timedelta(days=12):
            continue
        if enriched := enrich(e):
            upcoming.append(enriched)
    merged = dedupe(upcoming)
    merged.sort(key=lambda e: (e.start, e.title))
    return merged


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = tomllib.loads((ROOT / "sources.toml").read_text())
    wanted = argv or [n for n in SOURCES if config.get(n, {}).get("enabled", True)]
    with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
        results = list(pool.map(lambda n: _run_one(n, config.get(n, {})), wanted))

    events, statuses = [], []
    for name, found, status in results:
        if not status["ok"] and not status.get("skipped"):
            found = _previous(name)
            status["stale"] = len(found)
        events += found
        statuses.append({"id": name, "name": SOURCES[name][0], **status})
        log.info("%-18s %s", name, status)
    if argv:  # a partial run keeps everything else from the last full run
        try:
            old_statuses = json.loads(OUT.read_text())["sources"]
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            old_statuses = []
        for old in old_statuses:
            if old["id"] not in wanted:
                events += _previous(old["id"])
                statuses.append(old)

    now = datetime.now(UTC)
    final = build(events, config.get("days_ahead", 30), now)
    extract.save_cache()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": now.isoformat(timespec="seconds"),
        "sources": statuses,
        "regions": REGIONS,
        "topics": list(TOPICS),
        "events": [e.to_json() for e in final],
    }, ensure_ascii=False, separators=(",", ":")))
    log.info("wrote %d events (from %d raw) to %s", len(final), len(events), OUT)


if __name__ == "__main__":
    main(sys.argv[1:])
