from datetime import UTC, datetime, timedelta

import pytest

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
        ev("Club meeting", source="feeds", city=None),  # club feeds without a city are local
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


def test_merged_event_keeps_a_link_to_every_listing():
    luma = ev("Hike to the Big C", url="https://luma.com/bigc", image="img.png")
    club = ev("Hike to the Big C", url="https://calhiking.test/bigc", source="feeds",
              host="Cal Hiking Club")
    email = ev("Hike to the Big C!", url="", source="email")

    [merged] = build([email, club, luma], 30, NOW)

    assert merged.listings == [
        {"source": "luma", "url": "https://luma.com/bigc"},
        {"source": "feeds", "url": "https://calhiking.test/bigc", "name": "Cal Hiking Club"},
    ]
    assert merged.also_on == ["feeds", "email"]


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


SIX_PM = NOW + timedelta(days=1)


@pytest.mark.parametrize("a, b", [
    ("Matrix on Point: The State of U.S. Immigration Enforcement",
     "The State of U.S. Immigration Enforcement"),
    ("Film Screening: The Human Condition I: No Greater Love", "The Human Condition I: No Greater Love"),
    ("[SF] AI Dev Night with Microsoft and Elastic", "AI Dev Night with Microsoft and Elastic"),
    ("Neuro Night", "NeuroNight SF"),
    ("Defending Our Rights, Fighting For Our Future",
     "Defending Our Rights, Fighting For Our Future: The ACLU’s Cecillia Wang"),
    ("California Men’s Basketball vs Adams State - HOME OPENER",
     "California Men's Basketball vs Adams State - HOME OPENER"),
    ("Haas Tech & AI Summit 2026 · Where Intelligence Goes Next",
     "Tech and AI Summit 2026 - Where Intelligence Goes Next"),
    ("Own Your AI: Build an Agentic AI Model Factory - Hack Night",
     "Own Your AI: Build an Agentic AI Model Factory - in person"),
    ("Change Not Charity: The Americans with Disabilities Act at 36",
     "‘Change Not Charity: Americans With Disabilities Act at 36’"),
])
def test_same_event_listed_under_two_titles_is_merged(a, b):
    events = build([ev(a, SIX_PM, source="berkeley_calendar"), ev(b, SIX_PM, source="feeds")],
                   30, NOW)

    assert len(events) == 1 and events[0].also_on == ["feeds"]


def test_one_source_listing_an_event_from_two_platforms_is_merged():
    luma = ev("AWS Agentic Partner Showcase Extended - Temporal, Arize, Databricks", SIX_PM,
              source="cerebral_valley", url="https://luma.com/1xkwh68x")
    meetup = ev("AWS Partner Showcase - Temporal, Arize, Databricks", SIX_PM,
                source="cerebral_valley", url="https://www.meetup.com/svsiaa/events/316967081")

    assert len(build([luma, meetup], 30, NOW)) == 1


@pytest.mark.parametrize("a, b", [
    ("California Men’s Swimming & Diving vs CSL Wild Card",
     "California Women’s Swimming & Diving vs CSL Wild Card"),
    ("PG&E Monitoring Center Tour #1", "PG&E Monitoring Center Tour #2"),
    ("California Men’s Tennis vs Stanford", "California Women’s Tennis vs Stanford"),
    ("Advanced Program in Software Development Online Information Session",
     "Program in Software Development Online Information Session"),
])
def test_different_events_at_the_same_time_stay_separate(a, b):
    assert len(build([ev(a, SIX_PM), ev(b, SIX_PM)], 30, NOW)) == 2


def test_mens_and_womens_meets_from_two_sources_stay_separate():
    mens = ev("California Men’s Swimming & Diving vs CSL Wild Card", SIX_PM,
              source="berkeley_calendar")
    womens = ev("California Women’s Swimming & Diving vs CSL Wild Card", SIX_PM, source="feeds")

    assert len(build([mens, womens], 30, NOW)) == 2


def test_full_postponed_and_busy_placeholders_are_dropped():
    events = build([ev("FULL | Fall Bird Walk"), ev("POSTPONED Women’s Golf vs Hawaii"),
                    ev("Busy", source="feeds"), ev("Fall Bird Walk")], 30, NOW)

    assert [e.title for e in events] == ["Fall Bird Walk"]


def test_midnight_start_with_no_time_is_shown_as_all_day():
    midnight = datetime(2026, 10, 29, 7, tzinfo=UTC)  # 00:00 Pacific

    [e] = build([ev("Art + Comic Expo", midnight)], 30, NOW)

    assert e.all_day is True


def test_a_title_repeating_all_month_is_listed_once_with_its_count():
    daily = [ev("Technology Help", NOW + timedelta(days=d, hours=2), source="feeds",
                url="https://lib.test/help") for d in range(1, 6)]

    [e] = build(daily, 30, NOW)

    assert e.start == NOW + timedelta(days=1, hours=2) and e.repeats == 5


def test_cancelled_anywhere_in_title_is_dropped_and_venue_placeholders_cleared():
    events = build([ev("Sorry, canceled again... pls pencil in 11/12"),
                    ev("Careers Panel", venue="Sign in to download the location")], 30, NOW)

    assert [(e.title, e.venue) for e in events] == [("Careers Panel", None)]


def test_links_that_are_not_web_pages_never_reach_the_site():
    events = build([
        ev("Script link", url="javascript:alert(1)"),
        ev("Odd image", image="data:image/svg+xml,<svg onload=alert(1)>",
           listings=[{"source": "feeds", "url": "javascript:x"}, {"source": "luma", "url": "https://lu.ma/a"}]),
    ], 30, NOW)

    assert [e.title for e in events] == ["Odd image"]
    assert events[0].image is None
    assert "javascript:x" not in [x["url"] for x in events[0].listings]
