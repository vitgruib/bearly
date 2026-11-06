"use strict";

const TZ = "America/Los_Angeles";
const PAGE = 60;
const WHEN = [
  ["today", "Today"], ["tomorrow", "Tomorrow"], ["weekend", "This weekend"],
  ["week", "This week"], ["all", "All"], ["custom", "Custom dates"],
];
const DEFAULT_WHEN = "today";
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const TOPIC_EMOJI = {
  "AI & Tech": "🤖", "Startups": "🚀", "Hackathons": "🛠️", "Career": "💼", "Talks": "🎤",
  "Social": "🎉", "Arts & Music": "🎨", "Sports & Wellness": "🏃", "Community": "🤝",
  "Free food": "🍕",
};
// A cost filter beside "Free admission", not an event type: it narrows whatever types are picked.
const FOOD = "Free food";
// "On campus only" picks this location on its own; the Where menu lists the rest.
const CAMPUS = "Campus";
const STATUS = { now: "Happening now", soon: "Still to come", done: "Already finished" };
const SAVED_KEY = "lo-cal-saved";
const PREFS_KEY = "lo-cal-prefs";
const SORT_KEY = "lo-cal-sort";

const $ = (s) => document.querySelector(s);
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const weekdayOf = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short" });
const fmtTime = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
const fmtLong = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "long", month: "long", day: "numeric" });
const fmtDay = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "long" });
const fmtDate = new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "short", day: "numeric" });
const fmtYear = new Intl.DateTimeFormat("en-US", { timeZone: TZ, year: "numeric" });
const fmtMonth = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "long", year: "numeric" });
const hourOf = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", hourCycle: "h23" });

let data = { events: [], sources: [], topics: [], regions: [] };
let state = { q: "", when: DEFAULT_WHEN, from: "", to: "", topics: new Set(), regions: new Set(), free: false, status: "", saved: false, event: "" };
let filtered = [];
let items = [];
let rendered = 0;

/* ---------- Kept in this browser: saves, preferences, sort ---------- */

// Storage can be missing or throw (private windows, blocked site data); the page works without it.
function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* not kept, still works this visit */ }
}
const saved = new Set(load(SAVED_KEY, []));
const prefs = new Set(load(PREFS_KEY, []));
let sort = load(SORT_KEY, "time");

function toggleSave(id) {
  saved.has(id) ? saved.delete(id) : saved.add(id);
  store(SAVED_KEY, [...saved]);
  renderSavedCount();
}

/* ---------- URL state ---------- */

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.q = p.get("q") || "";
  // Links from before the redesign: "Everything" is now All, "Next 7 days" is This week.
  state.when = WHEN.some(([k]) => k === p.get("when")) ? p.get("when") : DEFAULT_WHEN;
  state.from = DAY.test(p.get("from")) ? p.get("from") : "";
  state.to = DAY.test(p.get("to")) ? p.get("to") : "";
  state.topics = new Set((p.get("t") || "").split(",").filter(Boolean));
  state.regions = new Set((p.get("r") || "").split(",").filter(Boolean));
  state.free = p.get("free") === "1";
  state.status = STATUS[p.get("status")] ? p.get("status") : "";
  state.saved = p.get("saved") === "1";
  state.event = p.get("event") || "";
}

function writeHash() {
  const p = new URLSearchParams();
  if (state.event) p.set("event", state.event);
  if (state.saved) p.set("saved", "1");
  if (state.q) p.set("q", state.q);
  if (state.when !== DEFAULT_WHEN) p.set("when", state.when);
  if (state.when === "custom") {
    if (state.from) p.set("from", state.from);
    if (state.to) p.set("to", state.to);
  }
  if (state.topics.size) p.set("t", [...state.topics].join(","));
  if (state.regions.size) p.set("r", [...state.regions].join(","));
  if (state.free) p.set("free", "1");
  if (state.status) p.set("status", state.status);
  const h = p.toString();
  history.replaceState(null, "", h ? `#${h}` : location.pathname + location.search);
}

/* ---------- Filtering ---------- */

function addDays(key, n) {
  const [y, m, d] = key.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n, 12));
  return dt.toISOString().slice(0, 10);
}

const daysBetween = (a, b) => Math.round((Date.parse(`${b}T12:00:00Z`) - Date.parse(`${a}T12:00:00Z`)) / 864e5);

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

const endOf = (e) => e._end || e._start + 2 * 3600e3;
function statusOf(e, now = Date.now()) {
  if (endOf(e) <= now) return "done";
  return e._start <= now ? "now" : "soon";
}

