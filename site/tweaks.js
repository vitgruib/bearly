"use strict";

// A floating panel for trying UI variations. It lives in a shadow root so the page's styles
// can't reach it and its styles can't leak into the page; it only touches the page by
// setting attributes and custom properties on <html>, which styles.css reads.
// Open it once with ?ui in the URL; it stays until closed with ×.

(() => {
  const KEY = "bearly-ui";
  const SHOW = "bearly-ui-panel";
  // [family, weight] for "Lo-" in the wordmark; the first is the default. All checked to load from Google Fonts.
  const WORD_FONTS = [
    ["Oleo Script", 700], ["Courgette", 400], ["Kaushan Script", 400], ["Lobster", 400],
    ["Lobster Two", 700], ["Leckerli One", 400], ["Yellowtail", 400], ["Pacifico", 400],
    ["Damion", 400], ["Grand Hotel", 400], ["Satisfy", 400], ["Dancing Script", 700],
    ["Norican", 400], ["Merienda", 700], ["Cookie", 400], ["Great Vibes", 400],
    ["Alex Brush", 400], ["Allura", 400], ["Sacramento", 400], ["Marck Script", 400],
    ["Mr Dafoe", 400], ["Rochester", 400], ["Shrikhand", 400], ["Playball", 400],
    ["Berkshire Swash", 400], ["Sriracha", 400], ["Pattaya", 400], ["Caveat Brush", 400],
    ["Permanent Marker", 400], ["Graduate", 400], ["Bevan", 400], ["Alfa Slab One", 400],
    ["Fugaz One", 400], ["Racing Sans One", 400], ["Titan One", 400], ["Bowlby One", 400],
    ["Righteous", 400], ["Chango", 400], ["Bungee", 400], ["Rubik Mono One", 400],
    ["Abril Fatface", 400], ["Ultra", 400], ["Onest", 700], ["Fraunces", 700],
    ["Instrument Serif", 400],
  ];
  const SITE_FONTS = [
    "Onest", "Inter", "Instrument Sans", "Bricolage Grotesque", "Libre Franklin", "Schibsted Grotesk",
    "Hanken Grotesk", "Geist", "Manrope", "Plus Jakarta Sans", "Figtree", "Archivo",
    "Public Sans", "IBM Plex Sans", "Familjen Grotesk", "Mona Sans", "Albert Sans", "Red Hat Display",
    "DM Sans", "Work Sans", "Nunito Sans", "Outfit", "Space Grotesk", "Sora",
    "Lexend", "Rubik", "Karla", "Barlow",
  ];
  const OPTIONS = [
    { id: "theme", label: "Theme", attr: true, choices: [["auto", "Auto"], ["light", "Light"], ["dark", "Dark"]] },
    { id: "word", label: "Lo- font", font: true, choices: WORD_FONTS.map(([f]) => [f, f]) },
    { id: "site", label: "Site font", font: true, choices: SITE_FONTS.map((f) => [f, f]) },
  ];

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  let prefs = {};
  try { prefs = JSON.parse(store.get(KEY)) || {}; } catch { prefs = {}; }
  // The default is the choice named "default", else the first one.
  const dflt = (o) => (o.choices.find(([v]) => v === "default") || o.choices[0])[0];
  const value = (o) => prefs[o.id] || dflt(o);

  const loaded = new Set(["Onest", "Oleo Script"]); // already linked by the page
  function load(families) {
    const want = families.filter((f) => !loaded.has(f));
    // One stylesheet per batch keeps the URL short; every family/weight pair was checked to exist.
    for (let i = 0; i < want.length; i += 12) {
      const q = want.slice(i, i + 12).map((f) => {
        const w = WORD_FONTS.find(([n]) => n === f);
        loaded.add(f);
        return `family=${f.replace(/ /g, "+")}:wght@${w && !SITE_FONTS.includes(f) ? w[1] : "400;500;600;700"}`;
      });
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = `https://fonts.googleapis.com/css2?${q.join("&")}&display=swap`;
      document.head.append(link);
    }
  }

  function apply() {
    const root = document.documentElement;
    for (const o of OPTIONS) {
      if (!o.attr) continue;
      const v = value(o);
      v === dflt(o) ? root.removeAttribute(`data-${o.id}`) : root.setAttribute(`data-${o.id}`, v);
    }
    const [word, weight] = WORD_FONTS.find(([f]) => f === value(OPTIONS[1]));
    const site = value(OPTIONS[2]);
    const custom = { "--wordmark-font": prefs.word && `"${word}"`, "--wordmark-weight": prefs.word && weight,
      "--display": prefs.site && `"${site}", sans-serif`, "--body": prefs.site && `"${site}", sans-serif` };
    for (const [k, v] of Object.entries(custom)) v ? root.style.setProperty(k, v) : root.style.removeProperty(k);
    load([prefs.word, prefs.site].filter(Boolean));
  }
  apply(); // before first paint: this script loads in <head>

  if (new URLSearchParams(location.search).has("ui")) store.set(SHOW, "1");
  if (!store.get(SHOW)) return;

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    .fab, .panel { font: 13px/1.4 system-ui, -apple-system, sans-serif; color: #16181d; }
    .fab {
      position: fixed; right: 18px; bottom: 18px; z-index: 2147483647;
      width: 46px; height: 46px; border-radius: 50%; border: 0; cursor: pointer;
      background: #16181d; color: #fff; font-size: 18px; box-shadow: 0 6px 24px rgb(0 0 0 / 25%);
    }
    .panel {
      position: fixed; right: 18px; bottom: 74px; z-index: 2147483647; width: min(360px, calc(100vw - 36px));
      max-height: calc(100vh - 100px); overflow-y: auto;
      background: #fff; border: 1px solid #e3e3e3; border-radius: 14px; padding: 12px 14px 14px;
      box-shadow: 0 12px 40px rgb(0 0 0 / 22%);
    }
    .panel[hidden] { display: none; }
    header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    header strong { font-size: 13px; }
    header button { border: 0; background: none; cursor: pointer; color: #6b6f78; font: inherit; padding: 2px 4px; }
    header button:hover { color: #16181d; }
    .opt { margin-top: 9px; }
    .opt span { display: block; font-size: 11px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: #6b6f78; margin-bottom: 4px; }
    .seg { display: flex; flex-wrap: wrap; background: #f1f1f1; border-radius: 8px; padding: 2px; gap: 2px; }
    .seg button {
      flex: 1 0 auto; border: 0; background: none; border-radius: 6px; padding: 5px 4px; cursor: pointer;
      font: 500 12px system-ui, sans-serif; color: #3a3d44;
    }
    .seg.fonts { display: grid; grid-template-columns: 1fr 1fr; max-height: 260px; overflow-y: auto; }
    @media (max-width: 600px) { .panel { max-height: 52vh; } .seg.fonts { max-height: 150px; } } /* keeps the wordmark visible while picking */
    .seg.fonts button { font-size: 15px; text-align: left; padding: 6px 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .seg button[aria-pressed="true"] { background: #fff; color: #16181d; box-shadow: 0 1px 3px rgb(0 0 0 / 15%); }
    footer { display: flex; justify-content: space-between; margin-top: 12px; }
    footer button { border: 0; background: none; cursor: pointer; font: 12px system-ui, sans-serif; color: #6b6f78; text-decoration: underline; padding: 0; }
  `;

  function build() {
    const host = document.createElement("div");
    const shadow = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = CSS;

    const fab = document.createElement("button");
    fab.className = "fab";
    fab.type = "button";
    fab.title = "Try UI options";
    fab.setAttribute("aria-label", "Try UI options");
    fab.textContent = "✦";

    const panel = document.createElement("div");
    panel.className = "panel";
    panel.hidden = true;
    panel.innerHTML = `<header><strong>UI options</strong><button type="button" class="hide" title="Hide this panel (open again with ?ui)">✕</button></header><div class="opts"></div>
      <footer><button type="button" class="reset">Reset to default</button><button type="button" class="copy">Copy settings</button></footer>`;

    const render = () => {
      panel.querySelector(".opts").replaceChildren(...OPTIONS.map((o) => {
        const row = document.createElement("div");
        row.className = "opt";
        const name = document.createElement("span");
        name.textContent = o.label;
        const seg = document.createElement("div");
        seg.className = o.font ? "seg fonts" : "seg";
        seg.append(...o.choices.map(([v, label]) => {
          const b = document.createElement("button");
          b.type = "button";
          b.textContent = o.id === "word" ? `Lo- ${label}` : label;
          b.title = label;
          if (o.font) b.style.fontFamily = `"${v}"`;
          b.setAttribute("aria-pressed", value(o) === v);
          b.onclick = () => {
            v === dflt(o) ? delete prefs[o.id] : (prefs[o.id] = v);
            store.set(KEY, Object.keys(prefs).length ? JSON.stringify(prefs) : null);
            apply();
            render();
          };
          return b;
        }));
        row.append(name, seg);
        return row;
      }));
    };
    render();

    fab.onclick = () => {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) load([...WORD_FONTS.map(([f]) => f), ...SITE_FONTS]); // so each button previews its font
    };
    panel.querySelector(".hide").onclick = () => { store.set(SHOW, null); host.remove(); };
    panel.querySelector(".reset").onclick = () => { prefs = {}; store.set(KEY, null); apply(); render(); };
    panel.querySelector(".copy").onclick = (ev) => {
      navigator.clipboard?.writeText(JSON.stringify(prefs, null, 2));
      ev.target.textContent = "Copied";
      setTimeout(() => { ev.target.textContent = "Copy settings"; }, 1200);
    };

    shadow.append(style, panel, fab);
    document.body.append(host);
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", build) : build();
})();
