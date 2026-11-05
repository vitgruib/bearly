"""Is an event on the UC Berkeley campus? Decided by the campus's own boundary, or by a campus
building named in the venue when a listing gives no coordinates.

A distance from campus can't answer this: downtown Berkeley and Southside are as close to the
middle of campus as its own east edge is."""

import json
import re
from itertools import pairwise
from pathlib import Path

# OpenStreetMap's outline of the university: the main campus and hill lands plus the separate
# parcels (Clark Kerr, BAMPFA, Berkeley Way West, the Southside residence halls, ...).
RINGS: list[list[tuple[float, float]]] = [
    [tuple(p) for p in ring]
    for ring in json.loads((Path(__file__).with_name("campus.json")).read_text())["rings"]]

# Names no off-campus place in Berkeley shares, matched on their own.
_UNIQUE = (r"dwinelle|etcheverry|sutardja dai|pimentel|zellerbach|moffitt|eshleman|kroeber|"
           r"wurster|giannini|hildebrand|latimer|koshland|mulford|haviland|hilgard|banatao|"
           r"vlsb|valley life sciences|bampfa|berkeley art museum|pauley ballroom|"
           r"mlk(?: jr\.?)? student union|martin luther king(?: jr\.?)? student union|"
           r"sproul plaza|upper sproul|lower sproul|memorial glade|faculty glade|sather gate|"
           r"sather tower|campanile|berkeley way west|li ka shing|genetics (?:and|&) plant biology|"
           r"social sciences building|hearst (?:memorial )?mining|hearst gym(?:nasium)?|"
           r"hearst field annex|doe (?:memorial )?library|bancroft library|gardner stacks|"
           r"main stacks|haas school|haas pavilion|recreational sports facility|"
           r"memorial stadium|greek theat(?:re|er)|international house|clark kerr|"
           r"lawrence hall of science|uc botanical garden|botanical garden at berkeley|"
           r"bakar bioenginuity|blackwell hall|jacobs institute|tang center|"
           r"(?:cesar )?ch[aá]vez student center|free speech movement caf[eé]|fsm caf[eé]|"
           r"berkeley law|boalt|law building|wozniak lounge|hargrove music library|"
           r"physics (?:north|south)|calvin lab|donner lab|weill hall|stanley hall|"
           r"energy biosciences building|university hall|california hall|north gate hall|"
           r"anthony hall|alumni house|faculty club|bowles hall|stern hall|south hall|"
           r"hertz concert hall|grimes engineering|jarvis auditorium|bakar gateway|"
           r"wu performance hall|maude fife|booth auditorium|goldberg room|heyman terrace|"
           r"morrison (?:&|and) foerster room|mario savio steps|savio steps|faculty grove|"
           r"spieker (?:aquatics|forum)|witter (?:rugby )?field|edwards stadium|evans diamond|"
           r"open computing facility|graduate assembly|ga (?:conference )?room|"
           r"inclusive excellence hub|magnes collection|gender equity resource center|"
           r"undergraduate academic building|anthropology (?:and|&) art practice|"
           r"anthropology reading room|berkeley school of education|2121 berkeley way|"
           r"other campus location|uc berkeley campus|mlk (?:first|second|third) floor|ocf|"
           r"warren room|goldberg memorial|centennial lobby|sproul tabling")
# Surnames streets and shops share ("Evans St", "Hearst Ave", "Wheeler Ave"), so these only
# count with a building word or a room number after them: "Evans Hall", "Wheeler 124".
_SHARED = (r"soda|cory|wheeler|evans|tolman|barrows|lewis|campbell|morrison|hertz|chou|cheit|"
           r"birge|le ?conte|mccone|hesse|davis|bechtel|mclaughlin|o'brien|jacobs|gilman|minor|"
           r"warren|wellman|morgan|moses|stephens|durant|philosophy|tan|simon|blum|sproul|hearst|"
           r"kerr|lipman|stanley|physics|gateway|hfa|ssb|ga")
_STREET = r"(?!\s+(?:st|street|ave|avenue|way|blvd|rd|road|dr|drive)\b)"
CAMPUS_BUILDING = re.compile(
    rf"\b(?:{_UNIQUE})\b"
    rf"|\b(?:{_SHARED})(?:\s+(?:hall|library|gym|auditorium|annex|lab|building|courtyard)\b"
    rf"|[\s-]+[a-z]?\d{{1,4}}[a-z]?\b{_STREET})"
    # "120 Latimer", "55A McCone": a street number has four digits, a room at most three.
    rf"|\b\d{{1,3}}[a-z]?\s+(?:{_SHARED})\b{_STREET}",
    re.IGNORECASE)
# Haas rooms on the campus calendar come bare: C for Cheit, N for Chou, F for the faculty wing.
JUST_UC = re.compile(r"(?:uc berkeley|on campus)(?:\s+uc berkeley)?", re.IGNORECASE)
HAAS_ROOM = re.compile(r"^(?:room\s+)?[cfns]\d{3}\b", re.IGNORECASE)
CAMPUS_ZIP = re.compile(r"\b94720\b")


def inside(lat: float, lng: float) -> bool:
    return any(_in_ring(lat, lng, ring) for ring in RINGS)


def _in_ring(lat: float, lng: float, ring: list[tuple[float, float]]) -> bool:
    hit = False
    for (y1, x1), (y2, x2) in pairwise(ring):
        if (y1 > lat) != (y2 > lat) and lng < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def named(text: str, url: str = "") -> bool:
    """The venue names a campus building or carries UC Berkeley's own ZIP code."""
    return bool(CAMPUS_ZIP.search(text) or CAMPUS_BUILDING.search(text)
                or JUST_UC.fullmatch(text.strip())
                or ("events.berkeley.edu/" in url and HAAS_ROOM.match(text.strip())))
