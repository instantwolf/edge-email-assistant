// Evaluation browser: run list, run detail, and multi-run latency comparison.
import { api } from "./lib/api.js";
import { el, clear, fmtTs, catPill } from "./lib/util.js";
import { renderMarkdown } from "./lib/md.js";

const COLORS = ["#4f46e5", "#16a34a", "#d97706", "#0891b2", "#db2777"];
let selected = new Set();   // run ids selected for comparison

export async function renderEval(root) {
  root.replaceChildren();
  selected = new Set();
  const page = el("div", { class: "page" });
  const detail = el("div", { class: "run-detail card", style: "padding:16px" },
    el("div", { class: "empty muted", text: "Select a run to see its interactions, or check two or more to compare." }));
  const list = el("div", { class: "run-list" }, el("div", { class: "empty muted", text: "Loading runs…" }));

  page.append(
    el("div", { class: "page-head" }, [
      el("div", {}, [el("h1", { text: "Evaluation" }),
        el("p", { class: "muted", text: "Runs recorded by eval/run_interactions.py — latency, correctness, edge-vs-cloud." })]),
    ]),
    el("div", { class: "eval-grid" }, [list, detail]),
  );
  root.append(page);

  const data = await api.evalRuns();
  clear(list);
  const runs = data.runs || [];
  if (!runs.length) { list.append(el("div", { class: "empty muted", text: "No runs found in eval/results/." })); return; }

  const cmpBar = el("div", { class: "cmp-row" }, [
    el("button", { class: "btn sm primary", onclick: () => showCompare(runs, detail) }, "Compare selected"),
    el("span", { class: "muted", id: "cmp-count", text: "0 selected" }),
  ]);
  list.append(cmpBar);

  runs.forEach((r) => list.append(runCard(r, detail)));
  // auto-open the newest run
  openRun(runs[0].id, detail);
  markActive(list, runs[0].id);
}

function runCard(r, detail) {
  const cb = el("input", { type: "checkbox", onclick: (e) => {
    e.stopPropagation();
    if (e.target.checked) selected.add(r.id); else selected.delete(r.id);
    const c = document.getElementById("cmp-count"); if (c) c.textContent = `${selected.size} selected`;
  } });
  const okRate = r.n ? Math.round((r.ok / r.n) * 100) : 0;
  const card = el("div", { class: "run-card card", "data-id": r.id, onclick: () => { openRun(r.id, detail); markActive(card.parentElement, r.id); } }, [
    el("div", { class: "rc-top" }, [
      el("span", { class: "rc-tag", text: r.tag }),
      el("label", { class: "cmp-cb", onclick: (e) => e.stopPropagation() }, [cb, "compare"]),
    ]),
    el("div", { class: "rc-meta" }, [
      el("span", { text: fmtTs(r.timestamp) }),
      el("span", {}, [el("span", { class: "pill " + (okRate === 100 ? "ok" : okRate >= 80 ? "warn" : "bad") }, `${r.ok}/${r.n} ok`)]),
      r.median != null ? el("span", { class: "mono", text: `med ${r.median}s` }) : null,
      r.hasScoring ? el("span", { class: "pill info", text: "scored" }) : null,
    ]),
  ]);
  return card;
}

function markActive(container, id) {
  container.querySelectorAll(".run-card").forEach((c) => c.classList.toggle("active", c.dataset.id === id));
}

async function openRun(id, detail) {
  clear(detail);
  detail.append(el("div", { class: "empty muted", text: "Loading…" }));
  const run = await api.evalRun(id);
  clear(detail);
  if (run.error) { detail.append(el("div", { class: "empty muted", text: run.error })); return; }

  const s = run.summary || {};
  detail.append(el("div", { class: "page-head", style: "margin-bottom:10px" }, [
    el("div", {}, [
      el("h2", { text: run.tag }),
      el("p", { class: "muted", text: `${s.n} interactions · ${s.ok}/${s.n} ok · latency min ${s.min ?? "?"}s / median ${s.median ?? "?"}s / max ${s.max ?? "?"}s` }),
    ]),
  ]));

  const maxLat = Math.max(1, ...(run.interactions || []).map((i) => Number(i.latency_s) || 0));
  const listEl = el("div", {});
  (run.interactions || []).forEach((ix) => listEl.append(interactionRow(ix, maxLat)));
  detail.append(listEl);

  if (run.scoring) {
    detail.append(el("details", { style: "margin-top:16px" }, [
      el("summary", { style: "cursor:pointer;font-weight:600", text: "Manual scoring notes" }),
      el("div", { class: "card", style: "padding:14px;margin-top:8px", html: renderMarkdown(run.scoring) }),
    ]));
  }
}

