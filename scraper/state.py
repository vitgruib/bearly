"""Run-to-run memory, published next to events.json as site/data/state.json.

The deployed site *is* the database: each CI run first downloads the last published
events.json and state.json, so nothing is ever committed back to the repo. State holds
per-source health (for alerting), when each source last ran (for per-source schedules),
and a free-form `memory` dict each source can use: discovered Luma calendars, the
Instagram high-water mark, Apify spend this month."""

import json
import logging
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import Event, parse_dt

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "site" / "data"
EVENTS = DATA / "events.json"
STATE = DATA / "state.json"

log = logging.getLogger(__name__)


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class State:
    def __init__(self) -> None:
        self.data = _read(STATE)
        self.data.setdefault("sources", {})
        self._previous = _read(EVENTS).get("events", [])

    def source(self, name: str) -> dict:
        return self.data["sources"].setdefault(name, {"counts": [], "failures": 0, "memory": {}})

    def memory(self, name: str) -> dict:
        return self.source(name).setdefault("memory", {})

    def due(self, name: str, every_hours: float, now: datetime) -> bool:
        last = self.source(name).get("last_run")
        # 15 min slack so a cron that fires a little early still counts.
        return not last or now - parse_dt(last) >= timedelta(hours=every_hours, minutes=-15)

    def previous_events(self, name: str) -> list[Event]:
        out = []
        for d in self._previous:
            if d["source"] != name:
                continue
            # to_json drops empty fields, so a link-less event comes back without "url".
            fields = {"url": "", **{k: v for k, v in d.items() if k not in ("id", "start", "end")}}
            out.append(Event(**fields, start=parse_dt(d["start"]),
                             end=parse_dt(d["end"]) if d.get("end") else None))
        return out

    def record(self, name: str, now: datetime, count: int | None, error: str | None,
               warnings: list[str]) -> str:
        """Store one run's outcome and return the source's health label."""
        s = self.source(name)
        s["last_run"] = now.isoformat(timespec="seconds")
        s["warnings"] = warnings[-10:]
        if error is None:
            s["last_ok"] = s["last_run"]
            s["failures"] = 0
            s["error"] = None
            s["counts"] = (s["counts"] + [count])[-10:]
        else:
            s["failures"] = s.get("failures", 0) + 1
            s["error"] = error[:300]
        s["health"] = health(s)
        return s["health"]

    def save(self) -> None:
        DATA.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(self.data, indent=1, sort_keys=True))


def health(s: dict) -> str:
    if s.get("failures", 0) >= 3:
        return "down"
    if s.get("failures", 0) > 0:
        return "failing"
    counts = s.get("counts", [])
    if len(counts) >= 4:
        typical = statistics.median(counts[:-1])
        # A scraper that silently returns far fewer events usually means the page changed.
        if typical >= 10 and counts[-1] < 0.3 * typical:
            return "degraded"
    return "ok"


class NotConfigured(Exception):
    """A source that needs credentials nobody has provided yet. Not a failure."""


def now_utc() -> datetime:
    return datetime.now(UTC)


class Context:
    """What a source gets besides its config: its own persistent memory, a place to report
    problems with individual feeds without failing the whole source, and the run clock."""

    def __init__(self, memory: dict, now: datetime) -> None:
        self.memory = memory
        self.now = now
        self.warnings: list[str] = []

    def warn(self, msg: str) -> None:
        log.warning(msg)
        self.warnings.append(msg[:200])
