"""Community sources and event reports, run from GitHub issues by .github/workflows/community.yml.

Anyone can open an "Add a source" issue with a calendar link. The bot works out which kind of
feed it is, fetches it once, and comments with the events it found. When the maintainer adds the
`approved` label, the source is saved as contributed/<slug>.toml and the next scrape lists it.
Only feed types the scraper already parses are accepted, so a contribution is data, never code.
A "Report an event" issue that gets `approved` hides that event (moderation.toml).

    python -m scraper.contribute check     # comment on a new or edited source issue
    python -m scraper.contribute approve   # save the approved source, or hide the reported event
    python -m scraper.contribute forms     # turn new Google Form responses into those issues

The Google Forms are the no-account path. Forms can't trigger GitHub, so a scheduled job reads
each form's published response sheet and files new rows as the same issues, with the bot's
check as a comment; approving them works the same way.

The issue comes in through ISSUE_TITLE, ISSUE_BODY, ISSUE_NUMBER, ISSUE_AUTHOR and ISSUE_LABELS; the comment
to post is written to COMMENT_FILE.
"""

import base64
import csv
import io
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import tomllib
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit

import httpx

from .http import get_json, get_text
from .run import build, load_config
from .schema_org import events_from_html
from .sources import feeds, luma
from .state import ROOT, now_utc

LUMA_HOSTS = {"luma.com", "lu.ma", "www.luma.com"}
EVENT_ID = re.compile(r"\[([0-9a-f]{12})\]\s*$")  # the Report link ends the title with [id]


class Rejected(Exception):
    """The submission can't be used; the message is shown to the person who sent it."""


def parse_issue(body: str) -> dict[str, str]:
    """A GitHub issue form body ("### Label" then the answer) -> {lowercased label: answer}."""
    fields = {}
    for block in re.split(r"^### ", body, flags=re.MULTILINE)[1:]:
        label, _, value = block.partition("\n")
        value = value.strip()
        fields[label.strip().lower()] = "" if value == "_No response_" else value
    return fields


def _private(host: str) -> bool:
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError):
        return False  # a name that doesn't resolve fails at fetch time, with a clearer message
    return not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)


def normalize(link: str) -> tuple[str | None, str]:
    """A pasted link -> (feed type, feed url), or (None, url) when only fetching can tell.
    Rejects anything that isn't a public web address: the check runs on a CI machine."""
    link = link.strip().strip("<>")
    if link.startswith("webcal://"):
        link = "https://" + link.removeprefix("webcal://")
    parts = urlsplit(link)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise Rejected("That doesn't look like a web link. Paste the full address, starting with https://")
    if parts.hostname in LUMA_HOSTS:
        slug = parts.path.strip("/").split("/")[0]
        if not slug:
            raise Rejected("Link the Luma calendar itself, like https://luma.com/yourclub")
        return "luma", slug
    if _private(parts.hostname):
        raise Rejected("That address isn't on the public web.")
    if parts.hostname == "calendar.google.com":
        q = parse_qs(parts.query)
        cal = (q.get("src") or [None])[0]
        if not cal and q.get("cid"):
            raw = q["cid"][0]
            cal = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        if not cal and "/ical/" in parts.path:
            cal = unquote(parts.path.split("/ical/")[1].split("/")[0])
        if not cal:
            raise Rejected("Use the calendar's public link: Google Calendar > Settings > your calendar "
                           "> Integrate calendar > Public address in iCal format.")
        return "ics", f"https://calendar.google.com/calendar/ical/{quote(cal, safe='')}/public/basic.ics"
    if parts.path.endswith(".ics"):
        return "ics", link
    return None, link


