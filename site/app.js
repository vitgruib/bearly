"use strict";

const TZ = "America/Los_Angeles";
const PAGE = 60;
const WHEN = [
  ["today", "Today"], ["tomorrow", "Tomorrow"], ["weekend", "This weekend"],
  ["week", "Next 7 days"], ["all", "Everything"], ["custom", "Custom"],
];
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const TOPIC_EMOJI = {
  "AI & Tech": "🤖", "Startups": "🚀", "Hackathons": "🛠️", "Career": "💼", "Talks": "🎤",
  "Social": "🎉", "Arts & Music": "🎨", "Sports & Wellness": "🏃", "Community": "🤝",
  "Free food": "🍕",
};
// One filter row per group; a topic missing from both lands in the second row.
const TOPIC_GROUPS = [
  ["AI & Tech", "Startups", "Hackathons", "Career", "Talks"],
  ["Social", "Arts & Music", "Sports & Wellness", "Community"],
];
// Its own chip beside "Free only", not in the event type rows.
const FOOD = "Free food";
// A Location filter with its own quick chip, so the most asked-for place is one tap away.
const CAMPUS = "Campus";

const $ = (s) => document.querySelector(s);
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const weekdayOf = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short" });
const fmtTime = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
const fmtDay = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "long" });
const fmtDate = new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "short", day: "numeric" });
const hourOf = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", hourCycle: "h23" });

let data = { events: [], sources: [], topics: [], regions: [] };
let state = { q: "", when: "week", from: "", to: "", topics: new Set(), regions: new Set(), free: false, src: new Set(), event: "" };
let filtered = [];
let rendered = 0;
let lastDay = null;
let fold = null;

/* ---------- URL state ---------- */

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.q = p.get("q") || "";
  state.when = WHEN.some(([k]) => k === p.get("when")) ? p.get("when") : "week";
  state.from = DAY.test(p.get("from")) ? p.get("from") : "";
  state.to = DAY.test(p.get("to")) ? p.get("to") : "";
  state.topics = new Set((p.get("t") || "").split(",").filter(Boolean));
  state.regions = new Set((p.get("r") || "").split(",").filter(Boolean));
  state.free = p.get("free") === "1";
  state.src = new Set((p.get("src") || "").split(",").filter(Boolean));
  state.event = p.get("event") || "";
}

function writeHash() {
  const p = new URLSearchParams();
  if (state.event) p.set("event", state.event);
  if (state.q) p.set("q", state.q);
  if (state.when !== "week") p.set("when", state.when);
  if (state.when === "custom") {
    if (state.from) p.set("from", state.from);
    if (state.to) p.set("to", state.to);
  }
  if (state.topics.size) p.set("t", [...state.topics].join(","));
  if (state.regions.size) p.set("r", [...state.regions].join(","));
  if (state.free) p.set("free", "1");
  if (state.src.size) p.set("src", [...state.src].join(","));
  const h = p.toString();
  history.replaceState(null, "", h ? `#${h}` : location.pathname + location.search);
}

/* ---------- Filtering ---------- */

function addDays(key, n) {
  const [y, m, d] = key.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n, 12));
  return dt.toISOString().slice(0, 10);
}

function whenRange(when) {
  const today = dayKey.format(new Date());
  switch (when) {
    case "today": return [today, today];
    case "tomorrow": return [addDays(today, 1), addDays(today, 1)];
    case "week": return [today, addDays(today, 6)];
    case "weekend": {
      const dow = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(weekdayOf.format(new Date()));
      if (dow === 0) return [today, today];
      return [dow === 6 ? today : addDays(today, 5 - dow), addDays(today, 7 - dow)];
    }
    // An empty end means open-ended; dates picked backwards still read as a range.
    case "custom": {
      const from = state.from || today, to = state.to || "9999";
      return from <= to ? [from, to] : [to, from];
    }
    default: return ["0000", "9999"];
  }
}

function matchesWhen(e, [from, to]) {
  // Something already under way still counts for "today".
  return e._day <= to && (e._endDay || e._day) >= from;
}

// Matched at word starts in e._norm, so "hack" finds "hackathon" but "thon" doesn't.
function termMatches(e, t) {
  return t.alts.some((a) => e._norm.includes(` ${a}`)) || t.tags.some((g) => e.tags?.includes(g));
}

