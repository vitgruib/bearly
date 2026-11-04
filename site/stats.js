"use strict";

const TZ = "America/Los_Angeles";
const GOATCOUNTER = "https://lo-cal.goatcounter.com";
const $ = (s) => document.querySelector(s);
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const fmtDay = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "short", month: "short", day: "numeric" });

function tile(value, label) {
  const d = document.createElement("div");
  d.className = "tile";
  d.innerHTML = "<strong></strong><span></span>";
  d.querySelector("strong").textContent = value;
  d.querySelector("span").textContent = label;
  return d;
}

// One series per chart: a single color, the number written beside each bar in ink.
function bars(el, rows, unit = "events") {
  const max = Math.max(1, ...rows.map(([, n]) => n));
  el.replaceChildren(...rows.map(([label, n]) => {
    const row = document.createElement("div");
    row.className = "bar";
    row.title = `${label}: ${n.toLocaleString()} ${unit}`;
    row.innerHTML = `<span class="label"></span><span class="track"><span class="fill"></span></span><span class="value"></span>`;
    row.querySelector(".label").textContent = label;
    row.querySelector(".fill").style.width = `${(n / max) * 100}%`;
    row.querySelector(".value").textContent = n.toLocaleString();
    return row;
  }));
}

function counted(events, keysOf) {
  const m = new Map();
  for (const e of events) for (const k of keysOf(e)) m.set(k, (m.get(k) || 0) + 1);
  return m;
}

function relTime(iso) {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso)) / 60000);
  if (mins < 60) return `${Math.max(mins, 1)} min ago`;
  if (mins < 48 * 60) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} days ago`;
}

// GoatCounter's public counter: one JSON file per page path, "TOTAL" for the whole site.
async function views(path) {
  const res = await fetch(`${GOATCOUNTER}/counter/${encodeURIComponent(path)}.json`);
  if (!res.ok) throw new Error(`goatcounter ${res.status}`);
  return (await res.json()).count;
}

async function traffic() {
  // GoatCounter neither counts nor answers a local copy of the site.
  if (/^(localhost|127\.|\[::1\])/.test(location.hostname)) {
    $("#traffic").innerHTML = `<p class="note">Visitor counts show on the live site.</p>`;
    return;
  }
  const base = location.pathname.replace(/[^/]*$/, "");
  const pages = [["TOTAL", "Visits, all pages"], [base, "Events page"], [`${base}about.html`, "How it works"],
    [`${base}stats.html`, "This page"]];
  try {
    const counts = await Promise.all(pages.map(([p]) => views(p).catch(() => "0")));
    $("#traffic").replaceChildren(...pages.map(([, label], i) => tile(counts[i], label)));
  } catch {
    $("#traffic").innerHTML = `<p class="note">Visitor counts aren't available yet.</p>`;
  }
}

async function events() {
  const data = await (await fetch("data/events.json", { cache: "no-cache" })).json();
  const now = Date.now();
  const list = data.events.filter((e) => (e.end ? Date.parse(e.end) : Date.parse(e.start) + 2 * 3600e3) > now);
  const name = Object.fromEntries(data.sources.map((s) => [s.id, s.name]));

  $("#totals").replaceChildren(
    tile(list.length.toLocaleString(), "Upcoming events"),
    tile(data.sources.filter((s) => s.count).length, "Sources with events"),
    tile(list.filter((e) => e.tags?.includes("Free food")).length.toLocaleString(), "With free food"),
    tile(`${Math.round((100 * list.filter((e) => e.access?.length).length) / Math.max(list.length, 1))}%`,
      "Say how to get in"),
  );
  $("#generated").textContent = `Updated ${relTime(data.generated_at)}. Counts include every place an event is listed, so sources add up to more than the total.`;

  const sorted = (m) => [...m].sort((a, b) => b[1] - a[1]);
  bars($("#by-source"), sorted(counted(list, (e) => [e.source, ...(e.also_on || [])])).map(([k, n]) => [name[k] || k, n]));
  const topics = counted(list, (e) => e.tags || []);
  bars($("#by-topic"), data.topics.map((t) => [t, topics.get(t) || 0]));
  const regions = counted(list, (e) => [e.region]);
  bars($("#by-region"), data.regions.map((r) => [r, regions.get(r) || 0]));

  const today = dayKey.format(new Date());
  const days = counted(list, (e) => [dayKey.format(new Date(Date.parse(e.start)))]);
  bars($("#by-day"), Array.from({ length: 14 }, (_, i) => {
    const d = new Date(`${today}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + i);
    return [fmtDay.format(d), days.get(d.toISOString().slice(0, 10)) || 0];
  }));

  const STATUS = { ok: "✓ OK", degraded: "▲ Fewer than usual", failing: "▲ Failing", down: "✕ Down", off: "– Not connected" };
  $("#health").replaceChildren(...data.sources.map((s) => {
    const tr = document.createElement("tr");
    const cells = [s.name, STATUS[s.health] || s.health, s.count.toLocaleString(), relTime(s.last_ok),
      `every ${s.every_hours} h`];
    tr.innerHTML = cells.map((_, i) => `<td${i === 2 ? ' class="num"' : ""}></td>`).join("");
    tr.querySelectorAll("td").forEach((td, i) => { td.textContent = cells[i]; });
    tr.dataset.health = s.health;
    return tr;
  }));
}

traffic();
events().catch((err) => {
  console.error(err);
  $("#totals").innerHTML = `<p class="note">Couldn't load events.json. Refresh to try again.</p>`;
});
