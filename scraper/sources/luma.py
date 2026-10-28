"""Luma: the geo "discover" feed around campus, plus specific club calendars."""

from datetime import UTC, datetime, timedelta

import httpx

from ..enrich import CAMPUS, haversine_km
from ..http import get_json
from ..models import Event, clean_text, parse_dt
from ..state import Context

API = "https://api.lu.ma"
DISCOVERY_KM = 3.0


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


def _page(path: str, horizon: datetime, max_pages: int, **params) -> list[dict]:
    entries, cursor = [], None
    for _ in range(max_pages):
        q = {"pagination_limit": 50, **params}
        if cursor:
            q["pagination_cursor"] = cursor
        data = get_json(f"{API}{path}", **q)
        batch = [e for e in data.get("entries", []) if e.get("event")]
        entries += batch
        cursor = data.get("next_cursor")
        if (not data.get("has_more") or not cursor
                or (batch and parse_dt(batch[-1]["event"]["start_at"]) > horizon)):
            break
    return entries


def calendar_events(slug_or_id: str, days_ahead: int = 30) -> list[Event]:
    cal_id = slug_or_id
    if not cal_id.startswith("cal-"):
        cal_id = get_json(f"{API}/url", url=slug_or_id)["data"]["calendar"]["api_id"]
    horizon = datetime.now(UTC) + timedelta(days=days_ahead)
    entries = _page("/calendar/get-items", horizon, 4, calendar_api_id=cal_id, period="future")
    return [parse_entry(e) for e in entries]


def _near_campus(entry: dict, km: float) -> bool:
    c = entry["event"].get("coordinate") or {}
    return (c.get("latitude") is not None
            and haversine_km(CAMPUS, (c["latitude"], c["longitude"])) <= km)


def discover_calendars(entries: list[dict], memory: dict, now: datetime) -> list[str]:
    """Remember every org calendar that hosts events near campus. Once one has hosted two
    distinct events, follow the calendar itself: it lists events beyond what the
    distance-sorted discover feed reaches, and catches the org's off-campus events too."""
    found = memory.setdefault("discovered", {})
    for e in entries:
        cal = e.get("calendar") or {}
        if (not cal.get("api_id") or cal.get("name") in (None, "Personal")
                or not _near_campus(e, DISCOVERY_KM)):
            continue
        rec = found.setdefault(cal["api_id"], {"name": cal["name"], "slug": cal.get("slug"),
                                               "events": [], "first_seen": now.isoformat()})
        if e["event"]["api_id"] not in rec["events"]:
            rec["events"] = (rec["events"] + [e["event"]["api_id"]])[-20:]
        rec["last_seen"] = now.isoformat()
    stale = now - timedelta(days=120)
    for cal_id in [c for c, r in found.items() if parse_dt(r["last_seen"]) < stale]:
        del found[cal_id]  # an org that stopped hosting near campus
    return [c for c, r in found.items() if len(r["events"]) >= 2]


def fetch(cfg: dict, ctx: Context) -> list[Event]:
    days = cfg.get("days_ahead", 30)
    horizon = ctx.now + timedelta(days=days)
    lat, lng = cfg.get("center", [37.8715, -122.2730])
    entries = _page("/discover/get-paginated-events", horizon, cfg.get("max_pages", 12),
                    latitude=lat, longitude=lng)
    # Category feeds reach further than the plain distance-sorted feed for busy topics.
    for cat in cfg.get("categories", []):
        try:
            entries += _page("/discover/get-paginated-events", horizon,
                             cfg.get("category_pages", 3), discover_category_api_id=cat,
                             latitude=lat, longitude=lng)
        except httpx.HTTPStatusError as exc:  # extra reach, not the core feed
            ctx.warn(f"luma category {cat}: {exc.response.status_code}")
    events = [parse_entry(e) for e in entries]
    calendars = dict.fromkeys(cfg.get("calendars", []))
    calendars.update(dict.fromkeys(discover_calendars(entries, ctx.memory, ctx.now)))
    for cal in calendars:
        try:
            events += calendar_events(cal, days)
        except (httpx.HTTPError, KeyError) as exc:  # a deleted calendar must not sink the rest
            ctx.warn(f"luma calendar {cal}: {exc}")
    return events
