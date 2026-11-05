"""Upcoming events as plain text for AI assistants: everything in llms-full.txt, and small slices\n(today, tomorrow, the weekend, each day, each topic) under data/llms/."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .enrich import TOPICS
from .ics import slug
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


def _line(e: Event, site_url: str) -> str:
    facts = [time_range(e), e.title, e.venue or e.address or ("Online" if e.online else ""), e.host or "",
             e.region or "", ", ".join(e.tags), "Free" if e.free else "",
             f"Getting in: {'; '.join(e.access)}" if e.access else "",
             e.url, f"{site_url}e/{e.id}.html"]
    return "- " + " | ".join(f for f in facts if f)


def _render(title: str, events: list[Event], site_url: str, now: datetime) -> str:
    lines = [
        f"# Lo-Cal: {title}",
        "",
        f"Generated {now.astimezone(PACIFIC):%Y-%m-%d %H:%M} Pacific. {len(events)} events, sorted by start.",
        (f"Times are Pacific. Other days and topics: {site_url}data/llms/index.txt. "
         f"About the fields and rules: {site_url}llms.txt"),
        "Tags, area, free and getting-in come from keyword rules, not people: check the event link.",
    ]
    day = None
    for e in events:
        d = e.start.astimezone(PACIFIC).date()
        if d != day:
            day = d
            lines += ["", f"## {d:%A %B %-d, %Y}", ""]
        lines.append(_line(e, site_url))
    if not events:
        lines += ["", "No events listed."]
    return "\n".join(lines) + "\n"


def write_llms_full(events: list[Event], site_url: str, path: Path, now: datetime) -> None:
    path.write_text(_render("upcoming Berkeley events", events, site_url, now))


def write_llms_slices(events: list[Event], site_url: str, out: Path, now: datetime) -> None:
    """Small files an assistant can read whole in one fetch, at addresses that never change:
    llms-full.txt is too long for most assistants' web tools, which cut a page off part way."""
    def day(e: Event) -> date:
        return e.start.astimezone(PACIFIC).date()

    today = now.astimezone(PACIFIC).date()
    saturday = today + timedelta(days=5 - today.weekday())  # on a Sunday, that's yesterday
    weekend = {saturday, saturday + timedelta(days=1)}
    week = today + timedelta(days=7)
    files = {
        "today.txt": (f"today, {today:%A %B %-d}", [e for e in events if day(e) == today]),
        "tomorrow.txt": ("tomorrow", [e for e in events if day(e) == today + timedelta(days=1)]),
        "weekend.txt": ("this weekend", [e for e in events if day(e) in weekend]),
    }
    for t in TOPICS:
        files[f"topics/{slug(t)}.txt"] = (f"{t}, next 7 days", [e for e in events if t in e.tags and day(e) < week])
    for d in sorted({day(e) for e in events}):
        files[f"days/{d}.txt"] = (f"{d:%A %B %-d, %Y}", [e for e in events if day(e) == d])

    for sub in ("days", "topics"):
        for old in (out / sub).glob("*.txt"):
            if f"{sub}/{old.name}" not in files:
                old.unlink()
    index = ["# Lo-Cal for AI assistants", "",
             "Each file below is one slice of upcoming Berkeley events, small enough to read in one fetch.",
             (f"Generated {now.astimezone(PACIFIC):%Y-%m-%d %H:%M} Pacific. Every event at once: "
             f"{site_url}data/llms-full.txt"), ""]
    for name, (title, chosen) in files.items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(_render(title, chosen, site_url, now))
        index.append(f"- {site_url}data/llms/{name}: {title} ({len(chosen)} events)")
    (out / "index.txt").write_text("\n".join(index) + "\n")
