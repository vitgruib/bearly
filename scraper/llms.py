"""llms-full.txt: every upcoming event as plain text an AI assistant can read in one fetch."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Event

PACIFIC = ZoneInfo("America/Los_Angeles")


def time_range(e: Event) -> str:
    if e.all_day:
        return "All day"
    start = e.start.astimezone(PACIFIC)
    out = f"{start:%-I:%M %p}".replace(":00", "")
    if e.end:
        out += f"–{e.end.astimezone(PACIFIC):%-I:%M %p}".replace(":00", "")
    return out


def write_llms_full(events: list[Event], site_url: str, path: Path, now: datetime) -> None:
    lines = [
        "# Lo-Cal: upcoming Berkeley events",
        "",
        f"Generated {now.astimezone(PACIFIC):%Y-%m-%d %H:%M} Pacific. {len(events)} events, sorted by start.",
        (f"Times are Pacific. The same data as JSON: {site_url}data/events.json. "
        f"About the fields and rules: {site_url}llms.txt"),
        "Tags, area, free and getting-in come from keyword rules, not people: check the event link.",
    ]
    day = None
    for e in events:
        d = e.start.astimezone(PACIFIC).date()
        if d != day:
            day = d
            lines += ["", f"## {d:%A %B %-d, %Y}", ""]
        facts = [time_range(e), e.title, e.venue or e.address or ("Online" if e.online else ""), e.host or "",
                 e.region or "", ", ".join(e.tags), "Free" if e.free else "",
                 f"Getting in: {'; '.join(e.access)}" if e.access else "",
                 e.url, f"{site_url}#event={e.id}"]
        lines.append("- " + " | ".join(f for f in facts if f))
    path.write_text("\n".join(lines) + "\n")
