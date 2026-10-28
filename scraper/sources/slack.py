"""Slack: read recent messages from channels in one or more workspaces.

Env: SLACK_TOKENS, comma-separated bot (xoxb-) or user (xoxp-) tokens with the
channels:history and channels:read scopes. Without an explicit channel list we read every
channel the token's bot is a member of, so adding the bot to a channel opts it in."""

import os
from datetime import UTC, datetime, timedelta

from ..http import request
from ..messages import events_from_message
from ..state import Context, NotConfigured

API = "https://slack.com/api"


def _call(token: str, method: str, **params) -> dict:
    r = request("GET", f"{API}/{method}", params=params,
                   headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"slack {method}: {data.get('error')}")
    return data


def fetch(cfg: dict, ctx: Context) -> list:
    tokens = [t.strip() for t in os.environ.get("SLACK_TOKENS", "").split(",") if t.strip()]
    if not tokens:
        raise NotConfigured("set SLACK_TOKENS")
    oldest = (datetime.now(UTC) - timedelta(days=cfg.get("days_back", 14))).timestamp()
    events = []
    for token in tokens:
        channels = cfg.get("channels") or [
            c["id"] for c in _call(token, "users.conversations", types="public_channel",
                                   limit=200)["channels"]]
        for channel in channels:
            history = _call(token, "conversations.history", channel=channel,
                            oldest=str(oldest), limit=200)
            for m in history.get("messages", []):
                if m.get("subtype") in ("channel_join", "channel_leave", "bot_add"):
                    continue
                # Slack wraps links as <url|label>; the URL regex stops at the "|".
                sent = datetime.fromtimestamp(float(m["ts"]), UTC)
                events += events_from_message(m.get("text", ""), sent, "slack")
    return events
