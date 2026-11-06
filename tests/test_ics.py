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


def test_filter_feed_holds_only_events_matching_every_filter(tmp_path):
    match = ev("Free pizza talk on campus", ["Talks", "Free food"], region="Campus", free=True)
    not_free = ev("Paid talk on campus with pizza", ["Talks", "Free food"], region="Campus", free=False)
    elsewhere = ev("Free pizza talk in SF", ["Talks", "Free food"], region="San Francisco", free=True)
    no_food = ev("Free talk on campus", ["Talks"], region="Campus", free=True)

    write_feeds([match, not_free, elsewhere, no_food], ["Talks", "Free food"], tmp_path, NOW,
                regions=["Campus", "San Francisco"])

    def titles(name):
        cal = Calendar.from_ical((tmp_path / "f" / name).read_bytes())
        return sorted(str(v["SUMMARY"]) for v in cal.walk("VEVENT"))

    assert titles("talks.campus.free-food.ics") == ["Free pizza talk on campus"]
    assert titles("talks.campus.food.ics") == ["Free pizza talk on campus", "Paid talk on campus with pizza"]
    assert titles("all.all.free.ics") == ["Free pizza talk in SF", "Free pizza talk on campus", "Free talk on campus"]
    assert len(titles("all.all.any.ics")) == 4
    # Free food is a cost filter, not an event type, so it gets no type of its own.
    assert not list((tmp_path / "f").glob("free-food.*"))
