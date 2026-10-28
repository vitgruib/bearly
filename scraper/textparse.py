"""Find events in free-form announcements (listserv emails, Slack posts, Instagram captions)
with plain pattern matching: no API, no cost.

Each paragraph that names a date gets parsed on its own, so a weekly newsletter listing five
events yields five events. A date is resolved against when the message was sent ("this
Friday" in a Tuesday email), and anything that resolves to the past is dropped, which also
discards recap posts ("thanks to everyone who came out Friday!")."""

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import Event, clean_text

PACIFIC = ZoneInfo("America/Los_Angeles")

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_WEEKDAY = r"(mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)(?:day)?s?\.?"
DATE_MONTH_DAY = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(20\d\d))?", re.IGNORECASE)
DATE_NUMERIC = re.compile(r"(?<![\d/$.])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/%])")
DATE_RELATIVE = re.compile(r"\b(today|tonight|tomorrow)\b", re.IGNORECASE)
DATE_WEEKDAY = re.compile(rf"\b(this\s+|next\s+|last\s+)?{_WEEKDAY}(?![a-z])", re.IGNORECASE)
TIME_RANGE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\s*(?:-|–|—|to|until)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", re.IGNORECASE)
TIME_SINGLE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", re.IGNORECASE)
TIME_NOON = re.compile(r"\b(noon|midnight)\b", re.IGNORECASE)

LOCATION_LABEL = re.compile(r"\b(?:location|where|place|venue|room)\s*[:\-–]\s*([^\n]{3,80})",
                            re.IGNORECASE)
LOCATION_AT = re.compile(
    r"(?:\bat\b|@|\bin\b)\s+((?:the\s+)?[A-Z0-9][\w'&.-]*(?:\s+(?:[A-Z0-9][\w'&.-]*|of|the|&))"
    r"{0,5}(?:\s+\d{2,4}[A-Z]?)?)")
CAMPUS_PLACES = re.compile(
    r"\b(soda|cory|wheeler|dwinelle|evans|etcheverry|sutardja dai|sdh|haas|chou|cheit|"
    r"moffitt|doe library|mlk|martin luther king|pauley ballroom|eshleman|hearst|stanley|"
    r"jacobs hall|wurster|vlsb|valley life sciences|barrows|tolman|lewis|latimer|pimentel|"
    r"zellerbach|sproul|memorial glade|kroeber|hertz|li ka shing|bechtel|mclaughlin|"
    r"o'brien|giannini|mulford|koshland|campbell|anthony hall|i-house|international house|"
    r"golden bear|upper sproul|lower sproul|rsf|recreational sports facility|"
    r"berkeley way west|bww|blum hall|genetics and plant biology|gpb|social sciences building|"
    r"boalt|law building|sather gate|the glade|faculty glade|unit [1-3]|clark kerr|foothill)\b",
    re.IGNORECASE)
PLACE_TAIL = re.compile(
    r"(?:\s+(?:Hall|Library|Ballroom|Auditorium|Center|Building|House|Plaza|Commons|Lounge|"
    r"Annex|Pavilion|Room))*(?:,?\s+(?:room\s+|rm\.?\s+|#)?\d{1,4}[A-Z]?\b)?", re.IGNORECASE)
FREE_FOOD = re.compile(
    r"free (?:food|pizza|boba|lunch|dinner|snacks|drinks)|(?:pizza|boba|food|snacks|lunch|"
    r"dinner|refreshments|drinks)\s+(?:will be\s+)?(?:provided|served)", re.IGNORECASE)
URL = re.compile(r"https?://\S+")


def _year_for(month: int, day: int, sent: date) -> int:
    """Announcements are about the near future: Jan 5 in a December email means next year."""
    candidate = date(sent.year, month, min(day, 28) if month == 2 else day)
    return sent.year + 1 if (sent - candidate).days > 60 else sent.year


def find_date(text: str, sent: date) -> date | None:
    if m := DATE_MONTH_DAY.search(text):
        month, day = MONTHS[m.group(1)[:3].lower()], int(m.group(2))
        if 1 <= day <= 31:
            year = int(m.group(3)) if m.group(3) else _year_for(month, day, sent)
            try:
                return date(year, month, day)
            except ValueError:
                pass
    if m := DATE_NUMERIC.search(text):
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            year = m.group(3)
            year = (2000 + int(year) if len(year) == 2 else int(year)) if year else \
                _year_for(month, day, sent)
            try:
                return date(year, month, day)
            except ValueError:
                pass
    if m := DATE_RELATIVE.search(text):
        return sent + timedelta(days=1 if m.group(1).lower() == "tomorrow" else 0)
    if m := DATE_WEEKDAY.search(text):
        target = WEEKDAYS.index(m.group(2)[:3].lower())
        ahead = (target - sent.weekday()) % 7
        prefix = (m.group(1) or "").strip().lower()
        if prefix == "last":
            return sent - timedelta(days=(7 - ahead) or 7)
        if prefix == "next" and ahead == 0:
            ahead = 7
        return sent + timedelta(days=ahead)
    return None