function base(skip, wide) {
  // A shared link shows just that event, whatever filters the viewer had.
  if (state.event) return data.events.filter((e) => e.id === state.event);
  const q = parseQuery();
  const today = dayKey.format(new Date());
  // Typed dates narrow the When row rather than replace it; "wide" is every upcoming date.
  let range = wide ? ["0000", "9999"] : whenRange(state.when);
  if (q.days && !wide) range = [q.days[0] > range[0] ? q.days[0] : range[0], q.days[1] < range[1] ? q.days[1] : range[1]];
  if (range[0] > range[1]) return [];
  // Today means what you can still go to; all-day events count as not started.
  const fresh = !wide && range[0] === today && range[1] === today && (state.when === "today" || q.days);
  const evening = !wide && q.evening;
  const free = state.free || q.free;
  const now = Date.now();
  return data.events.filter((e) =>
    (e._end || e._start + 2 * 3600e3) > now &&
    (skip === "src" || !state.src.size || state.src.has(e.source) || e.also_on?.some((s) => state.src.has(s))) &&
    matchesWhen(e, range) &&
    (!fresh || e._start > now || (e.all_day && e._day === today)) &&
    (!evening || (!e.all_day && e._hour >= EVENING && e._day >= range[0])) &&
    q.terms.every((t) => termMatches(e, t)) &&
    (!free || e.free === true) &&
    (!q.regions.size || q.regions.has(e.region)) &&
    q.topics.every((t) => e.tags?.includes(t)) &&
    (skip === "regions" || !state.regions.size || state.regions.has(e.region)) &&
    (skip === "topics" || !state.topics.size || e.tags?.some((t) => state.topics.has(t))));
}

/* ---------- Search words ---------- */

// The query is read fresh from state.q on every filter, so the URL's raw text alone
// reproduces the view. Words that name a time, place or event type become filters; a word
// in "quotes" is always searched as typed, which is how removing a filter chip works.

const EVENING = 17;
const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
const FILLER = new Set(["on", "in", "at", "near", "around", "the", "a", "an", "and", "&", "of", "this",
  "events", "event", "for", "me", "whats", "happening"]);
const TOPIC_ALIASES = {
  "AI & Tech": ["ai", "tech", "ml", "llm", "machine learning", "artificial intelligence"],
  "Startups": ["startup", "founder", "vc"],
  "Hackathons": ["hackathon", "hack night", "build night", "buildathon"],
  "Career": ["career", "job", "internship", "recruiting"],
  "Talks": ["talk", "lecture", "seminar", "panel", "colloquium"],
  "Social": ["party", "parties", "social", "mixer", "happy hour"],
  "Arts & Music": ["art", "music", "concert"],
  "Sports & Wellness": ["sport", "workout", "yoga", "fitness", "wellness"],
  "Community": ["community", "volunteer", "volunteering"],
  // The scraper's own food words (data.topic_words) are added at load.
  [FOOD]: ["food", "free food", "snack", "refreshment"],
};
const PLACE_ALIASES = [
  // Campus is in Berkeley, so "berkeley" covers both.
  [["Campus"], ["campus"]],
  [["Berkeley", "Campus"], ["berkeley"]],
  [["East Bay"], ["east bay", "oakland"]],
  [["San Francisco"], ["sf", "san francisco"]],
  [["Peninsula & South Bay"], ["peninsula", "south bay", "palo alto", "san jose"]],
  [["North Bay"], ["north bay"]],
  [["Sacramento"], ["sacramento"]],
  [["Los Angeles"], ["los angeles", "hollywood", "anaheim"]],
  [["San Diego"], ["san diego"]],
  [["Online"], ["online", "virtual", "zoom"]],
];
// Words close enough in meaning to search alongside, for words left as plain text.
const SYNONYMS = {
  food: ["pizza", "boba", "snacks", "refreshments", "lunch", "dinner"],
  hackathon: ["hack night", "build night"],
  talk: ["lecture", "seminar", "panel", "speaker"],
  lecture: ["talk", "seminar"],
  party: ["social", "mixer"],
  concert: ["music"],
};

const aliases = new Map();
let maxAlias = 1;
let vocab = null;
let parsed = { key: null };

