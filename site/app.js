"use strict";

const TZ = "America/Los_Angeles";
const PAGE = 60;
const WHEN = [
  ["today", "Today"], ["tomorrow", "Tomorrow"], ["weekend", "This weekend"],
  ["week", "Next 7 days"], ["all", "Everything"],
];
const TOPIC_EMOJI = {
  "AI & Tech": "🤖", "Startups": "🚀", "Hackathons": "🛠️", "Career": "💼", "Talks": "🎤",
  "Social": "🎉", "Arts & Music": "🎨", "Sports & Wellness": "🏃", "Community": "🤝",
  "Free food": "🍕",
};

const $ = (s) => document.querySelector(s);
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const weekdayOf = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short" });
const fmtTime = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
const fmtDay = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "long" });
const fmtDate = new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "short", day: "numeric" });

let data = { events: [], sources: [], topics: [], regions: [] };
let state = { q: "", when: "week", topics: new Set(), regions: new Set(), free: false, hide: new Set() };
let filtered = [];
let rendered = 0;
let lastDay = null;

/* ---------- URL state ---------- */

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.q = p.get("q") || "";
  state.when = WHEN.some(([k]) => k === p.get("when")) ? p.get("when") : "week";
  state.topics = new Set((p.get("t") || "").split(",").filter(Boolean));
  state.regions = new Set((p.get("r") || "").split(",").filter(Boolean));
  state.free = p.get("free") === "1";
  state.hide = new Set((p.get("hide") || "").split(",").filter(Boolean));
}

function writeHash() {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.when !== "week") p.set("when", state.when);
  if (state.topics.size) p.set("t", [...state.topics].join(","));
  if (state.regions.size) p.set("r", [...state.regions].join(","));
  if (state.free) p.set("free", "1");
  if (state.hide.size) p.set("hide", [...state.hide].join(","));
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
    !state.hide.has(e.source) &&
    matchesWhen(e, range) &&
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

  const forTopics = base("topics");
  $("#topics").replaceChildren(...data.topics.map((t) => {
    const n = forTopics.filter((e) => e.tags?.includes(t)).length;
    return chip(`${TOPIC_EMOJI[t] || ""} ${t}`, state.topics.has(t), n, () => toggle(state.topics, t));
  }));

  const forRegions = base("regions");
  $("#regions").replaceChildren(...data.regions.map((r) => {
    const n = forRegions.filter((e) => e.region === r).length;
    const title = r === "Campus" ? "On or right next to campus" : "";
    return chip(r === "Campus" ? "📍 Campus" : r, state.regions.has(r), n, () => toggle(state.regions, r), title);
  }).filter((b) => b.querySelector(".n").textContent !== "0" || b.getAttribute("aria-pressed") === "true"));

  $("#free").setAttribute("aria-pressed", state.free);

  const counts = {};
  data.events.forEach((e) => { counts[e.source] = (counts[e.source] || 0) + 1; });
  $("#sources").replaceChildren(...data.sources.filter((s) => counts[s.id]).map((s) => {
    const l = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = !state.hide.has(s.id);
    input.onchange = () => { input.checked ? state.hide.delete(s.id) : state.hide.add(s.id); update(); };
    l.append(input, s.name);
    const n = document.createElement("span");
    n.className = "n";
    n.textContent = counts[s.id];
    l.append(n);
    return l;
  }));
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
  const where = [e.online ? "Online" : e.venue || e.address || e.city, e.host].filter(Boolean);
  node.querySelector(".where").textContent = where.join(" · ");
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
  e.tags?.filter((t) => t !== "Free food").slice(0, 2).forEach((t) => add(t));
  [e.source, ...(e.also_on || [])].forEach((s) => add(sourceName(s), "src"));
  const img = node.querySelector(".thumb");
  if (e.image) img.src = e.image; else img.remove();
  img.onerror = () => img.remove();
  node.querySelector(".ical").onclick = () => downloadIcs(e);
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
    frag.append(card(e));
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
    $("#list").innerHTML = `<div class="empty"><strong>Nothing here — yet.</strong>Try a wider date range or fewer filters.</div>`;
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
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//bearly//berkeley events//EN", "BEGIN:VEVENT",
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

async function boot() {
  readHash();
  $("#q").value = state.q;
  let t;
  $("#q").addEventListener("input", (ev) => {
    clearTimeout(t);
    t = setTimeout(() => { state.q = ev.target.value.trim(); update(); }, 120);
  });
  $("#free").onclick = () => { state.free = !state.free; update(); };
  document.addEventListener("click", (ev) => {
    const menu = $(".sources-menu");
    if (menu.open && !menu.contains(ev.target)) menu.open = false;
  });

  const res = await fetch("data/events.json", { cache: "no-cache" });
  data = await res.json();
  for (const e of data.events) {
    e._start = Date.parse(e.start);
    e._end = e.end ? Date.parse(e.end) : null;
    e._day = dayKey.format(new Date(e._start));
    e._endDay = e._end ? dayKey.format(new Date(e._end - 1)) : null;
    e._text = [e.title, e.host, e.venue, e.address, e.description, e.region, ...(e.tags || [])]
      .join(" ").toLowerCase();
  }

  const live = data.sources.filter((s) => s.ok).map((s) => s.name);
  $("#updated").textContent = `Updated ${relTime(data.generated_at)} · ${data.events.length.toLocaleString()} upcoming events from ${live.join(", ")}.`;
  const off = data.sources.filter((s) => !s.ok).map((s) => `${s.name} (${s.skipped ? "not connected" : "temporarily unavailable"})`);
  $("#status").textContent = off.length ? `Not included right now: ${off.join(", ")}.` : "";

  const ro = new ResizeObserver(() =>
    document.documentElement.style.setProperty("--controls-h", `${$("#controls").offsetHeight}px`));
  ro.observe($("#controls"));
  new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && rendered < filtered.length) renderMore();
  }, { rootMargin: "800px" }).observe($("#sentinel"));

  update();
}

boot();