function base(skip, wide) {
  // A shared link shows just that event, whatever filters the viewer had.
  if (state.event) return data.events.filter((e) => e.id === state.event);
  const q = parseQuery();
  // Saved shows every saved event still on the calendar; other filters don't hide a plan.
  if (state.saved) return data.events.filter((e) => saved.has(e.id) && statusOf(e) !== "done");
  // Typed dates narrow the When choice rather than replace it; "wide" is every upcoming date.
  let range = wide ? ["0000", "9999"] : whenRange(state.when);
  if (q.days && !wide) range = [q.days[0] > range[0] ? q.days[0] : range[0], q.days[1] < range[1] ? q.days[1] : range[1]];
  if (range[0] > range[1]) return [];
  const evening = !wide && q.evening;
  const free = state.free || q.free;
  // Free food is a condition on top of the event types, not one more type to OR in.
  const food = state.topics.has(FOOD);
  const cats = [...state.topics].filter((t) => t !== FOOD);
  const now = Date.now();
  const today = dayKey.format(new Date(now));
  return data.events.filter((e) =>
    // Ended events only count on their own day, folded into "Earlier today".
    (statusOf(e, now) !== "done" || (e._endDay || e._day) === today) &&
    matchesWhen(e, range) &&
    (skip === "status" || !state.status || statusOf(e, now) === state.status) &&
    (!evening || (!e.all_day && e._hour >= EVENING && e._day >= range[0])) &&
    q.terms.every((t) => termMatches(e, t)) &&
    (!free || e.free === true) &&
    (!q.regions.size || q.regions.has(e.region)) &&
    q.topics.every((t) => e.tags?.includes(t)) &&
    (skip === "regions" || !state.regions.size || state.regions.has(e.region)) &&
    (!food || e.tags?.includes(FOOD)) &&
    (skip === "topics" || !cats.length || cats.some((t) => e.tags?.includes(t))));
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

/* ---------- Sidebar filters ---------- */

const typesOf = () => data.topics.filter((t) => t !== FOOD);
const otherRegions = () => data.regions.filter((r) => r !== CAMPUS);
const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

function checkRow(label, checked, count, onChange) {
  const row = document.createElement("label");
  row.className = "check";
  row.classList.toggle("zero", !count && !checked);
  const box = Object.assign(document.createElement("input"), { type: "checkbox", checked });
  box.onchange = onChange;
  row.append(box, ` ${label}`, Object.assign(document.createElement("span"), { className: "n", textContent: count }));
  return row;
}

function renderControls() {
  $("#when").replaceChildren(...WHEN.map(([k, label]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", !state.saved && state.when === k);
    if (k === "custom") {
      b.className = "custom";
      b.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5.5" width="16" height="14.5" rx="2.5"/><path d="M4 10h16M8.5 3.5v4m7-4v4"/></svg>`;
      b.append(label);
      if (state.when === "custom" && state.from) b.append(Object.assign(document.createElement("small"), { textContent: rangeLabel(...whenRange("custom")) }));
      b.onclick = openDates;
    } else {
      b.append(label);
      b.onclick = () => { state.when = k; state.saved = false; update(); };
    }
    return b;
  }));

  const forRegions = base("regions");
  $("#regions").replaceChildren(...otherRegions().map((r) => checkRow(r, state.regions.has(r),
    forRegions.filter((e) => e.region === r).length, () => {
      state.regions.delete(CAMPUS);
      toggle(state.regions, r);
    })));
  const regionPicks = [...state.regions].filter((r) => r !== CAMPUS);
  $("#loc-label").textContent = state.regions.has(CAMPUS) ? "On campus"
    : regionPicks.length === 1 ? regionPicks[0] : regionPicks.length ? `${regionPicks.length} locations` : "All Berkeley locations";
  $("#dd-loc").classList.toggle("on", state.regions.size > 0);
  $("#campus").checked = state.regions.has(CAMPUS);

  const forTypes = base("topics");
  $("#types").replaceChildren(...typesOf().map((t) => checkRow(`${TOPIC_EMOJI[t] || ""} ${t}`.trim(), state.topics.has(t),
    forTypes.filter((e) => e.tags?.includes(t)).length, () => toggle(state.topics, t))));
  const typePicks = [...state.topics].filter((t) => t !== FOOD);
  $("#type-label").textContent = typePicks.length === 1 ? typePicks[0] : typePicks.length ? `${typePicks.length} event types` : "All event types";
  $("#dd-type").classList.toggle("on", typePicks.length > 0);

  $("#free").checked = state.free;
  $("#food").checked = state.topics.has(FOOD);
  $("#event-status").value = state.status;
  $("#event-status").parentElement.classList.toggle("on", !!state.status);
  const n = activeFilters().length;
  $("#filters-n").textContent = n;
  $("#filters-n").hidden = !n;
  renderPills();
  renderQueryChips();
}

// Every filter in use, each with a way to drop it: the pills above the list and the Reset count.
function activeFilters() {
  const out = [];
  if (state.regions.has(CAMPUS)) out.push(["📍 On campus", () => toggle(state.regions, CAMPUS)]);
  for (const r of state.regions) if (r !== CAMPUS) out.push([`📍 ${r}`, () => toggle(state.regions, r)]);
  for (const t of state.topics) if (t !== FOOD) out.push([`${TOPIC_EMOJI[t] || ""} ${t}`.trim(), () => toggle(state.topics, t)]);
  if (state.free) out.push(["Free admission", () => { state.free = false; update(); }]);
  if (state.topics.has(FOOD)) out.push(["🍴 Free food", () => toggle(state.topics, FOOD)]);
  if (state.status) out.push([STATUS[state.status], () => { state.status = ""; update(); }]);
  return out;
}

function renderPills() {
  const when = WHEN.find(([k]) => k === state.when)[1];
  const pills = [];
  if (!state.saved && !state.event) {
    const label = state.when === "custom" ? rangeLabel(...whenRange("custom")) : when;
    pills.push(state.when === DEFAULT_WHEN
      ? Object.assign(document.createElement("span"), { className: "qchip", textContent: label })
      : removable(label, "Back to today", () => { state.when = DEFAULT_WHEN; update(); }));
  }
  pills.push(...activeFilters().map(([label, drop]) => removable(label, "Remove this filter", drop)));
  $("#pills").replaceChildren(...pills);
  const regions = [...state.regions];
  const types = [...state.topics].filter((t) => t !== FOOD);
  $("#scope").textContent = [
    regions.length ? "" : "All Berkeley",
    types.length ? "" : "All categories",
  ].filter(Boolean).join(" · ");
}

function toggle(set, v) {
  set.has(v) ? set.delete(v) : set.add(v);
  update();
}

/* ---------- View header ---------- */

const keyDate = (key) => new Date(`${key}T12:00:00Z`);
function rangeLabel(from, to) {
  if (to === "9999") return `From ${fmtDate.format(keyDate(from))}`;
  if (from === to) return fmtDate.format(keyDate(from));
  return `${fmtDate.format(keyDate(from))} – ${fmtDate.format(keyDate(to))}`;
}

function renderHead() {
  const today = dayKey.format(new Date());
  const [from, to] = whenRange(state.when);
  let title, date = "";
  if (state.event) title = "Shared event";
  else if (state.saved) [title, date] = ["Saved", "Events you saved in this browser"];
  else if (state.when === "all") [title, date] = ["All upcoming", ""];
  else if (from === to) {
    title = from === today ? "Today" : from === addDays(today, 1) ? "Tomorrow" : fmtDay.format(keyDate(from));
    date = fmtLong.format(keyDate(from));
  } else {
    title = WHEN.find(([k]) => k === state.when)[1];
    date = rangeLabel(from, to);
  }
  $("#view-title").textContent = title;
  $("#view-date").textContent = date;
  $("#count").textContent = plural(filtered.length, "event");
  // Arrows step by the length of what's shown: a day at a time, a week at a time.
  const stepping = !state.event && !state.saved && state.when !== "all" && to !== "9999";
  $("#prev").hidden = $("#next").hidden = !stepping;
  $("#prev").disabled = from <= today;
}

function step(dir) {
  const [from, to] = whenRange(state.when);
  const len = daysBetween(from, to) + 1;
  // A weekend steps to the next weekend, not to the days right after it.
  const by = len >= 2 && len <= 3 && keyDate(to).getUTCDay() === 0 ? 7 : len;
  const today = dayKey.format(new Date());
  let a = addDays(from, dir * by), b = addDays(to, dir * by);
  if (a < today) [a, b] = [today, addDays(today, len - 1)];
  const named = ["today", "tomorrow", "weekend", "week"].find((k) => {
    const [x, y] = whenRange(k);
    return x === a && y === b;
  });
  if (named) state.when = named;
  else Object.assign(state, { when: "custom", from: a, to: b });
  update();
}

function tick() {
  $("#clock").textContent = `${fmtTime.format(new Date())} · Pacific`;
}

/* ---------- List ---------- */

const sourceName = (id) => data.sources.find((s) => s.id === id)?.name || id;
const prefScore = (e) => (prefs.size ? -(e.tags || []).filter((t) => prefs.has(t)).length : 0);
const byStart = (a, b) => (sort === "prefs" && prefScore(a) - prefScore(b)) || a._start - b._start;

// All-day events, and multi-day ones already under way, have no time to plan around.
function untimed(e, today) {
  return e.all_day || (e._start < Date.now() && (e._day < today || (e._endDay || e._day) > e._day));
}

// Today splits into what's on now, still to come, all day, and (folded) what already ended.
// Later days list their timed events, then all day.
function plan(events) {
  const today = dayKey.format(new Date());
  const now = Date.now();
  const dayOf = (e) => (e._start < now ? today : e._day);
  const days = new Map();
  for (const e of events) {
    const k = dayOf(e);
    if (!days.has(k)) days.set(k, []);
    days.get(k).push(e);
  }
  const keys = [...days.keys()].sort();
  const single = keys.length <= 1 && !state.saved && whenRange(state.when)[0] === whenRange(state.when)[1];
  const out = [];
  for (const k of keys) {
    const list = days.get(k);
    if (!single) out.push({ day: k, n: list.length });
    const done = list.filter((e) => statusOf(e, now) === "done");
    const allDay = list.filter((e) => !done.includes(e) && untimed(e, today));
    const timed = list.filter((e) => !done.includes(e) && !allDay.includes(e)).sort(byStart);
    if (k === today) {
      const live = timed.filter((e) => e._start <= now);
      const soon = timed.filter((e) => e._start > now);
      if (live.length) out.push({ section: "Happening now", n: live.length, cls: "now" }, ...live.map((e) => ({ e })));
      if (soon.length) out.push({ section: "Still to come", n: soon.length }, ...soon.map((e) => ({ e })));
    } else {
      out.push(...timed.map((e) => ({ e })));
    }
    if (allDay.length) out.push({ section: "All day", n: allDay.length }, ...allDay.sort(byStart).map((e) => ({ e, row: true })));
    if (done.length) out.push({ earlier: done.sort(byStart) });
  }
  return out;
}

function renderMore() {
  const frag = document.createDocumentFragment();
  let shown = 0;
  while (rendered < items.length && shown < PAGE) {
    const it = items[rendered++];
    // One malformed event from a scraper must not take the rest of the list down with it.
    try {
      if (it.day) {
        const today = dayKey.format(new Date());
        const big = it.day === today ? "Today" : it.day === addDays(today, 1) ? "Tomorrow" : fmtDay.format(keyDate(it.day));
        const h = document.createElement("div");
        h.className = "day";
        h.innerHTML = `<h2></h2><span></span>`;
        h.querySelector("h2").textContent = big;
        h.querySelector("span").textContent = `${fmtDate.format(keyDate(it.day))} · ${plural(it.n, "event")}`;
        frag.append(h);
      } else if (it.section) {
        const h = document.createElement("div");
        h.className = `section ${it.cls || ""}`;
        h.innerHTML = `<span></span><span class="n"></span>`;
        h.firstChild.textContent = it.section;
        h.lastChild.textContent = it.n;
        frag.append(h);
      } else if (it.earlier) {
        const box = document.createElement("details");
        box.className = "earlier";
        box.innerHTML = `<summary><b>Earlier today</b><small></small><small>Past plans, tucked away.</small></summary>`;
        box.querySelector("small").textContent = plural(it.earlier.length, "ended event");
        box.append(...it.earlier.map((e) => card(e)));
        frag.append(box);
      } else {
        frag.append(card(it.e, it.row));
        shown++;
      }
    } catch (err) {
      console.warn("skipped item", it.e?.id, err);
    }
  }
  $("#list").append(frag);
}

function update() {
  writeHash();
  renderControls();
  filtered = base();
  items = plan(filtered);
  renderHead();
  $("#list").replaceChildren();
  rendered = 0;
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

const WHEN_PHRASE = { today: "today", tomorrow: "tomorrow", weekend: "this weekend", week: "this week", custom: "in those dates", all: "coming up" };

// Before giving up, check whether the same search finds anything on any upcoming date.
function renderEmpty() {
  const box = document.createElement("div");
  box.className = "empty";
  const strong = document.createElement("strong");
  box.append(strong);
  if (state.saved) {
    strong.textContent = "Nothing saved yet.";
    box.append("Tap Save on any event and it shows up here, ready to add to your calendar.");
    $("#list").replaceChildren(box);
    return;
  }
  const wider = state.event ? [] : base(undefined, true);
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

/* ---------- Cards ---------- */

const clock = (ms) => fmtTime.format(new Date(ms)).replace(":00", "");
const PIN = `<svg class="pin" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21z"/><circle cx="12" cy="10" r="2.3"/></svg>`;

function card(e, row = false) {
  const node = $("#card").content.firstElementChild.cloneNode(true);
  const now = Date.now();
  const today = dayKey.format(new Date(now));
  const live = !e.all_day && statusOf(e, now) === "now";
  node.classList.toggle("row", row);
  node.classList.toggle("now", live && !untimed(e, today));
  // A midnight-to-midnight listing would read "12 AM – 12 AM".
  const endClock = e.end && clock(e._end) !== clock(e._start) ? clock(e._end) : "";
  const time = node.querySelector(".time");
  if (e.all_day) time.textContent = "All day";
  else if (e._start < now && e._day < today) time.innerHTML = `Ongoing<small>until ${e.end ? fmtDate.format(new Date(e._end)) : ""}</small>`;
  else time.innerHTML = `${fmtTime.format(new Date(e._start))}${endClock ? `<small>– ${fmtTime.format(new Date(e._end))}</small>` : ""}`;
  if (live && !row && !untimed(e, today)) time.append(Object.assign(document.createElement("span"), { className: "live-pill", textContent: "Happening now" }));

  const a = node.querySelector(".title");
  a.textContent = e.title;
  if (e.url) a.href = e.url;

  const whereEl = node.querySelector(".where");
  const place = e.online ? "" : e.venue || e.address || e.city || "";
  const at = [e.online ? "Online" : e.region === CAMPUS ? "On campus" : e.region === "Berkeley" ? "" : e.city || e.region];
  if (place) {
    whereEl.innerHTML = PIN;
    const map = document.createElement("a");
    map.className = "map";
    map.textContent = place;
    map.title = "Open in Google Maps";
    const query = e.lat != null ? `${e.lat},${e.lng}` : [e.venue, e.address || e.city].filter(Boolean).join(", ");
    Object.assign(map, { href: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`, target: "_blank", rel: "noopener" });
    whereEl.append(map);
  }
  if (row) {
    if (e.free === true) at.push("Free admission");
    if (e._endDay && e._endDay > e._day) at.push(`Through ${fmtDate.format(new Date(e._end - 1))}`);
  }
  const rest = at.filter((x) => x && x !== place).join(" · ");
  if (rest) whereEl.append(`${place ? " · " : ""}${rest}`);
  if (!whereEl.textContent) whereEl.remove();

  // A concert at a big venue a train gets you to: a poster card that leads with the way there.
  if (e.big_show) {
    node.classList.add("big");
    a.before(Object.assign(document.createElement("span"), { className: "kicker", textContent: `🎤 Big show${e.city ? ` · ${e.city}` : ""}` }));
    if (e.transit) node.querySelector(".desc").before(Object.assign(document.createElement("p"), { className: "transit", textContent: `🚆 ${e.transit}` }));
  }
  if (e.reports?.length) {
    const reported = node.querySelector(".reported");
    reported.textContent = "⚠ Reported by visitors (unverified): " + e.reports
      .map((r) => (r.details ? `${r.kind}: ${r.details}` : r.kind)).join(" · ");
    reported.hidden = false;
  }
  node.querySelector(".desc").textContent = e.description || "";

  const badges = node.querySelector(".badges");
  const add = (text, cls = "") => badges.append(Object.assign(document.createElement("span"), { className: `badge ${cls}`, textContent: text }));
  const topics = e.tags?.filter((t) => t !== FOOD).slice(0, 2) || [];
  topics.forEach((t) => add(t));
  if (e.free === true) add("Free admission", "free");
  if (e.tags?.includes(FOOD)) add("🍴 Free food", "food");
  (e.access || []).filter((x) => !/^free$/i.test(x)).forEach((x) => add(x, "free"));
  if (e.repeats) add(`Repeats · ${e.repeats} dates`);
  // "via" the host and every place it's listed, each linking there.
  const listings = e.listings?.length ? e.listings
    : [{ source: e.source, url: e.url, name: e.source === "feeds" ? e.host : null }];
  const via = document.createElement("span");
  via.className = "via";
  const names = new Set();
  const parts = [];
  if (e.host) {
    names.add(e.host);
    parts.push(document.createTextNode(e.host));
  }
  for (const l of listings) {
    const label = l.name || sourceName(l.source);
    if (names.has(label)) continue;
    names.add(label);
    const link = Object.assign(document.createElement("a"), { textContent: label, title: `See it on ${label}` });
    if (l.url) Object.assign(link, { href: l.url, target: "_blank", rel: "noopener" });
    parts.push(link);
  }
  (e.also_on || []).map(sourceName).filter((n) => !names.has(n)).forEach((n) => { names.add(n); parts.push(document.createTextNode(n)); });
  if (parts.length) {
    via.append("via ");
    parts.forEach((p, i) => via.append(...(i ? [" · ", p] : [p])));
    badges.append(via);
  }

  const img = node.querySelector(".thumb");
  if (e.image && !row) img.src = e.image; else img.remove();
  img.onerror = () => img.remove();

  const save = node.querySelector(".save");
  const tomine = node.querySelector(".tomine");
  const showSaved = () => {
    const on = saved.has(e.id);
    save.setAttribute("aria-pressed", on);
    save.querySelector("span").textContent = on ? "Saved" : "Save";
    save.title = on ? "Remove from your Lo-Cal calendar" : "Save to your Lo-Cal calendar";
    tomine.textContent = on ? "✓ In my Lo-Cal calendar" : "Add to my Lo-Cal calendar";
  };
  save.onclick = tomine.onclick = () => { toggleSave(e.id); showSaved(); };
  showSaved();

  const end = endOf(e);
  const calPlace = e.address || e.venue || "";
  const details = `${e.description || ""}\n\n${e.url || ""}`.trim().slice(0, 1500);
  node.querySelector(".gcal").href = `https://calendar.google.com/calendar/render?${new URLSearchParams({
    action: "TEMPLATE", text: e.title, dates: `${icsDate(e._start)}/${icsDate(end)}`, details, location: calPlace })}`;
  node.querySelector(".ocal").href = `https://outlook.live.com/calendar/0/action/compose?${new URLSearchParams({
    subject: e.title, startdt: new Date(e._start).toISOString(), enddt: new Date(end).toISOString(),
    body: details, location: calPlace })}`;
  node.querySelector(".ics").onclick = () => downloadIcs([e], e.title);
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
    setTimeout(() => { share.textContent = "Copy link to event"; }, 1800);
  };
  if (data.forms?.report_prefill) {
    const flag = node.querySelector(".flag");
    // The build attaches the report to its event by the [id] at the end.
    const label = `${e.title} (${fmtDate.format(new Date(e._start))}) [${e.id}]`;
    flag.href = data.forms.report_prefill.replace("EVENT", encodeURIComponent(label));
    flag.hidden = false;
  }
  return node;
}

/* ---------- Calendar export ---------- */

function icsDate(ms) {
  return new Date(ms).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

function icsEscape(s) {
  return (s || "").replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/[,;]/g, (c) => `\\${c}`);
}

// One file however many events: calendar apps import it in a single step.
function downloadIcs(events, name) {
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Lo-Cal//berkeley events//EN", "X-WR-CALNAME:Lo-Cal"];
  for (const e of events) {
    lines.push("BEGIN:VEVENT", `UID:${e.id}@lo-cal`, `DTSTAMP:${icsDate(Date.now())}`,
      `DTSTART:${icsDate(e._start)}`, `DTEND:${icsDate(endOf(e))}`, `SUMMARY:${icsEscape(e.title)}`,
      `LOCATION:${icsEscape(e.address || e.venue || "")}`,
      `DESCRIPTION:${icsEscape(`${e.description || ""}\n\n${e.url || ""}`)}`,
      ...(e.url ? [`URL:${e.url}`] : []), "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\r\n")], { type: "text/calendar" }));
  a.download = `${name.replace(/[^\w]+/g, "-").slice(0, 50)}.ics`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ---------- My calendar ---------- */

const slug = (t) => t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const savedEvents = () => data.events.filter((e) => saved.has(e.id) && statusOf(e) !== "done").sort((a, b) => a._start - b._start);

function renderSavedCount() {
  $("#saved-n").textContent = savedEvents().length;
}

// The build writes one feed per filter combination (scraper/ics.py): f/<type>.<location>.<cost>.ics.
function feedFor() {
  const types = [...state.topics].filter((t) => t !== FOOD);
  const regions = [...state.regions];
  if (types.length > 1 || regions.length > 1) return null;
  const cost = state.free && state.topics.has(FOOD) ? "free-food" : state.free ? "free" : state.topics.has(FOOD) ? "food" : "any";
  const name = [types[0], regions[0] === CAMPUS ? "On campus" : regions[0],
    { any: "", free: "Free admission", food: "Free food", "free-food": "Free admission + free food" }[cost]].filter(Boolean).join(" · ");
  return { file: `data/cal/f/${types[0] ? slug(types[0]) : "all"}.${regions[0] ? slug(regions[0]) : "all"}.${cost}.ics`, name: name || "Every Berkeley event" };
}

function renderCalDialog() {
  const kind = document.querySelector("input[name=calkind]:checked").value;
  const evs = savedEvents();
  $("#saved-sum").textContent = `${plural(evs.length, "event")} · one file with all of them`;
  const feed = feedFor();
  $("#feed-sum").textContent = feed ? `${feed.name} · new events arrive on their own` : "Built from your filters. New events arrive on their own.";
  const google = $("#cal-google"), other = $("#cal-other"), note = $("#feed-note");
  note.hidden = true;
  google.classList.remove("disabled");
  other.classList.remove("disabled");
  google.onclick = other.onclick = null;
  if (kind === "saved") {
    google.querySelector("span").textContent = "Add to Google Calendar";
    // Google can't open a file from a link: download it, then open Google's import page.
    google.href = "https://calendar.google.com/calendar/u/0/r/settings/export";
    google.onclick = () => downloadIcs(evs, "lo-cal-saved");
    other.removeAttribute("href");
    other.onclick = () => downloadIcs(evs, "lo-cal-saved");
    other.querySelector("span").textContent = "Apple, Outlook, or another calendar";
    if (!evs.length) {
      note.textContent = "Save events first: tap Save on any event.";
      note.hidden = false;
      google.classList.add("disabled");
      other.classList.add("disabled");
    }
    $("#cal-privacy span").textContent = "Your saves stay in this browser; nothing is sent anywhere. The file is a one-time copy: add it again after saving more, or subscribe to a custom feed to stay in sync.";
  } else {
    google.querySelector("span").textContent = "Connect Google Calendar";
    other.querySelector("span").textContent = "Apple, Outlook, or another calendar";
    if (!feed) {
      note.textContent = "A feed follows one event type and one location. Pick at most one of each in the filters.";
      note.hidden = false;
      google.classList.add("disabled");
      other.classList.add("disabled");
    } else {
      const url = new URL(feed.file, location.href).href;
      const webcal = url.replace(/^https?:/, "webcal:");
      google.href = `https://calendar.google.com/calendar/render?cid=${encodeURIComponent(webcal)}`;
      other.href = webcal;
      if (state.q || state.when !== DEFAULT_WHEN || state.status) {
        note.textContent = "Search words, dates and status aren't part of a feed: it holds every upcoming event that matches.";
        note.hidden = false;
      }
    }
    $("#cal-privacy span").textContent = "Feeds are public files, the same for everyone. Subscribing sends nothing about you, and your calendar app checks for new events every few hours.";
  }
}

