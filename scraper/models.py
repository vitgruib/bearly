import hashlib
import html
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Event:
    title: str
    start: datetime  # timezone-aware
    url: str
    source: str  # which scraper found it: "luma", "feeds", ...
    end: datetime | None = None
    all_day: bool = False
    host: str | None = None
    venue: str | None = None
    address: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    online: bool = False
    image: str | None = None
    description: str = ""
    free: bool | None = None
    tags: list[str] = field(default_factory=list)
    region: str | None = None
    also_on: list[str] = field(default_factory=list)
    repeats: int | None = None  # this listing recurs; the record is its next occurrence

    @property
    def id(self) -> str:
        return hashlib.sha1(f"{dedupe_key(self)}".encode()).hexdigest()[:12]

    def to_json(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat() if self.end else None
        return {k: v for k, v in d.items() if v not in (None, [], "")}


def dedupe_key(e: Event) -> str:
    title = re.sub(r"[^a-z0-9]+", "", e.title.lower())[:40]
    return f"{title}|{e.start.date().isoformat()}"


_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(s: str | None, limit: int = 320) -> str:
    """HTML or messy text -> a single tidy plain-text paragraph."""
    if not s:
        return ""
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0] + "…"


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)
