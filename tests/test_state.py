"""Carry-over of the last published events for sources that did not run."""

import json
from datetime import UTC, datetime

from scraper import state
from scraper.models import Event


def test_previous_events_round_trip_an_event_without_a_link(tmp_path, monkeypatch):
    published = tmp_path / "events.json"
    e = Event(title="ASUC Senate meeting", start=datetime(2026, 11, 2, 2, tzinfo=UTC), url="",
              source="feeds", city="Berkeley")
    published.write_text(json.dumps({"events": [e.to_json()]}))
    monkeypatch.setattr(state, "EVENTS", published)
    monkeypatch.setattr(state, "STATE", tmp_path / "state.json")

    [back] = state.State().previous_events("feeds")

    assert (back.title, back.start, back.url, back.city) == (e.title, e.start, "", "Berkeley")


def test_a_source_whose_config_changed_runs_before_its_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "EVENTS", tmp_path / "events.json")
    monkeypatch.setattr(state, "STATE", tmp_path / "state.json")
    s = state.State()
    ran = datetime(2026, 10, 28, 7, tzinfo=UTC)
    s.record("feeds", ran, 0, None, [], {"list": []})
    an_hour_later = datetime(2026, 10, 28, 8, tzinfo=UTC)

    assert not s.due("feeds", 6, an_hour_later, {"list": []})
    assert s.due("feeds", 6, an_hour_later, {"list": [{"name": "ASUC"}]})
