"""Scrape every due source, normalize, dedupe, and write site/data/events.json + state.json.

    uv run python -m scraper.run            # every source that is due per its schedule
    uv run python -m scraper.run luma ics   # force just these; the rest keep last results
"""

import json
import logging
import re
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import http
from .dedupe import collapse_repeats, dedupe
from .enrich import REGIONS, TOPICS, enrich
from .models import Event
from .registry import SOURCES
from .state import EVENTS, ROOT, Context, NotConfigured, State, now_utc

log = logging.getLogger("scraper")
PACIFIC = ZoneInfo("America/Los_Angeles")
# "FULL | Bird Walk", "POSTPONED ...", and Google Calendar's free/busy-only "Busy" blocks.
PLACEHOLDER = re.compile(r"^(?:full|postponed|sold out)\b|\bcancel+ed\b|^busy$", re.IGNORECASE)
# CampusGroups hides locations from signed-out readers behind this text.
NO_VENUE = re.compile(r"^(?:sign in to|tbd$|tba$)", re.IGNORECASE)


def _run_one(name: str, cfg: dict, ctx: Context) -> tuple[list[Event] | None, str | None]:
    try:
        return SOURCES[name].module.fetch(cfg, ctx), None
    except NotConfigured:
        raise
    except Exception as exc:  # a broken source is reported, not fatal
        log.exception("%s failed", name)
        return None, f"{type(exc).__name__}: {exc}"


def build(events: list[Event], days_ahead: int, now: datetime) -> list[Event]:
    horizon = now + timedelta(days=days_ahead)
    upcoming = []
    for e in events:
        ends = e.end or e.start + timedelta(hours=2)
        # Multi-week "events" (programs, exhibits, month-long hackathons) aren't plans.
        if ends < now or e.start > horizon or (ends - e.start) > timedelta(days=12):
            continue
        if PLACEHOLDER.search(e.title):
            continue
        if e.venue and NO_VENUE.search(e.venue):
            e.venue = None
        local = e.start.astimezone(PACIFIC)
        if not e.all_day and local.hour == local.minute == 0 and e.end is None:
            e.all_day = True  # a date with no time, stored as midnight
        if enriched := enrich(e):
            upcoming.append(enriched)
    merged = dedupe(upcoming)
    merged.sort(key=lambda e: (e.start, e.title))
    return collapse_repeats(merged)


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = tomllib.loads((ROOT / "sources.toml").read_text())
    state = State()
    now = now_utc()

    enabled = [n for n in SOURCES if config.get(n, {}).get("enabled", True)]
    if unknown := set(argv) - set(SOURCES):
        raise SystemExit(f"unknown sources: {', '.join(sorted(unknown))}")
    if argv:
        to_run = argv
    else:
        to_run = [n for n in enabled
                  if state.due(n, config.get(n, {}).get("every_hours", SOURCES[n].every_hours),
                               now, config.get(n, {}))]
    contexts = {n: Context(state.memory(n), now) for n in to_run}

    def run(name: str):
        t0 = time.monotonic()
        try:
            found, error = _run_one(name, config.get(name, {}), contexts[name])
            return name, found, error, False, time.monotonic() - t0
        except NotConfigured as exc:
            log.info("%s: not configured (%s)", name, exc)
            return name, None, None, True, 0.0

    with ThreadPoolExecutor(max_workers=max(len(to_run), 1)) as pool:
        results = list(pool.map(run, to_run))

    events, statuses = [], {}
    for name, found, error, off, seconds in results:
        if off:
            state.source(name)["health"] = "off"
            statuses[name] = {"health": "off"}
            continue
        health = state.record(name, now, len(found) if found is not None else None, error,
                              contexts[name].warnings, config.get(name, {}))
        if found is None:
            found = state.previous_events(name)  # one flaky scrape never empties the site
        events += found
        statuses[name] = {"health": health, "seconds": round(seconds, 1)}
        log.info("%-18s %-8s %4d events %5.1fs%s", name, health, len(found), seconds,
                 f"  ({error})" if error else "")
    for name in enabled:
        if name not in statuses:  # not due this run: reuse what it found last time
            events += state.previous_events(name)
            statuses[name] = {"health": state.source(name).get("health", "ok"), "cached": True}

    final = build(events, config.get("days_ahead", 30), now)
    counts: dict[str, int] = {}
    for e in final:
        counts[e.source] = counts.get(e.source, 0) + 1
    state.data["last_run"] = now.isoformat(timespec="seconds")
    state.data["http"] = http.stats
    state.save()
    EVENTS.write_text(json.dumps({
        "generated_at": now.isoformat(timespec="seconds"),
        "sources": [{"id": n, "name": SOURCES[n].label, "count": counts.get(n, 0),
                     "last_ok": state.source(n).get("last_ok"), **statuses[n]}
                    for n in enabled],
        "regions": REGIONS,
        "topics": list(TOPICS),
        "events": [e.to_json() for e in final],
    }, ensure_ascii=False, separators=(",", ":")))
    log.info("wrote %d events (from %d raw); http %s", len(final), len(events), http.stats)


if __name__ == "__main__":
    main(sys.argv[1:])
