from datetime import UTC, datetime, timedelta

import pytest

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
    hide_event("0123456789ab", "Fake party", "Spam", 14, tmp_path)

    config = load_config(tmp_path)

    assert [f["name"] for f in config["feeds"]["list"]] == ["Haas", 'The "Quote" Club']
    assert config["feeds"]["list"][1]["campus"] is True
    assert config["luma"]["calendars"] == ["a", "calmsa"]
    assert config["contributed"] == [{"name": "Calmsa", "by": "other"},
                                     {"name": 'The "Quote" Club', "by": "someone"}]
    assert hidden_ids(tmp_path) == {"0123456789ab"}


def test_a_source_already_listed_is_not_saved_twice(tmp_path):
    (tmp_path / "sources.toml").write_text('[[feeds.list]]\nname = "X"\nurl = "https://q.test/c.ics"\n')
    with pytest.raises(Rejected, match="already"):
        save_source({"name": "X again", "type": "ics", "url": "https://q.test/c.ics"}, "a", 1, tmp_path)


def test_hidden_events_are_dropped_from_the_published_list():
    now = datetime(2026, 10, 27, 18, tzinfo=UTC)
    keep, spam = (Event(title=t, start=now + timedelta(days=1), url=f"https://x.test/{t}", source="feeds",
                        city="Berkeley") for t in ("Study night", "Crypto giveaway"))
    assert [e.title for e in build([keep, spam], 30, now, hidden={spam.id})] == ["Study night"]
