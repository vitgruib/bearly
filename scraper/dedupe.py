"""The same event is often on Luma, re-posted to a listserv and dropped in Slack. Merge them
into one record that remembers everywhere it was seen."""

from .models import Event, dedupe_key

# Platform listings carry structured data; message-derived records are best-effort.
PRIORITY = {"luma": 0, "partiful": 0, "eventbrite": 1, "cerebral_valley": 1,
            "berkeley_calendar": 1, "ics": 2, "email": 3, "slack": 3}


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


def dedupe(events: list[Event]) -> list[Event]:
    by_key: dict[str, list[Event]] = {}
    url_to_key: dict[str, str] = {}
    for e in events:
        url = e.url.split("?")[0].rstrip("/").replace("lu.ma/", "luma.com/")
        key = url_to_key.get(url) if url else None
        key = key or dedupe_key(e)
        by_key.setdefault(key, []).append(e)
        if url:
            url_to_key.setdefault(url, key)
    return [_merge(g) for g in by_key.values()]
