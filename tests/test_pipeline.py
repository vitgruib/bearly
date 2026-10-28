from datetime import UTC, datetime, timedelta

from scraper.links import event_urls
from scraper.models import Event
from scraper.run import build

NOW = datetime(2026, 10, 27, 18, tzinfo=UTC)


def ev(title="Intro to Rust", start=NOW + timedelta(days=1), **kw):
    kw.setdefault("city", "Berkeley")
    return Event(title=title, start=start, url=kw.pop("url", f"https://x.test/{title}"),
                 source=kw.pop("source", "luma"), **kw)


def test_regions_follow_distance_from_campus():
    events = build([
        ev("Soda Hall talk", lat=37.8756, lng=-122.2588),
        ev("Downtown Berkeley mixer", lat=37.8700, lng=-122.2970, city="Berkeley"),
        ev("SF demo night", lat=37.7813, lng=-122.4124, city="San Francisco"),
        ev("Palo Alto dinner", city="Palo Alto"),
        ev("Global hackathon", online=True),
    ], 30, NOW)

    assert {e.title: e.region for e in events} == {
        "Soda Hall talk": "Campus", "Downtown Berkeley mixer": "Berkeley",
        "SF demo night": "San Francisco", "Palo Alto dinner": "Peninsula & South Bay",
        "Global hackathon": "Online"}


def test_listings_far_away_or_unplaceable_are_dropped():
    events = build([
        ev("Toronto hackathon", city="Toronto", source="cerebral_valley"),
        ev("NYC party", lat=40.75, lng=-73.99),
        ev("Club meeting", source="ics", city=None),  # club feeds without a city are local
    ], 30, NOW)

    assert [e.title for e in events] == ["Club meeting"]


def test_past_far_future_and_month_long_events_are_dropped():
    events = build([
        ev("Yesterday", start=NOW - timedelta(days=1)),
        ev("Next spring", start=NOW + timedelta(days=120)),
        ev("Semester program", end=NOW + timedelta(days=60)),
        ev("Happening now", start=NOW - timedelta(hours=1), end=NOW + timedelta(hours=1)),
    ], 30, NOW)

    assert [e.title for e in events] == ["Happening now"]


def test_same_event_from_listserv_merges_into_platform_record():
    luma = ev("AI Safety Reading Group", url="https://luma.com/abc", image="img.png",
              lat=37.8756, lng=-122.2588)
    email = ev("AI Safety Reading Group!", url="", source="email",
               description="Pizza will be provided.")

    [merged] = build([email, luma], 30, NOW)

    assert merged.source == "luma"
    assert merged.also_on == ["email"]
    assert merged.image == "img.png"
    assert merged.description == "Pizza will be provided."
    assert "Free food" in merged.tags and "AI & Tech" in merged.tags


def test_event_links_are_pulled_out_of_messages():
    text = ("RSVP here: https://lu.ma/abc123. Also <https://partiful.com/e/XyZ|our party> and "
            "the form https://forms.gle/zzz and https://www.eventbrite.com/e/foo-123?aff=x")

    assert event_urls(text) == ["https://lu.ma/abc123", "https://partiful.com/e/XyZ",
                                "https://www.eventbrite.com/e/foo-123"]
