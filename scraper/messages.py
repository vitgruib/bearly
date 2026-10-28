"""Shared handling for message-based sources (email lists, Slack, Instagram): resolve any
event links, and parse the text itself for events announced without one."""

from datetime import datetime

from . import links
from .models import Event, dedupe_key
from .textparse import parse_announcement


def events_from_message(text: str, sent: datetime, source: str, *, subject: str | None = None,
                        host: str | None = None, url: str = "") -> list[Event]:
    found = []
    for link in links.event_urls(text):
        found += links.resolve(link, source)
    resolved = {dedupe_key(e) for e in found}
    for e in parse_announcement(text, sent, source, url=url, host=host, subject=subject):
        # A pasted Luma/Partiful link already gave us the authoritative record.
        if dedupe_key(e) in resolved or any(e.start == f.start for f in found):
            continue
        found.append(e)
    return found
