// Small DOM + formatting helpers shared across pages.
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

export function fmtTs(ts) {
  // "20260706T091119Z" -> "2026-07-06 09:11 UTC"
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(ts || "");
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]} UTC` : (ts || "");
}

// ---- people / avatars ----
export function parseFrom(raw) {
  const m = /^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$/.exec(raw || "");
  if (m) return { name: (m[1].trim() || m[2]), email: m[2] };
  return { name: raw || "", email: raw || "" };
}
export function initials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
export function hueFor(str) {
  let h = 0;
  for (const c of String(str || "")) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

// ---- dates ----
export function relDateMs(ms) {
  const n = Number(ms);
  if (!n) return "";
  const d = new Date(n), now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "now";
  if (diff < 3600) return Math.floor(diff / 60) + "m";
  if (d.toDateString() === now.toDateString()) return Math.floor(diff / 3600) + "h";
  if (diff < 7 * 86400) return d.toLocaleDateString(undefined, { weekday: "short" });
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
export function eventDay(iso) {
  const d = new Date(iso), now = new Date();
  const key = d.toDateString();
  const tomorrow = new Date(now.getTime() + 86400000);
  let label;
  if (key === now.toDateString()) label = "Today";
  else if (key === tomorrow.toDateString()) label = "Tomorrow";
  else label = d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
  return { key, label };
}
export function hhmm(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
export function dueBadge(due) {
  if (!due) return null;
  const d = new Date(due);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const dd = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((dd - today) / 86400000);
  const text = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  if (days < 0) return { text: "overdue · " + text, tone: "bad", order: days };
  if (days === 0) return { text: "today", tone: "warn", order: 0 };
  if (days === 1) return { text: "tomorrow", tone: "warn", order: 1 };
  return { text, tone: "", order: days };
}

export function catPill(cat) {
  const c = (cat || "").toLowerCase();
  if (c.includes("memory") || c.includes("action")) return "info";
  if (c.includes("tool") || c.includes("create") || c.includes("extract")) return "warn";
  return "";
}
