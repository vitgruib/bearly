"""Cerebral Valley: the /events page publishes its list as a JSON-LD ItemList."""

from ..http import get_text
from ..schema_org import events_from_html


def fetch(cfg: dict) -> list:
    events = []
    for path in cfg.get("pages", ["/events"]):
        events += events_from_html(get_text(f"https://cerebralvalley.ai{path}"),
                                   "cerebral_valley")
    for e in events:
        if e.host == "Cerebral Valley":
            e.host = None
    return events
