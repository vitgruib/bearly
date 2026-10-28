"""One shared HTTP client that is polite by construction: requests to the same host are
spaced out, 429/5xx responses back off (honouring Retry-After), and feeds that support it
are fetched conditionally (ETag / Last-Modified) so an unchanged feed costs a 304."""

import hashlib
import json
import os
import re
import ssl
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import certifi
import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "http"
MIN_INTERVAL = 1.0  # seconds between requests to one host
FAST_HOSTS = {"api.lu.ma": 0.3, "events.berkeley.edu": 0.3}  # JSON APIs built for this
RETRY_STATUS = {429, 500, 502, 503, 504}

client = httpx.Client(
    headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
    timeout=25,
    follow_redirects=True,
    transport=httpx.HTTPTransport(retries=2),  # connection-level retries only
)



def _proxied_client() -> httpx.Client | None:
    """Some sites refuse cloud IPs (Eventbrite answers GitHub runners with 405). Sources that
    set `proxy = true` go through PROXY_URL, e.g. a Bright Data zone; without it, direct.
    Unblocking proxies re-sign TLS with their own CA, so PROXY_CA_CERT (PEM) is trusted too."""
    if not os.environ.get("PROXY_URL"):
        return None
    tls = ssl.create_default_context(cafile=certifi.where())
    if os.environ.get("PROXY_CA_CERT"):
        tls.load_verify_locations(cadata=os.environ["PROXY_CA_CERT"])
    return httpx.Client(headers=client.headers, timeout=60, follow_redirects=True,
                        proxy=os.environ["PROXY_URL"], verify=tls)


_proxied = _proxied_client()
_host_locks: dict[str, threading.Lock] = {}
_host_next: dict[str, float] = {}
_registry_lock = threading.Lock()
stats = {"requests": 0, "not_modified": 0, "retries": 0}


def _wait_turn(host: str) -> None:
    with _registry_lock:
        lock = _host_locks.setdefault(host, threading.Lock())
    with lock:
        delay = _host_next.get(host, 0) - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _host_next[host] = time.monotonic() + FAST_HOSTS.get(host, MIN_INTERVAL)


def request(method: str, url: str, proxy: bool = False, **kw) -> httpx.Response:
    host = urlparse(url).netloc
    via = _proxied if proxy and _proxied else client
    for attempt in range(4):
        _wait_turn(host)
        stats["requests"] += 1
        r = via.request(method, url, **kw)
        if r.status_code not in RETRY_STATUS or attempt == 3:
            return r
        stats["retries"] += 1
        retry_after = r.headers.get("retry-after", "")
        time.sleep(min(float(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1), 60))
    return r


def get_json(endpoint: str, **params) -> dict:
    r = request("GET", endpoint, params=params or None)
    r.raise_for_status()
    return r.json()


def get_text(endpoint: str, conditional: bool = False, proxy: bool = False, **params) -> str:
    """conditional=True keeps a validator + body on disk and revalidates with the server."""
    if not conditional:
        r = request("GET", endpoint, proxy=proxy, params=params or None)
        r.raise_for_status()
        return r.text
    key = hashlib.sha1(f"{endpoint}?{sorted(params.items())}".encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    cached = json.loads(path.read_text()) if path.exists() else None
    headers = {}
    if cached:
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = cached["last_modified"]
    r = request("GET", endpoint, proxy=proxy, params=params or None, headers=headers)
    if r.status_code == 304 and cached:
        stats["not_modified"] += 1
        return cached["body"]
    r.raise_for_status()
    if r.headers.get("etag") or r.headers.get("last-modified"):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"etag": r.headers.get("etag"),
                                    "last_modified": r.headers.get("last-modified"),
                                    "body": r.text}))
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