def _clock(h: str, mnt: str | None, ampm: str | None, fallback: str | None = None) -> time | None:
    hour, minute = int(h), int(mnt or 0)
    mer = (ampm or fallback or "").lower().replace(".", "")
    if hour > 12 or minute > 59:
        return None
    if mer == "pm" and hour != 12:
        hour += 12
    elif mer == "am" and hour == 12:
        hour = 0
    elif not mer:
        return None
    return time(hour, minute)


def find_times(text: str) -> tuple[time | None, time | None]:
    if m := TIME_RANGE.search(text):
        end = _clock(m.group(4), m.group(5), m.group(6))
        start = _clock(m.group(1), m.group(2), m.group(3), fallback=m.group(6))
        # "11-1pm": the start is the morning one.
        if start and end and start > end and not m.group(3):
            start = _clock(m.group(1), m.group(2), "am")
        return start, end
    if m := TIME_SINGLE.search(text):
        return _clock(m.group(1), m.group(2), m.group(3)), None
    if m := TIME_NOON.search(text):
        return (time(12) if m.group(1).lower() == "noon" else time(0)), None
    return None, None


def find_location(text: str) -> str | None:
    if m := LOCATION_LABEL.search(text):
        return m.group(1).strip(" .,;")
    if m := CAMPUS_PLACES.search(text):
        # Take the building plus its "Hall"/"Library" suffix and a room number if present.
        tail = PLACE_TAIL.match(text, m.end())
        return (m.group(0) + tail.group(0)).strip()
    for m in LOCATION_AT.finditer(text):
        place = m.group(1).strip()
        if not TIME_SINGLE.match(place) and not DATE_WEEKDAY.match(place) and len(place) > 3:
            return place
    return None


def _has_words(s: str) -> bool:
    """True when something besides the date and time is left: a usable title."""
    bare = TIME_RANGE.sub("", s)
    bare = TIME_SINGLE.sub("", DATE_MONTH_DAY.sub("", DATE_NUMERIC.sub("", bare)))
    bare = DATE_WEEKDAY.sub("", DATE_RELATIVE.sub("", bare))
    return len(re.sub(r"[\W\d_]", "", bare)) >= 4


# "Join us for our Photocard Decorating Event", "at its weekly editing workshop"
_EVENT_NOUN = (r"workshop|social|gm|general meeting|meeting|night|fest(?:ival)?|drive|fundraiser|"
               r"fireside chat|chat|mixer|info session|session|party|tour|sale|talk|panel|lecture|"
               r"hackathon|showcase|tournament|retreat|conference|open house|screening|"
               r"celebration|potluck|kickoff|banquet|gala|concert|performance|show|meetup|event")
NAMED_EVENT = re.compile(
    rf"\b(?:our|an?|the|its|their|this)\s+((?:[\w'’&@-]+\s+){{0,5}}?(?:{_EVENT_NOUN}))\b",
    re.IGNORECASE)
GENERIC_NAME = re.compile(rf"^(?:(?:first|next|second|weekly|annual|this)\s+)?(?:{_EVENT_NOUN})$",
                          re.IGNORECASE)
LABEL_LINE = re.compile(r"^\W*(?:when|where|date|dates|time|location|rsvp|link)\b", re.IGNORECASE)
GREETING = re.compile(r"^\W*(?:hi|hey|hello|bello|happy|good morning|dear)\b", re.IGNORECASE)
# Deadlines look like events (a date and a time) but nobody attends them.
DEADLINE = re.compile(r"\b(?:deadline|due|apply by|register\b.{0,20}\bby|submit\b.{0,20}\bby|"
                      r"applications? (?:close|open))|\b11:59\s*(?:pm|p\.m\.)", re.IGNORECASE)
SHIFT_SIGNUP = re.compile(r"\bvolunteers?\b.*\b(?:slots?|shifts?)\b", re.IGNORECASE | re.DOTALL)


def _tidy(s: str) -> str:
    s = re.sub(r"^[^\w@]+|[^\w)!?.\'’]+$", "", URL.sub("", s)).strip()
    words = [w for w in s.split() if w.isalpha()]
    caps = [w for w in words if len(w) > 2 and w.isupper()]
    # "first BAKE SALE" or "HAPPY HALLOWEEN PARTY TONIGHT", but leave "IEEE GM 2" alone
    shouting = len(caps) >= 2 and (len(caps) < len(words) or len(words) >= 4)
    return s.title() if s.islower() or shouting else s


