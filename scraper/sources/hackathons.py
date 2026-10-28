"""Bay Area hackathons from the platforms that list them: Devpost, Y Combinator, MLH and
AGI House. Each feed lists far more than the Bay Area, so only in-person or hybrid events in
a known Bay Area city of California are kept; the state check matters because "Richmond",
"Dublin" and "Concord" are also cities elsewhere.

Times, checked against each source's own pages on 2026-10-28:
- Devpost: the API only has a submission window as text ("Oct 01 - Nov 12, 2026"), which for
  online contests is weeks long. Each in-person hackathon page carries JSON-LD whose
  startDate/endDate are that window with a UTC offset (matching its /details/dates
  schedule), so a hackathon is kept only when the window is at most MAX_SPAN_DAYS long, i.e.
  the window is the event itself. Longer windows are not a day anyone attends.
- YC and AGI House: UTC instants plus the event's IANA zone, shown in that zone on the site.
- MLH: no zone at all. The "Z" timestamps are the venue's wall clock stored as if it were US
  Eastern (SanD Hacks "14:00Z" is 9am PST on its Devpost schedule, Hack the Change "14:00Z"
  is 9am MST), and 01:11:11 / 23:59:59 stand for "date only".
"""

import json
import re
from datetime import date, datetime, time, timedelta
from html import unescape
from zoneinfo import ZoneInfo

import httpx

from ..enrich import EAST_BAY, PENINSULA
from ..http import get_json, get_text, json_ld
from ..models import Event, clean_text, dedupe_key
from ..state import Context

PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")

DEVPOST_API = "https://devpost.com/api/hackathons"
YC_URL = "https://www.ycombinator.com/events"
MLH_URL = "https://www.mlh.com/seasons/{season}/events"
AGI_API = "https://jtwthn6xog.execute-api.us-east-1.amazonaws.com/events"

MAX_SPAN_DAYS = 3  # Thursday to Sunday; anything longer on Devpost is a submission window
BAY_CITIES = {"berkeley", "san francisco"} | EAST_BAY | PENINSULA
CALIFORNIA = {"ca", "california"}
# AGI House's own venue, which its listings name but don't locate.
AGI_HOUSE_LATLNG = (37.5720, -122.3604)
MLH_DATE_ONLY = (time(1, 11, 11), time(23, 59, 59))


def _bay_city(city: str | None, state: str | None) -> str | None:
    """The city's name if it is in the Bay Area. `state`, when the source gives one, must be
    California."""
    city = (city or "").strip()
    if city.lower() not in BAY_CITIES:
        return None
    if state is not None and state.strip().lower() not in CALIFORNIA:
        return None
    return city


def _event(**kw) -> Event:
    return Event(source="hackathons", **kw)


# --- Devpost ---

_MONTH = "(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_WINDOW_RE = re.compile(rf"^{_MONTH} (\d{{1,2}})(?:, (\d{{4}}))?"
                        rf"(?: - (?:{_MONTH} )?(\d{{1,2}}), (\d{{4}}))?$")


def _window(s: str) -> tuple[date, date] | None:
    """"Oct 15 - 31, 2026", "Oct 31 - Nov 01, 2026", "Nov 14, 2026" -> (first, last day)."""
    m = _WINDOW_RE.match(s.strip())
    if not m:
        return None
    m1, d1, y1, m2, d2, y2 = m.groups()
    y1 = y1 or y2
    first = datetime.strptime(f"{m1} {d1} {y1}", "%b %d %Y").date()
    last = datetime.strptime(f"{m2 or m1} {d2 or d1} {y2 or y1}", "%b %d %Y").date()
    if first > last:  # "Dec 28 - Jan 02, 2027"
        first = first.replace(year=first.year - 1)
    return first, last


def devpost_candidates(data: dict, today: date, days_ahead: int) -> list[str]:
    """Hackathon page URLs worth opening: an event of a few days that is not over and starts
    within `days_ahead`. A window we cannot read is opened anyway; its page decides."""
    urls = []
    for h in data["hackathons"]:
        window = _window(h.get("submission_period_dates") or "")
        if window:
            first, last = window
            if ((last - first).days > MAX_SPAN_DAYS or last < today
                    or first > today + timedelta(days=days_ahead)):
                continue
        urls.append(h["url"])
    return urls


def parse_devpost_page(html: str) -> list[Event]:
    ld = next((d for d in json_ld(html) if "Hackathon" in (d.get("@type") or [])), None)
    if not ld or not ld.get("startDate") or not ld.get("endDate"):
        return []
    if ld.get("eventAttendanceMode", "").endswith("OnlineEventAttendanceMode"):
        return []
    addr = (ld.get("location") or {}).get("address") or {}
    city = _bay_city(addr.get("addressLocality"), addr.get("addressRegion") or "")
    start = datetime.fromisoformat(ld["startDate"]).astimezone(PT)
    end = datetime.fromisoformat(ld["endDate"]).astimezone(PT)
    if not city or (end.date() - start.date()).days > MAX_SPAN_DAYS:
        return []
    return [_event(
        title=clean_text(ld["name"], 200),
        start=start,
        end=end,
        url=ld["url"],
        host=(ld.get("organizer") or {}).get("name"),
        address=addr.get("streetAddress"),
        city=city,
        image=ld.get("image"),
        description=clean_text(ld.get("description")),
        tags=["Hackathon"],
    )]


