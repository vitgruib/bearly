# Features that need a server

The 2026-11 redesign mockups include features the static site on GitHub Pages can't support,
because they need to store data for each person. They are left off the site until Lo-Cal has a
backend (see the "Backend server" section of issue #4). This file is not linked from the site.

## Accounts and sign-in

- The header in the mockup shows a signed-in person (avatar, name, menu).
- Sign in with Google (Berkeley accounts first). Everything below hangs off an account.
- Until then, saves and preferences live in the visitor's browser (`localStorage`). They don't
  move between devices, and clearing site data loses them.

## Saved events that sync to a calendar subscription

- The mockup's "Your plans, in your calendar: subscribe to your saved events once, new saves stay
  in sync."
- Needs a private feed URL per person, for example `/u/<random-token>/saved.ics`, served from the
  saves stored on the server, so a calendar app subscribes once and each new save shows up on its
  next poll.
- Today the site offers a one-time `.ics` download of the saved events, plus self-updating feeds
  built from filters, which work without a server because every filter combination is
  pre-generated (`site/data/cal/f/`).
- The privacy note from the mockup applies: the feed link is private, so share it only with
  people you trust.

## "Connect Google Calendar" for saved events

- One button that adds the saved-events feed to Google Calendar. This works as soon as the
  per-person feed above exists (`calendar.google.com/calendar/render?cid=webcal://...`), with no
  Google API access needed.
- Pushing events straight into a calendar instead (Google Calendar API, OAuth consent) is
  heavier and only worth it if subscriptions turn out to be too slow to refresh (Google polls
  every several hours).

## Friends

- "Better with friends": a friend list, "Maya & Leo are going" on event cards, "Maya, Leo & Noor
  are going to events today" in the sidebar, and "View your 8 friends".
- Needs accounts, friend requests or invite links, a per-event "going" flag, and privacy
  controls (who can see what you're going to; default to friends only).

## Preferences that follow you

- The sidebar's "Your preferences" box (for example "Arts, live music & community") works now in
  the browser. With accounts it would sync across devices and could feed better ranking (what you
  saved or went to before).

## Rough shape of the backend

- Small and cheap: Cloudflare Workers + D1 (SQLite), or Supabase. Both have free tiers that fit.
- Tables: users, saves (user, event id), friendships, going (user, event id), preferences.
- Endpoints: sign-in callback, save/unsave, the per-user `.ics` feed, friends, going.
- Event ids already survive renames through the build's link memory (`scraper/reports.py`), so
  saves can key on them.
