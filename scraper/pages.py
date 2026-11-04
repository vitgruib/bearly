"""One static page per event at e/<id>.html, plus sitemap.xml.

Chat apps and search engines read a page's HTML without running its script, and never see
the part of a link after '#'. A real page per event is what gives a shared link its preview
card (Open Graph tags) and lets Google list the event (schema.org Event data)."""

import json
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .llms import time_range
from .models import Event

PACIFIC = ZoneInfo("America/Los_Angeles")
STATIC = ["", "about.html", "stats.html"]


def h(s: str | None) -> str:
    return escape(s or "", quote=True)


def _summary(e: Event) -> str:
    day = e.start.astimezone(PACIFIC)
    place = e.venue or e.address or ("Online" if e.online else "")
    return " · ".join(x for x in [f"{day:%a %b %-d}, {time_range(e)}", place] if x)


def _json_ld(e: Event, page: str) -> str:
    place = ({"@type": "VirtualLocation", "url": e.url} if e.online and not e.venue else
             {"@type": "Place", "name": e.venue or e.address or e.city or "Berkeley",
              "address": e.address or e.city or "Berkeley, CA"})
    data = {"@context": "https://schema.org", "@type": "Event", "name": e.title,
            "startDate": e.start.isoformat(), "url": page, "location": place,
            "eventAttendanceMode": "https://schema.org/" + (
                "OnlineEventAttendanceMode" if e.online and not e.venue else "OfflineEventAttendanceMode"),
            "description": e.description, "sameAs": e.url}
    if e.end:
        data["endDate"] = e.end.isoformat()
    if e.image:
        data["image"] = [e.image]
    if e.host:
        data["organizer"] = {"@type": "Organization", "name": e.host}
    if e.free:
        data["isAccessibleForFree"] = True
    # Titles and descriptions come from strangers: "</script>" in one must not end the block.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def _gcal(e: Event) -> str:
    fmt = "%Y%m%dT%H%M%SZ"
    end = e.end or e.start
    return "https://calendar.google.com/calendar/render?" + urlencode({
        "action": "TEMPLATE", "text": e.title, "details": e.url,
        "dates": f"{e.start.astimezone(ZoneInfo('UTC')):{fmt}}/{end.astimezone(ZoneInfo('UTC')):{fmt}}",
        "location": e.address or e.venue or ""})


def event_page(e: Event, site_url: str) -> str:
    page = f"{site_url}e/{e.id}.html"
    summary = _summary(e)
    blurb = e.description or f"{e.title}, on Lo-Cal, Berkeley's open-source event calendar."
    preview = " ".join(x for x in [summary + ".", blurb] if x)[:300]
    image = e.image or f"{site_url}og.png"
    facts = [f"<p class=\"when\">{h(summary)}</p>"]
    if e.host:
        facts.append(f"<p>Hosted by {h(e.host)}</p>")
    if e.access:
        facts.append(f"<p class=\"access\">Getting in: {h(' · '.join(e.access))}</p>")
    if e.tags:
        facts.append(f"<p class=\"tags\">{h(' · '.join(e.tags))}</p>")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(e.title)} · Lo-Cal</title>
  <meta name="description" content="{h(preview)}">
  <link rel="canonical" href="{h(page)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Lo-Cal">
  <meta property="og:title" content="{h(e.title)}">
  <meta property="og:description" content="{h(preview)}">
  <meta property="og:url" content="{h(page)}">
  <meta property="og:image" content="{h(image)}">
  <meta name="twitter:card" content="summary_large_image">
  <link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../styles.css">
  <link rel="stylesheet" href="../event.css">
  <script type="application/ld+json">{_json_ld(e, page)}</script>
  <script data-goatcounter="https://lo-cal.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>
</head>
<body>
  <main class="wrap event-page">
    <nav class="nav" aria-label="Site"><a href="../">All events</a><a href="../about.html">How it works</a></nav>
    <h1>{h(e.title)}</h1>
    {chr(10).join(facts)}
    <p class="desc-full">{h(e.description)}</p>
    <p class="actions">
      <a class="button" href="{h(e.url)}" rel="noopener">Event page &amp; RSVP</a>
      <a class="button ghost" href="{h(_gcal(e))}" target="_blank" rel="noopener">Add to Google Calendar</a>
      <a class="button ghost" href="../#event={e.id}">Open in Lo-Cal</a>
    </p>
    <p class="note">Found by Lo-Cal, Berkeley's open-source event calendar. Details come from the
      event's own listing; tags and "getting in" are keyword guesses, so check the event page.</p>
  </main>
</body>
</html>
"""


def write_pages(events: list[Event], site_url: str, site: Path, now: datetime) -> None:
    out = site / "e"
    out.mkdir(exist_ok=True)
    keep = set()
    for e in events:
        name = f"{e.id}.html"
        keep.add(name)
        (out / name).write_text(event_page(e, site_url))
    for old in out.glob("*.html"):  # ended or removed events
        if old.name not in keep:
            old.unlink()
    day = now.date().isoformat()
    urls = [f"{site_url}{p}" for p in STATIC] + [f"{site_url}e/{n}" for n in sorted(keep)]
    (site / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{escape(u)}</loc><lastmod>{day}</lastmod></url>\n" for u in urls)
        + "</urlset>\n")
