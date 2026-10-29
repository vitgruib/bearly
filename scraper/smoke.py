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


def check_events(page: Page, base: str, size: str, errors: list[str]) -> None:
    open_page(page, f"{base}/#when=all", errors)
    page.wait_for_selector(".card", timeout=10_000)
    for row in ("#when button", "#topics-0 .chip", "#topics-1 .chip", "#regions .chip", "#sources .chip"):
        if not page.locator(row).count():
            errors.append(f"index ({size}): no filters in {row.split()[0]}")
    if not page.locator(".card .flag:not([hidden])").count():
        errors.append(f"index ({size}): events have no Report link")
    before = page.locator("#count").inner_text()
    page.locator("#topics-0 .chip").first.click()
    if page.locator("#count").inner_text() == before:
        errors.append(f"index ({size}): clicking a topic did not change the list")
    page.locator("#clear").click()
    if page.locator("#count").inner_text() != before:
        errors.append(f"index ({size}): Clear filters did not restore the list")
    no_sideways_scroll(page, f"index ({size})", errors)


def check_about(page: Page, base: str, size: str, errors: list[str]) -> None:
    open_page(page, f"{base}/about.html", errors)
    page.wait_for_selector(".source .live", timeout=10_000)
    no_sideways_scroll(page, f"about ({size})", errors)


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
            for check in (check_events, check_about):
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
        print(f"smoke ok: {count} events, both pages, desktop and phone")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
