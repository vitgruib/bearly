"""Single events added by students: links someone sent through the form or an "Add an event"
issue, approved by a maintainer and saved in contributed/events.toml (see contribute.py). Each
is fetched every run like a link in an email, so time and place changes show up."""

from .. import links
from ..state import Context


def fetch(cfg: dict, ctx: Context) -> list:
    events = []
    for saved in cfg.get("events", []):
        events += links.resolve(saved["url"], "reports")
    return events
