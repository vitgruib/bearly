"""Turn event links pasted into emails / Slack into full Event records."""

import logging
import re
from urllib.parse import urlparse

from .http import get_json, get_text
from .models import Event
from .schema_org import events_from_html
from .sources import luma, partiful

log = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s<>\"')\]|>]+")

# Hosts whose event pages publish schema.org Event JSON-LD.
JSON_LD_HOSTS = ("eventbrite.com", "cerebralvalley.ai", "meetup.com", "events.berkeley.edu",
                 "posh.vip", "dice.fm", "allevents.in")
LUMA_HOSTS = ("lu.ma", "luma.com")
# Luma paths that are app pages rather than event or calendar slugs.
LUMA_RESERVED = {"home", "discover", "signin", "create", "calendar", "user", "pricing", "ios",
                 "android", "explore", "settings", "map", "event", "check-in"}


def event_urls(text: str) -> list[str]:
    seen, out = set(), []
    for raw in URL_RE.findall(text or ""):
        url = raw.rstrip(".,;:!?")
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if not (host in LUMA_HOSTS or host == "partiful.com"
                or any(host.endswith(h) for h in JSON_LD_HOSTS)):
            continue
        key = url.split("?")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def resolve(url: str, source: str) -> list[Event]:
    """Fetch one link. Luma calendar links expand to all of the calendar's upcoming events."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/")
    try:
        if host in LUMA_HOSTS:
            if not path or "/" in path or path in LUMA_RESERVED:
                return []
            data = get_json(f"{luma.API}/url", url=path)
            if data.get("kind") == "event":
                events = [luma.parse_entry(data["data"])]
            elif data.get("kind") == "calendar":
                events = luma.calendar_events(data["data"]["calendar"]["api_id"])
            else:
                events = []
        elif host == "partiful.com":
            events = [e] if path.startswith("e/") and (e := partiful.resolve(url)) else []
        else:
            events = events_from_html(get_text(url), source)
    except Exception as exc:  # noqa: BLE001 -- one dead link must not sink a whole inbox
        log.warning("could not resolve %s: %s", url, exc)
        return []
    for e in events:
        e.also_on.append(source)
    return events
