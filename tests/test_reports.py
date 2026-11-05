from datetime import datetime
from zoneinfo import ZoneInfo

from scraper.llms import write_llms_full
from scraper.models import Event
from scraper.pages import event_page
from scraper.reports import parse_reports

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
