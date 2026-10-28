"""Derive region and topic tags so the frontend can filter without knowing sources."""

import math
import re

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
    "daly city", "san bruno", "half moon bay",
}

LOCAL_SOURCES = {"email", "slack", "ics", "berkeley_calendar"}

REGIONS = ["Campus", "Berkeley", "East Bay", "San Francisco", "Peninsula & South Bay",
           "North Bay", "Online"]

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
    "Arts & Music": ["concert", "music", r"\bart\b", r"\barts\b", "exhibit", r"\bfilm",
                     "screening", "theater", "theatre", "dance", "gallery", "poetry",
                     "comedy", "performance", "jazz", "orchestra", "museum", "choir",
                     "symphony", "opera", "improv"],
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


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


def region_for(e: Event) -> str | None:
    """None means "too far away to list"."""
    if e.online:
        return "Online"
    city = (e.city or "").strip().lower()
    if e.lat is not None and e.lng is not None:
        km = haversine_km(CAMPUS, (e.lat, e.lng))
        if km <= 1.3:
            return "Campus"
        if km > 110:
            return None
        if city == "berkeley" or km <= 4:
            return "Berkeley"
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
    text = " ".join([e.title, e.description, " ".join(e.tags), e.host or ""])
    return [t for t, rx in _TOPIC_RES.items() if rx.search(text)]


def enrich(e: Event) -> Event | None:
    e.region = region_for(e)
    if e.region is None:
        return None
    e.tags = topics_for(e)
    if e.free is None and re.search(r"\bfree (admission|entry|event|to attend)\b|\bno cost\b",
                                    e.description, re.IGNORECASE):
        e.free = True
    return e