// Same treatment for event text and typed words: "Women's Café" -> "womens cafe".
function norm(s) {
  return s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase()
    .replace(/['’.]/g, "").replace(/[^\p{L}\p{N}&]+/gu, " ").trim();
}

function buildAliases() {
  const add = (phrase, hit) => {
    aliases.set(phrase, hit);
    maxAlias = Math.max(maxAlias, phrase.split(" ").length);
  };
  const food = (data.topic_words?.[FOOD] || []).map((p) => p.replace(/\\b/g, "")).filter((p) => /^[a-z ]+$/.test(p));
  for (const [topic, words] of Object.entries(TOPIC_ALIASES)) {
    if (!data.topics.includes(topic)) continue;
    const hit = { key: `t:${topic}`, topic, label: `${TOPIC_EMOJI[topic] || ""} ${topic}`.trim() };
    for (const w of [topic, ...words, ...(topic === FOOD ? food : [])]) add(norm(w), hit);
  }
  for (const [regions, words] of PLACE_ALIASES) {
    const hit = { key: `r:${regions}`, regions, label: `📍 ${regions[0]}` };
    for (const w of [regions.join(" "), ...words]) add(norm(w), hit);
  }
}

// Singular or plural both hit: "hackathons", "talks", "snacks".
function aliasOf(phrase) {
  return aliases.get(phrase) || aliases.get(phrase.replace(/s$/, "")) || aliases.get(`${phrase}s`);
}

function aliasAt(toks, i) {
  for (let n = Math.min(maxAlias, toks.length - i); n > 0; n--) {
    const run = toks.slice(i, i + n);
    if (run.some((t) => t.quoted)) continue;
    const hit = aliasOf(run.map((t) => t.w).join(" "));
    if (hit) return { ...hit, n };
  }
  return null;
}

// A time phrase starting at toks[i]: "tonight", "this weekend", "friday night".
function timeAt(toks, i, today) {
  const w = (k) => (toks[i + k] && !toks[i + k].quoted ? toks[i + k].w : "");
  const lead = w(0) === "this" ? 1 : 0;
  const word = w(lead);
  const day = (n) => [addDays(today, n), addDays(today, n)];
  let t = null;
  if (word === "today") t = { days: day(0), label: "Today", phrase: "today" };
  else if (word === "tonight" || (lead && word === "evening")) t = { days: day(0), evening: true, label: "Tonight", phrase: "tonight" };
  else if (word === "tomorrow") t = { days: day(1), label: "Tomorrow", phrase: "tomorrow" };
  else if (word === "weekend") t = { days: whenRange("weekend"), label: "This weekend", phrase: "this weekend" };
  else if (word === "week") t = { days: whenRange("week"), label: "This week", phrase: "this week" };
  else if (WEEKDAYS.includes(word)) {
    const label = word[0].toUpperCase() + word.slice(1);
    const dow = WEEKDAYS.findIndex((d) => d.startsWith(weekdayOf.format(new Date()).toLowerCase()));
    t = { days: day((WEEKDAYS.indexOf(word) - dow + 7) % 7), label, phrase: `on ${label}` };
  }
  if (!t) return null;
  t.n = lead + 1;
  if (!t.evening && t.days[0] === t.days[1] && ["night", "evening"].includes(w(t.n))) {
    t.n++;
    t.evening = true;
    t.label += " night";
    t.phrase += " night";
  }
  return t;
}

// Search alternatives for one plain word: itself, close synonyms, and the event type it names.
function related(w) {
  const tags = [aliasOf(w)?.topic].filter(Boolean);
  return { alts: [w, ...(SYNONYMS[w] || SYNONYMS[w.replace(/s$/, "")] || [])], tags };
}

function oneEdit(a, b) {
  if (a === b) return true;
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0;
  while (a[i] === b[i]) i++;
  if (a.length === b.length) {
    return a.slice(i + 1) === b.slice(i + 1) || (a[i] === b[i + 1] && a[i + 1] === b[i] && a.slice(i + 2) === b.slice(i + 2));
  }
  const [s, l] = a.length < b.length ? [a, b] : [b, a];
  return s.slice(i) === l.slice(i + 1);
}

// Words seen in titles and tags: the spellings a typo is most likely aiming for.
function vocabulary() {
  if (!vocab) {
    const words = new Set();
    for (const e of data.events) {
      for (const w of norm([e.title, ...(e.tags || [])].join(" ")).split(" ")) if (w.length >= 4) words.add(w);
    }
    vocab = [...words];
  }
  return vocab;
}

function parseQuery() {
  const today = dayKey.format(new Date());
  const key = `${state.q}|${today}`;
  if (parsed.key === key) return parsed;
  const toks = [];
  for (const m of state.q.matchAll(/"([^"]*)"?|[^\s"]+/g)) {
    const span = [m.index, m.index + m[0].length];
    if (m[0].startsWith('"')) {
      const w = norm(m[1]);
      if (w) toks.push({ w, span, quoted: true });
    } else {
      for (const w of norm(m[0]).split(" ").filter(Boolean)) toks.push({ w, span });
    }
  }
  const p = { key, days: null, evening: true, free: false, topics: [], regions: new Set(), terms: [], chips: new Map(), fixes: [], times: [] };
  const chipFor = (id, label, from, to) => {
    const c = p.chips.get(id) || { label, spans: [] };
    const span = [toks[from].span[0], toks[to - 1].span[1]];
    if (!c.spans.some((s) => s[0] === span[0])) c.spans.push(span);
    p.chips.set(id, c);
  };
  for (let i = 0; i < toks.length;) {
    const tok = toks[i];
    if (tok.quoted) {
      p.terms.push(related(tok.w));
      i++;
      continue;
    }
    const time = timeAt(toks, i, today);
    if (time) {
      // Several times ("friday saturday") widen to cover them all.
      p.days = p.days ? [p.days[0] < time.days[0] ? p.days[0] : time.days[0], p.days[1] > time.days[1] ? p.days[1] : time.days[1]] : time.days;
      p.evening = p.evening && !!time.evening;
      p.times.push(time.phrase);
      chipFor(`w:${time.label}`, time.label, i, i + time.n);
      i += time.n;
      continue;
    }
    // "free pizza" means free food, not "free" and "pizza".
    const next = tok.w === "free" ? aliasAt(toks, i + 1) : null;
    const hit = next?.topic === FOOD ? { ...next, n: next.n + 1 } : tok.w === "free" ? null : aliasAt(toks, i);
    if (hit) {
      if (hit.topic && !p.topics.includes(hit.topic)) p.topics.push(hit.topic);
      for (const r of hit.regions || []) p.regions.add(r);
      chipFor(hit.key, hit.label, i, i + hit.n);
      i += hit.n;
      continue;
    }
    if (tok.w === "free") {
      p.free = true;
      chipFor("free", "Free", i, i + 1);
    } else if (!FILLER.has(tok.w)) {
      p.terms.push({ ...related(tok.w), loose: true });
    }
    i++;
  }
  if (!p.days) p.evening = false;
  // A long word nothing contains is probably misspelled: try words one edit away.
  for (const t of p.terms) {
    const w = t.alts[0];
    if (!t.loose || w.length < 5 || w.includes(" ") || data.events.some((e) => termMatches(e, t))) continue;
    const near = vocabulary().filter((v) => oneEdit(w, v));
    for (const v of near) {
      const r = related(v);
      t.alts.push(...r.alts);
      t.tags.push(...r.tags);
    }
    if (near.length) p.fixes.push([w, near.slice(0, 3)]);
  }
  parsed = p;
  return p;
}

