import json
from datetime import UTC, datetime, timedelta

import pytest

from scraper import contribute
from scraper.contribute import Rejected, hide_event, parse_issue
from scraper.models import Event
from scraper.run import build, hidden_ids

REPORT = """### What's wrong?

Spam or not a real event

### Anything else?

_No response_
"""


def test_issue_form_body_becomes_fields():
    assert parse_issue(REPORT) == {"what's wrong?": "Spam or not a real event", "anything else?": ""}


def test_an_approved_report_hides_the_event(tmp_path):
    hide_event("Report: Fake party (Oct 30) [0123456789ab]", "Spam", 14, tmp_path)
    assert hidden_ids(tmp_path) == {"0123456789ab"}


def test_a_report_without_an_event_id_is_refused(tmp_path):
    with pytest.raises(Rejected, match="event id"):
        hide_event("Report: that party last week", "Spam", 15, tmp_path)


def test_hidden_events_are_dropped_from_the_published_list():
    now = datetime(2026, 10, 27, 18, tzinfo=UTC)
    keep, spam = (Event(title=t, start=now + timedelta(days=1), url=f"https://x.test/{t}", source="feeds",
                        city="Berkeley") for t in ("Study night", "Crypto giveaway"))
    assert [e.title for e in build([keep, spam], 30, now, hidden={spam.id})] == ["Study night"]


SHEET = """Timestamp,What's this about?,Event link,No link? Where was it posted?,Club or calendar name,Calendar link,Where are the events?,Event,What's wrong?,Details,Your feedback
10/29/2026 9:00:00,Add a club's calendar,,,Cal Hiking Club,https://luma.com/calhiking,On or near campus,,,,
10/29/2026 9:05:00,Add an event,https://luma.com/abc123,,,,,,,,
10/29/2026 9:10:00,Report an event,,,,,,Fake party (Oct 30) [0123456789ab],Spam or not a real event,ping @maintainer,
10/29/2026 9:15:00,Send feedback,,,,,,,,,The map filter is great
10/29/2026 9:20:00,Send feedback,,,,,,,,,
"""


class FakeGitHub:
    def __init__(self, existing):
        self.existing, self.created = existing, []

    def __call__(self, *args):
        if args[:2] == ("issue", "list"):
            return json.dumps(self.existing)
        if args[:2] == ("issue", "create"):
            self.created.append(dict(zip(args[2::2], args[3::2], strict=False)))
        return ""


def test_reports_and_feedback_from_the_form_become_issues_once(monkeypatch):
    monkeypatch.setattr(contribute, "get_text", lambda url: SHEET)
    gh = FakeGitHub([])
    config = {"community": {"sheet_csv": "sheet.csv"}}

    contribute.from_forms(config, gh)

    assert [(c["--label"], c["--title"]) for c in gh.created] == [
        ("report", "Report: Fake party (Oct 30) [0123456789ab]"),
        ("feedback", "Feedback: The map filter is great"),
    ]  # requests to add an event or calendar, and empty rows, file nothing
    assert parse_issue(gh.created[0]["--body"])["what's wrong?"] == "Spam or not a real event"
    assert "@maintainer" not in gh.created[0]["--body"]  # form text can't notify anyone

    gh.existing = [{"title": c["--title"], "body": c["--body"]} for c in gh.created]
    gh.created.clear()
    contribute.from_forms(config, gh)
    assert gh.created == []
