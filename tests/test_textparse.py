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


# Shapes below come from a hand-labelled sample of 80 club Instagram posts (2026-10-28).

def test_deadline_with_a_time_is_not_an_event():
    text = ("Our firm visit is Tuesday, November 3 in the afternoon.\n\n"
            "The deadline to apply for this event is Thursday, October 29 at 11:59 PM.")
    registration = "REGISTRATION IS NOW OPEN!!\n\nRegister your team by Sunday Nov 1st, 11:59pm!"

    assert parse_announcement(text, TUESDAY, "instagram") == []
    assert parse_announcement(registration, TUESDAY, "instagram") == []


def test_volunteer_shift_lists_are_not_events():
    text = ("We're looking for volunteers to lead campus tours!\n\n"
            "📍 Wednesday, November 4 | 10 AM – 2 PM\nHigh school visit @ UC Berkeley\n\n"
            "📍 Friday, November 6 | 10:30 AM – 11:15 AM\nCampus tour\n\n"
            "Please select ONLY one slot. Sign up below!")

    assert parse_announcement(text, TUESDAY, "instagram") == []


def test_title_is_the_named_event_not_a_label_or_greeting():
    labelled = ("Hi Community!!\n\nJoin us for our Photocard Decorating Event!\n\n"
                "📅 Date: Thursday, Oct 29\n🕔 Time: 8PM\n📍 Location: Dwinelle 243")
    tonight = ("CalTV is covering AFTER EFFECTS at its weekly editing workshop TONIGHT, "
               "8-10 PM in the ASUC Senate Chambers!")

    [a] = parse_announcement(labelled, TUESDAY, "instagram", host="Art and Mind")
    [b] = parse_announcement(tonight, TUESDAY, "instagram", host="CalTV")

    assert a.title == "Photocard Decorating Event"
    assert a.start == datetime(2026, 10, 29, 20, 0, tzinfo=PT)
    assert b.title == "Weekly Editing Workshop"


def test_each_line_of_an_event_list_is_titled_by_its_own_name():
    text = ("Halloween Week is here!\n\n"
            "👻 Wed 10/28 | 1–3 PM | Make Your Own Slime at the Undergrad Lounge\n\n"
            "🍫 Fri 10/30 | 12–2 PM | Haas Fall Fest at the Haas Courtyard")

    events = parse_announcement(text, TUESDAY, "instagram")

    assert [(e.title, e.start) for e in events] == [
        ("Make Your Own Slime", datetime(2026, 10, 28, 13, 0, tzinfo=PT)),
        ("Haas Fall Fest", datetime(2026, 10, 30, 12, 0, tzinfo=PT)),
    ]


def test_untitled_post_falls_back_to_the_host_not_a_fragment():
    text = "Support us by getting chipotle TOMORROW from 4-8PM!! Show this flyer at the cashier."

    [e] = parse_announcement(text, TUESDAY, "instagram", host="American Red Cross at Cal")

    assert e.title == "American Red Cross at Cal event"
