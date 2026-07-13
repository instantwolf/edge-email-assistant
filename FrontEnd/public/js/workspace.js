// Workspace: a live dashboard of the real Google data the agent operates on —
// Inbox (Gmail), Agenda (Calendar), Tasks (Google Tasks). Read-only.
import { api } from "./lib/api.js";
import { state } from "./main.js";
import { el, clear, parseFrom, initials, hueFor, relDateMs, eventDay, hhmm, dueBadge } from "./lib/util.js";

export async function renderWorkspace(root) {
  root.replaceChildren();
  const page = el("div", { class: "page ws-page" });

  const stamp = el("span", { class: "muted", style: "font-size:12px" });
  const refreshAll = el("button", { class: "btn sm", onclick: () => loadAll() }, "⟳ Refresh all");
  page.append(el("div", { class: "page-head" }, [
    el("div", {}, [
      el("h1", { text: "Workspace" }),
      el("p", { class: "muted", text: "Live Gmail, Calendar and Tasks — the real state the assistant reads and writes." }),
    ]),
    el("div", { style: "display:flex;gap:10px;align-items:center" }, [stamp, refreshAll]),
  ]));

  if (!state.health?.truth_enabled) {
    page.append(enableHint());
    root.append(page);
    return;
  }

  const inbox = panel("📥", "Inbox", "inbox");
  const agenda = panel("🗓", "Agenda", "agenda");
  const tasks = panel("✅", "Tasks", "tasks");
  page.append(el("div", { class: "ws-grid" }, [inbox.node, agenda.node, tasks.node]));
  root.append(page);

  async function loadAll() {
    stamp.textContent = "refreshing…";
    await Promise.all([loadInbox(inbox), loadAgenda(agenda), loadTasks(tasks)]);
    stamp.textContent = "updated " + new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  loadAll();
}

function panel(icon, title, cls) {
  const count = el("span", { class: "pill", text: "…" });
  const body = el("div", { class: "ws-body" }, el("div", { class: "ws-loading" }, [el("span", { class: "spinner" }), " Loading…"]));
  const spin = el("span", { class: "ws-panel-spin" });
  const node = el("div", { class: "ws-panel card " + cls }, [
    el("div", { class: "ws-head" }, [
      el("div", { class: "ws-title" }, [el("span", { class: "ws-ic", text: icon }), title, count]),
      spin,
    ]),
    body,
  ]);
  return { node, body, count, spin };
}

function enableHint() {
  return el("div", { class: "card", style: "padding:24px;max-width:640px" }, [
    el("h2", { text: "Live data is turned off", style: "margin-bottom:8px" }),
    el("p", { class: "muted", style: "margin:0 0 12px", html:
      "The Workspace shows your real Gmail, Calendar and Tasks. It is disabled by default so the UI never touches Google unless you ask it to." }),
    el("p", { style: "margin:0", html:
      "Restart the console with <code>ENABLE_TRUTH=1 ./FrontEnd/run.sh</code> to enable read-only Google access " +
      "(it reuses the OAuth tokens you already authorized in n8n — the same mechanism as <code>seed/google_token.py</code>)." }),
  ]);
}

// --------------------------------------------------------------- Inbox ---- //
async function loadInbox(p) {
  p.spin.classList.add("on");
  const data = await api.truth("emails");
  p.spin.classList.remove("on");
  clear(p.body);
  if (data.error) return p.body.append(errorBox(data.error));
  const items = data.items || [];
  const unread = items.filter((i) => i.unread).length;
  p.count.textContent = unread ? `${unread} unread` : `${items.length}`;
  p.count.className = "pill" + (unread ? " info" : "");
  if (!items.length) return p.body.append(emptyBox("Inbox is empty."));
  items.forEach((m) => p.body.append(mailRow(m)));
}

function mailRow(m) {
  const who = parseFrom(m.from);
  const av = el("div", { class: "avatar", style: `background:hsl(${hueFor(who.email)} 55% 45%)`, text: initials(who.name) });
  const bodyBox = el("div", { class: "mail-expand", style: "display:none" });
  let loaded = false;
  const row = el("div", { class: "mail" + (m.unread ? " unread" : "") }, [
    el("div", { class: "mail-main" }, [
      av,
      el("div", { class: "mail-text" }, [
        el("div", { class: "mail-l1" }, [
          el("span", { class: "mail-from", text: who.name }),
          el("span", { class: "mail-date", text: relDateMs(m.date) }),
        ]),
        el("div", { class: "mail-subj", text: m.subject }),
        el("div", { class: "mail-snip", text: m.snippet }),
      ]),
    ]),
    bodyBox,
  ]);
  row.querySelector(".mail-main").addEventListener("click", async () => {
    const open = bodyBox.style.display === "none";
    bodyBox.style.display = open ? "block" : "none";
    row.classList.toggle("open", open);
    if (open && !loaded) {
      loaded = true;
      bodyBox.append(el("div", { class: "ws-loading", html: '<span class="spinner"></span> Loading message…' }));
      const full = await api.message(m.id);
      clear(bodyBox);
      if (full.error) bodyBox.append(errorBox(full.error));
      else bodyBox.append(el("pre", { class: "mail-body", text: full.body || "(no text body)" }));
    }
    if (open && m.unread) { row.classList.remove("unread"); } // reading marks it visually seen
  });
  return row;
}

// -------------------------------------------------------------- Agenda ---- //
async function loadAgenda(p) {
  p.spin.classList.add("on");
  const data = await api.truth("events");
  p.spin.classList.remove("on");
  clear(p.body);
  if (data.error) return p.body.append(errorBox(data.error));
  const items = data.items || [];
  p.count.textContent = `${items.length}`;
  p.count.className = "pill";
  if (!items.length) return p.body.append(emptyBox("Nothing scheduled."));
  let lastDay = null;
  for (const e of items) {
    const day = eventDay(e.start);
    if (day.key !== lastDay) {
      lastDay = day.key;
      p.body.append(el("div", { class: "day-head", text: day.label }));
    }
    const seeded = /\[IOT26\]/i.test(e.summary || "");
    p.body.append(el("div", { class: "event" + (seeded ? " seeded" : "") }, [
      el("div", { class: "event-time", text: e.allDay ? "all day" : hhmm(e.start) }),
      el("div", { class: "event-body" }, [
        el("div", { class: "event-title" }, [
          e.summary,
          seeded ? el("span", { class: "pill info tiny", text: "IOT26" }) : null,
        ]),
        e.location ? el("div", { class: "event-loc", text: "📍 " + e.location }) : null,
      ]),
    ]));
  }
}

// --------------------------------------------------------------- Tasks ---- //
async function loadTasks(p) {
  p.spin.classList.add("on");
  const data = await api.truth("tasks");
  p.spin.classList.remove("on");
  clear(p.body);
  if (data.error) return p.body.append(errorBox(data.error));
  let items = (data.items || []).map((t) => ({ ...t, badge: dueBadge(t.due) }));
  // due items first (soonest/overdue at top), undated after, preserving API order within groups
  items = items.map((t, i) => ({ t, i }))
    .sort((a, b) => {
      const ao = a.t.badge ? a.t.badge.order : Infinity, bo = b.t.badge ? b.t.badge.order : Infinity;
      return ao === bo ? a.i - b.i : ao - bo;
    })
    .map((x) => x.t);
  const withDue = items.filter((t) => t.badge).length;
  p.count.textContent = `${items.length}`;
  p.count.className = "pill";
  if (!items.length) return p.body.append(emptyBox("No open tasks."));
  items.forEach((t) => p.body.append(taskRow(t)));
  if (withDue === 0) p.body.append(el("div", { class: "ws-note muted", text: "None of these tasks carry a due date." }));
}

function taskRow(t) {
  const b = t.badge;
  return el("div", { class: "task", title: "read-only" }, [
    el("div", { class: "task-check" + (b && b.tone === "bad" ? " overdue" : ""), html: "&#10003;" }),
    el("div", { class: "task-text" }, [
      el("div", { class: "task-title", text: t.title || "(untitled)" }),
      t.notes ? el("div", { class: "task-notes", text: t.notes }) : null,
    ]),
    b ? el("span", { class: "pill " + (b.tone || ""), text: b.text }) : null,
  ]);
}

// --------------------------------------------------------------- misc ----- //
function errorBox(msg) { return el("div", { class: "ws-error", text: "⚠ " + msg }); }
function emptyBox(msg) { return el("div", { class: "ws-loading muted", text: msg }); }
