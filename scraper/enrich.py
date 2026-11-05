"""Derive region and topic tags so the frontend can filter without knowing sources."""

import math
import re

from . import campus
from .models import Event

CAMPUS = (37.8719, -122.2585)

EAST_BAY = {
    "oakland", "emeryville", "albany", "el cerrito", "richmond", "alameda", "piedmont",
    "san leandro", "walnut creek", "lafayette", "orinda", "moraga", "concord",
    "pleasant hill", "hayward", "fremont", "pleasanton", "dublin", "livermore",
    "san ramon", "danville", "kensington", "el sobrante", "union city", "castro valley",
}
PENINSULA = {
    "palo alto", "stanford", "menlo park", "mountain view", "redwood city", "san mateo",
    "burlingame", "san carlos", "sunnyvale", "santa clara", "san jose", "cupertino",
    "foster city", "south san francisco", "millbrae", "belmont", "los altos", "milpitas",
    "daly city", "san bruno", "half moon bay", "hillsborough",
}

LOCAL_SOURCES = {"email", "slack", "feeds", "instagram", "berkeley_calendar"}

REGIONS = ["Campus", "Berkeley", "East Bay", "San Francisco", "Peninsula & South Bay",
           "North Bay", "Sacramento", "Los Angeles", "San Diego", "Online"]

# Ordered: the frontend shows chips in this order.
TOPICS: dict[str, list[str]] = {
    "AI & Tech": [r"\bai\b", r"\bml\b", "machine learning", r"\bllms?\b", r"\bagents?\b",
                  r"\bagentic\b", r"\bgpt", "artificial intelligence", "software", "developer",
                  "engineering", "coding", "robotic", "crypto", "web3", "blockchain",
                  "data science", r"\bdevs?\b", "open source", "computing", r"\btech\b",
                  "cybersecurity", "quantum"],
    "Startups": ["startup", "founder", r"\bvcs?\b", "venture", r"\bpitch", "demo day",
                 "entrepreneur", "fundrais", "accelerator", "skydeck", "investor"],
    "Hackathons": ["hackathon", "hack night", "build night", "game jam", "buildathon",
                   "hack day", r"\bhack with\b"],
    "Career": ["career", "recruit", "networking", "info session", "information session",
               "resume", "interview", r"\bjobs?\b", "internship", "fellowship", "employer",
               "coffee chat", "office hours", "professional"],
    "Talks": ["lecture", "seminar", "colloquium", r"\btalk\b", r"\btalks\b", "panel",
              "symposium", "journal club", "workshop", "conference", "reading group",
              "book launch", "in conversation", "fireside", "summit", "forum"],
    "Social": ["party", "mixer", "happy hour", "social", "meetup", "meet-up", "hangout",
               "brunch", "game night", "night out", "halloween", "rave", r"\bdj\b",
               "picnic", "potluck", "karaoke", "trivia", "wine", "billiards"],
    "Arts & Music": [r"\bconcerts?\b", "music", r"\bart\b", r"\barts\b", r"\bexhibits?\b", r"\bexhibitions?\b", r"\bfilm",
                     "screening", "theater", "theatre", r"\bdance", r"\bdancing", "gallery", "poetry",
                     "comedy", "performance", "jazz", r"\borchestras?\b", "museum", "choir",
                     "symphony", r"\boperas?\b", r"(?<!self-)(?<!self )\bimprov\b"],  # "self-improv" is self-help
    "Sports & Wellness": [r"\brun\b", "running", "yoga", "fitness", r"\bhike", "sports",
                          "basketball", "soccer", "football", "climbing", "meditation",
                          "wellness", "archery", "volleyball", "tennis", "swim", "pilates",
                          "mental health", "game day"],
    "Community": ["culture", "cultural", "heritage", "community", "volunteer", "faith",
                  "worship", "diversity", "inclusion", "sisters?", "brothers?", "msa",
                  "advocacy", "activism", "mutual aid", "civic"],
    "Free food": ["free food", "pizza", "boba", r"\blunch\b", r"\bdinner\b", "snacks",
                  "refreshments", "food will be", "food provided", "catered", "tacos",
                  "breakfast", "free drinks", "food and drinks", "food & drinks", "donuts",
                  "coffee &", "bagels", "dumplings"],
}
_TOPIC_RES = {t: re.compile("|".join(p), re.IGNORECASE) for t, p in TOPICS.items()}


