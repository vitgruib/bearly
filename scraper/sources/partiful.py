"""Partiful has no public search; we take the Bay Area "trending" section of /explore and
resolve individual partiful.com/e/<id> links that show up in emails and Slack."""

from ..http import get_text, next_data
from ..models import Event, clean_text, parse_dt
from ..state import Context


def parse_event(ev: dict) -> Event | None:
    if not ev.get("startDate") or ev.get("status", "PUBLISHED") != "PUBLISHED":
        return None
    loc = ev.get("locationInfo") or {}
    maps = loc.get("mapsInfo") or {}
    approx = maps.get("approximateLocation") or ""
    lines = loc.get("displayAddressLines") or maps.get("addressLines") or []
    upload = ((ev.get("image") or {}).get("upload") or {})
    image = upload.get("url") or (ev.get("image") or {}).get("url")
    ticketing = ev.get("ticketing") or {}
    return Event(
        title=ev["title"].strip(),
        start=parse_dt(ev["startDate"]),
        end=parse_dt(ev["endDate"]) if ev.get("endDate") else None,
        url=f"https://partiful.com/e/{ev['id']}",
        source="partiful",
        venue=loc.get("displayName"),
        address=", ".join(lines) or None,
        city=approx.split(",")[0].strip() or None,
        image=image,
        description=clean_text(ev.get("description")),
        free=not ticketing.get("enabled") if ticketing else None,
    )


def parse_explore(html: str, regions=("SF",)) -> list[Event]:
    sections = next_data(html)["props"]["pageProps"]["trendingSections"]
    out = []
    for region in regions:
        for item in (sections.get(region) or {}).get("items", []):
            if item.get("type") == "event" and (e := parse_event(item["event"])):
                out.append(e)
    return out


def resolve(url: str) -> Event | None:
    data = next_data(get_text(url))
    ev = (data or {}).get("props", {}).get("pageProps", {}).get("event")
    if not ev:
        return None
    ev.setdefault("id", url.rstrip("/").rsplit("/", 1)[-1])
    return parse_event(ev)


def fetch(cfg: dict, ctx: Context) -> list[Event]:
    events = parse_explore(get_text("https://partiful.com/explore"))
    for url in cfg.get("events", []):
        if e := resolve(url):
            events.append(e)
    return events
