"""Parsers against trimmed copies of real responses captured 2026-10-27."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scraper.schema_org import events_from_html
from scraper.sources import berkeley_calendar, eventbrite, feeds, luma, partiful

FIX = Path(__file__).parent / "fixtures"
PT = ZoneInfo("America/Los_Angeles")


def test_luma_entry_keeps_location_price_and_link():
    entries = json.loads((FIX / "luma_discover.json").read_text())["entries"]
    fung, unprompted = (luma.parse_entry(e) for e in entries)

    assert fung.title.startswith("Fung Fellowship x Berkeley Career Engagement Center")
    assert fung.start == datetime(2026, 10, 28, 17, tzinfo=UTC)
    assert fung.city == "Berkeley"
    assert fung.free is True
    assert unprompted.url == "https://luma.com/pywdcwal"
    assert unprompted.free is False
    assert unprompted.lat is not None and unprompted.lng is not None


def test_eventbrite_reads_embedded_results_in_local_time():
    events = eventbrite.parse_page((FIX / "eventbrite.html").read_text())

    assert [e.title for e in events][:2] == [
        "San Francisco Halloween Pub Crawl: Crawloween",
        "Downtown First Thursdays with Big Freedia | Nov. 5, 2026",
    ]
    assert events[0].start == datetime(2026, 10, 31, 14, tzinfo=PT)
    assert events[0].city == "San Francisco"


def test_cerebral_valley_json_ld_marks_online_and_free():
    events = events_from_html((FIX / "cerebral_valley.html").read_text(), "cerebral_valley")
    by_title = {e.title: e for e in events}

    assert by_title["Meta Global AI Developer Hackathon"].online is True
    aie = by_title["AIE Code Summit 2026 Hackathon"]
    assert (aie.city, aie.free, aie.online) == ("San Francisco", True, False)
    assert by_title["Agents in Context Toronto: a MongoDB Hackathon"].city == "Toronto"


def test_partiful_explore_takes_only_bay_area_section():
    events = partiful.parse_explore((FIX / "partiful_explore.html").read_text())

    assert [e.title for e in events] == ["Madrone Trivia Night", "NO BASIC"]
    assert events[0].city == "San Francisco"
    assert events[0].url.startswith("https://partiful.com/e/")


def _livewhale(**over):
    item = {"title": "Berkeley Book Chat", "url": "https://events.berkeley.edu/x/1",
            "date_iso": "2026-10-28T12:00:00-07:00", "date2_iso": "2026-10-28T13:00:00-07:00",
            "group_title": "Townsend Center for the Humanities", "location_title": "Geballe Room",
            "location_latitude": 37.8722, "location_longitude": -122.2595, "cost": "Free",
            "event_types": ["Lecture"], "thumbnail": None, "summary": "<p>A talk &amp; Q&A</p>"}
    return {**item, **over}


def test_campus_calendar_item_becomes_free_campus_event():
    e = berkeley_calendar.parse_item(_livewhale())

    assert e.start == datetime(2026, 10, 28, 12, tzinfo=PT)
    assert (e.free, e.venue, e.description) == (True, "Geballe Room", "A talk & Q&A")


def test_campus_calendar_drops_gym_hours_and_daily_exhibits():
    gym = _livewhale(title="Building Hours - RSF", group_title="Recreational Sports")
    exhibit = _livewhale(is_all_day=1, event_types=["Exhibits"])
    tournament = _livewhale(title="Pickleball Tournament", group_title="Recreational Sports")

    assert berkeley_calendar.parse_item(gym) is None
    assert berkeley_calendar.parse_item(exhibit) is None
    assert berkeley_calendar.parse_item(tournament) is not None


def test_campus_calendar_drops_away_games_but_keeps_home_games():
    sports = "Cal Bears Intercollegiate Sports"
    away = _livewhale(title="California Men’s Tennis vs Jack Kramer Invitational",
                      group_title=sports, location_title="Palos Verdes, Calif.")
    home = _livewhale(title="California Men's Basketball vs Adams State",
                      group_title=sports, location_title="Haas Pavilion")

    assert berkeley_calendar.parse_item(away) is None
    assert berkeley_calendar.parse_item(home) is not None


def test_ics_feed_expands_weekly_club_meeting():
    feed = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1
DTSTART;TZID=America/Los_Angeles:20261027T190000
DTEND;TZID=America/Los_Angeles:20261027T200000
RRULE:FREQ=WEEKLY;COUNT=10
SUMMARY:General Meeting
LOCATION:Soda 306
END:VEVENT
END:VCALENDAR
"""
    now = datetime(2026, 10, 27, 12, tzinfo=PT)

    events = feeds.parse_ics(feed, "Cal Hiking", days_ahead=15, now=now)

    assert [e.start.day for e in events] == [27, 3, 10]
    assert events[0].venue == "Soda 306" and events[0].host == "Cal Hiking"


def test_fullcalendar_reads_utc_start_and_naive_pacific_end():
    # Simons sends start in UTC but end as naive local time.
    [e] = feeds.parse_fullcalendar([{"start": "2026-10-29T20:30:00Z", "end": "2026-10-29T15:30:00",
                                     "title": " Depth-Optimal Quantum Compilation",
                                     "url": "/events/depth", "location": "Calvin Lab 116\n"}],
                                   "https://simons.berkeley.edu/api/events", "Simons Institute")
    assert e.title == "Depth-Optimal Quantum Compilation"
    assert e.end - e.start == timedelta(hours=2)
    assert e.url == "https://simons.berkeley.edu/events/depth"
