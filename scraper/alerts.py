"""Turn source health into GitHub issues so a silently broken scraper gets noticed.

    uv run python -m scraper.alerts     # in CI, with GH_TOKEN and GITHUB_REPOSITORY set

A source that is down (3+ failed runs in a row) or degraded (far fewer events than usual)
gets one open issue labelled `source-health`; the issue closes itself once the source
recovers."""

import json
import subprocess

from .registry import SOURCES
from .state import State

LABEL = "source-health"


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def title(name: str) -> str:
    return f"Source unhealthy: {SOURCES[name].label}"


def main() -> None:
    state = State()
    gh("label", "create", LABEL, "--color", "d93f0b", "--force",
       "--description", "Opened automatically when a scraper source breaks")
    open_issues = {i["title"]: i["number"] for i in json.loads(gh(
        "issue", "list", "--label", LABEL, "--state", "open", "--json", "number,title"))}
    for name in SOURCES:
        s = state.data["sources"].get(name, {})
        health = s.get("health", "ok")
        existing = open_issues.get(title(name))
        if health in ("down", "degraded") and not existing:
            body = (f"`{name}` is **{health}**.\n\n"
                    f"- last successful run: {s.get('last_ok') or 'never'}\n"
                    f"- consecutive failures: {s.get('failures', 0)}\n"
                    f"- recent event counts: {s.get('counts', [])}\n"
                    f"- error: `{s.get('error')}`\n- warnings: {s.get('warnings', [])}\n\n"
                    "The site keeps serving this source's last good events meanwhile. "
                    "Reproduce locally with `uv run python -m scraper.run " + name + "`.")
            gh("issue", "create", "--title", title(name), "--label", LABEL, "--body", body)
        elif health in ("ok", "off") and existing:
            gh("issue", "close", str(existing), "--comment", "Recovered on the latest run.")


if __name__ == "__main__":
    main()
