"""East Bay music and performance venues, one config entry per feed:

- venuepilot: venues ticketing through VenuePilot (Ashkenaz, Ivy Room); its public GraphQL
  API is what the venues' own calendar widgets read.
- anotherplanet: Another Planet Entertainment venue sites (Fox Theater, Greek Theatre),
  server-rendered listings with schema.org microdata.
- uctheatre: The UC Theatre's listing page, then each show's #event-data block (UTC times).
- resident_advisor: ra.co's GraphQL listings for an area; Bay-wide, filtered to the East Bay.
- dothebay: DoTheBay (DoStuff) venue pages as JSON, for a configured list of East Bay venues.
  One venue page covers weeks of shows; the per-day listings would cost ~6 requests a day.

The aggregators repeat what venues publish themselves, so within this module a show listed
by both is kept once, from the venue's own feed. A feed that fails is reported as a warning;
the others still count."""

import html
import re
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from ..enrich import EAST_BAY
from ..http import get_json, get_text, request
from ..models import Event, clean_text, parse_dt
from ..state import Context

PACIFIC = ZoneInfo("America/Los_Angeles")
CITIES = EAST_BAY | {"berkeley"}
OWN_FEEDS = {"venuepilot", "anotherplanet", "uctheatre"}  # preferred over aggregators
# Not shows anyone can go to, or not at the listed venue/time any more.
JUNK = re.compile(r"\b(private (party|event)|cancell?ed|postponed|moved to|box office"
                  r"|vip (experience|upgrade))\b", re.IGNORECASE)
_CITY_IN_ADDRESS = re.compile(
    r"\b(" + "|".join(sorted(CITIES, key=len, reverse=True)) + r")\b,?\s+(CA|California)\b",
    re.IGNORECASE)


def _price_free(text: str | None) -> bool | None:
    t = (text or "").strip().lower()
    if not t:
        return None
    if t in ("0", "0.00", "$0") or "free" in t or "no cover" in t:
        return True
    return False if re.search(r"[1-9]", t) else None


# --- DoTheBay ---------------------------------------------------------------------------

def parse_dothebay(data: dict) -> list[Event]:
    """A /venues/<slug>.json page. `begin_time` has the right wall-clock time under a wrong
    (Central) offset, and `tz_adjusted_begin_date` carries a weekly series' first date, so
    the start is `begin_date` + the wall clock, in Pacific. With `doors` set, that time is
    when doors open (checked against Yoshi's and the Fox's own pages)."""
    events = []
    for group in data.get("event_groups", []):
        for ev in group["events"]:
            # Weekly tours and month-long runs show up on every date; they aren't news.
            if ev.get("is_ongoing") or "/events/weekly/" in ev["permalink"]:
                continue
            clock = datetime.fromisoformat(ev["begin_time"]).time()
            if 3 <= clock.hour < 7:  # "4:00 AM daytime clubbing": a mistyped PM time
                continue
            start = datetime.combine(date.fromisoformat(ev["begin_date"]), clock,
                                     tzinfo=PACIFIC)
            v = ev.get("venue") or data.get("venue") or {}
            info = clean_text(ev.get("ticket_info"))
            doors = f"Doors {start:%-I:%M %p}" if ev.get("doors") else ""
            events.append(Event(
                title=clean_text(ev["title"], 200),
                start=start,
                url="https://dothebay.com" + ev["permalink"],
                source="venues",
                venue=clean_text(v.get("title")) or None,
                address=clean_text(v.get("full_address")) or None,
                city=(v.get("city") or "").strip() or None,
                lat=v.get("latitude"),
                lng=v.get("longitude"),
                description=" · ".join(x for x in (doors, info,
                                                   clean_text(ev.get("excerpt"))) if x),
                free=True if ev.get("is_free") else _price_free(info),
                tags=[ev["category"]] if ev.get("category") else [],
            ))
    return events


def fetch_dothebay(feed: dict, end: datetime) -> list[Event]:
    events = []
    for slug in feed["venues"]:
        page = 1
        while True:
            # ?page=1 redirects to the bare URL, so only later pages carry the parameter.
            data = get_json(f"https://dothebay.com/venues/{slug}.json",
                            **({"page": page} if page > 1 else {}))
            events += parse_dothebay(data)
            groups = data.get("event_groups") or []
            if (not groups or page >= data["paging"]["total_pages"]
                    or date.fromisoformat(groups[-1]["date"]) > end.date()):
                break
            page += 1
    return events


# --- Resident Advisor -------------------------------------------------------------------

RA_QUERY = """query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $pageSize: Int,
  $page: Int) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page) {
    data { event { id title startTime contentUrl cost
      venue { name address area { id } } } }
    totalResults } }"""


