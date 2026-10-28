"""Pull events out of free-form announcements (listserv emails, Slack posts) with Claude.

Only runs when ANTHROPIC_API_KEY is set. Results are cached by message hash in
data/llm_cache.json, so each message is paid for once even though the scraper reruns
every few hours."""

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
from pydantic import BaseModel

from .models import Event, clean_text

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
CACHE = Path(__file__).resolve().parent.parent / "data" / "llm_cache.json"
PACIFIC = ZoneInfo("America/Los_Angeles")

# Cheap pre-filter so we don't send newsletters with no event in them to the API.
EVENTY = re.compile(
    r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b|\b\d{1,2}(:\d{2})?\s?(am|pm)\b|"
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}\b|"
    r"\b\d{1,2}/\d{1,2}\b|\btonight\b|\btomorrow\b", re.IGNORECASE)


class ExtractedEvent(BaseModel):
    title: str
    start: str  # ISO 8601 local time, e.g. 2026-11-03T18:00
    end: str | None = None
    location: str | None = None
    online: bool = False
    url: str | None = None
    host: str | None = None
    description: str
    free_food: bool = False


class Extraction(BaseModel):
    events: list[ExtractedEvent]


SYSTEM = """You extract events from announcements sent to UC Berkeley students (mailing \
lists, club newsletters, Slack posts). Return every distinct event a student could attend \
that happens on or after the reference date. Skip deadlines, applications and job postings \
that are not events, and anything with no specific date. Resolve relative dates ("this \
Friday", "tomorrow") against the reference date, which is when the message was sent. \
Times are Pacific. If no time is given, use 00:00 for start. Keep description to one or \
two sentences in your own words. Set free_food when food or drinks are offered. Use the \
event's RSVP or info link as url when the message has one."""


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except FileNotFoundError:
        return {}


_cache = _load_cache()


def save_cache() -> None:
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(_cache, indent=0, sort_keys=True))


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _ask_claude(text: str, sent: datetime) -> list[dict]:
    client = anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": f"Reference date: {sent.astimezone(PACIFIC):%A %Y-%m-%d %H:%M}\n\n"
                       f"<message>\n{text[:30000]}\n</message>",
        }],
        output_format=Extraction,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return []
    return [e.model_dump() for e in response.parsed_output.events]


def extract(text: str, sent: datetime, source: str) -> list[Event]:
    if not EVENTY.search(text):
        return []
    key = hashlib.sha256(text.encode()).hexdigest()[:20]
    if key not in _cache:
        if not enabled():
            return []
        try:
            _cache[key] = _ask_claude(text, sent)
        except anthropic.APIError as exc:
            log.warning("extraction failed (%s); will retry next run", exc)
            return []
    events = []
    for x in _cache[key]:
        try:
            start = datetime.fromisoformat(x["start"])
            end = datetime.fromisoformat(x["end"]) if x.get("end") else None
        except ValueError:
            continue
        start = start if start.tzinfo else start.replace(tzinfo=PACIFIC)
        if end and not end.tzinfo:
            end = end.replace(tzinfo=PACIFIC)
        desc = clean_text(x["description"])
        events.append(Event(
            title=clean_text(x["title"], 200),
            start=start,
            end=end,
            all_day=start.hour == 0 and start.minute == 0 and end is None,
            url=x.get("url") or "",
            source=source,
            host=x.get("host"),
            venue=x.get("location"),
            online=x.get("online", False),
            description=desc + (" Free food." if x.get("free_food") else ""),
        ))
    return events
