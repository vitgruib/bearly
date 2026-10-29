"""Community sources, events and reports, run from GitHub issues by .github/workflows/community.yml.

Nothing a stranger sends goes up until the maintainer adds the `approved` label:
- "Add a source" (new-source): the bot works out which kind of feed the link is, fetches it
  once and comments with the events it found. Approved, it's saved as contributed/<slug>.toml.
  Only feed types the scraper already parses are accepted, so a contribution is data, never code.
- "Add an event" (new-event): the bot fetches the event and comments with a preview, or closes
  the issue when the site already lists it. Approved, its link goes in contributed/events.toml
  and the reports source re-reads it every run.
- "Report an event" (report): approved, that event is hidden (moderation.toml).

    python -m scraper.contribute check     # comment on a new or edited source or event issue
    python -m scraper.contribute approve   # save the source or event, or hide the reported event
    python -m scraper.contribute forms     # turn new Google Form responses into those issues

The Google Form is the no-account path: one form for all of the above plus feedback. Forms can't
trigger GitHub, so a scheduled job reads its published response sheet and files new rows as
the same issues, with the bot's check as a comment.

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

from . import links
from .http import get_json, get_text
from .run import EVENTS_FILE, build, load_config
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
    if path.exists() or path.name == EVENTS_FILE:
        path = folder / f"{_slug(source['name'])}-{issue}.toml"
    fields = {**source, "added_by": author, "issue": issue}
    path.write_text("".join(f"{k} = {json.dumps(v)}\n" for k, v in fields.items()))
    tomllib.loads(path.read_text())  # json strings, ints and bools are valid TOML; make sure
    return path


def _key(url: str) -> str:
    return url.split("?")[0].split("#")[0].rstrip("/").lower()


def _published(config: dict) -> dict[str, str]:
    """Every link the live site lists, mapped to that event's title."""
    owner, name = config["repo"].split("/")
    data = get_json(f"https://{owner}.github.io/{name}/data/events.json")
    return {_key(u): e["title"] for e in data["events"]
            for u in [e["url"], *(x["url"] for x in e.get("listings", []))] if u}


def event_link(fields: dict[str, str]) -> str:
    link = fields.get("event link", "").strip().strip("<>")
    if not link:
        raise Rejected("There's no event link to add. Add the event's page to the issue, or add "
                       "the club's calendar instead.")
    parts = urlsplit(link)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise Rejected("That doesn't look like a web link. Paste the full address, starting with https://")
    if _private(parts.hostname):
        raise Rejected("That address isn't on the public web.")
    return link


def check_event(fields: dict[str, str], config: dict) -> tuple[str | None, str, bool]:
    """(link to save or None, the bot's comment, whether the issue can be closed)."""
    if not fields.get("event link") and fields.get("no link? where was it posted?"):
        return None, ("**No link,** so a maintainer will look at where it was posted. If it's a "
                      "club that posts often, its calendar may be added instead."), False
    try:
        link = event_link(fields)
        if title := _published(config).get(_key(link)):
            return None, f"**Already listed** as {_code(title)}. Thanks!", True
        found = links.resolve(link, "reports")
    except Rejected as exc:
        return None, f"**Can't add this yet.** {exc}\n\nEdit the issue to fix it and I'll check again.", False
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return None, (f"**Couldn't read that page** ({type(exc).__name__}). Edit the issue with a "
                      "public link and I'll try again."), False
    if not found:
        return None, ("**Couldn't find an event on that page.** Links that work: Luma, Partiful, "
                      "Eventbrite, Meetup, or any page that lists its date in a standard format. "
                      "Edit the issue to fix it and I'll check again."), False
    if len(found) > 1:
        return None, (f"**That's a calendar** with {len(found)} events. To add all of them, use "
                      "Add a source instead."), False
    listed = build(found, 30, now_utc())
    e = found[0]
    where = "Online" if e.online else e.venue or e.address or e.city or "no place given"
    lines = [f"**Found it:** {_code(e.title)}, {e.start.strftime('%a %b %-d, %-I:%M %p')} UTC, {_code(where)}."]
    if not listed:
        lines.append("\nThe site wouldn't list it: it's past, more than 30 days out, or outside "
                     "the Bay Area.")
    lines.append("\nA maintainer will review it. Adding the `approved` label puts it on the site.")
    return link, "\n".join(lines), False


