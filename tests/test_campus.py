from datetime import UTC, datetime

import pytest

from scraper.enrich import region_for
from scraper.models import Event

START = datetime(2026, 11, 6, 18, tzinfo=UTC)


def ev(source="luma", **kw):
    return Event(title="Event", start=START, url="https://x.test/e", source=source, **kw)


# Coordinates are the places' own (Luma and the campus calendar geocode to the building).
@pytest.mark.parametrize("place, lat, lng", [
    ("Soda Hall", 37.8756, -122.2588),
    ("Philosophy Hall", 37.871016, -122.258087),
    ("Chou Hall, Haas", 37.8723, -122.254544),
    ("Greek Theatre", 37.8736, -122.2543),
    ("Bakar BioEnginuity Hub, 2625 Durant Ave", 37.8683207, -122.2556607),
    ("Clark Kerr Campus", 37.8640, -122.2470),
])
def test_points_inside_the_campus_boundary_are_campus(place, lat, lng):
    assert region_for(ev(venue=place, city="Berkeley", lat=lat, lng=lng)) == "Campus"


# All within 1.3 km of campus, which used to be enough to call them Campus.
@pytest.mark.parametrize("place, lat, lng", [
    ("The Freight, 2020 Addison St", 37.8706997, -122.2695537),
    ("SoCo coworking, 2170 Dwight Way", 37.8639033, -122.2654564),
    ("2180 Milvia St", 37.8695102, -122.2708727),
])
def test_downtown_and_southside_near_campus_are_berkeley(place, lat, lng):
    assert region_for(ev(venue=place, city="Berkeley", lat=lat, lng=lng)) == "Berkeley"


# Club and campus feeds give a room and no coordinates.
@pytest.mark.parametrize("venue", [
    "241 Giannini Hall", "C325 Cheit Hall", "120 Latimer Hall", "648 Evans Hall", "Wheeler 124",
    "105 Law Building", "Hildebrand Hall, Room B51", "Berkeley Way West, CR 1102",
    "Dwinelle Hall, South Dr, Berkeley, CA 94720, USA", "Moffitt Library 405", "BAMPFA",
    "MLK Student Union, Pauley Ballroom",
])
def test_campus_buildings_named_without_coordinates_are_campus(venue):
    assert region_for(ev(source="feeds", venue=venue)) == "Campus"


@pytest.mark.parametrize("venue", [
    "Berkeley Hillel-Bakar Auditorium", "Central Library - Community Meeting Room",
    "1950 Martin Luther King Jr Way", "Foothill Blvd, Oakland", "1801 Hearst Ave",
    "Evans Street Cafe", "Ashkenaz Music & Dance Community Center",
])
def test_streets_and_places_sharing_a_campus_name_are_not_campus(venue):
    assert region_for(ev(source="feeds", venue=venue)) != "Campus"


# Names from real listings that the first version of the matcher missed.
@pytest.mark.parametrize("venue", [
    "Hertz Concert Hall", "Jarvis Auditorium, Grimes Engineering Center", "Gateway 5340, 5th Floor",
    "Kayla Moore QTBIPOC Lounge (HFA A20)", "GA Conference Room 444A", "Booth Auditorium",
    "297 Goldberg Room", "Cory-521 Hogan Rm Cap:52", "Seminar Room (55A McCone)", "Stanley 177",
    "691 SSB (CRG Conference Room)", "Physics 3", "Mario Savio Steps, Sather Rd",
    "Wu Performance Hall, Morrison Building", "Other Campus Location (see event description)",
    "Spieker Aquatics Complex", "Magnes Collection of Jewish Life and Art", "OCF Computer Lab",
    "Cory Courtyard (2nd Floor)", "Warren Room & Donor Lobby", "UC Berkeley",
])
def test_more_campus_rooms_are_campus(venue):
    assert region_for(ev(source="feeds", venue=venue)) == "Campus"


def test_bare_haas_room_codes_count_only_on_the_campus_calendar():
    haas = Event(title="Seminar", start=START, url="https://events.berkeley.edu/haas/event/1-x",
                 source="berkeley_calendar", venue="C250", city="Berkeley")
    other = Event(title="Meetup", start=START, url="https://luma.com/x", source="luma",
                  venue="C250", city="Berkeley")
    assert (region_for(haas), region_for(other)) == ("Campus", "Berkeley")


def test_a_hybrid_event_in_a_campus_room_is_campus_not_online():
    assert region_for(ev(source="berkeley_calendar", venue="10 Stephens Hall", online=True)) == "Campus"


def test_campus_calendar_venue_entities_are_decoded():
    from scraper.sources.berkeley_calendar import parse_item
    e = parse_item({"title": "Talk", "date_iso": "2026-11-06T12:00:00-08:00", "url": "https://x.test",
                    "location_title": "100 Genetics &amp; Plant Biology Building",
                    "location": "100 Genetics &amp; Plant Biology Building"})
    assert (e.venue, e.region if e.region else region_for(e)) == (
        "100 Genetics & Plant Biology Building", "Campus")
