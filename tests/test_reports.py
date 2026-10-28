"""Missed-event reports read from the Google Form's published response sheet."""

from datetime import UTC, datetime

from scraper import links
from scraper.models import Event
from scraper.sources import reports
from scraper.state import Context

SHEET = """Timestamp,Event link,Event name,When and where,Where did you see it?
8/1/2026 10:00:00,https://luma.com/oldthing,Old mixer,,
10/27/2026 21:14:03,https://luma.com/abc123?tk=x,AI x Bio night,,eecs-ugrads
10/27/2026 22:01:44,see https://partiful.com/e/Zq9 !,Pi Phi party,Fri 9pm,instagram
10/28/2026 08:30:00,https://luma.com/abc123,AI x Bio night,,
10/28/2026 09:12:51,,Robotics GBM,Thu 7pm Soda 306,club slack
10/28/2026 09:40:00,https://luma.com/spam1,BUY CRYPTO,,
10/28/2026 10:05:00,https://instagram.com/p/xyz,Dance showcase,,
"""


def test_fetch_resolves_each_recent_reported_link_once_skipping_blocked(monkeypatch):
    resolved = []

    def resolve(url, source):
        resolved.append(url)
        return [Event(title=url, start=datetime(2026, 11, 1, tzinfo=UTC), url=url,
                      source="luma", also_on=[source])]

    monkeypatch.setattr(reports, "get_text", lambda url: SHEET)
    monkeypatch.setattr(links, "resolve", resolve)
    cfg = {"sheet_csv": "https://docs.google.com/x/pub?output=csv", "days_back": 60,
           "block": ["https://luma.com/spam1"]}

    events = reports.fetch(cfg, Context({}, datetime(2026, 10, 28, 18, tzinfo=UTC)))

    assert resolved == ["https://luma.com/abc123", "https://partiful.com/e/Zq9"]
    assert [e.also_on for e in events] == [["reports"], ["reports"]]
