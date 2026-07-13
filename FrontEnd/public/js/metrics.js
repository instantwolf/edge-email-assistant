// Metrics viewer: CPU / memory time series from metrics/*.csv (container + host).
import { api } from "./lib/api.js";
import { el, clear } from "./lib/util.js";

const SERIES_COLORS = ["#4f46e5", "#16a34a", "#d97706", "#0891b2", "#db2777", "#7c3aed"];

export async function renderMetrics(root) {
  root.replaceChildren();
  const page = el("div", { class: "page" });
  const files = el("div", { class: "run-list", style: "gap:6px" }, el("div", { class: "empty muted", text: "Loading…" }));
  const charts = el("div", {}, el("div", { class: "empty muted", text: "Select a metrics file." }));
  page.append(
    el("div", { class: "page-head" }, el("div", {}, [
      el("h1", { text: "Resource metrics" }),
      el("p", { class: "muted", text: "CPU and memory sampled during evaluation runs (docker stats + host psutil)." }),
    ])),
    el("div", { class: "metrics-grid" }, [files, charts]),
  );
  root.append(page);

  const data = await api.metricsFiles();
  clear(files);
  const list = data.files || [];
  if (!list.length) { files.append(el("div", { class: "empty muted", text: "No CSVs in metrics/." })); return; }
  list.forEach((f) => {
    const card = el("div", { class: "metric-file card", "data-name": f.name, onclick: () => { openFile(f.name, charts); mark(files, f.name); } }, [
      el("div", { class: "mf-name", text: f.name }),
      el("div", { class: "mf-meta" }, [
        el("span", { class: "pill " + (f.kind === "host" ? "info" : ""), text: f.kind }), " ",
        el("span", { text: `${f.rows} samples` }),
      ]),
    ]);
    files.append(card);
  });
  openFile(list[0].name, charts); mark(files, list[0].name);
}

function mark(container, name) {
  container.querySelectorAll(".metric-file").forEach((c) => c.classList.toggle("active", c.dataset.name === name));
}

async function openFile(name, charts) {
  clear(charts);
  charts.append(el("div", { class: "empty muted", text: "Loading…" }));
  const data = await api.metricsFile(name);
  clear(charts);
  if (data.error) { charts.append(el("div", { class: "empty muted", text: data.error })); return; }
  const rows = data.rows || [];
  if (!rows.length) { charts.append(el("div", { class: "empty muted", text: "Empty file." })); return; }

  const t0 = Number(rows[0].ts) || 0;
  const relT = (r) => (Number(r.ts) || 0) - t0;

  if (data.kind === "container") {
    // group by container; two charts: cpu %, mem MiB
    const groups = groupBy(rows, "container");
    charts.append(lineChartCard("CPU %", groups, relT, (r) => parsePct(r.cpu_perc)));
    charts.append(lineChartCard("Memory (MiB)", groups, relT, (r) => parseMem(r.mem_used)));
  } else if (data.kind === "host") {
    const groups = groupBy(rows, "command", (c) => (c || "").split("/").pop() || c);
    charts.append(lineChartCard("CPU %", groups, relT, (r) => Number(r.cpu_perc) || 0));
    charts.append(lineChartCard("RSS (MB)", groups, relT, (r) => Number(r.rss_mb) || 0));
  } else {
    charts.append(el("div", { class: "empty muted", text: "Unrecognized metrics format." }));
  }
}

function groupBy(rows, key, labelFn = (x) => x) {
  const g = {};
  for (const r of rows) {
    const lbl = labelFn(r[key]) || "?";
    (g[lbl] = g[lbl] || []).push(r);
  }
  return g;
}
function parsePct(s) { return Number(String(s).replace("%", "")) || 0; }
function parseMem(s) {
  const m = /([\d.]+)\s*([KMG]i?B)/i.exec(String(s));
  if (!m) return 0;
  const v = Number(m[1]); const u = m[2].toUpperCase();
  if (u.startsWith("G")) return v * 1024;
  if (u.startsWith("K")) return v / 1024;
  return v; // MiB
}

function lineChartCard(title, groups, xFn, yFn) {
  const names = Object.keys(groups);
  const W = 720, H = 220, PAD = { l: 46, r: 12, t: 10, b: 24 };
  const series = names.map((n) => groups[n].map((r) => ({ x: xFn(r), y: yFn(r) })).filter((p) => !isNaN(p.y)));
  const allX = series.flat().map((p) => p.x), allY = series.flat().map((p) => p.y);
  const xMax = Math.max(1, ...allX), yMax = Math.max(1, ...allY);
  const sx = (x) => PAD.l + (x / xMax) * (W - PAD.l - PAD.r);
  const sy = (y) => H - PAD.b - (y / yMax) * (H - PAD.t - PAD.b);

  const gridLines = [];
  for (let i = 0; i <= 4; i++) {
    const y = (yMax / 4) * i;
    gridLines.push(`<line x1="${PAD.l}" y1="${sy(y)}" x2="${W - PAD.r}" y2="${sy(y)}" stroke="var(--border)" stroke-width="1"/>`);
    gridLines.push(`<text x="${PAD.l - 6}" y="${sy(y) + 3}" text-anchor="end" font-size="10" fill="var(--text-dim)">${y.toFixed(y < 10 ? 1 : 0)}</text>`);
  }
  const paths = series.map((pts, i) => {
    if (!pts.length) return "";
    const d = pts.map((p, j) => (j ? "L" : "M") + sx(p.x).toFixed(1) + " " + sy(p.y).toFixed(1)).join(" ");
    return `<path d="${d}" fill="none" stroke="${SERIES_COLORS[i % SERIES_COLORS.length]}" stroke-width="1.8"/>`;
  });
  const svg = `<svg class="linechart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    ${gridLines.join("")}
    <line x1="${PAD.l}" y1="${H - PAD.b}" x2="${W - PAD.r}" y2="${H - PAD.b}" stroke="var(--text-dim)" stroke-width="1"/>
    <text x="${(W) / 2}" y="${H - 4}" text-anchor="middle" font-size="10" fill="var(--text-dim)">seconds since start →</text>
    ${paths.join("")}
  </svg>`;

  const legend = el("div", { class: "legend" }, names.map((n, i) =>
    el("span", {}, [el("i", { style: `background:${SERIES_COLORS[i % SERIES_COLORS.length]}` }), n])));
  return el("div", { class: "chart-card card" }, [
    el("h3", { text: title }),
    legend,
    el("div", { html: svg }),
  ]);
}
