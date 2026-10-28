"""schema.org Event (JSON-LD) -> Event. Many event sites publish this, so it doubles as the
generic fallback for any event link found in an email or Slack message."""

from .http import json_ld
from .models import Event, clean_text, parse_dt


def _is_event(node: dict) -> bool:
    t = node.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(isinstance(x, str) and x.endswith("Event") or x == "Hackathon" for x in types)


def iter_event_nodes(doc):
    if isinstance(doc, list):
        for d in doc:
            yield from iter_event_nodes(d)
    elif isinstance(doc, dict):
        if _is_event(doc):
            yield doc
        for key in ("itemListElement", "@graph", "item"):
            if key in doc:
                yield from iter_event_nodes(doc[key])


def to_event(node: dict, source: str) -> Event | None:
    if not node.get("startDate") or not node.get("name"):
        return None
    loc = node.get("location") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = loc.get("address") or {}
    if isinstance(addr, str):
        addr = {"streetAddress": addr}
    geo = loc.get("geo") or {}
    online = (loc.get("@type") == "VirtualLocation"
              or "Online" in str(node.get("eventAttendanceMode", "")))
    offers = node.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    free = node.get("isAccessibleForFree")
    if free is None and offers.get("price") is not None:
        free = float(offers["price"] or 0) == 0
    organizer = node.get("organizer") or {}
    if isinstance(organizer, list):
        organizer = organizer[0] if organizer else {}
    image = node.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    start = parse_dt(node["startDate"])
    if start.tzinfo is None:
        return None  # date-only listings can't be placed on a timeline reliably
    street = addr.get("streetAddress")
    return Event(
        title=clean_text(node["name"], 200),
        start=start,
        end=parse_dt(node["endDate"]) if node.get("endDate") else None,
        url=node.get("url") or "",
        source=source,
        host=organizer.get("name"),
        venue=loc.get("name") if loc.get("name") != addr.get("addressLocality") else street,
        address=", ".join(x for x in (street, addr.get("addressLocality")) if x) or None,
        city=addr.get("addressLocality"),
        lat=float(geo["latitude"]) if geo.get("latitude") else None,
        lng=float(geo["longitude"]) if geo.get("longitude") else None,
        online=online,
        image=image,
        description=clean_text(node.get("description")),
        free=free,
    )


def events_from_html(html: str, source: str) -> list[Event]:
    out = []
    for doc in json_ld(html):
        for node in iter_event_nodes(doc):
            if e := to_event(node, source):
                out.append(e)
    return out
