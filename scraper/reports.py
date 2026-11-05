"""Visitor reports of listed events, read from the Google Form's published response sheet.

Each report is shown on its event as the visitor wrote it, marked unverified, so other people
and their AI assistants see it too. The sheet is where the maintainer reviews them: deleting a
row withdraws that report, and adding the event's id to moderation.toml hides the event."""

import csv
import io
import re
from datetime import date, timedelta

from .models import Event

LINK_MEMORY = timedelta(days=60)
EVENT_ID = re.compile(r"\[([0-9a-f]{12})\]\s*$")  # the Report link ends the Event answer with [id]


def parse_reports(sheet: str) -> dict[str, list[dict]]:
    """The response sheet's CSV -> {event id: [{"kind", "details", "date"}]}, oldest first."""
    reports: dict[str, list[dict]] = {}
    for row in csv.DictReader(io.StringIO(sheet)):
        # One line per answer: the LLM files list each event on a single line.
        row = {k.strip().lower(): " ".join((v or "").split()) for k, v in row.items() if k}
        if row.get("what's this about?") != "Report an event":
            continue
        if not (m := EVENT_ID.search(row.get("event", ""))):
            continue
        reports.setdefault(m.group(1), []).append({
            "kind": row.get("what's wrong?") or "Other",
            "details": row.get("details", "")[:300],
            "date": row.get("timestamp", "").split(" ")[0],
        })
    return reports


def describe(report: dict) -> str:
    return f"{report['kind']}: {report['details']}" if report["details"] else report["kind"]


def _links(e: Event) -> set[str]:
    return {e.url, *(listing["url"] for listing in e.listings)} - {""}


def attach(events: list[Event], reports: dict[str, list[dict]], links: dict, today: date) -> None:
    """Put each report on its event. An id comes from the title and date, so it changes when either
    does; `links` (kept in state.json) remembers the links behind every id an event has had, and a
    report on an old id follows them to the event now listed there. A repeating series lists only
    its next date under one link, so there a report stays with the date it was about."""
    for e in events:
        links[e.id] = [sorted(_links(e)), today.isoformat(), e.start.date().isoformat()]
    by_id = {e.id: e for e in events}
    by_link = {link: e for e in events for link in _links(e)}
    for e in events:
        e.reports = []
    for event_id, found in reports.items():
        if not (e := by_id.get(event_id)) and event_id in links:
            old_links, _, old_date = links[event_id]
            e = next((by_link[u] for u in old_links if u in by_link), None)
            if e and e.repeats and e.start.date().isoformat() != old_date:
                e = None
        if e:
            e.reports += found
    cutoff = (today - LINK_MEMORY).isoformat()
    for event_id in [i for i, (_, seen, _) in links.items() if seen < cutoff]:
        del links[event_id]
