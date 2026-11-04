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


def test_a_carried_over_event_is_tagged_afresh_from_what_its_source_said(tmp_path, monkeypatch):
    # Run 1 tags the show from the venue's "Music" category. Run 2 reloads the published
    # record: it must still get Arts & Music, and its own published tags ("Arts & Music",
    # "RSVP required") must not be read back as text that re-triggers rules.
    from scraper.run import build

    now = datetime(2026, 11, 1, tzinfo=UTC)
    show = Event(title="Las Migas", start=datetime(2026, 11, 2, 4, tzinfo=UTC), url="https://v.test/1",
                 source="venues", city="Oakland", tags=["Music"], access=["$25 ticket"])
    stale = Event(title="Operators sync", start=datetime(2026, 11, 2, 16, tzinfo=UTC),
                  url="https://v.test/2", source="venues", city="Oakland")
    published = tmp_path / "events.json"
    first = build([show, stale], 30, now)
    records = [e.to_json() for e in first]
    records[1]["tags"] = ["Arts & Music"]  # what an older, looser rule wrote
    published.write_text(json.dumps({"events": records}))
    monkeypatch.setattr(state, "EVENTS", published)
    monkeypatch.setattr(state, "STATE", tmp_path / "state.json")

    again = {e.title: e for e in build(state.State().previous_events("venues"), 30, now)}

    assert again["Las Migas"].tags == ["Arts & Music"]
    assert again["Las Migas"].access == ["$25 ticket"]
    assert again["Operators sync"].tags == []