def _segment_title(line: str) -> str | None:
    """A one-line listing ("Wed 10/28 | 1–3 PM | Slime at the Lounge"): its non-date part."""
    line = re.sub(r"^\s*(?:\d+[.)]|[-•*#>])\s*", "", line)
    for seg in re.split(r"\s+[—–|]\s+|\s+-\s+|:\s+|\s*\|\s*", line):
        seg = re.sub(r"\s+(?:at|@|in)\s+(?:the\s+)?[A-Z].*$", "", _tidy(seg))
        if 4 <= len(seg) <= 90 and _has_words(seg) and not LABEL_LINE.match(seg):
            return seg
    return None


def _headline(text: str) -> str | None:
    for line in text.splitlines():
        line = _tidy(re.sub(r"^\s*(?:\d+[.)]|[-•*#>])\s*", "", line))
        if not line or LABEL_LINE.match(line) or GREETING.match(line) or line.startswith("#"):
            continue
        return line if len(line) <= 60 and _has_words(line) else None
    return None


def _named_event(text: str) -> str | None:
    names = []
    proper = []
    for m in NAMED_EVENT.finditer(text):
        name = _tidy(m.group(1))
        if any(w[0].isupper() for w in m.group(1).split()):
            proper.append(name)
        if GENERIC_NAME.match(name):
            # "an info session with Infiniti Solutions" is still a name
            if w := re.match(r"\s+with\s+((?:[A-Z][\w&'’.-]*\s?){1,4})", text[m.end():]):
                names.append(f"{name.title()} with {w.group(1).strip()}")
            continue
        names.append(name)
    # Prefer a proper name ("Sock Pumpkin Workshop") over a description ("cozy night").
    return next((n for n in names if n in proper), names[0] if names else None)


def _title(block: str, text: str, subject: str | None, host: str | None) -> str:
    lines = [ln for ln in block.splitlines() if ln.strip()]
    listing = (len(lines) == 1 and re.search(r"\s[|—–]\s|\s-\s", lines[0])
               and not re.search(r"\b(?:date|time)\s*:", lines[0], re.IGNORECASE))
    if listing and len(text.strip()) > len(block) and (t := _segment_title(lines[0])):
        return t  # one entry in a list of events
    return (subject or _named_event(block) or _named_event(text) or _headline(text)
            or (f"{host} event" if host else "Event"))


def _blocks(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\s*(?:\d+[.)]|[-•*])\s)", text)]
    return [p for p in parts if p]


def parse_announcement(text: str, sent: datetime, source: str, url: str = "",
                       host: str | None = None, subject: str | None = None,
                       horizon_days: int = 60) -> list[Event]:
    sent_local = sent.astimezone(PACIFIC)
    today = sent_local.date()
    events, seen = [], set()
    if SHIFT_SIGNUP.search(text):  # "volunteers needed, pick a slot": shifts, not events
        return []
    for block in _blocks(text):
        if DEADLINE.search(block):
            continue
        day = find_date(block, today)
        if day is None:
            continue
        start_t, end_t = find_times(block)
        if start_t is None:
            continue  # a bare date is usually a deadline, not an event
        if not (today <= day <= today + timedelta(days=horizon_days)):
            continue
        start = datetime.combine(day, start_t, PACIFIC)
        if start < sent_local - timedelta(hours=1):
            continue
        end = datetime.combine(day, end_t, PACIFIC) if end_t else None
        if end and end <= start:
            end += timedelta(days=1)
        title = _title(block, text, subject, host)
        key = (title.lower(), start)
        if key in seen:
            continue
        seen.add(key)
        place = find_location(block)
        on_campus = bool(place and CAMPUS_PLACES.search(place))
        desc = clean_text(URL.sub("", block))
        events.append(Event(
            title=clean_text(title, 120),
            start=start,
            end=end,
            url=(URL.search(block).group(0).rstrip(".,)") if URL.search(block) else url),
            source=source,
            host=host,
            venue=place,
            city="Berkeley" if on_campus else None,
            lat=37.8719 if on_campus else None,
            lng=-122.2585 if on_campus else None,
            online=bool(re.search(r"\bzoom\b|\bonline\b|\bvirtual\b", block, re.IGNORECASE)) and not place,
            description=desc + (" Free food." if FREE_FOOD.search(block)
                                and "free food" not in desc.lower() else ""),
        ))
    return events