def probe(url: str) -> tuple[str, str]:
    """Fetch a page to find which feed type it is (or which feed it links to)."""
    text = get_text(url)
    head = text.lstrip()[:500].lower()
    if head.startswith("begin:vcalendar"):
        return "ics", url
    if "<rss" in head or "<feed" in head:
        return "rss", url
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    for kind, path in (("tribe", "/wp-json/tribe/events/v1/events"), ("localist", "/api/2/events")):
        try:
            if "events" in get_json(urljoin(origin, path)):
                return kind, urljoin(origin, path)
        except (httpx.HTTPError, ValueError):
            pass
    if events_from_html(text, "feeds"):
        return "jsonld", url
    raise Rejected("I couldn't find a calendar feed on that page. Links that work: a public Google "
                   "Calendar, a Luma calendar, an .ics or RSS feed, or an events page that lists "
                   "dates (most WordPress, Localist and ticketing sites).")


def _known(config: dict) -> set[str]:
    urls = {f["url"] for f in config.get("feeds", {}).get("list", [])}
    return urls | set(config.get("luma", {}).get("calendars", []))


def source_from_issue(fields: dict[str, str]) -> dict:
    name = re.sub(r"\s+", " ", fields.get("club or calendar name", "")).strip()[:80]
    if not name:
        raise Rejected("Add the club or calendar's name.")
    kind, url = normalize(fields.get("calendar link", ""))
    if kind is None:
        kind, url = probe(url)
    source = {"name": name, "type": kind, "url": url}
    if kind != "luma":
        source["campus"] = fields.get("where are the events?", "").startswith("On or near campus")
    return source


def sample(source: dict) -> tuple[int, list]:
    """Fetch the source once: (upcoming events found, the ones the site would list)."""
    now = now_utc()
    if source["type"] == "luma":
        found = luma.calendar_events(source["url"], 30)
    else:
        found = feeds.fetch_feed(source, 30, now)
        if source.get("campus"):
            for e in found:
                e.city = e.city or "Berkeley"
    upcoming = [e for e in found if now - timedelta(hours=2) < e.start < now + timedelta(days=30)]
    return len(upcoming), build(found, 30, now)


def _code(s: str) -> str:
    """Untrusted text for a bot comment: inline code can't mention, link or format anything."""
    return "`" + re.sub(r"[`\n\r]", " ", s)[:90] + "`"


def check(fields: dict[str, str], config: dict) -> tuple[dict | None, str]:
    try:
        source = source_from_issue(fields)
        if source["url"] in _known(config):
            raise Rejected("This calendar is already on the site. Thanks!")
        upcoming, listed = sample(source)
    except Rejected as exc:
        return None, f"**Can't add this yet.** {exc}\n\nEdit the issue to fix it and I'll check again."
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return None, (f"**Couldn't read that calendar** ({type(exc).__name__}). Check that it's public, "
                      "then edit the issue and I'll try again.")
    lines = [(f"**Found the calendar.** It has {upcoming} upcoming event"
              f"{'' if upcoming == 1 else 's'} in the next 30 days; {len(listed)} would be listed "
              "(the site only shows in-person Bay Area and online events).")]
    lines += [f"- {e.start.strftime('%a %b %-d')}: {_code(e.title)}" for e in listed[:5]]
    if not upcoming:
        lines.append("\nNothing is scheduled yet. That's fine for a new calendar; it will be "
                     "checked every few hours once added.")
    lines.append("\nA maintainer will review it. Adding the `approved` label puts it on the site.")
    return source, "\n".join(lines)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "source"


def save_source(source: dict, author: str, issue: int, root: Path = ROOT) -> Path:
    if source["url"] in _known(load_config(root)):
        raise Rejected("This calendar is already on the site.")
    folder = root / "contributed"
    folder.mkdir(exist_ok=True)
    path = folder / f"{_slug(source['name'])}.toml"
    if path.exists():
        path = folder / f"{_slug(source['name'])}-{issue}.toml"
    fields = {**source, "added_by": author, "issue": issue}
    path.write_text("".join(f"{k} = {json.dumps(v)}\n" for k, v in fields.items()))
    tomllib.loads(path.read_text())  # json strings, ints and bools are valid TOML; make sure
    return path