def _devpost(cfg: dict, ctx: Context) -> list[Event]:
    today = ctx.now.astimezone(PT).date()
    urls, page = [], 1
    while page <= cfg.get("devpost_max_pages", 10):
        data = get_json(DEVPOST_API, **{"status[]": ["upcoming", "open"],
                                        "challenge_type[]": "in-person",
                                        "per_page": 40, "page": page})
        urls += devpost_candidates(data, today, cfg.get("days_ahead", 45))
        if len(data["hackathons"]) < 40:
            break
        page += 1
    events = []
    for url in dict.fromkeys(urls):
        try:
            events += parse_devpost_page(get_text(url))
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            ctx.warn(f"devpost {url}: {type(exc).__name__}: {exc}")
    return events


# --- Y Combinator ---

_DATA_PAGE_RE = re.compile(r'data-page="([^"]*)"')


def parse_yc(html: str) -> list[Event]:
    """Every Bay Area YC event (talks and paper clubs are worth listing too); only the
    hackathons are tagged as such."""
    m = _DATA_PAGE_RE.search(html)
    if not m:
        raise ValueError("YC events page has no data-page")
    events = []
    for it in json.loads(unescape(m.group(1)))["props"]["events"]:
        parts = [p.strip() for p in (it.get("city") or "").split(",")]
        city = _bay_city(parts[0], parts[1] if len(parts) > 1 else None)
        if not city or not it.get("starts_at"):
            continue
        tz = ZoneInfo(it.get("time_zone") or "America/Los_Angeles")
        label = it.get("event_type_label") or ""
        hackathon = "hack" in f"{label} {it['title']}".lower()
        events.append(_event(
            title=clean_text(it["title"], 200),
            start=datetime.fromisoformat(it["starts_at"]).astimezone(tz),
            end=datetime.fromisoformat(it["ends_at"]).astimezone(tz) if it.get("ends_at")
            else None,
            url=f"https://events.ycombinator.com/{it['slug']}",
            host="Y Combinator",
            city=city,
            image=it.get("cover_img_url"),
            tags=["Hackathon"] if hackathon else [],
        ))
    return events


# --- MLH ---

_MLH_RE = re.compile(r'<script[^>]*data-page="app"[^>]*>(.*?)</script>', re.DOTALL)


def _mlh_time(s: str, tz: ZoneInfo, end: bool) -> tuple[datetime, bool]:
    """MLH timestamp -> (local time, date_only)."""
    dt = datetime.fromisoformat(s)
    if dt.time() in MLH_DATE_ONLY:
        return datetime.combine(dt.date(), time(23, 59) if end else time(0), tz), True
    return dt.astimezone(ET).replace(tzinfo=tz), False


def parse_mlh(html: str) -> list[Event]:
    m = _MLH_RE.search(html)
    if not m:
        raise ValueError("MLH season page has no data-page script")
    events = []
    for it in json.loads(m.group(1))["props"]["upcomingEvents"]:
        venue = it.get("venueAddress") or {}
        city = _bay_city(venue.get("city"), venue.get("state") or "")
        if not city or "physical" not in (it.get("formatType") or ""):
            continue
        # Only Bay Area events survive, so the venue's zone is Pacific.
        start, date_only = _mlh_time(it["startsAt"], PT, end=False)
        end, _ = _mlh_time(it["endsAt"], PT, end=True)
        events.append(_event(
            title=clean_text(it["name"], 200),
            start=start,
            end=end,
            all_day=date_only,
            url=it.get("websiteUrl") or f"https://www.mlh.com{it['url']}",
            host="Major League Hacking",
            city=city,
            image=it.get("backgroundUrl"),
            tags=["Hackathon"],
        ))
    return events


# --- AGI House ---

_AGI_CITY_RE = re.compile(r"^(.*?)(?:,?\s+([A-Z]{2})(?:\s+\d{5})?)?$")


def parse_agi(data: dict) -> list[Event]:
    events = []
    for it in data["events"]:
        loc = it.get("location") or {}
        if (it.get("privacy") != "public" or it.get("status") != "published"
                or it.get("dateTbd") or loc.get("isVirtual") or not it.get("startTime")):
            continue
        m = _AGI_CITY_RE.match((loc.get("city") or "").strip())
        city = _bay_city(*m.groups())
        if not city:
            continue
        tz = ZoneInfo(it.get("timezone") or "America/Los_Angeles")
        at_house = loc.get("name") == "AGI House"
        events.append(_event(
            title=clean_text(it["title"], 200),
            start=datetime.fromisoformat(it["startTime"]).astimezone(tz),
            end=datetime.fromisoformat(it["endTime"]).astimezone(tz) if it.get("endTime")
            else None,
            url=f"https://agihouse.org/events/{it['slug']}",
            host="AGI House",
            venue=loc.get("name"),
            address=loc.get("address"),
            city=city,
            lat=AGI_HOUSE_LATLNG[0] if at_house else None,
            lng=AGI_HOUSE_LATLNG[1] if at_house else None,
            image=it.get("coverImageUrl"),
            tags=["Hackathon"] if it.get("type") == "hackathon" else [],
        ))
    return events


def fetch(cfg: dict, ctx: Context) -> list[Event]:
    season = ctx.now.year + (ctx.now.month >= 8)  # MLH's 2027 season is the 2026-27 school year
    # Ordered by how trustworthy the times are: when a hackathon is on two feeds, the first wins.
    feeds = {
        "yc": lambda: parse_yc(get_text(YC_URL)),
        "agi_house": lambda: parse_agi(get_json(AGI_API, limit=100)),
        "mlh": lambda: parse_mlh(get_text(MLH_URL.format(season=season))),
        "devpost": lambda: _devpost(cfg, ctx),
    }
    events, seen = [], set()
    for name, load in feeds.items():
        try:
            found = load()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            ctx.warn(f"{name}: {type(exc).__name__}: {exc}")
            continue
        for e in found:
            if (e.end or e.start) < ctx.now or e.url in seen or dedupe_key(e) in seen:
                continue
            seen |= {e.url, dedupe_key(e)}
            events.append(e)
    return events
