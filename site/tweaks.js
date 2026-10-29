"use strict";

// A floating panel for trying UI variations. It lives in a shadow root so the page's styles
// can't reach it and its styles can't leak into the page; it only touches the page by
// setting attributes and custom properties on <html>, which styles.css reads.
// Open it once with ?ui in the URL; it stays until closed with ×.

(() => {
  const KEY = "bearly-ui";
  const SHOW = "bearly-ui-panel";
  const OPTIONS = [
    { id: "theme", label: "Theme", attr: true, choices: [["auto", "Auto"], ["light", "Light"], ["dark", "Dark"]] },
    { id: "accent", label: "Accent", choices: [["default", "Cal blue"], ["gold", "Gold"], ["green", "Green"], ["rose", "Rose"]] },
    { id: "headings", label: "Headings", attr: true, choices: [["serif", "Serif"], ["sans", "Sans"]] },
    { id: "layout", label: "Events", attr: true, choices: [["cards", "Cards"], ["list", "List"]] },
    { id: "density", label: "Density", attr: true, choices: [["comfortable", "Comfy"], ["compact", "Compact"]] },
    { id: "thumbs", label: "Images", attr: true, choices: [["on", "On"], ["off", "Off"]] },
    { id: "radius", label: "Corners", choices: [["default", "Round"], ["soft", "Soft"], ["square", "Square"]] },
    { id: "width", label: "Width", choices: [["narrow", "Narrow"], ["default", "Normal"], ["wide", "Wide"]] },
  ];
  // [accent, text on accent]
  const ACCENTS = { gold: ["#fdb515", "#14161a"], green: ["#1f7a4d", "#ffffff"], rose: ["#c2410c", "#ffffff"] };
  const RADII = { soft: "8px", square: "2px" };
  const WIDTHS = { narrow: "700px", wide: "1080px" };

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  let prefs = {};
  try { prefs = JSON.parse(store.get(KEY)) || {}; } catch { prefs = {}; }
  // The default is the choice named "default", else the first one.
  const dflt = (o) => (o.choices.find(([v]) => v === "default") || o.choices[0])[0];
  const value = (o) => prefs[o.id] || dflt(o);

  function apply() {
    const root = document.documentElement;
    for (const o of OPTIONS) {
      if (!o.attr) continue;
      const v = value(o);
      v === dflt(o) ? root.removeAttribute(`data-${o.id}`) : root.setAttribute(`data-${o.id}`, v);
    }
    const accent = ACCENTS[prefs.accent];
    if (accent) {
      root.style.setProperty("--accent", accent[0]);
      root.style.setProperty("--accent-ink", accent[1]);
    } else {
      root.style.removeProperty("--accent");
      root.style.removeProperty("--accent-ink");
    }
    RADII[prefs.radius] ? root.style.setProperty("--radius", RADII[prefs.radius]) : root.style.removeProperty("--radius");
    WIDTHS[prefs.width] ? root.style.setProperty("--wrap", WIDTHS[prefs.width]) : root.style.removeProperty("--wrap");
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
      position: fixed; right: 18px; bottom: 74px; z-index: 2147483647; width: 280px;
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
    .seg { display: flex; background: #f1f1f1; border-radius: 8px; padding: 2px; gap: 2px; }
    .seg button {
      flex: 1; border: 0; background: none; border-radius: 6px; padding: 5px 4px; cursor: pointer;
      font: 500 12px system-ui, sans-serif; color: #3a3d44;
    }
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
        seg.className = "seg";
        seg.append(...o.choices.map(([v, label]) => {
          const b = document.createElement("button");
          b.type = "button";
          b.textContent = label;
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

    fab.onclick = () => { panel.hidden = !panel.hidden; };
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