def parse_resident_advisor(data: dict) -> list[Event]:
    """Times are naive local times. A multi-night event is listed once per night under the
    same event id and start, so ids are kept once."""
    events, seen = [], set()
    for listing in data["data"]["eventListings"]["data"]:
        ev = listing["event"]
        if ev["id"] in seen:
            continue
        seen.add(ev["id"])
        v = ev.get("venue") or {}
        address = v.get("address") or ""
        m = _CITY_IN_ADDRESS.search(address)
        events.append(Event(
            title=clean_text(ev["title"], 200),
            start=parse_dt(ev["startTime"]).replace(tzinfo=PACIFIC),
            url="https://ra.co" + ev["contentUrl"],
            source="venues",
            venue=clean_text(v.get("name")) or None,
            address=clean_text(address) or None,
            city=m.group(1).title() if m else None,
            free=_price_free(ev.get("cost")),
            tags=["Nightlife"],
        ))
    return events


def fetch_resident_advisor(feed: dict, now: datetime, end: datetime) -> list[Event]:
    filters = {"areas": {"eq": feed.get("area", 218)},
               "listingDate": {"gte": f"{now.astimezone(PACIFIC).date()}T00:00:00.000Z",
                               "lte": f"{end.astimezone(PACIFIC).date()}T23:59:59.999Z"}}
    events = []
    for page in range(1, 6):  # 100 per page (RA's maximum); a month is ~200 listings
        r = request("POST", "https://ra.co/graphql",
                    json={"query": RA_QUERY, "operationName": "GET_EVENT_LISTINGS",
                          "variables": {"filters": filters, "pageSize": 100, "page": page}},
                    headers={"Referer": "https://ra.co/events/us/sanfrancisco"})
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise ValueError(data["errors"][0].get("message"))
        events += parse_resident_advisor(data)
        listings = data["data"]["eventListings"]
        if page * 100 >= listings["totalResults"] or not listings["data"]:
            break
    return events


# --- VenuePilot -------------------------------------------------------------------------

VP_QUERY = """{ publicEvents(accountIds: [%d], startDate: "%s") {
  id name date startTime status minimumAge ticketsUrl support
  venue { name city timezone } tickets { price } } }"""


def parse_venuepilot(data: dict, fallback_url: str) -> list[Event]:
    """`date` + `startTime` are the venue's wall clock; `status` is the ticket button text
    ("Tickets", "NO COVER CHARGE", "PRIVATE PARTY")."""
    events = []
    for ev in data["data"]["publicEvents"]:
        v = ev.get("venue") or {}
        status = ev.get("status") or ""
        if JUNK.search(f"{ev['name']} {status}"):
            continue
        tz = ZoneInfo(v.get("timezone") or "America/Los_Angeles")
        start = datetime.fromisoformat(f"{ev['date']}T{ev['startTime']}").replace(tzinfo=tz)
        prices = [t["price"] for t in ev.get("tickets") or [] if t.get("price") is not None]
        free = _price_free(status) or (False if any(p > 0 for p in prices) else None)
        age = ev.get("minimumAge")
        events.append(Event(
            title=clean_text(ev["name"], 200),
            start=start,
            url=ev.get("ticketsUrl") or fallback_url,
            source="venues",
            venue=v.get("name"),
            city=v.get("city"),
            description=" · ".join(x for x in (clean_text(ev.get("support")),
                                               f"{age}+" if age else "") if x),
            free=free,
            tags=["Music"],
        ))
    return events


# --- Another Planet (Fox Theater, Greek Theatre) ----------------------------------------

def parse_anotherplanet(page: str, venue: str, city: str) -> list[Event]:
    """Each listed show is a `mix detail-information` block; the featured slider above the
    list repeats some shows and is skipped by only reading those blocks."""
    events = []
    for block in page.split('<div class="mix detail-information">')[1:]:
        name = re.search(r'itemprop="name">(.*?)</h2>', block, re.DOTALL)
        when = re.search(r'single-date-show" itemprop="startDate" content="([^"]+)"', block)
        info = re.search(r'href="([^"]+)" class="button ghost more-info"', block)
        if not (name and when and info):
            continue
        start = datetime.strptime(re.sub(r"\s+", " ", when.group(1)).replace(" pm", "pm")
                                  .replace(" am", "am"), "%B %d, %Y %I:%M%p")
        support = re.search(r'<div class="support">(.*?)</div>', block, re.DOTALL)
        events.append(Event(
            title=clean_text(name.group(1), 200),
            start=start.replace(tzinfo=PACIFIC),
            url=info.group(1),
            source="venues",
            venue=venue,
            city=city,
            description=clean_text(support.group(1).replace("<br>", " · ")) if support
            else "",
            free=False if "ticketmaster.com" in block else None,
            tags=["Music"],
        ))
    return events


# --- The UC Theatre ---------------------------------------------------------------------

_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_SLUG_DATE = re.compile(r"-(\d{1,2})-(" + "|".join(_MONTHS) + r")(?:-|$)")


def parse_uctheatre_listing(page: str) -> list[str]:
    """Show URLs from /events, in page order."""
    slugs = dict.fromkeys(re.findall(r'href="(/shows/[^"#?]+)"', page))
    return [f"https://www.theuctheatre.org{s}" for s in slugs]