def save_event(link: str, author: str, issue: int, root: Path = ROOT) -> None:
    path = root / "contributed" / EVENTS_FILE
    saved = tomllib.loads(path.read_text()).get("events", []) if path.exists() else []
    if any(_key(e["url"]) == _key(link) for e in saved):
        raise Rejected("This event was already added.")
    path.parent.mkdir(exist_ok=True)
    entry = {"url": link, "by": author, "issue": issue}
    with path.open("a") as f:
        f.write("\n[[events]]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in entry.items()))


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
    """Response rows keyed by lowercased question title."""
    if not sheet_csv:
        return []
    return [{k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            for row in csv.DictReader(io.StringIO(get_text(sheet_csv)))]


def _form_body(fields: dict[str, str], stamp: str) -> str:
    answers = "".join(f"### {label}\n\n{_quiet(value) or '_No response_'}\n\n"
                      for label, value in fields.items())
    return f"{answers}_Sent through the Google Form ({stamp})._"


def _form_issue(row: dict[str, str]) -> tuple[str, str, dict[str, str]] | None:
    """A response row -> (issue title, label, answers), or None for a row with nothing in it."""
    kind = row.get("what's this about?", "")
    if kind == "Add an event":
        fields = {"Event link": row.get("event link", ""),
                  "No link? Where was it posted?": row.get("no link? where was it posted?", "")}
        if not any(fields.values()):
            return None
        title = fields["Event link"] or fields["No link? Where was it posted?"]
        return f"Add event: {_quiet(title, 80)}", "new-event", fields
    if kind == "Add a club's calendar":
        fields = {"Club or calendar name": row.get("club or calendar name", ""),
                  "Calendar link": row.get("calendar link", ""),
                  "Where are the events?": row.get("where are the events?", "")}
        if not fields["Calendar link"]:
            return None
        return f"Add source: {_quiet(fields['Club or calendar name'], 80)}", "new-source", fields
    if kind == "Report an event":
        if not (event := row.get("event", "")):
            return None
        fields = {"What's wrong?": row.get("what's wrong?", ""), "Details": row.get("details", "")}
        return f"Report: {_quiet(event, 150)}", "report", fields
    if kind == "Send feedback":
        if not (text := row.get("your feedback", "")):
            return None
        return f"Feedback: {_quiet(text, 60)}", "feedback", {"Your feedback": text}
    return None


def from_forms(config: dict, gh=_gh) -> None:
    issues = json.loads(gh("issue", "list", "--state", "all", "--limit", "1000",
                           "--json", "title,body"))
    filed = "\n".join(i["body"] for i in issues)
    made = 0
    for row in _rows(config.get("community", {}).get("sheet_csv")):
        stamp = row.get("timestamp", "")
        if made >= FORM_BATCH or f"Google Form ({stamp})" in filed or not (issue := _form_issue(row)):
            continue
        title, label, fields = issue
        body = _form_body(fields, stamp)
        url = gh("issue", "create", "--title", title, "--label", label, "--body", body)
        number = url.strip().rsplit("/", 1)[1]
        if label == "new-source":
            _, comment = check(parse_issue(body), config)
            gh("issue", "comment", number, "--body", comment)
        elif label == "new-event":
            _, comment, close = check_event(parse_issue(body), config)
            gh("issue", "close" if close else "comment", number, "--comment" if close else "--body", comment)
        filed += "\n" + body
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
        author = os.environ.get("ISSUE_AUTHOR", "")
        # Form submissions are filed by the bot; the person who sent them is anonymous.
        author = "" if author.endswith("[bot]") else author
        if "new-event" in labels and command == "approve":
            save_event(event_link(fields), author, issue)
            comment.write_text("Added. It shows up on the site within a few minutes. Thanks!")
            return 0
        if "new-event" in labels:
            _, text, close = check_event(fields, load_config())
            if close and (out := os.environ.get("GITHUB_OUTPUT")):
                with open(out, "a") as f:
                    f.write("close=true\n")
            comment.write_text(text)
            return 0
        source, text = check(fields, load_config())
        if command == "approve" and source:
            path = save_source(source, author, issue)
            text = (f"Added as `{path.relative_to(ROOT)}`. Its events show up on the site within a "
                    "few minutes. Thanks for contributing!")
        comment.write_text(text)
        return 0 if source else 1
    except Rejected as exc:
        comment.write_text(f"**Can't do this yet.** {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