// Removing a chip quotes the words behind it, so they're searched as plain text instead.
function unfilter(spans) {
  let q = state.q;
  for (const [a, b] of [...spans].sort((x, y) => y[0] - x[0])) q = `${q.slice(0, a)}"${q.slice(a, b)}"${q.slice(b)}`;
  setQuery(q);
}

function setQuery(q) {
  state.q = q;
  $("#q").value = q;
  update();
}

function removable(label, title, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "qchip";
  b.textContent = label;
  b.append(Object.assign(document.createElement("span"), { textContent: "✕", ariaHidden: "true" }));
  b.title = title;
  b.setAttribute("aria-label", `Remove filter ${label}`);
  b.onclick = onClick;
  return b;
}

function renderQueryChips() {
  const q = parseQuery();
  const el = $("#qchips");
  const chips = [...q.chips.values()].map(({ label, spans }) =>
    removable(label, `Search the word${spans.length > 1 ? "s" : ""} as typed instead`, () => unfilter(spans)));
  const fixes = q.fixes.map(([typed, near]) =>
    Object.assign(document.createElement("span"), { className: "qnote", textContent: `“${typed}” → ${near.join(", ")}` }));
  el.replaceChildren(...chips, ...fixes);
  el.hidden = state.event || !(chips.length || fixes.length);
}

/* ---------- Controls ---------- */

function chip(label, pressed, count, onClick, title) {
  const b = document.createElement("button");
  b.className = "chip";
  b.type = "button";
  b.setAttribute("aria-pressed", pressed);
  b.innerHTML = `${label}<span class="n">${count}</span>`;
  b.classList.toggle("zero", !count);
  if (title) b.title = title;
  b.onclick = onClick;
  return b;
}

function renderControls() {
  const when = $("#when");
  when.replaceChildren(...WHEN.map(([k, label]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", state.when === k);
    b.textContent = label;
    b.onclick = () => { state.when = k; update(); };
    return b;
  }));
  $("#range").hidden = state.when !== "custom";
  $("#from").value = state.from || dayKey.format(new Date());
  $("#to").value = state.to;

  const forTopics = base("topics");
  const grouped = TOPIC_GROUPS.flat();
  const rows = [TOPIC_GROUPS[0],
    [...TOPIC_GROUPS[1], ...data.topics.filter((t) => !grouped.includes(t) && t !== FOOD)]];
  rows.forEach((row, i) => {
    $(`#topics-${i}`).replaceChildren(...row.filter((t) => data.topics.includes(t)).map((t) => {
      const n = forTopics.filter((e) => e.tags?.includes(t)).length;
      return chip(`${TOPIC_EMOJI[t] || ""} ${t}`, state.topics.has(t), n, () => toggle(state.topics, t));
    }));
  });

  const forRegions = base("regions");
  $("#regions").replaceChildren(...data.regions.map((r) => {
    const n = forRegions.filter((e) => e.region === r).length;
    const title = r === CAMPUS ? "On or right next to campus" : "";
    return chip(r === CAMPUS ? "📍 Campus" : r, state.regions.has(r), n, () => toggle(state.regions, r), title);
  }));

  const forSources = base("src");
  // Sources with no events at all (not connected yet) are left out; the rest always show.
  $("#sources").replaceChildren(...data.sources.filter((s) => s.count).map((s) => {
    const n = forSources.filter((e) => e.source === s.id || e.also_on?.includes(s.id)).length;
    return chip(s.name, state.src.has(s.id), n, () => toggle(state.src, s.id));
  }));

  $("#free").setAttribute("aria-pressed", state.free);
  $("#food").setAttribute("aria-pressed", state.topics.has(FOOD));
  $("#campus").setAttribute("aria-pressed", state.regions.has(CAMPUS));
  $("#clear").hidden = !(state.topics.size || state.regions.size || state.src.size || state.free);
  renderMoreFilters();
  renderShowing();
  renderQueryChips();
  showPickedWhen();
  markScrollRows();
}

