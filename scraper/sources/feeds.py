"""Calendar feeds in the standard formats, one config entry per feed:

- ics: iCalendar. Most clubs run a public Google Calendar, which Google exposes as ICS
  (Calendar settings -> "Public address in iCal format"); departments often use Trumba.
- rss: an announcements feed (newsletter archive, blog); items are read with the free
  text parser, so only posts that name a date and time become events.
- jsonld: any page that embeds schema.org Event data (most venue and ticketing sites).
- tribe: WordPress sites running The Events Calendar (/wp-json/tribe/events/v1/events).
- localist: Localist calendars (/api/2/events).

A feed that fails is reported as a warning; the others still count."""

from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from ..http import get_json, get_text
from ..messages import events_from_message
from ..models import Event, clean_text
from ..schema_org import events_from_html
from ..state import Context

PACIFIC = ZoneInfo("America/Los_Angeles")


def _as_dt(v) -> tuple[datetime, bool]:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=PACIFIC)), False
    assert isinstance(v, date)
    return datetime(v.year, v.month, v.day, tzinfo=PACIFIC), True


def parse_ics(text: str, host: str, days_ahead: int, now: datetime | None = None) -> list:
    now = now or datetime.now(UTC)
    cal = icalendar.Calendar.from_ical(text)
    events = []
    for comp in recurring_ical_events.of(cal).between(now, now + timedelta(days=days_ahead)):
        start, all_day = _as_dt(comp.get("DTSTART").dt)
        end = _as_dt(comp.get("DTEND").dt)[0] if comp.get("DTEND") else None
        url = str(comp.get("URL") or "")
        desc = str(comp.get("DESCRIPTION") or "")
        events.append(Event(
            title=clean_text(str(comp.get("SUMMARY") or "Untitled"), 200),
            start=start,
            end=end,
            all_day=all_day,
            url=url,
            source="feeds",
            host=host,
            venue=clean_text(str(comp.get("LOCATION") or ""), 200) or None,
            online="zoom.us" in str(comp.get("LOCATION") or "").lower(),
            description=clean_text(desc),
        ))
    return events


def parse_rss(xml: str, host: str) -> list[Event]:
    root = ElementTree.fromstring(xml)
    events = []
    for item in root.iter("item"):
        text = f"{item.findtext('title') or ''}\n\n{item.findtext('description') or ''}"
        sent = item.findtext("pubDate")
        sent_dt = parsedate_to_datetime(sent) if sent else datetime.now(UTC)
        events += events_from_message(clean_text(text, 20000), sent_dt, "feeds", host=host,
                                      subject=item.findtext("title"),
                                      url=item.findtext("link") or "")
    return events


def parse_tribe(data: dict, host: str) -> list[Event]:
    events = []
    for ev in data.get("events", []):
        venue = ev.get("venue") or {}
        if isinstance(venue, list):
            venue = venue[0] if venue else {}
        cost = (ev.get("cost") or "").lower()
        events.append(Event(
            title=clean_text(ev["title"], 200),
            start=datetime.fromisoformat(ev["utc_start_date"]).replace(tzinfo=UTC),
            end=datetime.fromisoformat(ev["utc_end_date"]).replace(tzinfo=UTC)
            if ev.get("utc_end_date") else None,
            all_day=bool(ev.get("all_day")),
            url=ev.get("url") or "",
            source="feeds",
            host=host,
            venue=clean_text(venue.get("venue")) or None,
            address=clean_text(venue.get("address")) or None,
            city=venue.get("city"),
            image=(ev.get("image") or {}).get("url") if ev.get("image") else None,
            description=clean_text(ev.get("description")),
            free=True if "free" in cost else (False if "$" in cost else None),
        ))
    return events


def parse_localist(data: dict, host: str) -> list[Event]:
    events = []
    for wrapper in data.get("events", []):
        ev = wrapper["event"]
        for inst in ev.get("event_instances", []):
            i = inst["event_instance"]
            events.append(Event(
                title=clean_text(ev["title"], 200),
                start=datetime.fromisoformat(i["start"]),
                end=datetime.fromisoformat(i["end"]) if i.get("end") else None,
                all_day=bool(i.get("all_day")),
                url=ev.get("localist_url") or ev.get("url") or "",
                source="feeds",
                host=host,
                venue=ev.get("location_name"),
                address=ev.get("address"),
                lat=float(ev["geo"]["latitude"]) if (ev.get("geo") or {}).get("latitude")
                else None,
                lng=float(ev["geo"]["longitude"]) if (ev.get("geo") or {}).get("longitude")
                else None,
                online=ev.get("experience") == "virtual",
                image=ev.get("photo_url"),
                description=clean_text(ev.get("description_text")),
                free=ev.get("free"),
            ))
    return events


def fetch_feed(feed: dict, days_ahead: int, now: datetime) -> list[Event]:
    kind, url, host = feed.get("type", "ics"), feed["url"], feed["name"]
    if kind == "ics":
        return parse_ics(get_text(url, conditional=True), host, days_ahead, now)
    if kind == "rss":
        return parse_rss(get_text(url, conditional=True), host)
    if kind == "jsonld":
        events = events_from_html(get_text(url), "feeds")
        for e in events:
            e.host = e.host or host
        return events
    if kind == "tribe":
        return parse_tribe(get_json(url, per_page=50, start_date=now.date().isoformat()), host)
    if kind == "localist":
        return parse_localist(get_json(url, days=min(days_ahead, 90), pp=100), host)
    raise ValueError(f"unknown feed type {kind!r}")


def fetch(cfg: dict, ctx: Context) -> list[Event]:
    events = []
    for feed in cfg.get("list", []):
        try:
            found = fetch_feed(feed, cfg.get("days_ahead", 30), ctx.now)
        except (httpx.HTTPError, ValueError, KeyError, ElementTree.ParseError) as exc:
            ctx.warn(f"{feed['name']}: {type(exc).__name__}: {exc}")
            continue
        if feed.get("campus"):  # department calendars that never say "Berkeley"
            for e in found:
                e.city = e.city or "Berkeley"
        events += found
    return events
