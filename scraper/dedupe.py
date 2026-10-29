"""The same event is often on Luma, re-posted to a listserv and dropped in Slack. Merge them
into one record that remembers everywhere it was seen."""

import re
from urllib.parse import urlparse

from .models import Event, dedupe_key

# Platform listings carry structured data; message-derived records are best-effort.
PRIORITY = {"luma": 0, "partiful": 0, "cerebral_valley": 1,
            "berkeley_calendar": 1, "hackathons": 1, "venues": 1, "feeds": 2, "instagram": 3, "email": 3, "slack": 3}


def _richness(e: Event) -> tuple:
    return (PRIORITY.get(e.source, 2), -bool(e.image), -(e.lat is not None), -len(e.description))


def _listing(e: Event) -> dict:
    # Every club calendar is source "feeds"; the club's name is what tells listings apart.
    return {"source": e.source, "url": e.url, **({"name": e.host} if e.source == "feeds" and e.host else {})}


def _listings(group: list[Event]) -> list[dict]:
    out, seen = [], set()
    for e in group:
        for item in [_listing(e), *e.listings]:
            url = item["url"].split("?")[0].rstrip("/")
            if url and url not in seen:
                seen.add(url)
                out.append(item)
    return out if len(out) > 1 else []


def _merge(group: list[Event]) -> Event:
    group.sort(key=_richness)
    best = group[0]
    listings = _listings(group)
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
    best.listings = listings
    return best


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"^\[[^\]]*\]", "", title.lower()))


DISTINGUISHING = {"men", "mens", "women", "womens", "boys", "girls", "jv", "varsity", "i", "ii",
                  "iii", "iv", "part", "session", "advanced", "intro", "beginner", "beginners"}


def _words(title: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", title.lower().replace("’", "'").replace("'", "")))


def _host(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def _same_listing(a: Event, b: Event) -> bool:
    """One listing's title is the other's plus extra words ("Film Screening: X" / "X",
    "Neuro Night" / "NeuroNight SF", "AWS Agentic Partner Showcase Extended - …" / "AWS Partner
    Showcase - …"), at the same minute, from different sources or different sites. Two such
    titles on one site at one time are that site's two different listings (tour #1 / #2)."""
    if a.start != b.start or (a.source == b.source and _host(a.url) == _host(b.url)):
        return False
    x, y = sorted((_norm(a.title), _norm(b.title)), key=len)
    if len(x) >= 8 and x in y:
        return True
    wx, wy = sorted((_words(a.title), _words(b.title)), key=len)
    if len(wx) >= 3 and wx <= wy:
        return True
    # Two sources' own wording of one title ("Haas Tech & AI Summit" / "Tech and AI Summit"):
    # most words shared, and none of the differing ones tells two events apart.
    differ = wx ^ wy
    return (a.source != b.source and len(wx) >= 5 and len(wx & wy) >= 0.8 * len(wx)
            and not differ & DISTINGUISHING and not any(w.isdigit() for w in differ))


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