function openCal() {
  if (!savedEvents().length && feedFor()) document.querySelector("input[name=calkind][value=feed]").checked = true;
  renderCalDialog();
  $("#cal-dlg").showModal();
}

/* ---------- Custom dates ---------- */

let pick = { a: "", b: "", month: "" };

function openDates() {
  const today = dayKey.format(new Date());
  pick = state.when === "custom" && state.from
    ? { a: state.from, b: state.to === "9999" ? "" : state.to, month: state.from.slice(0, 7) }
    : { a: "", b: "", month: today.slice(0, 7) };
  renderDates();
  $("#dates-dlg").showModal();
}

function renderDates() {
  const today = dayKey.format(new Date());
  const [y, m] = pick.month.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1, 1, 12));
  $("#cal-month").textContent = fmtMonth.format(first);
  $("#cal-prev").disabled = pick.month <= today.slice(0, 7);
  const start = addDays(`${pick.month}-01`, -first.getUTCDay());
  const [lo, hi] = pick.b && pick.b < pick.a ? [pick.b, pick.a] : [pick.a, pick.b || pick.a];
  const cells = ["S", "M", "T", "W", "T", "F", "S"].map((d) => Object.assign(document.createElement("span"), { className: "dow", textContent: d }));
  for (let i = 0; i < 42; i++) {
    const k = addDays(start, i);
    const b = Object.assign(document.createElement("button"), { type: "button", textContent: Number(k.slice(8)) });
    b.classList.toggle("out", k.slice(0, 7) !== pick.month);
    b.disabled = k < today;
    b.classList.toggle("end", k === lo || k === hi);
    b.classList.toggle("in", !!lo && k > lo && k < hi);
    b.setAttribute("aria-label", fmtLong.format(keyDate(k)));
    b.onclick = () => {
      if (!pick.a || pick.b) pick = { ...pick, a: k, b: "" };
      else pick = { ...pick, ...(k < pick.a ? { a: k, b: pick.a } : { b: k }) };
      renderDates();
    };
    cells.push(b);
  }
  $("#cal-grid").replaceChildren(...cells);
  if (!lo) {
    $("#range-text").textContent = "Pick a start date";
    $("#range-days").textContent = "Then an end date, or apply for one day";
  } else {
    $("#range-text").textContent = `${rangeLabel(lo, hi)}, ${fmtYear.format(keyDate(hi))}`;
    $("#range-days").textContent = `${plural(daysBetween(lo, hi) + 1, "day")} · Pacific time`;
  }
  $("#apply-dates").disabled = !lo;
}