// Location and Source sit behind "More filters", which only the user opens. While it's shut,
// their picks show as pills so a narrowed list always says why; Campus has its quick chip.
function renderMoreFilters() {
  const open = !$("#more").hidden;
  const n = state.regions.size + state.src.size;
  $("#more-toggle").setAttribute("aria-expanded", open);
  $("#more-n").textContent = n ? ` · ${n}` : "";
  const remove = "Remove this filter";
  $("#pills").replaceChildren(...(open ? [] : [
    ...[...state.regions].filter((r) => r !== CAMPUS).map((r) => removable(`📍 ${r}`, remove, () => toggle(state.regions, r))),
    ...[...state.src].map((s) => removable(sourceName(s), remove, () => toggle(state.src, s))),
  ]));
}

// On a phone the When row scrolls sideways; bring the picked option clear of the edge fade
// without scrollIntoView, which would also scroll the page.
function showPickedWhen() {
  const row = $("#when").parentElement;
  const a = $("#when [aria-checked=\"true\"]").getBoundingClientRect();
  const r = row.getBoundingClientRect();
  if (a.right > r.right - 36) row.scrollLeft += a.right - r.right + 36;
  else if (a.left < r.left) row.scrollLeft -= r.left - a.left;
}

// A chip row cut off at the right edge fades there, so it reads as scrollable.
function markScrollRows(rows = document.querySelectorAll(".fchips")) {
  for (const row of rows) row.classList.toggle("more-right", row.scrollLeft + row.clientWidth < row.scrollWidth - 1);
}

// Spells out how the picks combine: any chip within a row, every row that has one.
function renderShowing() {
  const groups = [
    [...state.topics],
    [...state.regions],
    [...state.src].map(sourceName),
    state.free ? ["Free"] : [],
  ].filter((g) => g.length);
  const el = $("#showing");
  if (!groups.length) {
    el.replaceChildren();
    return;
  }
  const word = (w) => Object.assign(document.createElement("b"), { textContent: ` ${w} ` });
  el.replaceChildren("Showing ");
  groups.forEach((g, i) => {
    if (i) el.append(word("and"));
    const span = document.createElement("span");
    span.className = "pick-group";
    g.forEach((label, j) => {
      if (j) span.append(word("or"));
      span.append(label);
    });
    el.append(span);
  });
}

function toggle(set, v) {
  set.has(v) ? set.delete(v) : set.add(v);
  update();
}

/* ---------- List ---------- */

const sourceName = (id) => data.sources.find((s) => s.id === id)?.name || id;

function dayLabel(key) {
  const today = dayKey.format(new Date());
  const d = new Date(`${key}T12:00:00Z`);
  if (key === today) return ["Today", fmtDate.format(d)];
  if (key === addDays(today, 1)) return ["Tomorrow", fmtDate.format(d)];
  return [fmtDay.format(d), fmtDate.format(d)];
}

