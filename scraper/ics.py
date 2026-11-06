"""Subscribable calendar feeds, rebuilt every run: everything, one per topic, and one per
combination of the site's filters (event type, location, cost), so a calendar built from
filters keeps updating without a server.

Calendar apps poll a subscribed URL on their own schedule (Apple: as often as every few
minutes; Google: every several hours), so these follow the site within a few hours."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Event

PACIFIC = ZoneInfo("America/Los_Angeles")


def slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _fold(line: str) -> list[str]:
    """RFC 5545: lines over 75 octets continue on the next line after a space."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > 75:
            out.append(cur)
            cur = " "
        cur += ch
    return [*out, cur]


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _vevent(e: Event, stamp: str) -> list[str]:
    if e.all_day:
        day = e.start.astimezone(PACIFIC).date()
        last = (e.end.astimezone(PACIFIC).date() if e.end else day)
        when = [f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
                f"DTEND;VALUE=DATE:{max(last, day) + timedelta(days=1):%Y%m%d}"]
    else:
        when = [f"DTSTART:{_utc(e.start)}", f"DTEND:{_utc(e.end or e.start + timedelta(hours=2))}"]
    notes = [e.description, f"Getting in: {' · '.join(e.access)}" if e.access else "", e.url]
    lines = ["BEGIN:VEVENT", f"UID:{e.id}@lo-cal", f"DTSTAMP:{stamp}", *when,
             f"SUMMARY:{_escape(e.title)}",
             f"DESCRIPTION:{_escape(chr(10).join(x for x in notes if x))}"]
    if place := e.address or e.venue:
        lines.append(f"LOCATION:{_escape(place)}")
    if e.url:
        lines.append(f"URL:{e.url}")
    return [*lines, "END:VEVENT"]


def calendar(name: str, events: list[Event], now: datetime) -> str:
    stamp = _utc(now)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Lo-Cal//berkeley events//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape(name)}",
             "X-WR-TIMEZONE:America/Los_Angeles",
             "REFRESH-INTERVAL;VALUE=DURATION:PT3H", "X-PUBLISHED-TTL:PT3H"]
    for e in events:
        lines += _vevent(e, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"


FOOD = "Free food"
COSTS = {"any": lambda e: True, "free": lambda e: e.free is True, "food": lambda e: FOOD in e.tags,
         "free-food": lambda e: e.free is True and FOOD in e.tags}


def write_feeds(events: list[Event], topics: list[str], out: Path, now: datetime,
                regions: list[str] = ()) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "all.ics").write_text(calendar("Lo-Cal: all Berkeley events", events, now))
    for t in topics:
        chosen = [e for e in events if t in e.tags]
        (out / f"{slug(t)}.ics").write_text(calendar(f"Lo-Cal: {t}", chosen, now))
    # f/<type>.<location>.<cost>.ics, "all" for any type or location. Free food is a cost.
    (out / "f").mkdir(exist_ok=True)
    for t in [None, *(t for t in topics if t != FOOD)]:
        for r in [None, *regions]:
            for cost, ok in COSTS.items():
                chosen = [e for e in events if (not t or t in e.tags) and (not r or e.region == r) and ok(e)]
                name = " · ".join(x for x in [t, r, {"any": "", "free": "Free", "food": "Free food",
                                                    "free-food": "Free, with food"}[cost]] if x)
                (out / "f" / f"{slug(t) if t else 'all'}.{slug(r) if r else 'all'}.{cost}.ics").write_text(
                    calendar(f"Lo-Cal: {name or 'all Berkeley events'}", chosen, now))
