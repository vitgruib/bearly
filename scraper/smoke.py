"""Load the built site in a real browser and refuse to publish it if it is broken.

Run after scraping and before deploying: a non-zero exit skips the deploy, so the last good
site stays up. Checks both pages at desktop and phone width for uncaught errors, that events
and every filter row render, that filters respond, that nothing scrolls sideways, and that
the event count hasn't collapsed against the previously published data.

    python -m scraper.smoke [previous-events.json]
"""

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import Page, sync_playwright

SITE = Path(__file__).resolve().parent.parent / "site"
MIN_KEEP = 0.5  # a run that loses more than half the events is a scraper failure, not news
VIEWPORTS = {"desktop": (1280, 900), "phone": (390, 844)}


def serve() -> str:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=SITE)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}"


def open_page(page: Page, url: str, errors: list[str]) -> None:
    origin = url.split("/", 3)[:3]
    page.on("pageerror", lambda e: errors.append(f"{url}: uncaught {e}"))
    # Only our own errors count: a club's expired Instagram image is not a broken page.
    page.on("console", lambda m: m.type == "error" and m.location.get("url", "").split("/", 3)[:3] == origin
            and errors.append(f"{url}: console {m.text}"))
    page.goto(url, wait_until="networkidle")


def no_sideways_scroll(page: Page, where: str, errors: list[str]) -> None:
    if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
        errors.append(f"{where}: page scrolls sideways")


def count(page: Page) -> str:
    return page.locator("#count").inner_text().replace(",", "")


def events(n: int) -> str:
    return f"{n} event{'' if n == 1 else 's'}"


def show_filters(page: Page) -> None:
    """On a phone the filters are a drawer behind the Filters button."""
    if page.locator("#open-filters").is_visible() and not page.locator("#sidebar.open").count():
        page.locator("#open-filters").click()
        page.wait_for_selector("#sidebar.open #when", state="visible")


def pick(page: Page, menu: str, label: str):
    """Open a sidebar dropdown and return the row with this label."""
    show_filters(page)
    if not page.locator(f"#{menu}[open]").count():
        page.locator(f"#{menu} > summary").click()
    return page.locator(f"#{menu} .check", has_text=label)


def reset(page: Page) -> None:
    """Reset clears every filter, When included; the checks run on All."""
    page.locator("#reset").click()
    page.locator("#when button", has_text="All").click()


def check_events(page: Page, base: str, size: str, errors: list[str]) -> None:
    where = f"index ({size})"
    open_page(page, f"{base}/#when=all", errors)
    page.wait_for_selector(".card >> visible=true", timeout=10_000)
    labels = page.locator("#when button").all_inner_texts()
    if [x.strip() for x in labels[:5]] != ["Today", "Tomorrow", "This weekend", "This week", "All"]:
        errors.append(f"{where}: When choices are {labels}")
    if page.locator("#sources").count():
        errors.append(f"{where}: the source filter is back")
    if not page.locator(".card .flag:not([hidden])").count():
        errors.append(f"{where}: events have no Report link")
    before = count(page)

    talks = pick(page, "dd-type", "Talks")
    n = int(talks.locator(".n").inner_text())
    talks.locator("input").check()
    if count(page) != events(n):
        errors.append(f"{where}: picking an event type shows {count(page)}, its menu said {n}")
    if not page.locator("#pills .qchip", has_text="Talks").count():
        errors.append(f"{where}: a picked event type shows no pill")
    reset(page)
    if count(page) != before:
        errors.append(f"{where}: Reset did not restore the list")

    # Free food narrows whatever type is picked: a row's count is what checking it shows.
    page.locator("#food").check()
    talks = pick(page, "dd-type", "Talks")
    n = int(talks.locator(".n").inner_text())
    talks.locator("input").check()
    if count(page) != events(n):
        errors.append(f"{where}: Free food plus an event type did not show only events that are both")
    reset(page)

    page.locator("#campus").check()
    if count(page) in (before, events(0)) or page.locator("#loc-label").inner_text() != "On campus":
        errors.append(f"{where}: On campus only did not narrow to campus events")
    page.locator("#campus").uncheck()
    if count(page) != before:
        errors.append(f"{where}: turning On campus off did not restore the list")
    if page.locator("#side-close").is_visible():
        page.locator("#side-close").click()

    # Saving puts the event in the Saved view and in the bundled calendar file.
    page.locator(".card .save >> visible=true").first.click()
    if page.locator("#saved-n").inner_text() != "1":
        errors.append(f"{where}: saving an event did not count it in the header")
    page.locator("#mycal").click()
    if not page.locator("#cal-dlg[open]").count() or not page.locator("#saved-sum").inner_text().startswith("1 event"):
        errors.append(f"{where}: My calendar does not offer the saved event")
    page.keyboard.press("Escape")
    page.locator("#saved-link").click()
    page.wait_for_function("document.querySelector('#count').textContent === '1 event'", timeout=5_000)

    page.goto(f"{base}/#when=all", wait_until="networkidle")
    show_filters(page)
    page.locator("#when .custom").click()
    if not page.locator("#dates-dlg[open] #cal-grid button").count():
        errors.append(f"{where}: Custom dates does not open a calendar")
    page.keyboard.press("Escape")
    no_sideways_scroll(page, where, errors)


def check_about(page: Page, base: str, size: str, errors: list[str]) -> None:
    open_page(page, f"{base}/about.html", errors)
    page.wait_for_selector(".source .live", timeout=10_000)
    no_sideways_scroll(page, f"about ({size})", errors)


def check_stats(page: Page, base: str, size: str, errors: list[str]) -> None:
    open_page(page, f"{base}/stats.html", errors)
    page.wait_for_selector("#by-source .bar", timeout=10_000)
    no_sideways_scroll(page, f"stats ({size})", errors)


def check_data(previous: Path | None, errors: list[str]) -> int:
    events = json.loads((SITE / "data" / "events.json").read_text())["events"]
    if not events:
        errors.append("events.json has no events")
    if previous and previous.exists():
        before = len(json.loads(previous.read_text())["events"])
        if before and len(events) < before * MIN_KEEP:
            errors.append(f"event count fell from {before} to {len(events)}")
    return len(events)


def main(previous: Path | None) -> int:
    errors: list[str] = []
    count = check_data(previous, errors)
    base = serve()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for size, (w, h) in VIEWPORTS.items():
            for check in (check_events, check_about, check_stats):
                page = browser.new_page(viewport={"width": w, "height": h})
                try:
                    check(page, base, size, errors)
                except BrowserError as e:  # a timeout or missing element fails the check
                    errors.append(f"{check.__name__} ({size}): {e}")
                page.close()
        browser.close()
    for e in errors:
        print(f"SMOKE FAIL: {e}")
    if not errors:
        print(f"smoke ok: {count} events, all pages, desktop and phone")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
