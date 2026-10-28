"""iCalendar feeds: most clubs run a public Google Calendar, and Google exposes each as ICS
(Calendar settings -> "Public address in iCal format")."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from ..http import get_text
from ..models import Event, clean_text

PACIFIC = ZoneInfo("America/Los_Angeles")


def _as_dt(v) -> tuple[datetime, bool]:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=PACIFIC)), False
    assert isinstance(v, date)
    return datetime(v.year, v.month, v.day, tzinfo=PACIFIC), True


def parse_feed(text: str, host: str, days_ahead: int, now: datetime | None = None) -> list:
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
            source="ics",
            host=host,
            venue=clean_text(str(comp.get("LOCATION") or ""), 200) or None,
            online="zoom.us" in str(comp.get("LOCATION") or "").lower(),
            description=clean_text(desc),
        ))
    return events


def fetch(cfg: dict) -> list:
    events = []
    for feed in cfg.get("feeds", []):
        events += parse_feed(get_text(feed["url"]), feed["name"], cfg.get("days_ahead", 30))
    return events
