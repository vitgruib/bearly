"""Append a content hash to every local .css/.js reference in site/*.html before publishing.

A browser that has cached an old app.js would otherwise run it against new HTML (and blank
the page); with the hash in the URL, a changed file is a new URL and an unchanged one stays
cached."""

import hashlib
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
REF = re.compile(r'(href|src)="([\w./-]+\.(?:css|js))(?:\?v=[\w]*)?"')


def stamp(site: Path = SITE) -> None:
    for page in site.glob("*.html"):
        def versioned(m: re.Match) -> str:
            asset = site / m.group(2)
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:10]
            return f'{m.group(1)}="{m.group(2)}?v={digest}"'
        page.write_text(REF.sub(versioned, page.read_text()))


if __name__ == "__main__":
    stamp()
