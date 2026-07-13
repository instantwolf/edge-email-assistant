// Router, theme, and shared top-bar health/model state.
import { api } from "./lib/api.js";
import { renderChat } from "./chat.js";
import { renderWorkspace } from "./workspace.js";
import { renderEval } from "./eval.js";
import { renderMetrics } from "./metrics.js";
import { renderStatus } from "./status.js";

const view = document.getElementById("view");
const ROUTES = { chat: renderChat, workspace: renderWorkspace, eval: renderEval, metrics: renderMetrics, status: renderStatus };

// Shared, lightweight app state other modules can read.
export const state = { health: null, onHealth: [] };

// ---- theme ----
const savedTheme = localStorage.getItem("ac-theme");
if (savedTheme) document.documentElement.setAttribute("data-theme", savedTheme);
else if (matchMedia("(prefers-color-scheme: dark)").matches)
  document.documentElement.setAttribute("data-theme", "dark");
document.getElementById("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("ac-theme", next);
});

// ---- routing ----
function route() {
  const name = (location.hash.replace("#", "") || "chat").split("/")[0];
  const fn = ROUTES[name] || renderChat;
  document.querySelectorAll(".rail-item[data-route]").forEach((a) =>
    a.classList.toggle("active", a.dataset.route === name));
  view.replaceChildren();
  fn(view);
}
window.addEventListener("hashchange", route);

// ---- health poll ----
async function refreshHealth() {
  try {
    const h = await api.health();
    state.health = h;
    paintHealth(h);
    state.onHealth.forEach((cb) => { try { cb(h); } catch (e) {} });
  } catch (e) {
    state.health = null;
  }
}
function paintHealth(h) {
  for (const svc of ["n8n", "ollama", "postgres"]) {
    const dot = document.querySelector(`.dot[data-svc="${svc}"]`);
    if (!dot) continue;
    const up = h[svc] && h[svc].up;
    dot.classList.toggle("up", !!up);
    dot.classList.toggle("down", !up);
    dot.title = up ? `${svc} up (${h[svc].latency_ms} ms)` : `${svc} down — ${h[svc]?.error || "?"}`;
  }
  const loaded = h.ollama?.loaded?.[0] || h.ollama?.models?.[0] || "—";
  document.getElementById("model-badge").textContent = "model " + loaded;
  const target = document.getElementById("target-badge");
  target.textContent = (h.n8n?.url || "").includes("localhost") ? "edge" : "cloud";
  target.title = h.n8n?.url || "";
}
document.getElementById("refresh-health").addEventListener("click", refreshHealth);

refreshHealth();
setInterval(refreshHealth, 15000);
route();