def hide_event(issue_title: str, reason: str, issue: int, root: Path = ROOT) -> None:
    if not (m := EVENT_ID.search(issue_title)):
        raise Rejected("The title has no event id in [brackets]. Use the Report link on the event.")
    title = issue_title[: m.start()].removeprefix("Report:").strip()
    path = root / "moderation.toml"
    entry = {"id": m.group(1), "title": title[:120], "reason": reason[:60], "issue": issue}
    with path.open("a") as f:
        f.write("\n[[hidden]]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in entry.items()))


FORM_BATCH = 10  # new issues per run, so a flooded form can't bury the issue list


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _quiet(s: str, limit: int = 500) -> str:
    """Form text goes into public issues: no @mentions, and a sane length."""
    return s.replace("@", "@\u200b").strip()[:limit]


def _rows(sheet_csv: str | None) -> list[dict[str, str]]:
    """Response rows keyed by lowercased question, so the forms' wording can change a bit."""
    if not sheet_csv:
        return []
    return [{k.strip().lower(): v for k, v in row.items() if k}
            for row in csv.DictReader(io.StringIO(get_text(sheet_csv)))]


def _answer(row: dict[str, str], word: str) -> str:
    return next((v.strip() for k, v in row.items() if word in k), "")


def _form_body(fields: dict[str, str], stamp: str) -> str:
    answers = "".join(f"### {label}\n\n{_quiet(value) or '_No response_'}\n\n"
                      for label, value in fields.items())
    return f"{answers}_Sent through the Google Form ({stamp})._"


def from_forms(config: dict, gh=_gh) -> None:
    c = config.get("community", {})
    issues = json.loads(gh("issue", "list", "--state", "all", "--limit", "1000",
                           "--json", "title,body"))
    filed = "\n".join(f"{i['title']}\n{i['body']}" for i in issues)
    made = 0
    for row in _rows(c.get("source_sheet_csv")):
        link = _answer(row, "link")
        if not link or link in filed or made >= FORM_BATCH:
            continue
        fields = {"Club or calendar name": _answer(row, "name"), "Calendar link": link,
                  "Where are the events?": _answer(row, "where"),
                  "Anything else?": _answer(row, "anything")}
        body = _form_body(fields, row.get("timestamp", ""))
        url = gh("issue", "create", "--title", f"Add source: {_quiet(fields['Club or calendar name'], 80)}",
                 "--label", "new-source", "--body", body)
        _, comment = check(parse_issue(body), config)
        gh("issue", "comment", url.strip().rsplit("/", 1)[1], "--body", comment)
        filed += "\n" + link
        made += 1
    for row in _rows(c.get("report_sheet_csv")):
        stamp, event = row.get("timestamp", ""), _answer(row, "event")
        body = _form_body({"What's wrong?": _answer(row, "wrong"),
                           "Anything else?": _answer(row, "anything")}, stamp)
        if not event or (f"({stamp})" in filed and event in filed) or made >= FORM_BATCH:
            continue
        gh("issue", "create", "--title", f"Report: {_quiet(event, 150)}", "--label", "report",
           "--body", body)
        filed += f"\n{event}\n({stamp})"
        made += 1


def main(command: str) -> int:
    if command == "forms":
        from_forms(load_config())
        return 0
    fields = parse_issue(os.environ.get("ISSUE_BODY", ""))
    issue = int(os.environ["ISSUE_NUMBER"])
    labels = set(json.loads(os.environ.get("ISSUE_LABELS", "[]")))
    comment = Path(os.environ.get("COMMENT_FILE", "comment.md"))
    try:
        if "report" in labels and command == "approve":
            hide_event(os.environ.get("ISSUE_TITLE", ""), fields.get("what's wrong?", ""), issue)
            comment.write_text("Thanks for the report. This event is now hidden from the site; "
                               "it disappears on the next update.")
            return 0
        source, text = check(fields, load_config())
        if command == "approve" and source:
            author = os.environ.get("ISSUE_AUTHOR", "")
            # Form submissions are filed by the bot; the person who sent them is anonymous.
            path = save_source(source, "" if author.endswith("[bot]") else author, issue)
            text = (f"Added as `{path.relative_to(ROOT)}`. Its events show up on the site within a "
                    "few minutes. Thanks for contributing!")
        comment.write_text(text)
        return 0 if source else 1
    except Rejected as exc:
        comment.write_text(f"**Can't do this yet.** {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
