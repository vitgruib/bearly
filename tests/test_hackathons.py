"""Hackathon feeds against trimmed copies of real responses captured 2026-10-28."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from scraper.sources import hackathons
from scraper.state import Context

FIX = Path(__file__).parent / "fixtures"
PT = ZoneInfo("America/Los_Angeles")


def _text(name: str) -> str:
    return (FIX / f"hackathons_{name}").read_text()


def _mlh_page(*events: dict) -> str:
    return ('<script data-page="app" type="application/json">'
            + json.dumps({"props": {"upcomingEvents": list(events)}}) + "</script>")


def _sf_hacks(**over) -> dict:
    page = _text("mlh.html")
    item = next(e for e in json.loads(page[page.index("{"):page.rindex("}") + 1])["props"]
                ["upcomingEvents"] if e["name"].strip() == "SF Hacks")
    return {**item, **over}


def test_devpost_page_reads_bay_area_event_from_json_ld():
    [e] = hackathons.parse_devpost_page(_text("devpost_searchhack.html"))

    assert e.title == "SearchHack: Build the next layer of AI search"
    assert e.start == datetime(2026, 11, 14, 10, tzinfo=PT)
    assert e.end == datetime(2026, 11, 14, 17, tzinfo=PT)
    assert (e.city, e.host, e.url) == ("Sunnyvale", "Telem AI", "https://searchhack.devpost.com/")
    assert e.tags == ["Hackathon"]


def test_devpost_drops_multi_week_submission_window():
    assert hackathons.parse_devpost_page(_text("devpost_developerweek.html")) == []


def test_devpost_drops_same_named_city_outside_california():
    assert hackathons.parse_devpost_page(_text("devpost_richmond.html")) == []


def test_devpost_list_opens_only_short_upcoming_hackathons():
    data = json.loads(_text("devpost_list.json"))

    urls = hackathons.devpost_candidates(data, date(2026, 10, 28), days_ahead=45)

    # Not DeveloperWeek or Tech to Treasure (weeks-long windows), not BISV Hacks (March).
    assert urls == ["https://searchhack.devpost.com/", "https://ship-it-hackathon.devpost.com/",
                    "https://haven-richmond.devpost.com/",
                    "https://solix-ai-hackathon-2026.devpost.com/"]


def test_yc_keeps_bay_area_events_and_tags_only_hackathons():
    haunted, paper_club = hackathons.parse_yc(_text("yc.html"))  # Taipei dropped

    assert haunted.start == datetime(2026, 10, 31, 10, tzinfo=PT)
    assert haunted.url == "https://events.ycombinator.com/haunted-hacks-2026"
    assert haunted.tags == ["Hackathon"]
    assert paper_club.start == datetime(2026, 11, 4, 17, tzinfo=PT)
    assert (paper_club.city, paper_club.tags) == ("Mountain View", [])


def test_mlh_reads_eastern_labelled_times_as_venue_wall_clock():
    [e] = hackathons.parse_mlh(_text("mlh.html"))  # La Jolla, Texas and Toronto dropped

    assert e.title == "SF Hacks"
    assert e.start == datetime(2027, 2, 19, 12, tzinfo=PT)
    assert e.end == datetime(2027, 2, 21, 16, tzinfo=PT)
    assert (e.city, e.url, e.all_day) == ("San Francisco", "https://sfhacks.io", False)


def test_mlh_placeholder_times_mean_whole_days():
    sf = _sf_hacks(startsAt="2027-02-19T01:11:11Z", endsAt="2027-02-21T23:59:59Z")

    [e] = hackathons.parse_mlh(_mlh_page(sf))

    assert e.all_day is True
    assert e.start == datetime(2027, 2, 19, 0, tzinfo=PT)
    assert e.end == datetime(2027, 2, 21, 23, 59, tzinfo=PT)


def test_agi_house_skips_other_states_and_finished_listings():
    events = hackathons.parse_agi(json.loads(_text("agi.json")))

    # Not the Cambridge, MA build day, nor the "completed" Gemini Build Day.
    assert [e.title for e in events] == [
        "Personal Agent to Real-World Deployment Build Day", "The Google Gemma Hardware Hackathon",
        "AGI Game Night: SCB 10X", "Real-Time Agents Build Evening"]
    build_day, _, game_night, _ = events
    assert build_day.start == datetime(2026, 11, 8, 10, tzinfo=PT)
    assert build_day.url == "https://agihouse.org/events/lenovo-x-agi-house-build-day"
    assert (build_day.city, build_day.lat is not None) == ("Hillsborough", True)
    assert (build_day.tags, game_night.tags) == (["Hackathon"], [])


def _offline(monkeypatch, mlh: str | None = None) -> None:
    pages = {
        hackathons.YC_URL: _text("yc.html"),
        hackathons.MLH_URL.format(season=2027): mlh or _text("mlh.html"),
        "https://searchhack.devpost.com/": _text("devpost_searchhack.html"),
        "https://ship-it-hackathon.devpost.com/": _text("devpost_shipit.html"),
        "https://haven-richmond.devpost.com/": _text("devpost_richmond.html"),
    }
    apis = {hackathons.AGI_API: json.loads(_text("agi.json")),
            hackathons.DEVPOST_API: json.loads(_text("devpost_list.json"))}

    def get_text(url, **_):
        if url not in pages:
            raise httpx.ConnectError(f"offline: {url}")
        return pages[url]

    monkeypatch.setattr(hackathons, "get_text", get_text)
    monkeypatch.setattr(hackathons, "get_json", lambda url, **_: apis[url])


def test_fetch_merges_feeds_drops_past_and_warns_on_failed_page(monkeypatch):
    _offline(monkeypatch)
    ctx = Context({}, datetime(2026, 10, 28, 15, tzinfo=UTC))

    events = hackathons.fetch({}, ctx)

    assert [e.title for e in events] == [
        "Haunted Hacks: Real-Time AI Edition", "YC Paper Club - AI for Biology",
        "Personal Agent to Real-World Deployment Build Day", "SF Hacks",
        "SearchHack: Build the next layer of AI search", "Ship It: The Product Builders' Hackathon"]
    assert {e.source for e in events} == {"hackathons"}
    assert len(ctx.warnings) == 1 and "solix-ai-hackathon-2026" in ctx.warnings[0]


def test_fetch_lists_a_hackathon_on_two_feeds_once(monkeypatch):
    on_mlh_too = _sf_hacks(name="SearchHack: Build the next layer of AI search",
                           startsAt="2026-11-14T15:00:00Z", endsAt="2026-11-14T22:00:00Z",
                           venueAddress={"city": "Sunnyvale", "state": "CA", "country": "US"})
    _offline(monkeypatch, mlh=_mlh_page(on_mlh_too))

    events = hackathons.fetch({}, Context({}, datetime(2026, 10, 28, 15, tzinfo=UTC)))

    assert [e.title for e in events].count("SearchHack: Build the next layer of AI search") == 1
