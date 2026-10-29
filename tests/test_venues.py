"""Venue feeds, against trimmed copies of real responses captured 2026-10-28."""

import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from scraper.models import Event
from scraper.sources import venues
from scraper.state import Context

FIX = Path(__file__).parent / "fixtures"
PT = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 28, 10, tzinfo=PT)
HORIZON = datetime(2026, 11, 27, 10, tzinfo=PT)


def _json(name):
    return json.loads((FIX / name).read_text())


def test_dothebay_takes_listed_date_and_wall_clock_and_skips_weekly_series():
    events = venues.parse_dothebay(_json("venues_dothebay.json"))
    braun = [e for e in events if e.title == "Rick Braun"]

    # begin_time says -05:00, but 7:00 PM Pacific is when Yoshi's opens doors for the show.
    assert [e.start for e in braun] == [datetime(2026, 10, 30, 19, tzinfo=PT),
                                        datetime(2026, 10, 30, 21, 15, tzinfo=PT)]
    assert braun[0].url == "https://dothebay.com/events/2026/10/30/rick-braun-tickets"
    assert (braun[0].venue, braun[0].city, braun[0].free) == ("Yoshi's Oakland", "Oakland", False)
    assert braun[0].description.startswith("Doors 7:00 PM")
    assert "North Berkeley Food Tour" not in [e.title for e in events]


def test_resident_advisor_lists_multi_night_event_once_with_city_from_address():
    events = venues.parse_resident_advisor(_json("venues_ra.json"))
    by_title = {e.title[:10]: e for e in events}

    assert len(events) == 4
    hugel = by_title["Hugel"]
    assert hugel.start == datetime(2026, 11, 7, 18, tzinfo=PT)
    assert (hugel.city, hugel.url) == ("Berkeley", "https://ra.co/events/2557363")
    assert by_title["Factory 93"].city == "Alameda"


def test_venuepilot_reads_venue_wall_clock_and_drops_private_parties():
    events = venues.parse_venuepilot(_json("venues_venuepilot.json"), "https://www.ivyroom.com/")
    plunder, taste = events

    assert len(events) == 2
    assert plunder.start == datetime(2026, 10, 30, 20, 30, tzinfo=PT)
    assert (plunder.city, plunder.free) == ("Albany", False)
    assert plunder.url.startswith("https://tickets.venuepilot.com/e/plunder-cielo")
    assert (taste.free, taste.url) == (True, "https://www.ivyroom.com/")


def test_another_planet_reads_listing_blocks_not_the_featured_slider():
    events = venues.parse_anotherplanet((FIX / "venues_fox.html").read_text(), "Fox Theater",
                                        "Oakland")

    assert [(e.title, e.start) for e in events] == [
        ("Shpongle", datetime(2026, 10, 30, 20, tzinfo=PT)),
        ("Shpongle", datetime(2026, 10, 31, 20, tzinfo=PT)),
        ("Jessie Reyez", datetime(2026, 11, 6, 20, tzinfo=PT)),
    ]
    assert events[0].url == "https://thefoxoakland.com/events/shpongle-261030"


def test_uc_theatre_show_time_is_utc_not_new_york():
    show = venues.parse_uctheatre_show((FIX / "venues_uctheatre_show.html").read_text())
    urls = venues.parse_uctheatre_listing((FIX / "venues_uctheatre_events.html").read_text())

    # The listing says "Show: 7:45 pm" on Thu Nov 19.
    assert show.start == datetime(2026, 11, 19, 19, 45, tzinfo=PT)
    assert (show.venue, show.city, show.free) == ("The UC Theatre", "Berkeley", False)
    assert urls == ["https://www.theuctheatre.org/shows/mumiy-troll-28-oct",
                    "https://www.theuctheatre.org/shows/bridge-city-sinners-29-oct",
                    "https://www.theuctheatre.org/shows/rocky-horror-picture-show-31-oct-cc0d6"]


def test_keep_drops_past_shows_and_shows_past_the_horizon():
    dtb = {e.title: e for e in venues.parse_dothebay(_json("venues_dothebay.json"))}
    greek = {e.title: e for e in venues.parse_anotherplanet(
        (FIX / "venues_greek.html").read_text(), "Greek Theatre", "Berkeley")}

    assert not venues.keep(dtb["Direct From Sweden: The Music Of Abba"], NOW, HORIZON)
    assert not venues.keep(greek["The Red Clay Strays"], NOW, HORIZON)
    assert venues.keep(greek["HUGEL"], NOW, HORIZON)


def test_keep_drops_shows_outside_the_east_bay():
    ra = {e.title[:20]: e for e in venues.parse_resident_advisor(_json("venues_ra.json"))}

    assert not venues.keep(ra["Strut SF and F8 pres"], NOW, HORIZON)  # San Francisco
    assert not venues.keep(ra["BlackandWhitesound p"], NOW, HORIZON)  # venue TBA
    assert venues.keep(ra["Factory 93: Hallowee"], NOW, HORIZON)  # Alameda


@pytest.mark.parametrize("title", [
    "Bridge City Sinners ** MOVED TO CRYBABY OAKLAND**",
    "Daley   Preshow Vip Experience",
    "PRIVATE PARTY",
    "Box Office Hours",
])
def test_keep_drops_listings_that_are_not_a_show_at_that_venue(title):
    e = Event(title=title, start=datetime(2026, 10, 29, 19, tzinfo=PT), url="", source="venues",
              city="Berkeley")

    assert not venues.keep(e, NOW, HORIZON)


def _offline(monkeypatch, fail_venuepilot=False):
    def get_text(url, **_):
        return (FIX / "venues_greek.html").read_text()

    def request(method, url, **_):
        if "venuepilot" in url and fail_venuepilot:
            raise httpx.ConnectError("unreachable")
        body = _json("venues_ra.json" if "ra.co" in url else "venues_venuepilot.json")
        return httpx.Response(200, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr(venues, "get_text", get_text)
    monkeypatch.setattr(venues, "request", request)


def test_fetch_keeps_the_venues_own_listing_of_a_show_an_aggregator_repeats(monkeypatch):
    _offline(monkeypatch)
    cfg = {"list": [{"type": "resident_advisor", "name": "RA"},
                    {"type": "anotherplanet", "name": "Greek", "venue": "Greek Theatre",
                     "city": "Berkeley", "url": "https://thegreekberkeley.com/event-listing/"}]}

    events = venues.fetch(cfg, Context({}, NOW))
    hugel = [e for e in events if e.title.lower() == "hugel"]

    assert len(hugel) == 1
    assert hugel[0].url == "https://thegreekberkeley.com/events/hugel-261107"
    assert hugel[0].also_on == []
    assert hugel[0].listings[-1] == {"source": "venues", "url": "https://ra.co/events/2557363",
                                     "name": "ra.co"}
    assert all(e.start.tzinfo is not None and e.city for e in events)


def test_fetch_warns_about_a_failing_feed_and_keeps_the_rest(monkeypatch):
    _offline(monkeypatch, fail_venuepilot=True)
    cfg = {"list": [{"type": "venuepilot", "name": "Ivy Room", "account": 992,
                     "url": "https://www.ivyroom.com/"},
                    {"type": "resident_advisor", "name": "RA"}]}
    ctx = Context({}, NOW.astimezone(UTC))

    events = venues.fetch(cfg, ctx)

    assert [e.city for e in events] == ["Alameda", "Berkeley"]
    assert len(ctx.warnings) == 1 and ctx.warnings[0].startswith("Ivy Room: ConnectError")
