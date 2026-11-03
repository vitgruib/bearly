# Existing tools for UC Berkeley and East Bay event discovery (as of 2026-11-03)

Research date: 2026-11-03. About 17 tool calls (web search, page fetches, and direct reads of public JSON endpoints). Search coverage of Reddit, Hacker News and Product Hunt was weak: Reddit results came back only as third-party snapshot mirrors, and no Show HN or Product Hunt launch for a Berkeley aggregator turned up. Treat "not found" below as "not found by this search", not as "does not exist".

## Official channels: what they cover and what they miss

### Takeaway
Campus has an official calendar for departments (events.berkeley.edu) and a separate official system for registered student orgs (CalLink, on Campus Labs/Anthology Engage). Neither is built to include Instagram-only clubs, Luma or Partiful events, or off-campus parties. Haas clubs use a third system, CampusGroups. No official channel joins all of these together.

### Cited Findings
- **events.berkeley.edu ("Berkeley Events")** is "the official calendar system for promoting events that are hosted across campus, including lectures, conferences, performing arts, community activities." Units manage their own calendar groups. A "Campuswide" calendar combines all unit calendars, and Strategic Communications curates a "Featured Events" calendar. Units without their own calendar can submit events for approval. Login is through CalNet SSO. The page does not mention student organizations. — [Strategic Communications: Berkeley Events](https://strategiccommunications.berkeley.edu/resources/berkeley-events/); [Public Affairs: Berkeley Events](https://publicaffairs.berkeley.edu/berkeley-events)
- events.berkeley.edu runs on **LiveWhale**. A third-party scraper (CalEvents) pulled **2,791 raw / 1,448 deduped upcoming events** from its "livewhale" source on 2026-11-02, by far its biggest source. — [cal-events.com/status.json](https://cal-events.com/status.json), [cal-events.com/events.json](https://cal-events.com/events.json) (read directly 2026-11-03)
- **CalLink** is "the online central hub for Registered Student Organizations (RSOs)". Students follow orgs and find events on the CalLink calendar, and orgs are sorted into 38 categories with a filterable Events tab. Reported RSO counts disagree: "1,000+", "1,200+", "1,300+" and "over 1,500" all appear on official pages. The fall 2026 Calapalooza page says ">1,200 registered student organizations". — [LEAD Center: get involved](https://lead.berkeley.edu/get-involved); [Berkeley Life: Finding Community in Clubs](https://life.berkeley.edu/finding-community-in-clubs/); [Calapalooza](https://lead.berkeley.edu/about/calapalooza/)
- CalLink's discovery API (`/api/discovery/event/search`, `/api/discovery/search/organizations`) redirected an unauthenticated request to the "CampusLabs Identity System" login page on 2026-11-03. Programmatic access appears to require CalNet login. — direct curl of callink.berkeley.edu, 2026-11-03 (primary observation; the redirect could also be bot-blocking rather than a deliberate auth wall)
- Starting a new org goes through OASIS registration, which is separate from CalLink. Clubs that are not registered RSOs, such as informal or Instagram-only groups, therefore do not appear on CalLink by construction. — [LEAD Center](https://lead.berkeley.edu/get-involved)
- **Berkeley Haas CampusGroups** (haas.campusgroups.com) is where Haas students "explore all of the student clubs and organizations at Haas". Club pages there offer group calendars, and the system appears to need a Haas or Berkeley login. — [Haas EWMBA student groups](https://haas.berkeley.edu/ewmba/student-experience/student-groups-clubs/); [Haas Sports Business Club on CampusGroups](https://haas.campusgroups.com/sportsbusi)
- Other official, narrower channels:
  - Student Union programs page (free MLK and Headlands events only) — [Student Union programs](https://studentunion.berkeley.edu/programs/)
  - Berkeley Life Instagram (@ucberkeleylife, about 42K followers) and the monthly "Berkeley Life Roundup" email from Student Affairs — [Berkeley Life: How to Stay in Touch](https://life.berkeley.edu/how-to-stay-in-touch/); [@ucberkeleylife](https://www.instagram.com/ucberkeleylife/)
  - An official UC Berkeley Discord promoted as a place to "discover student organization events" — [Berkeley Life: Connect](https://life.berkeley.edu/connect/)
  - A university "Cal Event Guides" iOS app whose App Store listing dates to 2019 — [App Store](https://apps.apple.com/us/app/uc-berkeley-cal-event-guides/id1004743884)
- Off campus, **Berkeleyside** runs an events calendar (powered by Events.com) and a Thursday "The Scene" roundup newsletter, which covered Halloween events as recently as 2026-10-29. — [Berkeleyside events](https://www.berkeleyside.org/events); [Berkeleyside 2026-10-29](https://www.berkeleyside.org/2026/10/29/around-berkeley-halloween-and-dia-de-los-muertos-events-and-celebrations); [Berkeleyside 2026-08-25](https://www.berkeleyside.org/2026/08/25/things-to-do-berkeley)

### Inferences
- The campus record is split three ways: departments on LiveWhale, RSOs on CalLink, Haas on CampusGroups. None of the three takes in Luma, Partiful, Instagram posts, listservs or Slack. That is the specific gap Lo-Cal's scrapers fill.
- CalLink's login wall (if it is one) makes it harder for third parties to aggregate RSO events than LiveWhale events. This likely explains why the CalEvents aggregator below has no CalLink source.

### Gaps
- I did not find whether the **ASUC** runs its own event calendar separate from CalLink. I also did not find whether the **Daily Californian** runs an event listing; searches of dailycal.org returned no events calendar or app.
- I did not find what share of RSOs actually post events on CalLink, as opposed to only on Instagram.
- I did not determine whether events.berkeley.edu exposes ICS/RSS feeds, though LiveWhale normally does and CalEvents scrapes it successfully.
- I did not survey department newsletters (EECS, etc.).

## Student-built Berkeley event aggregators, past and present

### Takeaway
At least three or four student-built Berkeley event and club discovery sites are live as of late 2026: CalEvents (cal-events.com), Berkeley Events (calevents.app), Berkeley Goggles, and Eventreels. Only CalEvents could be verified as actively refreshing, and it is almost entirely official calendars plus a little Luma. None verifiably scrapes Instagram, Partiful, listservs or Slack at Lo-Cal's breadth. I found no dated "dead project" post-mortems.

### Cited Findings
- **CalEvents (cal-events.com).** Aggregates "upcoming events from campus calendars and public source feeds," refreshed every morning. Sources: LiveWhale (events.berkeley.edu), BAMPFA, Cal Bears athletics, Cal Performances, Haas, Berkeley Law, Simons Institute, Luma, BEGIN, AI risk, BRSL, CLTC.
  - Snapshot generated 2026-11-02T21:34Z: **1,840 upcoming events** after removing 599 duplicates. By source: LiveWhale 1,448, BAMPFA 133, Cal Bears 131, Berkeley Law 39, Cal Performances 25, Simons 21, Haas 20, **Luma 12**, BEGIN 9.
  - Exposes `events.json`, `status.json` and an `llms-full.txt` for agents.
  - Owner and launch date not stated. No Instagram, CalLink, Partiful or party sources.
  - [cal-events.com](https://cal-events.com/); [status.json](https://cal-events.com/status.json); [llms-full.txt](https://cal-events.com/llms-full.txt) (read 2026-11-03)
- **Berkeley Events (calevents.app).** "A Sunny Jayaram production." Claims to stream in "and parse information from all of Berkeley's clubs" into one feed with one-click add-to-calendar, and claims "1000+ Clubs". Data sources are not named. The page rendered only "Loading" placeholders when fetched, so how current its listings are could not be verified. HTTP 200 on 2026-11-03. — [calevents.app](https://www.calevents.app/); [Sunny Jayaram](https://www.sunny-jay.com/)
- **Berkeley Goggles (berkeleygoggles.org).** "Berkeley's Largest Club Discovery Platform", an ASUC Office of the CTO project credited to Prakriti Saxena and Navya Gupta.
  - Has 1,300+ AI-summarized club profiles "from publicly available sources", an AI chat ("Bart"), and a "Berkeley Events" section that showed only "Loading events…".
  - Its pitch notes club discovery is "largely word of mouth" with information scattered across websites and social pages.
  - Mainly a club directory, not an event feed.
  - [berkeleygoggles.org](https://berkeleygoggles.org/)
- **Eventreels (eventreels.com/ucberkley).** A "verified campus event platform" that requires a berkeley.edu email.
  - Focuses on Greek life (frat parties, formals, rush), ASUC and cultural-org socials, Big Game tailgates and South Side nightlife, with RSVPs, tickets and photos.
  - Claims "thousands of verified students" overall; no Berkeley figure. Multi-campus ("Find your campus").
  - It is a posting platform (hosts must list events there), not a scraper. Owner and dates not stated.
  - [Eventreels UC Berkeley](https://eventreels.com/ucberkley)
- **Berkeley Clubs (berkeleyclubs.com)** is a club finder "made 100% by students". It is a directory, not an event feed. — [berkeleyclubs.com](https://berkeleyclubs.com/)
- **Free food:**
  - **berkeley-free-food-finder** (GitHub, Shri2007) is a user-posted free-food web app. The README calls it an early skeleton with no validation or rate limiting. Repo created 2026-09-21, last push 2026-10-09, 0 stars. — [GitHub](https://github.com/Shri2007/berkeley-free-food-finder); GitHub API read 2026-11-03
  - No Berkeley free-food bot or Instagram account was found. Comparable services exist elsewhere: BYU "Lunchbox" (2017) and UW–Madison "Free Food Alert". — [BYU Universe 2017](https://universe.byu.edu/2017/03/17/app-advertising-free-food-reaches-out-to-struggling-students/); [UW–Madison](https://sustainability.wisc.edu/fight-food-waste-with-free-food-alert/)
- **Older GitHub efforts:** "Berkeley-Event-Scraping" by AkshatJain1 collected Facebook events from Berkeley clubs. It is undated, and Facebook Events has since lost relevance among students. — [github.com/AkshatJain1](https://www.Github.com/AkshatJain1)
- **Instagram roundups:** No dedicated weekly "this week at Berkeley" Instagram roundup was found. Individual orgs post their own weekly schedules (e.g. @calpirg_ucb). — [CALPIRG UC Berkeley](https://calpirgstudents.org/chapters/uc-berkeley/)

### Inferences
- Several near-competitors are live at the same time, which suggests real demand and also a crowded, low-barrier space. Each covers one slice:
  - CalEvents: official calendars
  - Goggles and Berkeley Clubs: club directories
  - Eventreels: parties, but hosts must post there
  - calevents.app: club feed, method unknown
- Lo-Cal's distinctive coverage is the combination of Instagram (about 850 accounts), Partiful, Luma at scale, hackathons, listservs and Slack. CalEvents gets only 12 Luma events, which suggests it is not crawling Berkeley Luma calendars broadly.
- The name collision matters: "CalEvents" (cal-events.com) and "Berkeley Events" (calevents.app) are two different products with near-identical names.
- Likely reasons student aggregators die are the same everywhere: the maintainer graduates, scrapers break (the Facebook Events scraper is an example), and there is no distribution. I found no Berkeley-specific post-mortem to confirm this. Treat it as inference.

### Gaps
- Owners, launch dates and traction (users, traffic) for CalEvents, calevents.app, Berkeley Goggles and Eventreels are not public in what I found.
- Whether calevents.app actually scrapes Instagram or only CalLink is unknown, because the page is client-rendered.
- r/berkeley threads asking "where do I find events" could not be retrieved; search returned only mirror snapshots.
- No Daily Cal coverage of any student event aggregator was found.
- GroupMe, Discord and Slack event channels beyond the official Discord were not enumerated.

## Bay Area tech-event aggregators students use

### Takeaway
For tech, AI and hackathon events, students rely on Luma (hosts and discovery), Partiful (social and party invites), Cerebral Valley (AI event digest and Slack), a16z Tech Week, Eventbrite and Meetup. All are SF- or Bay-wide and none is Berkeley-student-specific. Berkeley clubs themselves host heavily on Luma.

### Cited Findings
- **Luma is the default host platform for Berkeley tech and AI events.** Examples:
  - "Build Smth AI-Native Hackathon @Cal" (HKN + Butterai)
  - "Ara X UCBerkeley" hackathon ($10K prizes)
  - OpenAI Codex Hackathon — Berkeley (Haas AI Club)
  - BASIS US AI Policy Hackathon
  - UC Berkeley AI Hackathon 2024 awards at Zellerbach

  [luma.com/7i8crpqz](https://luma.com/7i8crpqz); [luma.com/aranucberkeley](https://luma.com/aranucberkeley); [luma.com/laqw076z](https://luma.com/laqw076z); [luma.com/tnzft5wg](https://luma.com/tnzft5wg); [luma.com/ucbaihackathon2024](https://luma.com/ucbaihackathon2024)
- **Cerebral Valley** publishes a weekly "Week Of" SF AI events digest on Beehiiv (posts found mostly from 2023–2024), plus an events spreadsheet, an event submission form and a Slack community. No 2026 page was confirmed in search. — [Cerebral Valley Beehiiv](https://cerebralvalley.beehiiv.com/p/cerebral-valley-week-june-19th); [CV events sheet](https://docs.google.com/spreadsheets/d/1P6ut7vL-gXKbeDeh3nuPqBjoCupjIt87Sw7TnhumBSU/edit)
- **a16z Tech Week** runs a curated calendar of hundreds of independently hosted events over one week per city. It is a periodic burst, not a continuous feed. — (tool description of the official Tech Week MCP connector available in this session; not independently web-sourced)
- **Eventbrite** has a "UC Berkeley" discovery page. Bending Spoons reportedly agreed to acquire Eventbrite for about $500M in cash in December 2025. That claim comes from a single secondary source and needs verification. — [Eventbrite UC Berkeley](https://www.eventbrite.com/d/ca--berkeley/uc-berkeley/); acquisition claim via a search summary, unverified
- Meetup and Partiful Explore were not specifically researched.

### Inferences
- Because clubs host on Luma, a scraper of Berkeley-affiliated Luma calendars captures a large share of tech and hackathon events. Luma's own discovery, however, is city-level and not filtered to Berkeley students.
- Cerebral Valley and Tech Week skew SF and professional. Berkeley students need to cross-reference them by hand.

### Gaps
- Whether Luma has a dedicated "Berkeley" discovery page or calendar as of late 2026 is not confirmed.
- Cerebral Valley's current (2026) events product and subscriber count were not found.
- Meetup's Berkeley relevance and Partiful Explore's coverage were not checked.

## Pricing, user counts and traction

### Takeaway
All the Berkeley-specific aggregators are free and publish no traction numbers. Public traction data exists only for the large platforms, and it is dated.

### Cited Findings
- **Partiful:**
  - Said it added about 2M new users in 2025; one source says this figure covers H1 2025 only.
  - Sensor Tower estimated about 500K MAU in Q1 2025, up 400% year over year.
  - "Over 60% of active app users check Partiful weekly."
  - Core demographic is ages 20–30, with the most need "postgrad".
  - Has Org Profiles suited to fraternities and clubs.

  [NBC/CNBC: Meet Partiful](https://www.nbcnewyork.com/news/business/money-report/meet-partiful-the-gen-z-party-planning-staple-thats-taking-on-apple/6231135/); [Sacra (analyst writeup)](https://sacra.com/chat/h/d75d313a-21c0-4696-ae31-3ccb39d25c1c/)
- **Luma (lu.ma events):** $3M seed in December 2020 (Maven Ventures, Venrock) and more than 500K users by December 2020. No 2025 or 2026 user figure was found. Do not confuse it with Luma AI, the video model company that raised a $900M Series C in November 2025. — [Crunchbase News](https://news.crunchbase.com/?p=39471); [Luma AI Series C](https://www.pulse.bot/venture-capital/deals/luma-ai-secures-900m-series-c-funding-led-by-humain-91d3781a-1798-4319-b29f-afb5afee45d0)
- **Berkeley-specific:**
  - Berkeley Life Instagram: about 42K followers ([Instagram](https://www.instagram.com/ucberkeleylife/))
  - CalEvents: 1,840 events listed, no user data ([status.json](https://cal-events.com/status.json))
  - Eventreels: "thousands of verified students" across all campuses ([Eventreels](https://eventreels.com/ucberkley))
  - Goggles: 1,300+ club profiles ([berkeleygoggles.org](https://berkeleygoggles.org/))
  - No pricing found for any of these; all appear free to students.

### Inferences
- With no aggregator publishing usage, no one has demonstrated a durable student audience. That means the field is open, and also that monetization and retention are unproven.

### Gaps
- No traffic or user data for any Berkeley aggregator.
- No current Luma user count.
- Partiful figures are company-reported or third-party estimates.
