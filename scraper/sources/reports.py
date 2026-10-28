"""Missed-event reports: the "Missing an event?" link on the site opens a Google Form, and
its response sheet is published to the web as CSV. Every event link in a recent report is
fetched like a link in an email, so a report goes up on the next run when the link is a real
Luma, Partiful, Eventbrite, Meetup... event in the Bay Area (the region filter still applies).
Reports with no supported link stay in the sheet for a person to read."""

import csv
import io
from datetime import datetime, timedelta

from .. import links
from ..http import get_text
from ..state import Context, NotConfigured


def _key(url: str) -> str:
    return url.split("?")[0].rstrip("/")


def fetch(cfg: dict, ctx: Context) -> list:
    if not cfg.get("sheet_csv"):
        raise NotConfigured("set [reports] sheet_csv")
    # Form timestamps are the sheet owner's local time; a few hours either way doesn't matter.
    since = ctx.now.replace(tzinfo=None) - timedelta(days=cfg.get("days_back", 60))
    blocked = {_key(u) for u in cfg.get("block", [])}
    urls: list[str] = []
    for row in list(csv.reader(io.StringIO(get_text(cfg["sheet_csv"]))))[1:]:
        try:
            if datetime.strptime(row[0], "%m/%d/%Y %H:%M:%S") < since:
                continue
        except (ValueError, IndexError):
            pass  # an edited or oddly formatted row is still worth reading
        urls += [u for u in links.event_urls(" ".join(row)) if u not in urls and u not in blocked]
    events = []
    for url in urls:
        events += links.resolve(url, "reports")
    return [e for e in events if _key(e.url) not in blocked]
