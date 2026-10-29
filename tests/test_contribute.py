import json
from datetime import UTC, datetime, timedelta

import pytest

from scraper import contribute
from scraper.contribute import Rejected, hide_event, normalize, parse_issue, save_source
from scraper.models import Event
from scraper.run import build, hidden_ids, load_config

FORM = """### Club or calendar name

Cal Hiking Club

### Calendar link

https://calendar.google.com/calendar/embed?src=calhiking%40gmail.com&ctz=America%2FLos_Angeles

### Where are the events?

On or near campus

### Anything else?

_No response_
"""


def test_issue_form_body_becomes_fields():
    assert parse_issue(FORM) == {
        "club or calendar name": "Cal Hiking Club",
        "calendar link": "https://calendar.google.com/calendar/embed?src=calhiking%40gmail.com"
                         "&ctz=America%2FLos_Angeles",
        "where are the events?": "On or near campus",
        "anything else?": "",
    }


@pytest.mark.parametrize(("link", "kind", "url"), [
    ("https://calendar.google.com/calendar/embed?src=calhiking%40gmail.com&ctz=America%2FLA",
     "ics", "https://calendar.google.com/calendar/ical/calhiking%40gmail.com/public/basic.ics"),
    # "Share" links carry the calendar id base64-encoded: Y2FsaGlraW5nQGdtYWlsLmNvbQ = calhiking@gmail.com
    ("https://calendar.google.com/calendar/u/0?cid=Y2FsaGlraW5nQGdtYWlsLmNvbQ",
     "ics", "https://calendar.google.com/calendar/ical/calhiking%40gmail.com/public/basic.ics"),
    ("webcal://example.org/club.ics", "ics", "https://example.org/club.ics"),
    ("https://luma.com/calmsa", "luma", "calmsa"),
    ("https://lu.ma/calmsa?period=past", "luma", "calmsa"),
])
def test_known_calendar_links_are_recognized_without_fetching(link, kind, url):
    assert normalize(link) == (kind, url)


def test_unknown_links_are_left_for_probing():
    assert normalize("https://someclub.berkeley.edu/events") == (None, "https://someclub.berkeley.edu/events")


@pytest.mark.parametrize("link", ["ftp://example.org/x.ics", "not a link", "http://localhost/x.ics",
                                  "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/cal"])
def test_links_that_are_not_public_web_pages_are_rejected(link):
    with pytest.raises(Rejected):
        normalize(link)


def test_saved_sources_and_hidden_events_reach_the_scraper(tmp_path):
    (tmp_path / "sources.toml").write_text('[feeds]\n[[feeds.list]]\nname = "Haas"\ntype = "tribe"\n'
                                           'url = "https://haas.test/x"\n\n[luma]\ncalendars = ["a"]\n')
    save_source({"name": 'The "Quote" Club', "type": "ics", "url": "https://q.test/c.ics", "campus": True},
                "someone", 12, tmp_path)
    save_source({"name": "Calmsa", "type": "luma", "url": "calmsa"}, "other", 13, tmp_path)
    hide_event("Report: Fake party (Oct 30) [0123456789ab]", "Spam", 14, tmp_path)

    config = load_config(tmp_path)

    assert [f["name"] for f in config["feeds"]["list"]] == ["Haas", 'The "Quote" Club']
    assert config["feeds"]["list"][1]["campus"] is True
    assert config["luma"]["calendars"] == ["a", "calmsa"]
    assert config["contributed"] == [{"name": "Calmsa", "by": "other"},
                                     {"name": 'The "Quote" Club', "by": "someone"}]
    assert hidden_ids(tmp_path) == {"0123456789ab"}


def test_a_report_without_an_event_id_is_refused(tmp_path):
    with pytest.raises(Rejected, match="event id"):
        hide_event("Report: that party last week", "Spam", 15, tmp_path)


def test_a_source_already_listed_is_not_saved_twice(tmp_path):
    (tmp_path / "sources.toml").write_text('[[feeds.list]]\nname = "X"\nurl = "https://q.test/c.ics"\n')
    with pytest.raises(Rejected, match="already"):
        save_source({"name": "X again", "type": "ics", "url": "https://q.test/c.ics"}, "a", 1, tmp_path)


def test_hidden_events_are_dropped_from_the_published_list():
    now = datetime(2026, 10, 27, 18, tzinfo=UTC)
    keep, spam = (Event(title=t, start=now + timedelta(days=1), url=f"https://x.test/{t}", source="feeds",
                        city="Berkeley") for t in ("Study night", "Crypto giveaway"))
    assert [e.title for e in build([keep, spam], 30, now, hidden={spam.id})] == ["Study night"]


SOURCE_SHEET = """Timestamp,Club or calendar name,Calendar link,Where are the events?,Anything else?
10/29/2026 9:00:00,Cal Hiking Club,https://luma.com/calhiking,On or near campus,
10/29/2026 9:05:00,Already filed,https://luma.com/filed,On or near campus,
10/29/2026 9:10:00,@everyone spam,https://spam.test/cal.ics,Mostly online,ping @maintainer
"""
REPORT_SHEET = """Timestamp,Event,What's wrong?,Anything else?
10/29/2026 9:20:00,Fake party (Oct 30) [0123456789ab],Spam or not a real event,
"""


class FakeGitHub:
    def __init__(self, existing):
        self.existing, self.created, self.comments = existing, [], []

    def __call__(self, *args):
        if args[:2] == ("issue", "list"):
            return json.dumps(self.existing)
        if args[:2] == ("issue", "create"):
            opts = dict(zip(args[2::2], args[3::2], strict=False))
            self.created.append(opts)
            return f"https://github.com/o/r/issues/{len(self.created) + 40}\n"
        self.comments.append(args)
        return ""


def test_form_responses_become_issues_once(monkeypatch):
    sheets = {"src.csv": SOURCE_SHEET, "rep.csv": REPORT_SHEET}
    monkeypatch.setattr(contribute, "get_text", lambda url: sheets[url])
    monkeypatch.setattr(contribute, "check", lambda fields, config: (None, "bot says hi"))
    gh = FakeGitHub([{"title": "Add source: x", "body": "https://luma.com/filed"}])
    config = {"community": {"source_sheet_csv": "src.csv", "report_sheet_csv": "rep.csv"}}

    contribute.from_forms(config, gh)

    titles = [c["--title"] for c in gh.created]
    assert titles == ["Add source: Cal Hiking Club", "Add source: @\u200beveryone spam",
                      "Report: Fake party (Oct 30) [0123456789ab]"]
    first = parse_issue(gh.created[0]["--body"])
    assert first["calendar link"] == "https://luma.com/calhiking"
    assert "@maintainer" not in gh.created[1]["--body"]  # form text can't notify anyone
    assert [c["--label"] for c in gh.created] == ["new-source", "new-source", "report"]
    assert ("issue", "comment", "41", "--body", "bot says hi") in gh.comments

    gh.existing += [{"title": c["--title"], "body": c["--body"]} for c in gh.created]
    gh.created.clear()
    contribute.from_forms(config, gh)
    assert gh.created == []  # a row already turned into an issue is skipped next run