# Ordered: the card lists them in this order, after what the source itself says.
ACCESS: list[tuple[str, str]] = [
    ("RSVP required", r"\bplease rsvp|\brsvp (is )?required|\bmust rsvp|\brsvp (at|here|by|to|on|now|below)\b"),
    ("Registration required", (r"\bregistration (is )?(required|necessary)|\bmust register\b|\bpre-?regist"
                              r"|\bregister (at|here|by|now|online|in advance|ahead)\b"
                              r"|\bsign up (at|here|by|in advance|ahead)\b")),
    ("Open to everyone", r"\bopen to (the public|all|everyone)\b|\ball are welcome|\beveryone (is )?welcome"),
    ("No RSVP needed", (r"\bno (rsvp|registration|tickets?|sign-?up)s? (is |are )?(needed|required|necessary)"
                       r"|\bdrop[- ]in\b|\bjust show up\b|\bwalk-?ins? welcome")),
    ("Berkeley students only", (r"\b(cal|berkeley|ucb) students only\b"
                               r"|\bonly (open )?to (current )?(uc )?(cal|berkeley|ucb) students\b")),
    ("Members only", r"\bmembers[- ]only\b"),
    ("Invite only", r"\binvite[- ]only\b|\bby invitation\b"),
    ("21+", r"\b21\+|\b21 ?(and|&) ?(over|up)\b|\bmust be 21\b"),
    ("18+", r"\b18\+|\b18 ?(and|&) ?(over|up)\b|\bmust be 18\b"),
    ("Bring your Cal ID", r"\b(bring|show|present|with) (your |a )?(valid )?(cal|student|berkeley) id\b"),
    ("First come, first served", r"\bfirst[- ]come,? first[- ]serve"),
]
_ACCESS_RES = [(label, re.compile(rx, re.IGNORECASE)) for label, rx in ACCESS]
_SIGN_UP = re.compile(r"rsvp|regist|ticket|waitlist|sold out|request to join", re.IGNORECASE)


def access_for(e: Event) -> list[str]:
    text = f"{e.title} {e.description}"
    out = list(e.source_access)
    for label, rx in _ACCESS_RES:
        if label in out or not rx.search(text):
            continue
        # A platform that takes RSVPs knows better than wording that says to just show up.
        if label == "No RSVP needed" and any(_SIGN_UP.search(a) for a in out):
            continue
        out.append(label)
    return out


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


def far_region(lat: float, lng: float) -> str | None:
    """A big show beyond the Bay Area: each of these is a train ride from Berkeley."""
    if 38.3 < lat < 38.9 and lng > -121.8:  # east of the Delta, so never the North Bay
        return "Sacramento"
    if 33.5 < lat < 34.5 and lng > -119:
        return "Los Angeles"  # Anaheim and Inglewood included
    if 32.5 < lat < 33.3 and lng > -117.5:
        return "San Diego"
    return None


def region_for(e: Event) -> str | None:
    """None means "too far away to list". Only big-venue concerts are listed beyond the Bay
    Area; any other event that far away is not."""
    named_campus = campus.named(f"{e.venue or ''} {e.address or ''}", e.url or "")
    # A hybrid event in a campus room is still an event on campus.
    if e.online and not named_campus:
        return "Online"
    # Sacramento is just inside the 110 km below, and its city in no Bay Area list.
    if e.big_show and e.lat is not None and (far := far_region(e.lat, e.lng)):
        return far
    city = (e.city or "").strip().lower()
    if e.lat is not None and e.lng is not None:
        km = haversine_km(CAMPUS, (e.lat, e.lng))
        if km > 110:
            return None
        # A geocoder can put a building at its street address, just outside the line.
        if campus.inside(e.lat, e.lng) or (named_campus and km <= 2):
            return "Campus"
        if city == "berkeley" or km <= 4:
            return "Berkeley"
    elif named_campus:
        return "Campus"
    if city == "berkeley":
        return "Berkeley"
    if city in EAST_BAY:
        return "East Bay"
    if city in ("san francisco", "sf"):
        return "San Francisco"
    if city in PENINSULA:
        return "Peninsula & South Bay"
    if e.lat is not None and e.lng is not None:
        if e.lng < -122.36 and 37.70 < e.lat < 37.82:
            return "San Francisco"
        if e.lat > 37.95 and e.lng < -122.3:
            return "North Bay"
        if e.lat < 37.70:
            return "Peninsula & South Bay"
        return "East Bay"
    # Club calendars and campus lists rarely spell out a city; their events are local.
    # Platform listings with an unrecognized city ("Toronto", "Other") are not.
    return "Berkeley" if e.source in LOCAL_SOURCES else None


def topics_for(e: Event) -> list[str]:
    text = " ".join([e.title, e.description, " ".join(e.source_tags), e.host or ""])
    return [t for t, rx in _TOPIC_RES.items() if rx.search(text)]


def enrich(e: Event) -> Event | None:
    e.region = region_for(e)
    if e.region is None:
        return None
    e.source_tags, e.source_access = list(e.tags), list(e.access)
    e.tags = topics_for(e)
    e.access = access_for(e)
    if e.free is None and re.search(r"\bfree (admission|entry|event|to attend)\b|\bno cost\b",
                                    e.description, re.IGNORECASE):
        e.free = True
    return e