def _slug_date(url: str, today: date) -> date | None:
    """Slugs end in day-month ("gwar-19-nov"); the year is the next one that date falls in."""
    m = _SLUG_DATE.search(url.rsplit("/", 1)[-1])
    if not m:
        return None
    day, month = int(m.group(1)), _MONTHS.index(m.group(2)) + 1
    try:
        d = date(today.year, month, day)
        return d if d >= today - timedelta(days=1) else date(today.year + 1, month, day)
    except ValueError:
        return None


def parse_uctheatre_show(page: str) -> Event | None:
    """The show page's #event-data div holds UTC timestamps (data-start is show time). The
    page's own script that re-labels them with a New York offset is ignored."""
    m = re.search(r'<div id="event-data"(.*?)>', page, re.DOTALL)
    if not m:
        return None
    attrs = {k: html.unescape(v) for k, v in re.findall(r'data-([\w-]+)="([^"]*)"',
                                                          m.group(1))}
    if not attrs.get("start") or not attrs.get("name"):
        return None
    return Event(
        title=clean_text(attrs["name"], 200),
        start=datetime.fromisoformat(attrs["start"]),
        end=datetime.fromisoformat(attrs["end"])
        if attrs.get("end") else None,
        url=attrs.get("ticket-url") or attrs.get("id") or "",
        source="venues",
        venue=attrs.get("venue"),
        address=", ".join(x for x in (attrs.get("street"), attrs.get("city")) if x) or None,
        city=attrs.get("city"),
        image=attrs.get("image") or None,
        description=clean_text(attrs.get("description")),
        free=_price_free(attrs.get("price")),
        tags=["Music"],
    )


def fetch_uctheatre(feed: dict, now: datetime, end: datetime) -> list[Event]:
    today = now.astimezone(PACIFIC).date()
    urls = []
    for url in parse_uctheatre_listing(get_text(feed["url"])):
        d = _slug_date(url, today)
        if d is None or today <= d <= end.date():  # undated slugs are fetched to find out
            urls.append(url)
    events = []
    for url in urls[: feed.get("max_shows", 25)]:
        if e := parse_uctheatre_show(get_text(url)):
            events.append(e)
    return events


# --- Shared -----------------------------------------------------------------------------

def fetch_feed(feed: dict, now: datetime, end: datetime) -> list[Event]:
    kind = feed["type"]
    if kind == "dothebay":
        return fetch_dothebay(feed, end)
    if kind == "resident_advisor":
        return fetch_resident_advisor(feed, now, end)
    if kind == "venuepilot":
        r = request("POST", "https://www.venuepilot.co/graphql",
                    json={"query": VP_QUERY % (feed["account"],
                                               now.astimezone(PACIFIC).date())})
        r.raise_for_status()
        return parse_venuepilot(r.json(), feed["url"])
    if kind == "anotherplanet":
        return parse_anotherplanet(get_text(feed["url"]), feed["venue"], feed["city"])
    if kind == "uctheatre":
        return fetch_uctheatre(feed, now, end)
    raise ValueError(f"unknown venue feed type {kind!r}")


def keep(e: Event, now: datetime, end: datetime) -> bool:
    return (now <= e.start <= end
            and (e.city or "").strip().lower() in CITIES
            and not JUNK.search(e.title))


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def dedupe(events: list[Event]) -> list[Event]:
    """Same local date and the same title, or one title containing the other in the same
    city ("Kamasi Washington" / "Kamasi Washington KEXP Yule Benefit"). Callers pass the
    venues' own feeds first, so their copy wins; the loser is kept in its listings."""
    out: list[Event] = []
    for e in events:
        day, title = e.start.astimezone(PACIFIC).date(), _norm(e.title)
        for k in out:
            other = _norm(k.title)
            if k.start.astimezone(PACIFIC).date() != day:
                continue
            short, long = sorted((title, other), key=len)
            if title == other or (len(short) >= 5 and short in long
                                  and (k.city or "").lower() == (e.city or "").lower()):
                if e.url and e.url != k.url and e.url not in {x["url"] for x in k.listings}:
                    k.listings = k.listings or [{"source": "venues", "url": k.url}]
                    k.listings.append({"source": "venues", "url": e.url,
                                       "name": urlparse(e.url).netloc.removeprefix("www.")})
                break
        else:
            out.append(e)
    return out


def fetch(cfg: dict, ctx: Context) -> list[Event]:
    now = ctx.now.astimezone(UTC)
    end = now + timedelta(days=cfg.get("days_ahead", 30))
    feeds = sorted(cfg.get("list", []), key=lambda f: f["type"] not in OWN_FEEDS)
    events = []
    for feed in feeds:
        try:
            found = fetch_feed(feed, now, end)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            ctx.warn(f"{feed.get('name', feed['type'])}: {type(exc).__name__}: {exc}")
            continue
        events += [e for e in found if keep(e, now, end)]
    return dedupe(events)
