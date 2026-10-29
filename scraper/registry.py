"""Every source the scraper knows. `every_hours` is the default schedule; sources.toml can
override it per source. Slow-changing or rate-limited sources run less often, which is what
keeps the whole thing inside free tiers and polite to the sites."""

from dataclasses import dataclass
from types import ModuleType

from .sources import (
    berkeley_calendar,
    cerebral_valley,
    email_inbox,
    feeds,
    hackathons,
    instagram,
    luma,
    partiful,
    reports,
    slack,
    venues,
)


@dataclass(frozen=True)
class Source:
    label: str
    module: ModuleType
    every_hours: float


SOURCES = {
    "luma": Source("Luma", luma, 3),
    "cerebral_valley": Source("Cerebral Valley", cerebral_valley, 6),
    "partiful": Source("Partiful", partiful, 6),
    "berkeley_calendar": Source("UC Berkeley Events", berkeley_calendar, 6),
    "feeds": Source("Club & department calendars", feeds, 6),
    "email": Source("Mailing lists", email_inbox, 3),
    "slack": Source("Slack", slack, 3),
    "hackathons": Source("Hackathons", hackathons, 24),
    "venues": Source("Music & venues", venues, 12),
    "instagram": Source("Instagram", instagram, 24),
    "reports": Source("Added by students", reports, 3),
}
