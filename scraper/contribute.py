"""Event reports, run from GitHub issues by .github/workflows/community.yml.

New sources come only through pull requests to sources.toml; there is no way for the public to
add a calendar or an event. What strangers can do is report a listed event: once the maintainer
adds the `approved` label to a "Report an event" (report) issue, that event is hidden
(moderation.toml).

    python -m scraper.contribute approve   # hide the reported event
    python -m scraper.contribute forms     # turn new Google Form responses into issues

The Google Form is the no-account path for reports and feedback. Forms can't trigger GitHub,
so a scheduled job reads its published response sheet and files new rows as the same issues.

The issue comes in through ISSUE_TITLE, ISSUE_BODY and ISSUE_NUMBER; the comment to post is
written to COMMENT_FILE.
"""

import csv
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .http import get_text
from .run import load_config
from .state import ROOT

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
    """A response row -> (issue title, label, answers), or None for a row that isn't a report or
    feedback, or has nothing in it. Rows asking to add an event or calendar are dropped:
    sources come only through pull requests."""
    kind = row.get("what's this about?", "")
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
        gh("issue", "create", "--title", title, "--label", label, "--body", body)
        filed += "\n" + body
        made += 1


def main(command: str) -> int:
    if command == "forms":
        from_forms(load_config())
        return 0
    if command != "approve":
        raise SystemExit(f"unknown command: {command}")
    fields = parse_issue(os.environ.get("ISSUE_BODY", ""))
    comment = Path(os.environ.get("COMMENT_FILE", "comment.md"))
    try:
        hide_event(os.environ.get("ISSUE_TITLE", ""), fields.get("what's wrong?", ""),
                   int(os.environ["ISSUE_NUMBER"]))
    except Rejected as exc:
        comment.write_text(f"**Can't do this yet.** {exc}")
        return 1
    comment.write_text("Thanks for the report. This event is now hidden from the site; "
                       "it disappears on the next update.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
