"""Instagram via Apify, with Apify mocked at the HTTP boundary (it is a paid API)."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from scraper import http
from scraper.sources import instagram
from scraper.state import Context

PT = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=PT)
POST = {"url": "https://www.instagram.com/p/abc/", "ownerFullName": "Codeology",
        "timestamp": "2026-10-26T20:00:00.000Z", "displayUrl": "https://img.test/a.jpg",
        "caption": "Codeology x Hackers@Berkeley game night 🎲\nThursday 10/29 7pm, Soda 306"}


@pytest.fixture
def apify(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.method == "POST":
            return httpx.Response(201, json={"data": {"id": "r1", "status": "SUCCEEDED",
                                                      "defaultDatasetId": "d1",
                                                      "usageTotalUsd": 0.04}})
        return httpx.Response(200, json=[POST])

    monkeypatch.setenv("APIFY_TOKEN", "test-token")
    monkeypatch.setattr(http, "client", httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    return calls


def test_new_posts_become_events_and_are_remembered(apify):
    ctx = Context({}, NOW)

    [e] = instagram.fetch({"accounts": ["codeology"]}, ctx)

    assert e.title == "Codeology x Hackers@Berkeley game night 🎲"
    assert e.start == datetime(2026, 10, 29, 19, 0, tzinfo=PT)
    assert (e.host, e.image, e.url) == ("Codeology", "https://img.test/a.jpg", POST["url"])
    assert ctx.memory["budget"]["spent_usd"] == 0.04
    sent = json.loads(apify[0].content)
    assert sent["username"] == ["codeology"] and sent["onlyPostsNewerThan"] == "2026-10-25"


def test_accounts_are_read_in_rotating_slices(apify):
    ctx = Context({}, NOW)
    cfg = {"accounts": ["a", "b", "c"], "accounts_per_run": 2}

    instagram.fetch(cfg, ctx)
    instagram.fetch(cfg, ctx)

    sent = [json.loads(r.content) for r in apify if r.method == "POST"]
    assert [s["username"] for s in sent] == [["a", "b"], ["c", "a"]]
    # 3 accounts / 2 per run = 2 daily runs per cycle, plus a day of overlap
    assert sent[0]["onlyPostsNewerThan"] == "2026-10-24"


def test_exhausted_monthly_budget_skips_apify_but_keeps_known_events(apify):
    memory = {"budget": {"month": "2026-10", "spent_usd": 3.0},
              "posts": {POST["url"]: {"caption": POST["caption"], "timestamp": POST["timestamp"],
                                      "url": POST["url"], "owner": "Codeology"}}}
    ctx = Context(memory, NOW)

    events = instagram.fetch({"accounts": ["codeology"], "monthly_budget_usd": 3.0}, ctx)

    assert apify == []
    assert [e.title for e in events] == ["Codeology x Hackers@Berkeley game night 🎲"]
    assert "budget" in ctx.warnings[0]
