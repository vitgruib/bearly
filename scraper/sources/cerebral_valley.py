"""Cerebral Valley: the AI-community calendar behind cerebralvalley.ai/events. Its public API
lists every approved Bay Area event; the /events page shows only the first 20. Times are
naive UTC (checked against the same events on Luma)."""

from datetime import UTC, datetime

from ..http import get_json
from ..models import Event, clean_text
from ..state import Context

API = "https://api.cerebralvalley.ai/v1/public/event/pull"


def _utc(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v).replace(tzinfo=UTC) if v else None


def parse_item(it: dict) -> Event | None:
    if not it.get("startDateTime") or not it.get("url"):
        return None
    city = (it.get("location") or "").split(",")[0].strip() or None
    return Event(
        title=clean_text(it["name"], 200),
        start=_utc(it["startDateTime"]),
        end=_utc(it.get("endDateTime")),
        url=it["url"],
        source="cerebral_valley",
        venue=clean_text(it.get("venue")) or None,
        city=None if city in ("Other", "Remote") else city,
        online=city == "Remote",
        image=it.get("imageUrl"),
        description=clean_text(it.get("descriptionSummary") or it.get("description")),
        tags=["Hackathon"] if it.get("type") == "HACKATHON" else [],
    )


def fetch(cfg: dict, ctx: Context) -> list[Event]:
    events, offset = [], 0
    while offset < cfg.get("max_events", 600):
        data = get_json(API, approved="true", location=cfg.get("location", "BAY_AREA"),
                        startDateTime=ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        limit=100, offset=offset)
        batch = data.get("events", [])
        events += [e for it in batch if (e := parse_item(it))]
        offset += len(batch)
        if not batch or offset >= data.get("totalCount", 0):
            break
    return events
