"""events.berkeley.edu (LiveWhale). Asked one day at a time; busy days run past the API's
100-per-page cap, so we follow its pages."""

import re
from datetime import date, timedelta

from ..http import get_json
from ..models import Event, clean_text, parse_dt

BASE = "https://events.berkeley.edu/live/json/v2/events"
FIELDS = "location,tags,summary,image,event_types,group_title,cost"
# Rec Sports publishes gym hours, lap swim and PE class sections as "events".
REC_KEEP = re.compile(r"tournament|clinic|workshop|festival|\b5k\b|race|fair|night", re.IGNORECASE)


def parse_item(it: dict) -> Event | None:
    types = it.get("event_types") or []
    # Long-running exhibits repeat every single day and would bury everything else.
    if it.get("is_canceled") or (it.get("is_all_day") and "Exhibits" in types):
        return None
    if it.get("group_title") == "Recreational Sports" and not REC_KEEP.search(it["title"]):
        return None
    start = parse_dt(it["date_iso"])
    cost = str(it.get("cost") or "").lower()
    return Event(
        title=clean_text(it["title"], 200),
        start=start,
        end=parse_dt(it["date2_iso"]) if it.get("date2_iso") else None,
        all_day=bool(it.get("is_all_day")),
        url=it["url"],
        source="berkeley_calendar",
        host=clean_text(it.get("group_title")) or None,
        venue=it.get("location_title") or it.get("location"),
        address=it.get("location"),
        city="Berkeley" if not it.get("is_online") else None,
        lat=it.get("location_latitude"),
        lng=it.get("location_longitude"),
        online=bool(it.get("is_online")) and not it.get("location_latitude"),
        image=(it.get("thumbnail") or "").replace("/width/80/height/80/",
                                                  "/width/640/height/360/") or None,
        description=clean_text(it.get("summary")),
        free=True if "free" in cost else (False if "$" in cost else None),
        tags=[*types, *(it.get("tags") or [])],
    )


def fetch(cfg: dict) -> list[Event]:
    events = []
    today = date.today()
    for i in range(cfg.get("days_ahead", 21)):
        d = today + timedelta(days=i)
        url = (f"{BASE}/start_date/{d.isoformat()}/end_date/{(d + timedelta(days=1)).isoformat()}"
               f"/response_fields/{FIELDS}/")
        page, pages = 1, 1
        while page <= pages:
            data = get_json(url, page=page)
            pages = data.get("meta", {}).get("total_pages") or 1
            for it in data.get("data", []):
                if (e := parse_item(it)) and e.start.date() == d:
                    events.append(e)
            page += 1
    return events