function interactionRow(ix, maxLat) {
  const lat = Number(ix.latency_s) || 0;
  const ok = ix.ok === true || ix.ok === "True" || ix.ok === "true";
  const body = el("div", { class: "ix-body", style: "display:none" });
  let loaded = false;
  const top = el("div", { class: "ix-top", onclick: () => {
    const show = body.style.display === "none";
    body.style.display = show ? "block" : "none";
    if (show && !loaded) {
      loaded = true;
      body.textContent = ix.output || "(no output captured in this run file)";
      if (ix.error) body.append(el("div", { class: "ix-error", text: ix.error }));
    }
  } }, [
    el("span", { class: "ix-id", text: "#" + ix.id }),
    el("span", { class: "pill " + catPill(ix.category), text: ix.category }),
    el("span", { class: "ix-msg", title: ix.message || "", text: ix.message || "" }),
    el("div", { class: "latbar-wrap" }, el("div", { class: "latbar", style: `width:${(lat / maxLat) * 100}%` })),
    el("span", { class: "ix-lat", text: lat.toFixed(1) + "s" }),
    el("span", { class: "pill " + (ok ? "ok" : "bad"), text: ok ? String(ix.http_status || "200") : "fail" }),
  ]);
  return el("div", { class: "interaction" }, [top, body]);
}

// ---- comparison view ----
async function showCompare(runs, detail) {
  if (selected.size < 1) { detail.replaceChildren(el("div", { class: "empty muted", text: "Check one or more runs first." })); return; }
  clear(detail);
  detail.append(el("div", { class: "empty muted", text: "Loading runs…" }));
  const ids = [...selected];
  const loaded = await Promise.all(ids.map((id) => api.evalRun(id)));
  clear(detail);

  detail.append(el("h2", { text: "Comparison", style: "margin-bottom:4px" }));
  detail.append(el("p", { class: "muted", text: ids.join("  vs  "), style: "margin-bottom:12px" }));

  // legend + summary table
  const legend = el("div", { class: "legend" }, loaded.map((r, i) =>
    el("span", {}, [el("i", { style: `background:${COLORS[i % COLORS.length]}` }),
      `${r.tag} — ${r.summary.ok}/${r.summary.n} ok, med ${r.summary.median ?? "?"}s`])));
  detail.append(legend);

  // per-interaction grouped bars keyed by interaction id
  const byId = {};
  loaded.forEach((r, ri) => (r.interactions || []).forEach((ix) => {
    const k = ix.id;
    (byId[k] = byId[k] || { id: ix.id, message: ix.message, cat: ix.category, vals: [] }).vals[ri] = Number(ix.latency_s) || 0;
  }));
  const maxLat = Math.max(1, ...Object.values(byId).flatMap((g) => g.vals.map((v) => v || 0)));
  const chart = el("div", { class: "cmp-chart card", style: "padding:16px;margin-top:12px" });
  Object.values(byId).sort((a, b) => a.id - b.id).forEach((g) => {
    const bars = loaded.map((_, i) => {
      const v = g.vals[i] || 0;
      return el("div", { class: "cmp-bar", style: `width:${Math.max(2, (v / maxLat) * 100)}%;background:${COLORS[i % COLORS.length]}` }, v ? v.toFixed(1) + "s" : "");
    });
    chart.append(el("div", { class: "cmp-bar-group" }, [
      el("div", { class: "cbg-label" }, [
        el("span", {}, [el("span", { class: "ix-id", text: "#" + g.id }), " ",
          el("span", { class: "pill " + catPill(g.cat), text: g.cat })]),
      ]),
      el("div", { title: g.message || "" }, bars),
    ]));
  });
  detail.append(chart);
}
