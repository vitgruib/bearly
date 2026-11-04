from datetime import UTC, datetime, timedelta

from icalendar import Calendar

from scraper.ics import write_feeds
from scraper.models import Event

NOW = datetime(2026, 11, 3, 18, tzinfo=UTC)


def ev(title, tags, **kw):
    kw.setdefault("start", NOW + timedelta(days=1))
    return Event(title=title, url=f"https://x.test/{len(title)}", source="luma", tags=tags, **kw)


def test_topic_feed_holds_only_that_topic_and_parses_as_a_calendar(tmp_path):
    pizza = ev("Pizza GBM; bring friends, all welcome", ["Free food"], access=["RSVP on Luma"],
               description="Long description " * 20)
    talk = ev("Rust talk", ["Talks"])

    write_feeds([pizza, talk], ["Free food", "Talks"], tmp_path, NOW)

    food = Calendar.from_ical((tmp_path / "free-food.ics").read_bytes())
    [vevent] = food.walk("VEVENT")
    assert str(vevent["SUMMARY"]) == "Pizza GBM; bring friends, all welcome"
    assert "Getting in: RSVP on Luma" in str(vevent["DESCRIPTION"])
    assert vevent.decoded("DTSTART") == NOW + timedelta(days=1)
    everything = Calendar.from_ical((tmp_path / "all.ics").read_bytes())
    assert len(everything.walk("VEVENT")) == 2


def test_all_day_event_is_a_date_not_midnight(tmp_path):
    fair = ev("Career fair", [], all_day=True, start=datetime(2026, 11, 5, 8, tzinfo=UTC))

    write_feeds([fair], [], tmp_path, NOW)

    [vevent] = Calendar.from_ical((tmp_path / "all.ics").read_bytes()).walk("VEVENT")
    assert str(vevent.decoded("DTSTART")) == "2026-11-05"
    assert str(vevent.decoded("DTEND")) == "2026-11-06"


def test_no_line_is_longer_than_75_octets(tmp_path):
    write_feeds([ev("Ünïcödé " * 30, [], description="é" * 400)], [], tmp_path, NOW)

    lines = (tmp_path / "all.ics").read_bytes().split(b"\r\n")
    assert max(len(x) for x in lines) <= 75
