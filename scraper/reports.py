"""Visitor reports of listed events, read from the Google Form's published response sheet.

Each report is shown on its event as the visitor wrote it, marked unverified, so other people
and their AI assistants see it too. The sheet is where the maintainer reviews them: deleting a
row withdraws that report, and adding the event's id to moderation.toml hides the event."""

import csv
import io
import re

EVENT_ID = re.compile(r"\[([0-9a-f]{12})\]\s*$")  # the Report link ends the Event answer with [id]


def parse_reports(sheet: str) -> dict[str, list[dict]]:
    """The response sheet's CSV -> {event id: [{"kind", "details", "date"}]}, oldest first."""
    reports: dict[str, list[dict]] = {}
    for row in csv.DictReader(io.StringIO(sheet)):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
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
