from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scraper.llms import write_llms_full
from scraper.models import Event
from scraper.pages import event_page
from scraper.reports import attach, parse_reports

PT = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 5, 9, tzinfo=PT)
SITE = "https://example.github.io/lo-cal/"

SHEET = """Timestamp,What's this about?,Event link,No link? Where was it posted?,Club or calendar name,Calendar link,Where are the events?,Event,What's wrong?,Details,Your feedback
11/5/2026 10:02:11,Report an event,,,,,,Rust talk (Thu Nov 5) [0123456789ab],Cancelled,Speaker is sick,
11/5/2026 11:15:40,Report an event,,,,,,Rust talk (Thu Nov 5) [0123456789ab],Wrong time or place,"Moved to Wheeler 150, 7pm",
11/5/2026 12:00:00,Send feedback,,,,,,,,,Love it
11/5/2026 12:30:00,Report an event,,,,,,Some event with no id,Spam or not a real event,,
"""


def test_reports_from_the_sheet_are_grouped_by_event_id():
    assert parse_reports(SHEET) == {"0123456789ab": [
        {"kind": "Cancelled", "details": "Speaker is sick", "date": "11/5/2026"},
        {"kind": "Wrong time or place", "details": "Moved to Wheeler 150, 7pm", "date": "11/5/2026"},
    ]}


def test_a_reported_event_shows_its_reports_to_people_and_llms(tmp_path):
    e = Event(title="Rust talk", start=NOW, url="https://luma.com/rust", source="luma",
              reports=[{"kind": "Cancelled", "details": "<b>Speaker</b> is sick", "date": "11/5/2026"}])
    write_llms_full([e], SITE, tmp_path / "llms-full.txt", NOW)
    llms = (tmp_path / "llms-full.txt").read_text()
    page = event_page(e, SITE)
    assert "Reported by a visitor (unverified): Cancelled: <b>Speaker</b> is sick" in llms
    assert "Cancelled: &lt;b&gt;Speaker&lt;/b&gt; is sick" in page


def test_multiline_details_keep_an_event_on_one_line_for_llms(tmp_path):
    sheet = SHEET.splitlines()[0] + '\n11/5/2026 10:00:00,Report an event,,,,,,Rust talk [0123456789ab],Wrong time or place,"Now in Wheeler 150,\nstarts 7pm"\n'
    e = Event(title="Rust talk", start=NOW, url="https://luma.com/rust", source="luma",
              reports=parse_reports(sheet)["0123456789ab"])
    write_llms_full([e], SITE, tmp_path / "llms-full.txt", NOW)
    lines = [ln for ln in (tmp_path / "llms-full.txt").read_text().splitlines() if "luma.com/rust" in ln]
    assert len(lines) == 1 and "Wrong time or place: Now in Wheeler 150, starts 7pm" in lines[0]


def test_a_report_follows_its_event_through_a_rename():
    before = Event(title="Greptile Outpost", start=NOW, url="https://cerebralvalley.ai/e/greptile", source="luma")
    links: dict = {}
    attach([before], {}, links, NOW.date())
    # Next build: a merge picked another listing's title and link; the old link is still a listing.
    after = Event(title="Greptile Outpost at SOHN", start=NOW, url="https://luma.com/greptile", source="luma",
                  listings=[{"source": "luma", "url": "https://luma.com/greptile"},
                            {"source": "cerebral_valley", "url": "https://cerebralvalley.ai/e/greptile"}])
    report = {"kind": "Cancelled or moved", "details": "", "date": "11/5/2026"}
    attach([after], {before.id: [report]}, links, NOW.date())
    assert before.id != after.id and after.reports == [report]


def test_a_deleted_sheet_row_withdraws_the_report():
    e = Event(title="Rust talk", start=NOW, url="https://luma.com/rust", source="luma",
              reports=[{"kind": "Duplicate", "details": "", "date": "11/5/2026"}])  # carried from the last build
    attach([e], {}, {}, NOW.date())
    assert e.reports == []


def test_a_report_on_one_date_of_a_series_stays_off_its_next_date():
    tour = {"title": "Exhibition Tour", "url": "https://bampfa.org/tour", "source": "feeds", "repeats": 6}
    links: dict = {}
    today = Event(start=NOW, **tour)
    attach([today], {}, links, NOW.date())
    tomorrow = Event(start=NOW + timedelta(days=1), **tour)
    attach([tomorrow], {today.id: [{"kind": "Cancelled or moved", "details": "", "date": "11/5/2026"}]},
           links, (NOW + timedelta(days=1)).date())
    assert tomorrow.reports == []
