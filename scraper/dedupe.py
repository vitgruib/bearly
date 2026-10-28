"""The same event is often on Luma, re-posted to a listserv and dropped in Slack. Merge them
into one record that remembers everywhere it was seen."""

import re

from .models import Event, dedupe_key

# Platform listings carry structured data; message-derived records are best-effort.
PRIORITY = {"luma": 0, "partiful": 0, "eventbrite": 1, "cerebral_valley": 1,
            "berkeley_calendar": 1, "hackathons": 1, "venues": 1, "feeds": 2, "instagram": 3, "email": 3, "slack": 3}


def _richness(e: Event) -> tuple:
    return (PRIORITY.get(e.source, 2), -bool(e.image), -(e.lat is not None), -len(e.description))


def _merge(group: list[Event]) -> Event:
    group.sort(key=_richness)
    best = group[0]
    for other in group[1:]:
        for field in ("end", "host", "venue", "address", "city", "lat", "lng", "image",
                      "free", "region"):
            if getattr(best, field) is None:
                setattr(best, field, getattr(other, field))
        if not best.description:
            best.description = other.description
        best.tags += [t for t in other.tags if t not in best.tags]
    seen = {best.source}
    for other in group:
        for s in [other.source, *other.also_on]:
            if s not in seen:
                seen.add(s)
                best.also_on.append(s)
    best.also_on = [s for s in best.also_on if s != best.source]
    return best


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"^\[[^\]]*\]", "", title.lower()))


def _same_listing(a: Event, b: Event) -> bool:
    """One source's title is the other's plus a prefix or suffix ("Film Screening: X" / "X",
    "Neuro Night" / "NeuroNight SF"). Only across sources and at the same minute: within one
    source, two similar titles at one time are two different listings."""
    if a.source == b.source or a.start != b.start:
        return False
    x, y = sorted((_norm(a.title), _norm(b.title)), key=len)
    return len(x) >= 8 and x in y


def dedupe(events: list[Event]) -> list[Event]:
    by_key: dict[str, list[Event]] = {}
    url_to_key: dict[tuple, str] = {}
    for e in events:
        url = e.url.split("?")[0].rstrip("/").replace("lu.ma/", "luma.com/")
        # A recurring listing shares one URL across dates; only merge on the same day.
        url_day = (url, e.start.date())
        key = url_to_key.get(url_day) if url else None
        key = key or dedupe_key(e)
        by_key.setdefault(key, []).append(e)
        if url:
            url_to_key.setdefault(url_day, key)
    groups = list(by_key.values())
    by_start: dict = {}
    for g in groups:
        by_start.setdefault(g[0].start, []).append(g)
    merged = []
    for same_time in by_start.values():
        while same_time:
            g = same_time.pop()
            for other in [o for o in same_time if any(_same_listing(a, b) for a in g for b in o)]:
                same_time.remove(other)
                g += other
            merged.append(_merge(g))
    return merged


def collapse_repeats(events: list[Event], min_count: int = 3) -> list[Event]:
    """Daily library hours, weekly exec meetings and month-long exhibits would fill the list:
    show each recurring listing once, at its next occurrence. Events must be sorted by start."""
    series: dict[tuple, list[Event]] = {}
    for e in events:
        series.setdefault((_norm(e.title), e.source, e.host), []).append(e)
    out = []
    for e in events:
        group = series[(_norm(e.title), e.source, e.host)]
        if len(group) < min_count:
            out.append(e)
        elif group[0] is e:
            e.repeats = len(group)
            out.append(e)
    return out

