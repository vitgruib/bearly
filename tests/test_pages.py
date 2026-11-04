import json
import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

from scraper.models import Event
from scraper.pages import write_pages

NOW = datetime(2026, 10, 27, 18, tzinfo=UTC)
SITE = "https://example.github.io/lo-cal/"


def ev(title="Intro to Rust", **kw):
    return Event(title=title, start=kw.pop("start", NOW + timedelta(days=1)), url="https://luma.com/x",
                 source="luma", **kw)


class Head(HTMLParser):
    """Collects what a link-preview bot reads: meta tags and the JSON-LD block."""

    def __init__(self):
        super().__init__()
        self.meta, self.ld, self._in_ld = {}, "", False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            self.meta[a.get("property") or a.get("name")] = a.get("content")
        self._in_ld = tag == "script" and a.get("type") == "application/ld+json"

    def handle_data(self, data):
        if self._in_ld:
            self.ld += data


def read(path):
    head = Head()
    head.feed(path.read_text())
    return head


def test_event_page_gives_link_previews_and_search_engines_the_event(tmp_path):
    e = ev("Founder Dinner", venue="Spieker Forum", host="BEGIN", image="https://img.test/a.png",
           description="Pizza and pitches.")
    write_pages([e], SITE, tmp_path, NOW)

    head = read(tmp_path / "e" / f"{e.id}.html")
    ld = json.loads(head.ld)

    assert head.meta["og:title"] == "Founder Dinner"
    assert head.meta["og:image"] == "https://img.test/a.png"
    assert head.meta["og:url"] == f"{SITE}e/{e.id}.html"
    assert "Spieker Forum" in head.meta["og:description"]
    assert (ld["@type"], ld["name"], ld["location"]["name"]) == ("Event", "Founder Dinner", "Spieker Forum")


def test_hostile_event_text_cannot_inject_markup(tmp_path):
    e = ev('"><script>alert(1)</script>', description="</script><img src=x onerror=alert(1)>")
    write_pages([e], SITE, tmp_path, NOW)

    html = (tmp_path / "e" / f"{e.id}.html").read_text()
    head = read(tmp_path / "e" / f"{e.id}.html")

    assert len(re.findall(r"<script", html)) == 2  # the JSON-LD block and the counter
    assert "<img" not in html
    assert json.loads(head.ld)["description"] == "</script><img src=x onerror=alert(1)>"


def test_pages_of_ended_events_are_removed_and_sitemap_lists_current_ones(tmp_path):
    old, new = ev("Last week's talk"), ev("Next week's talk")
    write_pages([old], SITE, tmp_path, NOW)
    write_pages([new], SITE, tmp_path, NOW)

    sitemap = (tmp_path / "sitemap.xml").read_text()

    assert [p.name for p in (tmp_path / "e").iterdir()] == [f"{new.id}.html"]
    assert f"{SITE}e/{new.id}.html" in sitemap and old.id not in sitemap
