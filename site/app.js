"use strict";

const TZ = "America/Los_Angeles";
const PAGE = 60;
const WHEN = [
  ["today", "Today (not started)"], ["tomorrow", "Tomorrow"], ["weekend", "This weekend"],
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
  ["Social", "Arts & Music", "Sports & Wellness", "Community", "Free food"],
];

const $ = (s) => document.querySelector(s);
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const weekdayOf = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short" });
const fmtTime = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
const fmtDay = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "long" });
const fmtDate = new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "short", day: "numeric" });

let data = { events: [], sources: [], topics: [], regions: [] };
let state = { q: "", when: "week", from: "", to: "", topics: new Set(), regions: new Set(), free: false, src: new Set() };
let filtered = [];
let rendered = 0;
let lastDay = null;

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
}

function writeHash() {
  const p = new URLSearchParams();
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

function matchesSearch(e, terms) {
  return terms.every((t) => e._text.includes(t));
}

function base(skip) {
  const range = whenRange(state.when);
  const terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
  const now = Date.now();
  return data.events.filter((e) =>
    (e._end || e._start + 2 * 3600e3) > now &&
    (skip === "src" || !state.src.size || state.src.has(e.source) || e.also_on?.some((s) => state.src.has(s))) &&
    matchesWhen(e, range) &&
    // Today means what you can still go to; all-day events count as not started.
    (state.when !== "today" || e._start > now || (e.all_day && e._day === range[0])) &&
    matchesSearch(e, terms) &&
    (!state.free || e.free === true) &&
    (skip === "regions" || !state.regions.size || state.regions.has(e.region)) &&
    (skip === "topics" || !state.topics.size || e.tags?.some((t) => state.topics.has(t))));
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
  const rows = [TOPIC_GROUPS[0], [...TOPIC_GROUPS[1], ...data.topics.filter((t) => !grouped.includes(t))]];
  rows.forEach((row, i) => {
    $(`#topics-${i}`).replaceChildren(...row.filter((t) => data.topics.includes(t)).map((t) => {
      const n = forTopics.filter((e) => e.tags?.includes(t)).length;
      return chip(`${TOPIC_EMOJI[t] || ""} ${t}`, state.topics.has(t), n, () => toggle(state.topics, t));
    }));
  });

  const forRegions = base("regions");
  $("#regions").replaceChildren(...data.regions.map((r) => {
    const n = forRegions.filter((e) => e.region === r).length;
    const title = r === "Campus" ? "On or right next to campus" : "";
    return chip(r === "Campus" ? "📍 Campus" : r, state.regions.has(r), n, () => toggle(state.regions, r), title);
  }));

  const forSources = base("src");
  // Sources with no events at all (not connected yet) are left out; the rest always show.
  $("#sources").replaceChildren(...data.sources.filter((s) => s.count).map((s) => {
    const n = forSources.filter((e) => e.source === s.id || e.also_on?.includes(s.id)).length;
    return chip(s.name, state.src.has(s.id), n, () => toggle(state.src, s.id));
  }));

  $("#free").setAttribute("aria-pressed", state.free);
  $("#clear").hidden = !(state.topics.size || state.regions.size || state.src.size || state.free);
  renderShowing();
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
  node.querySelector(".time").innerHTML = e.all_day
    ? "All day"
    : started && e._day < dayKey.format(new Date())
      ? `Ongoing<small>until ${e.end ? fmtDate.format(new Date(e._end)) : ""}</small>`
      : `${fmtTime.format(new Date(e._start)).replace(":00", "")}${
        e.end ? `<small>– ${fmtTime.format(new Date(e._end)).replace(":00", "")}</small>` : ""}`;
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
  e.tags?.filter((t) => t !== "Free food").slice(0, 2).forEach((t) => add(t));
  // One badge per place the event is listed, each linking there; sources seen without a
  // link of their own (an email, a Slack post) get a plain badge.
  const listings = e.listings?.length ? e.listings
    : [{ source: e.source, url: e.url, name: e.source === "feeds" ? e.host : null }];
  const linked = new Set(listings.map((l) => l.source));
  const named = new Set();
  for (const l of listings) {
    const label = l.name || sourceName(l.source);
    if (named.has(label)) continue;
    named.add(label);
    const a = document.createElement("a");
    a.className = "badge src";
    a.textContent = label;
    a.title = `See it on ${a.textContent}`;
    if (l.url) Object.assign(a, { href: l.url, target: "_blank", rel: "noopener" });
    badges.append(a);
  }
  (e.also_on || []).filter((s) => !linked.has(s)).forEach((s) => add(sourceName(s), "src"));
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
  if (data.repo) {
    const flag = node.querySelector(".flag");
    // The bot finds the event by the [id] at the end. GitHub's issue page drops prefilled form
    // fields but keeps the title, so on GitHub the id rides there.
    const label = `${e.title} (${fmtDate.format(new Date(e._start))}) [${e.id}]`;
    const q = new URLSearchParams({ template: "report-event.yml", title: `Report: ${label}` });
    flag.href = data.forms?.report_prefill
      ? data.forms.report_prefill.replace("EVENT", encodeURIComponent(label))
      : `https://github.com/${data.repo}/issues/new?${q}`;
    flag.hidden = false;
  }
  return node;
}

function renderMore() {
  const list = $("#list");
  const frag = document.createDocumentFragment();
  for (const e of filtered.slice(rendered, rendered + PAGE)) {
    const day = e._start < Date.now() ? dayKey.format(new Date()) : e._day;
    if (day !== lastDay) {
      lastDay = day;
      const [big, small] = dayLabel(day);
      const n = filtered.filter((x) => (x._start < Date.now() ? dayKey.format(new Date()) : x._day) === day).length;
      const h = document.createElement("div");
      h.className = "day";
      h.innerHTML = `<h2>${big}</h2><span>${small} · ${n} event${n === 1 ? "" : "s"}</span>`;
      frag.append(h);
    }
    // One malformed event from a scraper must not take the rest of the list down with it.
    try {
      frag.append(card(e));
    } catch (err) {
      console.warn("skipped event", e.id, err);
    }
  }
  rendered += PAGE;
  list.append(frag);
}

function update() {
  writeHash();
  renderControls();
  filtered = base();
  $("#count").textContent = `${filtered.length.toLocaleString()} event${filtered.length === 1 ? "" : "s"}`;
  $("#list").replaceChildren();
  rendered = 0;
  lastDay = null;
  if (!filtered.length) {
    $("#list").innerHTML = `<div class="empty"><strong>No events match.</strong>Try a wider date range or fewer filters.</div>`;
    return;
  }
  renderMore();
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
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Bearly//berkeley events//EN", "BEGIN:VEVENT",
    `UID:${e.id}@bearly`, `DTSTAMP:${icsDate(Date.now())}`,
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
  $("#from").onchange = (ev) => { state.from = ev.target.value; update(); };
  $("#to").onchange = (ev) => { state.to = ev.target.value; update(); };
  $("#clear").onclick = () => {
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
    e._text = [e.title, e.host, e.venue, e.address, e.description, e.region, ...(e.tags || [])]
      .join(" ").toLowerCase();
  }

  const live = data.sources.filter((s) => s.count > 0).map((s) => `${s.name} (${s.count})`);
  $("#updated").textContent = `Updated ${relTime(data.generated_at)} · ${data.events.length.toLocaleString()} upcoming events from ${live.join(", ")}.`;
  const notes = data.sources.filter((s) => s.health !== "ok" && !(s.health === "off" && s.count)).map((s) =>
    `${s.name} (${s.health === "off" ? "not connected" : `having trouble; showing results from ${s.last_ok ? relTime(s.last_ok) : "earlier"}`})`);
  $("#status").textContent = notes.length ? `Also: ${notes.join(", ")}.` : "";

  new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && rendered < filtered.length) renderMore();
  }, { rootMargin: "800px" }).observe($("#sentinel"));

  update();
}

boot();
