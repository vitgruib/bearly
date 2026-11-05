"""Big-venue concerts, against a trimmed copy of livenation.com's Wiltern page (2026-11-04)."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scraper.models import Event
from scraper.run import build
from scraper.sources import big_shows
from scraper.state import Context

FIX = Path(__file__).parent / "fixtures"
PT = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 4, 10, tzinfo=PT)
WILTERN = {"name": "The Wiltern", "city": "Los Angeles", "type": "livenation",
           "url": "https://www.livenation.com/venue/KovZpZAEAl6A/the-wiltern-events",
           "transit": "Wilshire/Western (Metro D Line), 1 min walk", "lat": 34.0617, "lng": -118.3089}


def test_livenation_reads_wall_clock_and_ticketmaster_classification():
    events = big_shows.parse_livenation((FIX / "big_shows_livenation.html").read_text())
    bonobo = events[0]

    # Four shows, the one the page lists twice kept once.
    assert [e.title[:14] for e in events] == ["KCRW Presents ", "Ólafur Arnalds", "John Mulaney: ",
                                             "NUTCRACKER! Ma"]
    assert bonobo.start == datetime(2026, 11, 11, 19, tzinfo=PT)
    assert bonobo.tags == ["Music", "Dance/Electronic"]
    assert bonobo.description == "With Sofia Kourtesis"
    assert bonobo.url.startswith("https://www.ticketmaster.com/")
    assert bonobo.image.endswith("_TABLET_LANDSCAPE_3_2.jpg")  # 1024 wide, not the 2048 one


def test_fetch_keeps_concerts_and_marks_them_with_the_way_there(monkeypatch):
    monkeypatch.setattr(big_shows, "get_text",
                        lambda url, **_: (FIX / "big_shows_livenation.html").read_text())

    events = big_shows.fetch({"venues": [WILTERN]}, Context({}, NOW))

    # Comedy and ballet are Ticketmaster "Arts & Theatre"; a classical concert is too, and stays.
    assert [e.title[:14] for e in events] == ["KCRW Presents ", "Ólafur Arnalds"]
    assert all(e.big_show and e.transit == WILTERN["transit"] for e in events)
    assert (events[0].venue, events[0].city, events[0].lat) == ("The Wiltern", "Los Angeles",
                                                                34.0617)


@pytest.mark.parametrize("title, tags, concert", [
    ("Teddy Swims: The UGLY Tour", ["Music", "Pop"], True),
    ("Golden State Warriors vs. Miami Heat", ["Sports"], False),
    ("Jo Koy", ["Comedy"], False),
    ("That's Not Me Comedy Tour with Concrete", ["Music"], False),
    ("Parking - John Mulaney - Not a Concert Ticket", ["Music"], False),
    ("Premium Club Seats - Dan + Shay: The Young Tour", ["Music"], False),
    ("Dark Star Orchestra 2 Day Pass", ["Music", "Rock"], False),
])
def test_only_concerts_count(title, tags, concert):
    e = Event(title=title, start=NOW, url="", source="big_shows", tags=tags)

    assert big_shows.is_concert(e) is concert


def _ev(title, **kw):
    return Event(title=title, start=datetime(2026, 11, 21, 19, tzinfo=PT),
                 url=kw.pop("url", f"https://x.test/{title}"), **kw)


def test_far_away_only_big_venue_concerts_are_listed():
    events = build([
        _ev("KATSEYE: THE WILDWORLD TOUR", source="big_shows", big_show=True,
            transit="Pico (Metro A/E Line), 3 min walk", venue="Crypto.com Arena",
            city="Los Angeles", lat=34.0430, lng=-118.2673),
        _ev("LA founders brunch", source="luma", city="Los Angeles", lat=34.0522, lng=-118.2437),
        # Sacramento is under 110 km from campus, so distance alone doesn't place it.
        _ev("Teddy Swims", source="big_shows", big_show=True, transit="7th & K, 2 min walk",
            venue="Golden 1 Center", city="Sacramento", lat=38.5802, lng=-121.4997),
    ], 30, NOW)

    assert sorted((e.title, e.region) for e in events) == [
        ("KATSEYE: THE WILDWORLD TOUR", "Los Angeles"), ("Teddy Swims", "Sacramento")]


def test_a_show_the_venues_source_also_lists_is_one_big_card():
    fox = {"venue": "Fox Theater", "city": "Oakland", "url": "https://thefoxoakland.com/events/x"}
    [show] = build([
        _ev("Jessie Reyez", source="venues", **fox),
        _ev("Jessie Reyez", source="big_shows", big_show=True, lat=37.8078, lng=-122.2702,
            transit="19th St Oakland BART, 2 min walk", **fox),
    ], 30, NOW)

    assert (show.big_show, show.transit, show.region) == (
        True, "19th St Oakland BART, 2 min walk", "East Bay")