function card(e) {
  const node = $("#card").content.firstElementChild.cloneNode(true);
  const started = e._start < Date.now();
  const clock = (ms) => fmtTime.format(new Date(ms)).replace(":00", "");
  // A midnight-to-midnight listing would read "12 AM – 12 AM".
  const endClock = e.end && clock(e._end) !== clock(e._start) ? clock(e._end) : "";
  node.querySelector(".time").innerHTML = e.all_day
    ? "All day"
    : started && e._day < dayKey.format(new Date())
      ? `Ongoing<small>until ${e.end ? fmtDate.format(new Date(e._end)) : ""}</small>`
      : `${clock(e._start)}${endClock ? `<small>– ${endClock}</small>` : ""}`;
  const a = node.querySelector(".title");
  a.textContent = e.title;
  if (e.url) a.href = e.url;
  const whereEl = node.querySelector(".where");
  const place = e.online ? "" : e.venue || e.address || e.city || "";
  if (place) {
    const map = document.createElement("a");
    map.className = "map";
    map.textContent = place;
    map.title = "Open in Google Maps";
    const query = e.lat != null ? `${e.lat},${e.lng}` : [e.venue, e.address || e.city].filter(Boolean).join(", ");
    Object.assign(map, { href: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`, target: "_blank", rel: "noopener" });
    whereEl.append(map);
  }
  const rest = [e.online ? "Online" : "", e.host].filter(Boolean).join(" · ");
  if (rest) whereEl.append(`${place ? " · " : ""}${rest}`);
  // A concert at a big venue a train gets you to: a poster card that leads with the way there.
  if (e.big_show) {
    node.classList.add("big");
    const kicker = Object.assign(document.createElement("span"), { className: "kicker", textContent: `🎤 Big show${e.city ? ` · ${e.city}` : ""}` });
    a.before(kicker);
    if (e.transit) whereEl.after(Object.assign(document.createElement("p"), { className: "transit", textContent: `🚆 ${e.transit}` }));
  }
  if (e.access?.length) {
    const access = node.querySelector(".access");
    access.textContent = `Getting in: ${e.access.join(" · ")}`;
    access.hidden = false;
  }
  if (e.reports?.length) {
    const reported = node.querySelector(".reported");
    reported.textContent = "⚠ Reported by visitors (unverified): " + e.reports
      .map((r) => (r.details ? `${r.kind}: ${r.details}` : r.kind)).join(" · ");
    reported.hidden = false;
  }
  node.querySelector(".desc").textContent = e.description || "";
  const badges = node.querySelector(".badges");
  const add = (text, cls = "") => {
    const s = document.createElement("span");
    s.className = `badge ${cls}`;
    s.textContent = text;
    badges.append(s);
  };
  if (e.tags?.includes("Free food")) add("🍕 Free food", "food");
  if (e.free === true) add("Free", "free");
  if (e.repeats) add(`Repeats · ${e.repeats} dates`);
  const topics = e.tags?.filter((t) => t !== "Free food").slice(0, 2) || [];
  topics.forEach((t) => add(t));
  // One badge per place the event is listed, each linking there; sources seen without a
  // link of their own (an email, a Slack post) get a plain badge. A badge that only repeats
  // the host or a topic shown just above is dropped, unless it leads somewhere the title doesn't.
  const listings = e.listings?.length ? e.listings
    : [{ source: e.source, url: e.url, name: e.source === "feeds" ? e.host : null }];
  const linked = new Set(listings.map((l) => l.source));
  const named = new Set();
  const repeats = (label) => label === e.host || topics.includes(label);
  for (const l of listings) {
    const label = l.name || sourceName(l.source);
    if (named.has(label) || (repeats(label) && (!l.url || l.url === e.url))) continue;
    named.add(label);
    const a = document.createElement("a");
    a.className = "badge src";
    a.textContent = label;
    a.title = `See it on ${a.textContent}`;
    if (l.url) Object.assign(a, { href: l.url, target: "_blank", rel: "noopener" });
    badges.append(a);
  }
  (e.also_on || []).filter((s) => !linked.has(s) && !repeats(sourceName(s))).forEach((s) => add(sourceName(s), "src"));
  const img = node.querySelector(".thumb");
  if (e.image) img.src = e.image; else img.remove();
  img.onerror = () => img.remove();
  const end = e._end || e._start + 2 * 3600e3;
  const calPlace = e.address || e.venue || "";
  const details = `${e.description || ""}\n\n${e.url || ""}`.trim().slice(0, 1500);
  node.querySelector(".gcal").href = `https://calendar.google.com/calendar/render?${new URLSearchParams({
    action: "TEMPLATE", text: e.title, dates: `${icsDate(e._start)}/${icsDate(end)}`, details, location: calPlace })}`;
  node.querySelector(".ocal").href = `https://outlook.live.com/calendar/0/action/compose?${new URLSearchParams({
    subject: e.title, startdt: new Date(e._start).toISOString(), enddt: new Date(end).toISOString(),
    body: details, location: calPlace })}`;
  node.querySelector(".ics").onclick = () => downloadIcs(e);
  const share = node.querySelector(".share");
  share.onclick = async () => {
    // The event's own page, not #event=: chat apps read that page for the preview card.
    const url = new URL(`e/${e.id}.html`, location.href).href;
    if (navigator.share && matchMedia("(pointer: coarse)").matches) {
      try { await navigator.share({ title: e.title, url }); } catch { /* closed the share sheet */ }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      share.textContent = "Link copied";
    } catch {
      // No clipboard access: put the link in the address bar to copy from there.
      history.replaceState(null, "", `#event=${e.id}`);
      share.textContent = "Link in address bar";
    }
    setTimeout(() => { share.textContent = "Share"; }, 1800);
  };
  if (data.repo) {
    const flag = node.querySelector(".flag");
    // The build attaches the report to its event by the [id] at the end.
    const label = `${e.title} (${fmtDate.format(new Date(e._start))}) [${e.id}]`;
    if (data.forms?.report_prefill) {
      flag.href = data.forms.report_prefill.replace("EVENT", encodeURIComponent(label));
      flag.hidden = false;
    }
  }
  return node;
}

// Something already under way is listed under today, whatever day it began.
const dayOf = (e, today) => (e._start < Date.now() ? today : e._day);

// All-day events, and multi-day ones already under way, have no time to plan around.
function untimed(e, today) {
  return e.all_day || (e._start < Date.now() && (e._day < today || (e._endDay || e._day) > e._day));
}

// Each day lists its untimed events first, so they can fold into one line above the timed ones.
function byDay(events) {
  const today = dayKey.format(new Date());
  const keyed = events.map((e) => [dayOf(e, today), untimed(e, today) ? 0 : 1, e]);
  keyed.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] - b[1]));
  return keyed.map(([, , e]) => e);
}

