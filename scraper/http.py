import json
import re

import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

client = httpx.Client(
    headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
    timeout=25,
    follow_redirects=True,
    transport=httpx.HTTPTransport(retries=2),
)


def get_json(endpoint: str, **params) -> dict:
    r = client.get(endpoint, params=params or None)
    r.raise_for_status()
    return r.json()


def get_text(endpoint: str, **params) -> str:
    r = client.get(endpoint, params=params or None)
    r.raise_for_status()
    return r.text


_LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
_NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def json_ld(html: str) -> list:
    out = []
    for m in _LD_RE.finditer(html):
        try:
            out.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    return out


def next_data(html: str) -> dict | None:
    m = _NEXT_RE.search(html)
    return json.loads(m.group(1)) if m else None
