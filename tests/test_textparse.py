from datetime import datetime
from zoneinfo import ZoneInfo

from scraper.textparse import parse_announcement

PT = ZoneInfo("America/Los_Angeles")
TUESDAY = datetime(2026, 10, 27, 10, 0, tzinfo=PT)


def test_club_meeting_email_with_room_and_food():
    text = "ML@B General Meeting\nThursday 10/29, 7-8:30pm in Soda 306\nFree pizza!"

    [e] = parse_announcement(text, TUESDAY, "email")

    assert e.title == "ML@B General Meeting"
    assert e.start == datetime(2026, 10, 29, 19, 0, tzinfo=PT)
    assert e.end == datetime(2026, 10, 29, 20, 30, tzinfo=PT)
    assert e.venue == "Soda 306"
    assert e.city == "Berkeley"
    assert "Free food" in e.description


def test_newsletter_lists_each_event_separately():
    text = ("Upcoming events this week:\n\n"
            "1. Resume Workshop — Wed Oct 28, 12-1pm, Location: 220 Stephens Hall\n\n"
            "2. Startup Mixer — Nov 3 at 6:30 PM @ Chou Hall")

    events = parse_announcement(text, TUESDAY, "email")

    assert [(e.title, e.start, e.venue) for e in events] == [
        ("Resume Workshop", datetime(2026, 10, 28, 12, 0, tzinfo=PT), "220 Stephens Hall"),
        ("Startup Mixer", datetime(2026, 11, 3, 18, 30, tzinfo=PT), "Chou Hall"),
    ]
    assert events[0].end == datetime(2026, 10, 28, 13, 0, tzinfo=PT)


def test_relative_dates_resolve_against_send_time():
    [e] = parse_announcement("Boba social tomorrow 4pm on Memorial Glade!", TUESDAY, "slack")

    assert e.start == datetime(2026, 10, 28, 16, 0, tzinfo=PT)
    assert e.venue == "Memorial Glade"


def test_recaps_and_deadlines_are_not_events():
    recap = "Thank you all for coming out last Friday at 7pm! See you next semester."
    deadline = "Reminder: applications are due Friday 11/7."
    past = "Our info session was on 10/20 at 6pm in Wheeler 150."

    assert parse_announcement(recap, TUESDAY, "instagram") == []
    assert parse_announcement(deadline, TUESDAY, "email") == []
    assert parse_announcement(past, TUESDAY, "email") == []


def test_january_date_in_a_december_email_is_next_year():
    december = datetime(2026, 12, 10, 9, 0, tzinfo=PT)

    [e] = parse_announcement("Winter hack night Jan 8, 6pm", december, "email")

    assert e.start == datetime(2027, 1, 8, 18, 0, tzinfo=PT)