function renderMore() {
  const list = $("#list");
  const frag = document.createDocumentFragment();
  const today = dayKey.format(new Date());
  // Folded cards don't count toward a page: a page of only those would leave the sentinel in
  // view with nothing new to trigger the next one.
  let shown = 0;
  while (rendered < filtered.length && shown < PAGE) {
    const e = filtered[rendered++];
    const day = dayOf(e, today);
    if (day !== lastDay) {
      lastDay = day;
      const events = filtered.filter((x) => dayOf(x, today) === day);
      const n = events.length;
      const [big, small] = dayLabel(day);
      const h = document.createElement("div");
      h.className = "day";
      h.innerHTML = `<h2>${big}</h2><span>${small} · ${n} event${n === 1 ? "" : "s"}</span>`;
      frag.append(h);
      // A day of only untimed events shows them as they are; folding them would hide the day.
      const k = events.filter((x) => untimed(x, today)).length;
      fold = null;
      if (k && k < n) {
        fold = document.createElement("details");
        fold.className = "fold";
        fold.innerHTML = `<summary>All day &amp; ongoing (${k})</summary>`;
        frag.append(fold);
      }
    }
    // One malformed event from a scraper must not take the rest of the list down with it.
    try {
      if (fold && untimed(e, today)) {
        fold.append(card(e));
      } else {
        frag.append(card(e));
        shown++;
      }
    } catch (err) {
      console.warn("skipped event", e.id, err);
    }
  }
  list.append(frag);
}

function update() {
  writeHash();
  renderControls();
  filtered = byDay(base());
  $("#count").textContent = `${filtered.length.toLocaleString()} event${filtered.length === 1 ? "" : "s"}`;
  $("#list").replaceChildren();
  rendered = 0;
  lastDay = null;
  fold = null;
  if (state.event) {
    const back = document.createElement("div");
    back.className = "shared";
    back.innerHTML = `<span>${filtered.length ? "A shared event." : "This event has ended or was removed."}</span><button class="link" type="button">See all events</button>`;
    back.querySelector("button").onclick = () => { state.event = ""; update(); };
    $("#list").append(back);
    if (!filtered.length) return;
  }
  if (!filtered.length) {
    renderEmpty();
    return;
  }
  renderMore();
}

const WHEN_PHRASE = { today: "today", tomorrow: "tomorrow", weekend: "this weekend", week: "in the next 7 days", custom: "in those dates" };

// Before giving up, check whether the same search finds anything on any upcoming date.
function renderEmpty() {
  const wider = state.event ? [] : base(undefined, true);
  const box = document.createElement("div");
  box.className = "empty";
  const strong = document.createElement("strong");
  box.append(strong);
  if (!wider.length) {
    strong.textContent = "No events match.";
    box.append("Try fewer words or filters.");
  } else {
    const q = parseQuery();
    // The search minus its time words is what to look for on other dates.
    const timeSpans = [...q.chips].filter(([id]) => id.startsWith("w:")).flatMap(([, c]) => c.spans);
    let rest = state.q;
    for (const [a, b] of timeSpans.sort((x, y) => y[0] - x[0])) rest = rest.slice(0, a) + rest.slice(b);
    rest = rest.replace(/\s+/g, " ").trim();
    const when = q.times.length ? q.times.join(" or ") : WHEN_PHRASE[state.when];
    strong.textContent = `Nothing ${when}${rest ? ` for “${rest}”` : " with these filters"}.`;
    const widen = document.createElement("button");
    widen.type = "button";
    widen.className = "widen";
    widen.textContent = `${wider.length.toLocaleString()} upcoming →`;
    widen.onclick = () => {
      state.when = "all";
      setQuery(rest);
    };
    box.append(widen);
  }
  $("#list").replaceChildren(box);
}

/* ---------- Calendar export ---------- */

function icsDate(ms) {
  return new Date(ms).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

function icsEscape(s) {
  return (s || "").replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/[,;]/g, (c) => `\\${c}`);
}

function downloadIcs(e) {
  const end = e._end || e._start + 2 * 3600e3;
  const ics = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Lo-Cal//berkeley events//EN", "BEGIN:VEVENT",
    `UID:${e.id}@lo-cal`, `DTSTAMP:${icsDate(Date.now())}`,
    `DTSTART:${icsDate(e._start)}`, `DTEND:${icsDate(end)}`,
    `SUMMARY:${icsEscape(e.title)}`,
    `LOCATION:${icsEscape(e.address || e.venue || "")}`,
    `DESCRIPTION:${icsEscape(`${e.description || ""}\n\n${e.url || ""}`)}`,
    e.url ? `URL:${e.url}` : "", "END:VEVENT", "END:VCALENDAR",
  ].filter(Boolean).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([ics], { type: "text/calendar" }));
  a.download = `${e.title.replace(/[^\w]+/g, "-").slice(0, 50)}.ics`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ---------- Boot ---------- */

