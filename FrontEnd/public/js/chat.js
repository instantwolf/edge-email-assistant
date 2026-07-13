// Chat console: sessions sidebar + thread + composer + ground-truth drawer.
import { api } from "./lib/api.js";
import { state } from "./main.js";
import { el, clear } from "./lib/util.js";
import { renderMarkdown, escapeHtml } from "./lib/md.js";

const CHIPS = [
  "Summarize today's emails.",
  "Summarize today's emails and schedule my meetings.",
  "What's on my agenda this week?",
  "Find deadlines in my inbox and save them as tasks.",
  "What open tasks do I have?",
];

let current = null;         // current sessionId
let busy = false;
let truthOpen = false;
let truthTab = "emails";

function newSessionId() {
  const b = crypto.getRandomValues(new Uint8Array(3));
  return "web-" + [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
}

export async function renderChat(root) {
  root.replaceChildren();          // idempotent: safe for internal re-renders (drawer toggle)
  current = current || newSessionId();
  const truthEnabled = !!state.health?.truth_enabled;

  const wrap = el("div", { class: "chat-wrap" + (truthEnabled && truthOpen ? " with-truth" : "") });

  // ---- sessions sidebar ----
  const sideList = el("div", { class: "session-list" });
  const side = el("div", { class: "sessions" }, [
    el("div", { class: "sessions-head" }, [
      el("h2", { text: "Sessions" }),
      el("button", { class: "btn sm", onclick: () => startNew() }, "+ New"),
    ]),
    sideList,
  ]);

  // ---- thread column ----
  const thread = el("div", { class: "thread" });
  const chips = el("div", { class: "chips" },
    CHIPS.map((c) => el("div", { class: "chip", title: c, onclick: () => fillAndSend(c) },
      c.length > 34 ? c.slice(0, 32) + "…" : c)));
  const ta = el("textarea", { rows: "1", placeholder: "Message the assistant…  (Enter to send, Shift+Enter for newline)" });
  const sendBtn = el("button", { class: "send-btn", title: "Send", onclick: () => send() }, "➤");
  ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 140) + "px"; });
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  const composer = el("div", { class: "composer" }, [
    chips,
    el("div", { class: "composer-row" }, [ta, sendBtn]),
  ]);
  const threadCol = el("div", { class: "thread-col" }, [thread, composer]);

  // ---- truth drawer (only built when actually shown) ----
  let truthBody = null;
  const drawer = (truthEnabled && truthOpen) ? buildTruthDrawer() : null;
  if (drawer) truthBody = drawer.body;

  wrap.append(side, threadCol);
  if (drawer) wrap.append(drawer.node);
  root.append(wrap);

  // add a drawer toggle into the composer chips row area when enabled but closed
  if (truthEnabled && !truthOpen) {
    chips.prepend(el("div", { class: "chip truth-toggle", onclick: () => { truthOpen = true; renderChat(root); },
      title: "Show live Gmail/Calendar/Tasks state" }, "👁 Ground truth"));
  }

  // ---- helpers bound to this render ----
  function addMsg(role, content, foot) {
    const bubble = el("div", { class: "bubble" });
    if (role === "assistant") bubble.innerHTML = renderMarkdown(content);
    else bubble.textContent = content;
    const parts = [bubble];
    if (foot) parts.push(el("div", { class: "msg-foot" }, foot));
    const m = el("div", { class: "msg " + role }, parts);
    thread.append(m);
    thread.scrollTop = thread.scrollHeight;
    return m;
  }

  function fillAndSend(text) { if (!busy) { ta.value = text; send(); } }

  async function send() {
    const message = ta.value.trim();
    if (!message || busy) return;
    busy = true; sendBtn.disabled = true; ta.value = ""; ta.style.height = "auto";
    addMsg("user", message);

    // pending row with live elapsed timer + cancel
    const controller = new AbortController();
    const timerLabel = el("span", { text: "0.0s" });
    const cancelBtn = el("button", { class: "btn sm", onclick: () => controller.abort() }, "cancel");
    const pending = el("div", { class: "msg assistant" }, [
      el("div", { class: "bubble" }, [
        el("span", { class: "pending" }, [el("span", { class: "spinner" }), "thinking… ", timerLabel, " ", cancelBtn]),
      ]),
    ]);
    thread.append(pending); thread.scrollTop = thread.scrollHeight;
    const t0 = performance.now();
    const timer = setInterval(() => { timerLabel.textContent = ((performance.now() - t0) / 1000).toFixed(1) + "s"; }, 100);

    let res;
    try {
      const r = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: current, message }), signal: controller.signal,
      });
      res = await r.json();
    } catch (e) {
      res = { error: controller.signal.aborted ? "cancelled (n8n may still be running server-side)" : String(e) };
    }
    clearInterval(timer);
    pending.remove();

    const model = state.health?.ollama?.loaded?.[0] || state.health?.ollama?.models?.[0] || "";
    if (res.error) {
      addMsg("system", "");
      thread.lastChild.querySelector(".bubble").innerHTML =
        '<strong>⚠ Request failed</strong><br>' + escapeHtml(res.error);
    } else {
      const foot = [
        el("span", {}, `⏱ ${res.latency_s}s`),
        el("span", {}, `· ${res.status}`),
        model ? el("span", {}, `· ${model}`) : null,
      ].filter(Boolean);
      addMsg("assistant", res.output || "(empty response)", foot);
    }
    busy = false; sendBtn.disabled = false; ta.focus();
    loadSessions();                 // reflect the (possibly new) session
    if (truthEnabled && truthOpen) loadTruth(truthTab, truthBody);
  }

  function startNew() { current = newSessionId(); clear(thread); loadSessions(); ta.focus(); }

  async function loadSession(id) {
    current = id; clear(thread);
    const data = await api.transcript(id);
    if (data.error) { addMsg("system", ""); thread.lastChild.querySelector(".bubble").textContent = data.error; }
    for (const m of data.messages || []) addMsg(m.role, m.content, m.role === "assistant" ? [el("span", { class: "muted" }, "from memory")] : null);
    highlightActive();
  }

  async function loadSessions() {
    const data = await api.sessions();
    clear(sideList);
    if (data.error) { sideList.append(el("div", { class: "empty", text: data.error })); return; }
    const web = (data.sessions || []).filter((s) => s.kind === "web");
    const ev = (data.sessions || []).filter((s) => s.kind === "eval");
    const groups = [["Web", web], ["Eval", ev]];
    if (!web.some((s) => s.sessionId === current)) {
      // show the current fresh session at the top even before its first turn persists
      sideList.append(sessionRow({ sessionId: current, messages: 0, kind: "web" }, true));
    }
    for (const [label, list] of groups) {
      if (!list.length) continue;
      sideList.append(el("div", { class: "session-group-label", text: label }));
      list.forEach((s) => sideList.append(sessionRow(s, s.sessionId === current)));
    }
  }
  function sessionRow(s, active) {
    return el("div", { class: "session " + s.kind + (active ? " active" : ""), onclick: () => loadSession(s.sessionId) }, [
      el("div", { class: "sid", text: s.sessionId }),
      el("div", { class: "meta", text: s.messages ? `${s.messages} messages` : "new — not saved yet" }),
    ]);
  }
  function highlightActive() {
    sideList.querySelectorAll(".session").forEach((r) =>
      r.classList.toggle("active", r.querySelector(".sid")?.textContent === current));
  }

  // ---- ground-truth drawer ----
  function buildTruthDrawer() {
    const body = el("div", { class: "truth-body" }, el("div", { class: "empty muted", text: "Loading…" }));
    const tabs = el("div", { class: "truth-tabs" },
      [["emails", "Inbox"], ["events", "Calendar"], ["tasks", "Tasks"]].map(([k, lbl]) =>
        el("div", { class: "truth-tab" + (k === truthTab ? " active" : ""), onclick: () => {
          truthTab = k;
          tabs.querySelectorAll(".truth-tab").forEach((t) => t.classList.toggle("active", t.textContent === lbl));
          loadTruth(k, body);
        } }, lbl)));
    const node = el("div", { class: "truth" }, [
      el("div", { class: "truth-head" }, [
        el("h2", { text: "Ground truth" }),
        el("div", {}, [
          el("button", { class: "btn-icon", title: "Refresh", onclick: () => loadTruth(truthTab, body) }, "⟳"),
          el("button", { class: "btn-icon", title: "Hide", onclick: () => { truthOpen = false; renderChat(root); } }, "✕"),
        ]),
      ]),
      tabs, body,
    ]);
    setTimeout(() => loadTruth(truthTab, body), 0);
    return { node, body };
  }

  // initial load
  loadSessions();
  setTimeout(() => ta.focus(), 0);
}

async function loadTruth(kind, body) {
  clear(body);
  body.append(el("div", { class: "empty muted", text: "Loading…" }));
  const data = await api.truth(kind);
  clear(body);
  if (data.error) { body.append(el("div", { class: "empty muted", text: data.error })); return; }
  const items = data.items || [];
  if (!items.length) { body.append(el("div", { class: "empty muted", text: "No items." })); return; }
  for (const it of items) {
    if (kind === "emails") {
      body.append(el("div", { class: "truth-item" }, [
        el("div", { class: "t1", text: (it.unread ? "● " : "") + (it.subject || "(no subject)") }),
        el("div", { class: "t2", text: it.from }),
      ]));
    } else if (kind === "events") {
      body.append(el("div", { class: "truth-item" }, [
        el("div", { class: "t1", text: it.summary }),
        el("div", { class: "t2", text: `${it.start || ""} → ${it.end || ""}` }),
      ]));
    } else {
      body.append(el("div", { class: "truth-item" }, [
        el("div", { class: "t1", text: it.title }),
        el("div", { class: "t2", text: (it.due ? "due " + it.due.slice(0, 10) + " · " : "") + (it.notes || "") }),
      ]));
    }
  }
}
