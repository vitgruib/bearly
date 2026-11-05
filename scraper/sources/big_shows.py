"""Concerts at California's big venues (about 2,500 seats and up) that a train gets you to:
within a ~15 minute walk of a rail station, or on the venue's official shuttle from one. Each
venue in sources.toml carries its capacity, how to get there, and one listing:

- livenation: the venue's page on livenation.com, which lists every Ticketmaster show there.
  Its JSON-LD calls comedy and ballet MusicEvents too, so the page's Next.js payload is read
  instead: it carries Ticketmaster's own classification (segment "Music", genre "Comedy").
- dothebay: the venue's DoTheBay page (Bay Area), whose category tells concerts from games.
- anotherplanet: the Fox and the Greek, read by the venues source's parser.

Only concerts are kept: no games, comedy, ballet, parking or suite listings. These are the only
events listed beyond the Bay Area (enrich.far_region). A venue whose listing fails is a warning;
the others still count."""

import json
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from ..http import get_text
from ..models import Event, clean_text
from ..state import Context
from . import venues

# Ticketmaster files classical concerts under "Arts & Theatre", the rest under "Music".
CONCERT_TAGS = {"Music", "Classical"}
# Listings that ride on a show without being one, and acts a "Music" label doesn't rule out.
NOT_A_CONCERT = re.compile(
    r"\b(parking|suites?|lounge access|club (access|seats)|not a concert ticket|vip|premium"
    r"|\d[- ]day pass|venue tours?|comedy|comedian|stand-?up|podcast|in conversation"
    r"|wwe|ufc|aew|monster jam|disney on ice|globetrotters|graduation|commencement)\b"
    r"|\bvs?\.\s", re.IGNORECASE)
_FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')


def is_concert(e: Event) -> bool:
    return (bool(CONCERT_TAGS & set(e.tags)) and not NOT_A_CONCERT.search(e.title)
            and not venues.JUNK.search(e.title))


def _poster(images: list[dict]) -> str | None:
    """The smallest image that still fills a poster-sized card, else the widest there is."""
    sized = sorted((i for i in images if i.get("url")), key=lambda i: i.get("width") or 0)
    big = [i for i in sized if (i.get("width") or 0) >= 1000]
    return (big[0] if big else sized[-1])["url"] if sized else None


def parse_livenation(page: str) -> list[Event]:
    """Each show is a {"event_data_type": ...} object inside the page's React payload, which is
    split across self.__next_f.push() string chunks. Times are the venue's wall clock."""
    flight = "".join(json.loads(c) for c in _FLIGHT.findall(page))
    decoder = json.JSONDecoder()
    events, seen = [], set()
    for m in re.finditer(r'\{"event_data_type":', flight):
        ev, _ = decoder.raw_decode(flight, m.start())
        if ev["discovery_id"] in seen or ev.get("status_code") in ("cancelled", "postponed"):
            continue
        seen.add(ev["discovery_id"])
        tz = ZoneInfo(ev.get("timezone") or "America/Los_Angeles")
        clock = ev.get("start_time_local") or "00:00:00"
        v = ev.get("venue") or {}
        loc = v.get("location") or {}
        support = [a["name"] for a in (ev.get("artists") or [])[1:] if a.get("name")]
        events.append(Event(
            title=clean_text(ev["name"], 200),
            start=datetime.fromisoformat(f"{ev['start_date_local']}T{clock}").replace(tzinfo=tz),
            url=ev.get("url") or "",
            source="big_shows",
            venue=v.get("name"),
            address=", ".join(x for x in (loc.get("street_address"), loc.get("locality")) if x)
            or None,
            city=loc.get("locality"),
            lat=loc.get("latitude"),
            lng=loc.get("longitude"),
            image=_poster(ev.get("images") or []),
            description=f"With {', '.join(support)}" if support else "",
            free=False,
            tags=[t for t in (ev.get("segment"), ev.get("genre")) if t],
        ))
    return events


def fetch_venue(v: dict, end: datetime) -> list[Event]:
    kind = v["type"]
    if kind == "livenation":
        return parse_livenation(get_text(v["url"]))
    if kind == "dothebay":
        return venues.fetch_dothebay({"venues": [v["slug"]]}, end)
    if kind == "anotherplanet":
        return venues.parse_anotherplanet(get_text(v["url"]), v["name"], v["city"])
    raise ValueError(f"unknown big venue type {kind!r}")


def fetch(cfg: dict, ctx: Context) -> list[Event]:
    now = ctx.now.astimezone(UTC)
    end = now + timedelta(days=cfg.get("list_days", 90))
    events = []
    for v in cfg.get("venues", []):
        try:
            found = fetch_venue(v, end)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            ctx.warn(f"{v['name']}: {type(exc).__name__}: {exc}")
            continue
        for e in found:
            if not (now <= e.start <= end and is_concert(e)):
                continue
            # The venue's own name and coordinates, so every listing of it reads and maps alike.
            e.source, e.big_show, e.transit = "big_shows", True, v["transit"]
            e.venue, e.city, e.lat, e.lng = v["name"], v["city"], v["lat"], v["lng"]
            events.append(e)
    return events
