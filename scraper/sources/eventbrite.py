"""Eventbrite: the location search pages embed their results as window.__SERVER_DATA__."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from ..http import get_text
from ..models import Event, clean_text

MARKER = "window.__SERVER_DATA__ = "


def _dt(date: str | None, time: str | None, tz: ZoneInfo) -> datetime | None:
    if not date:
        return None
    return datetime.fromisoformat(f"{date}T{time or '00:00'}").replace(tzinfo=tz)


def parse_page(html: str) -> list[Event]:
    i = html.find(MARKER)
    if i < 0:
        raise ValueError("Eventbrite page has no __SERVER_DATA__ (layout changed?)")
    data, _ = json.JSONDecoder().raw_decode(html[i + len(MARKER):])
    results = data["search_data"]["events"]["results"]
    events = []
    for r in results:
        if r.get("is_cancelled"):
            continue
        tz = ZoneInfo(r.get("timezone") or "America/Los_Angeles")
        venue = r.get("primary_venue") or {}
        addr = venue.get("address") or {}
        lat, lng = addr.get("latitude"), addr.get("longitude")
        events.append(Event(
            title=r["name"].strip(),
            start=_dt(r["start_date"], r.get("start_time"), tz),
            end=_dt(r.get("end_date"), r.get("end_time"), tz),
            url=r["url"],
            source="eventbrite",
            venue=venue.get("name"),
            address=addr.get("localized_address_display"),
            city=addr.get("city"),
            lat=float(lat) if lat else None,
            lng=float(lng) if lng else None,
            online=bool(r.get("is_online_event")),
            image=(r.get("image") or {}).get("url"),
            description=clean_text(r.get("summary")),
            tags=[t["display_name"] for t in r.get("tags") or [] if t.get("display_name")],
        ))
    return events


def fetch(cfg: dict) -> list[Event]:
    events = []
    for place in cfg.get("places", ["ca--berkeley"]):
        for page in range(1, cfg.get("pages", 4) + 1):
            events += parse_page(get_text(
                f"https://www.eventbrite.com/d/{place}/all-events/", page=page))
    return events
