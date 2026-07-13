// Status page: health, Ollama models, and the weekly-OAuth reminder card.
import { state } from "./main.js";
import { api } from "./lib/api.js";
import { el, clear } from "./lib/util.js";

const REAUTH_KEY = "ac-last-reauth";
const WEEK_MS = 7 * 24 * 3600 * 1000;

export async function renderStatus(root) {
  root.replaceChildren();          // idempotent: safe when re-invoked (e.g. re-auth button)
  const page = el("div", { class: "page" });
  page.append(el("div", { class: "page-head" }, el("div", {}, [
    el("h1", { text: "Status" }),
    el("p", { class: "muted", text: "Health of the running stack and operational reminders." }),
  ])));
  const grid = el("div", { class: "status-grid" });
  page.append(grid);
  root.append(page);

  const h = state.health || (await api.health().catch(() => null));
  renderGrid(grid, h);

  // subscribe to future health refreshes while on this page
  const cb = (hh) => { if (root.isConnected) renderGrid(grid, hh); };
  state.onHealth.push(cb);
}

function svcCard(name, s) {
  const up = s && s.up;
  const rows = [
    kv("state", up ? "● up" : "● down", up ? "ok" : "bad"),
    s?.latency_ms != null ? kv("latency", s.latency_ms + " ms") : null,
    s?.url ? kv("url", s.url) : null,
    s?.db ? kv("db", s.db) : null,
    s?.error ? kv("error", s.error, "bad") : null,
  ].filter(Boolean);
  return el("div", { class: "status-card card" }, [el("h3", {}, [name]), ...rows]);
}

function kv(k, v, tone) {
  return el("div", { class: "kv" }, [
    el("span", { class: "k", text: k }),
    el("span", { class: "v" + (tone ? " " : ""), style: tone === "ok" ? "color:var(--ok)" : tone === "bad" ? "color:var(--bad)" : "", text: String(v) }),
  ]);
}

function renderGrid(grid, h) {
  clear(grid);
  if (!h) { grid.append(el("div", { class: "empty muted", text: "Health unavailable." })); return; }

  grid.append(svcCard("n8n", h.n8n));
  grid.append(svcCard("Ollama", h.ollama));
  grid.append(svcCard("Postgres", h.postgres));

  // Ollama models
  if (h.ollama?.up) {
    const loaded = new Set(h.ollama.loaded || []);
    const tags = (h.ollama.models || []).map((m) =>
      el("span", { class: "model-tag" + (loaded.has(m) ? " loaded" : ""), title: loaded.has(m) ? "loaded in memory" : "installed", text: m }));
    grid.append(el("div", { class: "status-card card" }, [
      el("h3", {}, ["Ollama models"]),
      tags.length ? el("div", {}, tags) : el("div", { class: "muted", text: "none installed" }),
      el("div", { class: "muted", style: "margin-top:8px;font-size:12px", text: "Green = currently loaded/warm." }),
    ]));
  }

  // Ground-truth availability
  grid.append(el("div", { class: "status-card card" }, [
    el("h3", {}, ["Ground-truth panel"]),
    kv("live Google reads", h.truth_enabled ? "enabled" : "disabled", h.truth_enabled ? "ok" : null),
    el("div", { class: "muted", style: "margin-top:8px;font-size:12px",
      text: h.truth_enabled ? "The Chat page can show live Gmail/Calendar/Tasks state." :
        "Restart the server with ENABLE_TRUTH=1 to compare agent claims against real Google state." }),
  ]));

  // OAuth reminder
  grid.append(oauthCard(h));
}

function oauthCard(h) {
  const last = Number(localStorage.getItem(REAUTH_KEY) || 0);
  const now = Date.now();
  const age = last ? now - last : null;
  const due = !last || age > WEEK_MS;
  const daysLeft = last ? Math.ceil((WEEK_MS - age) / (24 * 3600 * 1000)) : null;

  const status = !last ? "unknown — click after you next sign in"
    : due ? "overdue — re-authorize now"
      : `ok — ~${daysLeft} day(s) left`;

  return el("div", { class: "status-card card oauth-card" }, [
    el("h3", {}, ["⚠ Google OAuth (Testing mode)"]),
    el("p", { class: "muted", style: "font-size:12.5px;margin:0 0 8px", html:
      "Refresh tokens expire every <strong>7 days</strong>. Re-do the three &ldquo;Sign in with Google&rdquo; clicks in n8n before eval runs and demos." }),
    kv("last re-auth", last ? new Date(last).toISOString().slice(0, 10) : "—", due ? "bad" : "ok"),
    kv("status", status, due ? "bad" : "ok"),
    el("div", { style: "display:flex;gap:8px;margin-top:10px;flex-wrap:wrap" }, [
      el("a", { class: "btn sm", href: (h.n8n?.url || "http://localhost:5678") + "/home/credentials", target: "_blank" }, "Open n8n credentials"),
      el("button", { class: "btn sm primary", onclick: (e) => {
        localStorage.setItem(REAUTH_KEY, String(Date.now()));
        renderStatus(document.getElementById("view"));
      } }, "I re-authorized just now"),
    ]),
  ]);
}