function relTime(iso) {
  const mins = Math.round((Date.now() - new Date(iso)) / 60000);
  if (mins < 60) return `${Math.max(mins, 1)} min ago`;
  if (mins < 48 * 60) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} days ago`;
}

const slug = (t) => t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function renderFeeds() {
  const rows = [["Everything", "all"], ...data.topics.map((t) => [`${TOPIC_EMOJI[t] || ""} ${t}`, slug(t)])];
  $("#feeds").replaceChildren(...rows.map(([label, file]) => {
    const url = new URL(`data/cal/${file}.ics`, location.href).href;
    const webcal = url.replace(/^https?:/, "webcal:");
    const row = document.createElement("div");
    row.className = "feed";
    row.innerHTML = `<span></span><a target="_blank" rel="noopener">Google</a><a>Apple / Outlook</a>`;
    row.querySelector("span").textContent = label;
    const [google, apple] = row.querySelectorAll("a");
    google.href = `https://calendar.google.com/calendar/render?cid=${encodeURIComponent(webcal)}`;
    apple.href = webcal;
    return row;
  }));
}

document.addEventListener("click", (ev) => {
  for (const d of document.querySelectorAll("details.addcal[open]")) {
    if (!d.contains(ev.target) || ev.target.closest(".calmenu")) d.open = false;
  }
});

async function boot() {
  readHash();
  $("#q").value = state.q;
  let t;
  $("#q").addEventListener("input", (ev) => {
    clearTimeout(t);
    t = setTimeout(() => { state.q = ev.target.value.trim(); update(); }, 120);
  });
  $("#free").onclick = () => { state.free = !state.free; update(); };
  $("#food").onclick = () => toggle(state.topics, FOOD);
  $("#campus").onclick = () => toggle(state.regions, CAMPUS);
  $("#more-toggle").onclick = () => {
    $("#more").hidden = !$("#more").hidden;
    renderMoreFilters();
    markScrollRows();
  };
  // Scroll events don't bubble, so one capturing listener covers every chip row.
  document.addEventListener("scroll", (ev) => {
    if (ev.target.classList?.contains("fchips")) markScrollRows([ev.target]);
  }, { capture: true, passive: true });
  addEventListener("resize", () => markScrollRows());
  $("#from").onchange = (ev) => { state.from = ev.target.value; update(); };
  $("#to").onchange = (ev) => { state.to = ev.target.value; update(); };
  $("#copy-llms").onclick = async (ev) => {
    const btn = ev.currentTarget;
    try {
      await navigator.clipboard.writeText(new URL("llms.txt", location.href).href);
      btn.textContent = "Copied";
    } catch {
      btn.textContent = "Right-click the link to copy";  // no clipboard access
    }
    setTimeout(() => { btn.textContent = "Copy link"; }, 1800);
  };
  $("#clear").onclick = () => {
    state.event = "";
    state.topics.clear(); state.regions.clear(); state.src.clear(); state.free = false;
    update();
  };

  try {
    const res = await fetch("data/events.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`events.json: HTTP ${res.status}`);
    data = await res.json();
  } catch (err) {
    console.error(err);
    $("#list").innerHTML = `<div class="empty"><strong>Couldn't load events.</strong>Check your connection and refresh the page.</div>`;
    return;
  }
  // The data comes from scrapers: drop anything the page can't place on a calendar.
  data.events = data.events.filter((e) => e.title && Number.isFinite(Date.parse(e.start)));
  for (const e of data.events) {
    e._start = Date.parse(e.start);
    e._end = e.end ? Date.parse(e.end) : null;
    e._day = dayKey.format(new Date(e._start));
    e._endDay = e._end ? dayKey.format(new Date(e._end - 1)) : null;
    e._hour = Number(hourOf.format(new Date(e._start)));
    // Spaces at both ends let one includes(" word") check mean "a word starting with this".
    e._norm = ` ${norm([e.title, e.host, e.venue, e.address, e.description, e.region, ...(e.tags || [])]
      .filter(Boolean).join(" "))} `;
  }
  buildAliases();

  const live = data.sources.filter((s) => s.count > 0).map((s) => `${s.name} (${s.count})`);
  $("#updated").textContent = `Updated ${relTime(data.generated_at)} · ${data.events.length.toLocaleString()} upcoming events from ${live.join(", ")}.`;
  const notes = data.sources.filter((s) => s.health !== "ok" && !(s.health === "off" && s.count)).map((s) =>
    `${s.name} (${s.health === "off" ? "not connected" : `having trouble; showing results from ${s.last_ok ? relTime(s.last_ok) : "earlier"}`})`);
  $("#status").textContent = notes.length ? `Also: ${notes.join(", ")}.` : "";

  new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && rendered < filtered.length) renderMore();
  }, { rootMargin: "800px" }).observe($("#sentinel"));

  renderFeeds();
  // A shared link pasted into an open tab only changes the hash.
  addEventListener("hashchange", () => { readHash(); $("#q").value = state.q; update(); });
  update();
}

boot();
