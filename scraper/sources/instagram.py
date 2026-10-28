"""Instagram: most clubs announce events only as an Instagram post. Read through Apify's
Instagram Post Scraper (pay-per-post), and parse captions with the free text parser.

Cost control, because this is the one paid source:
- accounts (sources.toml plus clubs/instagram.txt, ~850 clubs from CalLink) are read in
  slices of `accounts_per_run`, each slice once per full cycle, asking only for posts newer
  than one cycle (plus a day of overlap), so each post is paid for about once;
- spend is tracked per calendar month in state and the run is capped to what is left of
  `monthly_budget_usd` (Apify enforces the cap server-side via maxTotalChargeUsd);
- captions of the last `keep_days` are remembered, so events announced in an older post
  keep showing without refetching it.

Env: APIFY_TOKEN."""

import math
import os
import time
from datetime import timedelta

from ..http import request
from ..messages import events_from_message
from ..models import Event, parse_dt
from ..state import ROOT, Context, NotConfigured

ACTOR = "apify~instagram-post-scraper"
API = "https://api.apify.com/v2"


def _apify(method: str, path: str, token: str, **kw) -> dict:
    r = request(method, f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, **kw)
    r.raise_for_status()
    return r.json()


def _run_actor(token: str, payload: dict, max_usd: float, timeout_s: int = 900) -> tuple:
    run = _apify("POST", f"/acts/{ACTOR}/runs", token, json=payload,
                 params={"maxTotalChargeUsd": f"{max_usd:.2f}", "timeout": timeout_s})["data"]
    deadline = time.monotonic() + timeout_s + 60
    while run["status"] in ("READY", "RUNNING") and time.monotonic() < deadline:
        time.sleep(15)
        run = _apify("GET", f"/actor-runs/{run['id']}", token)["data"]
    if run["status"] not in ("SUCCEEDED", "TIMED-OUT", "ABORTED"):
        raise RuntimeError(f"apify run {run['id']} ended {run['status']}")
    items = _apify("GET", f"/datasets/{run['defaultDatasetId']}/items", token,
                   params={"clean": "true", "fields": "url,caption,displayUrl,ownerUsername,"
                           "ownerFullName,timestamp,error"})
    return items, float(run.get("usageTotalUsd") or 0)


def events_from_posts(posts: dict[str, dict]) -> list[Event]:
    events = []
    for p in posts.values():
        for e in events_from_message(p["caption"], parse_dt(p["timestamp"]), "instagram",
                                     host=p.get("owner"), url=p["url"]):
            e.image = e.image or p.get("image")
            events.append(e)
    return events


def load_accounts(cfg: dict) -> list[str]:
    accounts = list(cfg.get("accounts", []))
    if path := cfg.get("accounts_file"):
        for line in (ROOT / path).read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                accounts.append(line.strip())
    return list(dict.fromkeys(accounts))


def fetch(cfg: dict, ctx: Context) -> list[Event]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise NotConfigured("set APIFY_TOKEN")
    accounts = load_accounts(cfg)
    mem = ctx.memory
    posts: dict[str, dict] = mem.setdefault("posts", {})
    month = ctx.now.strftime("%Y-%m")
    budget = mem.setdefault("budget", {"month": month, "spent_usd": 0.0})
    if budget["month"] != month:
        budget.update(month=month, spent_usd=0.0)
    remaining = cfg.get("monthly_budget_usd", 5.0) - budget["spent_usd"]
    per_run = min(remaining, cfg.get("max_run_usd", 0.5))

    if accounts and per_run >= 0.02:
        size = min(cfg.get("accounts_per_run", 100), len(accounts))
        start = mem.get("cursor", 0) % len(accounts)
        batch = (accounts + accounts)[start:start + size]
        runs_per_cycle = math.ceil(len(accounts) / size)
        cycle = timedelta(hours=runs_per_cycle * cfg.get("every_hours", 24))
        items, cost = _run_actor(token, {
            "username": batch,
            "resultsLimit": cfg.get("posts_per_account", 4),
            "onlyPostsNewerThan": (ctx.now - cycle - timedelta(days=1)).date().isoformat(),
            "skipPinnedPosts": True,
            "dataDetailLevel": "basicData",
        }, per_run)
        budget["spent_usd"] = round(budget["spent_usd"] + cost, 4)
        mem["cursor"] = (start + size) % len(accounts)
        for it in items:
            if it.get("error") or not it.get("caption"):
                continue
            posts[it["url"]] = {"caption": it["caption"], "timestamp": it["timestamp"],
                                "url": it["url"], "image": it.get("displayUrl"),
                                "owner": it.get("ownerFullName") or it.get("ownerUsername")}
        if len(items) == 0:
            ctx.warn("instagram: run returned no posts")
    elif accounts:
        ctx.warn(f"instagram: monthly budget used (${budget['spent_usd']:.2f}); skipping fetch")

    cutoff = ctx.now - timedelta(days=cfg.get("keep_days", 45))
    for url in [u for u, p in posts.items() if parse_dt(p["timestamp"]) < cutoff]:
        del posts[url]
    return events_from_posts(posts)
