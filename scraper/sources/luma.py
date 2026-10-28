"""Luma: the geo "discover" feed around campus, plus specific club calendars."""

from datetime import UTC, datetime, timedelta

from ..http import get_json
from ..models import Event, clean_text, parse_dt

API = "https://api.lu.ma"


def parse_entry(entry: dict) -> Event:
    ev = entry["event"]
    geo = ev.get("geo_address_info") or {}
    coord = ev.get("coordinate") or {}
    ticket = entry.get("ticket_info") or {}
    hosts = [h.get("name") for h in entry.get("hosts") or [] if h.get("name")]
    cal = entry.get("calendar") or {}
    host = cal.get("name") if cal.get("name") not in (None, "Personal") else None
    return Event(
        title=ev["name"].strip(),
        start=parse_dt(ev["start_at"]),
        end=parse_dt(ev["end_at"]) if ev.get("end_at") else None,
        url=f"https://luma.com/{ev['url']}",
        source="luma",
        host=host or (", ".join(hosts[:2]) or None),
        venue=geo.get("address"),
        address=geo.get("full_address"),
        city=geo.get("city"),
        lat=coord.get("latitude"),
        lng=coord.get("longitude"),
        online=ev.get("location_type") == "online",
        image=ev.get("cover_url"),
        description=clean_text(cal.get("description_short")),
        free=ticket.get("is_free"),
    )


def _page(path: str, horizon: datetime, max_pages: int, **params) -> list[Event]:
    events, cursor = [], None
    for _ in range(max_pages):
        q = {"pagination_limit": 50, **params}
        if cursor:
            q["pagination_cursor"] = cursor
        data = get_json(f"{API}{path}", **q)
        batch = [parse_entry(e) for e in data.get("entries", []) if e.get("event")]
        events += batch
        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor or (batch and batch[-1].start > horizon):
            break
    return events


def calendar_events(slug_or_id: str, days_ahead: int = 30) -> list[Event]:
    cal_id = slug_or_id
    if not cal_id.startswith("cal-"):
        cal_id = get_json(f"{API}/url", url=slug_or_id)["data"]["calendar"]["api_id"]
    horizon = datetime.now(UTC) + timedelta(days=days_ahead)
    return _page("/calendar/get-items", horizon, 4, calendar_api_id=cal_id, period="future")


def fetch(cfg: dict) -> list[Event]:
    days = cfg.get("days_ahead", 30)
    horizon = datetime.now(UTC) + timedelta(days=days)
    lat, lng = cfg.get("center", [37.8715, -122.2730])
    events = _page("/discover/get-paginated-events", horizon, cfg.get("max_pages", 12),
                   latitude=lat, longitude=lng)
    for slug in cfg.get("calendars", []):
        events += calendar_events(slug, days)
    return events