function shiftMonth(n) {
  const [y, m] = pick.month.split("-").map(Number);
  pick.month = new Date(Date.UTC(y, m - 1 + n, 1)).toISOString().slice(0, 7);
  renderDates();
}

/* ---------- Preferences ---------- */

function renderPrefs() {
  const list = [...prefs];
  $("#pref-summary").textContent = list.length
    ? `${list.join(", ")}. Make discoveries more you.`
    : "Pick what you're into and sort by it. Make discoveries more you.";
  $("#pref-grid").replaceChildren(...data.topics.map((t) => {
    const row = document.createElement("label");
    row.className = "check";
    const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: prefs.has(t) });
    box.onchange = () => {
      prefs.has(t) ? prefs.delete(t) : prefs.add(t);
      store(PREFS_KEY, [...prefs]);
      if (prefs.size && sort !== "prefs") setSort("prefs");
      else update();
      renderPrefs();
    };
    row.append(box, ` ${TOPIC_EMOJI[t] || ""} ${t}`);
    return row;
  }));
}

function setSort(v) {
  sort = v;
  store(SORT_KEY, v);
  $("#sort").value = v;
  update();
}

/* ---------- Boot ---------- */

function relTime(iso) {
  const mins = Math.round((Date.now() - new Date(iso)) / 60000);
  if (mins < 60) return `${Math.max(mins, 1)} min ago`;
  if (mins < 48 * 60) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} days ago`;
}

function setDrawer(open) {
  $("#sidebar").classList.toggle("open", open);
  $("#scrim").hidden = !open;
}

document.addEventListener("click", (ev) => {
  for (const d of document.querySelectorAll("details.addcal[open], details.dd[open]")) {
    if (!d.contains(ev.target) || ev.target.closest(".calmenu")) d.open = false;
  }
});

async function boot() {
  readHash();
  $("#q").value = state.q;
  let t;
  $("#q").addEventListener("input", (ev) => {
    clearTimeout(t);
    t = setTimeout(() => { state.q = ev.target.value.trim(); state.saved = false; update(); }, 120);
  });
  $("#search").onsubmit = (ev) => {
    ev.preventDefault();
    clearTimeout(t);
    state.q = $("#q").value.trim();
    state.saved = false;
    update();
    if (matchMedia("(pointer: coarse)").matches) $("#q").blur();
  };
  addEventListener("keydown", (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") {
      ev.preventDefault();
      $("#q").focus();
      $("#q").select();
    } else if (ev.key === "Escape") setDrawer(false);
  });
  $("#free").onchange = () => { state.free = !state.free; update(); };
  $("#food").onchange = () => toggle(state.topics, FOOD);
  $("#campus").onchange = () => {
    // On campus is a location of its own: it replaces the Where picks, and they replace it.
    const on = !state.regions.has(CAMPUS);
    state.regions.clear();
    if (on) state.regions.add(CAMPUS);
    update();
  };
  $("#event-status").onchange = (ev) => { state.status = ev.target.value; update(); };
  $("#sort").value = sort;
  $("#sort").onchange = (ev) => {
    if (ev.target.value === "prefs" && !prefs.size) $("#pref-dlg").showModal();
    setSort(ev.target.value);
  };
  $("#reset").onclick = () => {
    Object.assign(state, { event: "", saved: false, when: DEFAULT_WHEN, from: "", to: "", free: false, status: "" });
    state.topics.clear(); state.regions.clear();
    update();
  };
  $("#prev").onclick = () => step(-1);
  $("#next").onclick = () => step(1);
  $("#open-filters").onclick = () => setDrawer(true);
  $("#side-close").onclick = $("#scrim").onclick = () => setDrawer(false);
  $("#mycal").onclick = $("#setup-cal").onclick = openCal;
  for (const r of document.querySelectorAll("input[name=calkind]")) r.onchange = renderCalDialog;
  $("#edit-prefs").onclick = () => $("#pref-dlg").showModal();
  $("#pref-clear").onclick = () => {
    prefs.clear();
    store(PREFS_KEY, []);
    renderPrefs();
    setSort("time");
  };
  $("#cal-prev").onclick = () => shiftMonth(-1);
  $("#cal-next").onclick = () => shiftMonth(1);
  $("#clear-dates").onclick = () => {
    pick = { ...pick, a: "", b: "" };
    renderDates();
    if (state.when === "custom") {
      state.when = DEFAULT_WHEN;
      update();
    }
  };
  $("#apply-dates").onclick = () => {
    const [lo, hi] = pick.b && pick.b < pick.a ? [pick.b, pick.a] : [pick.a, pick.b || pick.a];
    Object.assign(state, { when: "custom", from: lo, to: hi, saved: false });
    $("#dates-dlg").close();
    update();
  };
  for (const dlg of document.querySelectorAll("dialog")) {
    dlg.addEventListener("click", (ev) => {
      // A click on the backdrop lands on the dialog itself.
      if (ev.target === dlg || ev.target.closest("[data-close]")) dlg.close();
    });
  }
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
  tick();
  setInterval(tick, 30_000);

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
  renderSavedCount();
  renderPrefs();

  $("#updated").textContent = `Updated ${relTime(data.generated_at)}`;
  const notes = data.sources.filter((s) => s.health !== "ok" && !(s.health === "off" && s.count)).map((s) =>
    `${s.name} (${s.health === "off" ? "not connected" : `having trouble; showing results from ${s.last_ok ? relTime(s.last_ok) : "earlier"}`})`);
  $("#status").textContent = notes.length ? `Also: ${notes.join(", ")}.` : "";

  new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && rendered < items.length) renderMore();
  }, { rootMargin: "800px" }).observe($("#sentinel"));

  // A shared link pasted into an open tab, or the header's Saved link, only changes the hash.
  addEventListener("hashchange", () => { readHash(); $("#q").value = state.q; update(); });
  update();
}

boot();
