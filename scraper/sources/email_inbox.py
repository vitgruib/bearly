"""Mailing lists: subscribe one inbox (e.g. a Gmail account with an "events" label that a
filter applies to every listserv) and read it over IMAP.

Env: IMAP_USER, IMAP_PASSWORD (a Gmail app password), optional IMAP_HOST."""

import email
import html
import imaplib
import os
import re
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from ..messages import events_from_message
from ..models import clean_text


def message_text(msg: email.message.Message) -> str:
    plain, rich = [], []
    for part in msg.walk():
        if part.get_content_maintype() != "text" or part.get_filename():
            continue
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        (plain if part.get_content_subtype() == "plain" else rich).append(text)
    if plain:
        return "\n".join(plain)
    # Keep hrefs: listserv HTML often hides the RSVP link behind "click here".
    joined = "\n".join(rich)
    hrefs = " ".join(html.unescape(h) for h in re.findall(r'href="([^"]+)"', joined))
    return clean_text(joined, 50000) + "\n" + hrefs


def fetch(cfg: dict) -> list:
    user, password = os.environ.get("IMAP_USER"), os.environ.get("IMAP_PASSWORD")
    if not (user and password):
        raise RuntimeError("not configured: set IMAP_USER and IMAP_PASSWORD")
    since = (datetime.now(UTC) - timedelta(days=cfg.get("days_back", 14))).strftime("%d-%b-%Y")
    events = []
    with imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST", "imap.gmail.com")) as imap:
        imap.login(user, password)
        imap.select(f'"{cfg.get("folder", "INBOX")}"', readonly=True)
        _, ids = imap.search(None, "SINCE", since)
        for num in ids[0].split():
            _, data = imap.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            sent = parsedate_to_datetime(msg["Date"]) if msg["Date"] else datetime.now(UTC)
            events += events_from_message(f"Subject: {subject}\n\n{message_text(msg)}",
                                          sent, "email")
    return events
