"""Shared handling for message-based sources (email lists, Slack): resolve any event links,
and have Claude read the text for events that were announced without one."""

from datetime import datetime

from . import extract, links
from .models import Event


def events_from_message(text: str, sent: datetime, source: str) -> list[Event]:
    found = []
    for url in links.event_urls(text):
        found += links.resolve(url, source)
    for e in extract.extract(text, sent, source):
        # A pasted Luma/Partiful link already gave us the authoritative record.
        if e.url and any(e.url.rstrip("/") in f.url for f in found):
            continue
        found.append(e)
    return found
