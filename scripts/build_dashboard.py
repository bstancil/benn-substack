#!/usr/bin/env python3
"""
Generate dashboard/dashboard.html from data/substack.duckdb.

The output is a single self-contained file (data inlined as JSON, hand-rolled
SVG charts, no external requests). Queries live in QUERIES below, separated
from the template, so swapping in different views later is easy.
"""

import json
from datetime import date
from urllib.parse import urlparse

import duckdb

from substack_api import BASE_URL, ROOT_DIR

PUB_NAME = urlparse(BASE_URL).hostname or "substack"

DB_PATH = ROOT_DIR / "data" / "substack.duckdb"
OUT_PATH = ROOT_DIR / "dashboard" / "dashboard.html"

QUERIES = {
    "subscribers": """
        SELECT date::VARCHAR AS date, subscribers
        FROM subscriber_timeseries ORDER BY date
    """,
    "traffic": """
        SELECT date::VARCHAR AS date, visits
        FROM traffic_daily ORDER BY date
    """,
    "sub_sources": """
        SELECT source, sum(subscribers)::INT AS subscribers, sum(paid)::INT AS paid
        FROM subscriber_sources GROUP BY 1 ORDER BY subscribers DESC
    """,
    "posts": """
        SELECT
            post_id,
            strftime(post_date, '%Y-%m-%d') AS post_date,
            title, canonical_url, wordcount,
            deliveries, opens, open_rate, views,
            signups_within_1_day, likes, comments, restacks
        FROM posts_overview
        ORDER BY post_date DESC
    """,
}


def fetch_data():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        data = {}
        for key, sql in QUERIES.items():
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description]
            data[key] = [dict(zip(cols, row)) for row in cur.fetchall()]
        return data
    finally:
        con.close()


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__PUB_NAME__ — dashboard</title>
<style>
  :root {
    --page: #f9f9f7; --surface: #fcfcfb;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --grid: #e1e0d9; --baseline: #c3c2b7;
    --border: rgba(11,11,11,0.10);
    --accent: #2a78d6; --accent-dim: #9ec5f4;
    --up: #006300;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --page: #0d0d0d; --surface: #1a1a19;
      --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --baseline: #383835;
      --border: rgba(255,255,255,0.10);
      --accent: #3987e5; --accent-dim: #1c5cab;
      --up: #0ca30c;
    }
  }
  * { box-sizing: border-box; margin: 0; }
  body {
    background: var(--page); color: var(--ink);
    font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 28px clamp(16px, 4vw, 48px) 64px;
  }
  header { display: flex; align-items: baseline; gap: 14px; margin-bottom: 20px; flex-wrap: wrap; }
  header h1 { font-size: 20px; font-weight: 650; }
  header .meta { color: var(--muted); font-size: 12.5px; }
  .warn { color: var(--ink-2); background: var(--surface); border: 1px solid var(--border);
          border-radius: 10px; padding: 10px 14px; margin-bottom: 16px; font-size: 13px; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .tile { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
  .tile .label { color: var(--ink-2); font-size: 12.5px; }
  .tile .value { font-size: 26px; font-weight: 600; margin-top: 2px; }
  .tile .delta { font-size: 12.5px; margin-top: 2px; color: var(--muted); }
  .tile .delta.up { color: var(--up); }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 12px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; min-width: 0; }
  .card.wide { grid-column: 1 / -1; }
  .card h2 { font-size: 13.5px; font-weight: 600; margin-bottom: 2px; }
  .card .sub { color: var(--muted); font-size: 12px; margin-bottom: 8px; }
  .chart { position: relative; }
  .chart svg { display: block; width: 100%; height: auto; }
  .tooltip {
    position: absolute; pointer-events: none; display: none; z-index: 5;
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 7px 10px; font-size: 12px; box-shadow: 0 4px 14px rgba(0,0,0,.14);
    min-width: 120px; max-width: 260px;
  }
  .tooltip .t-date { color: var(--muted); margin-bottom: 3px; }
  .tooltip .t-row { display: flex; align-items: baseline; gap: 8px; }
  .tooltip .t-key { width: 12px; height: 0; border-top: 2px solid var(--accent); flex: none; align-self: center; }
  .tooltip .t-val { font-weight: 600; }
  .tooltip .t-name { color: var(--ink-2); }
  .bars { display: grid; gap: 7px; margin-top: 4px; }
  .bar-row { display: grid; grid-template-columns: 150px 1fr 64px; align-items: center; gap: 10px; font-size: 12.5px; }
  .bar-row .b-label { color: var(--ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bar-row .b-track { height: 14px; }
  .bar-row .b-fill { height: 100%; background: var(--accent); border-radius: 0 4px 4px 0; min-width: 2px; }
  .bar-row .b-val { text-align: right; font-variant-numeric: tabular-nums; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
  th, td { text-align: right; padding: 6px 10px; white-space: nowrap; }
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
  td:first-child { color: var(--muted); }
  thead th { color: var(--ink-2); font-weight: 600; border-bottom: 1px solid var(--baseline);
             cursor: pointer; user-select: none; position: sticky; top: 0; background: var(--surface); }
  thead th:hover { color: var(--ink); }
  tbody td { border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }
  tbody tr:hover td { background: color-mix(in srgb, var(--accent) 6%, transparent); }
  td.title a { color: var(--ink); text-decoration: none; }
  td.title a:hover { color: var(--accent); text-decoration: underline; }
</style>
</head>
<body>
<header>
  <h1>__PUB_NAME__</h1>
  <span class="meta" id="meta"></span>
</header>
<div id="warn"></div>
<div class="tiles" id="tiles"></div>
<div class="cards" id="cards"></div>

<script>
const DATA = /*__DATA__*/;

// ---------- helpers ----------
const fmt = n => n == null ? "–" : n.toLocaleString("en-US");
const compact = n => {
  if (n == null) return "–";
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 10e3) return (n / 1e3).toFixed(1) + "K";
  return fmt(Math.round(n * 10) / 10);
};
const pct = n => n == null ? "–" : (n * 100).toFixed(1) + "%";
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const niceTicks = (max, count = 4) => {
  if (!(max > 0)) return [0, 1];
  const step = Math.pow(10, Math.floor(Math.log10(max / count)));
  const err = max / count / step;
  const mult = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  const s = step * mult, top = Math.ceil(max / s) * s;
  const ticks = [];
  for (let v = 0; v <= top + 1e-9; v += s) ticks.push(v);
  return ticks;
};

// ---------- generic time/sequence line chart ----------
// series: [{x (label), y}], opts: {fmtY, area}
function lineChart(container, points, opts = {}) {
  const W = 640, H = 240, m = { t: 12, r: 12, b: 26, l: 46 };
  const fmtY = opts.fmtY || compact;
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const xs = points.map((_, i) => i);
  const ymax = Math.max(...points.map(p => p.y ?? 0));
  const ticks = niceTicks(opts.pct ? Math.min(Math.max(ymax, 0.0001), 1) : ymax);
  const top = ticks[ticks.length - 1];
  const X = i => m.l + (points.length === 1 ? 0.5 : i / (points.length - 1)) * (W - m.l - m.r);
  const Y = v => H - m.b - (v / top) * (H - m.t - m.b);

  const add = (name, attrs, parent = svg) => {
    const n = document.createElementNS(svgNS, name);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    parent.appendChild(n);
    return n;
  };

  for (const t of ticks) {
    add("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), stroke: "var(--grid)", "stroke-width": 1 });
    const lbl = add("text", { x: m.l - 8, y: Y(t) + 3.5, "text-anchor": "end", fill: "var(--muted)", "font-size": 10.5 });
    lbl.textContent = opts.pct ? (t * 100).toFixed(0) + "%" : compact(t);
  }
  add("line", { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: "var(--baseline)", "stroke-width": 1 });

  // x labels: ~5 evenly spaced
  const nLab = Math.min(5, points.length);
  for (let k = 0; k < nLab; k++) {
    const i = Math.round(k * (points.length - 1) / Math.max(1, nLab - 1));
    const lbl = add("text", { x: X(i), y: H - 8, "text-anchor": k === 0 ? "start" : k === nLab - 1 ? "end" : "middle",
                              fill: "var(--muted)", "font-size": 10.5 });
    lbl.textContent = points[i].x;
  }

  const path = points.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(2)},${Y(p.y ?? 0).toFixed(2)}`).join("");
  if (opts.area !== false) {
    add("path", { d: `${path}L${X(points.length - 1)},${Y(0)}L${X(0)},${Y(0)}Z`, fill: "var(--accent)", opacity: 0.1 });
  }
  add("path", { d: path, fill: "none", stroke: "var(--accent)", "stroke-width": 2,
                "stroke-linejoin": "round", "stroke-linecap": "round" });

  // end dot + label
  const last = points[points.length - 1];
  add("circle", { cx: X(points.length - 1), cy: Y(last.y ?? 0), r: 4, fill: "var(--accent)",
                  stroke: "var(--surface)", "stroke-width": 2 });
  const endLbl = add("text", { x: X(points.length - 1) - 8, y: Y(last.y ?? 0) - 8, "text-anchor": "end",
                               fill: "var(--ink-2)", "font-size": 11, "font-weight": 600 });
  endLbl.textContent = opts.pct ? pct(last.y) : compact(last.y);

  // crosshair + tooltip
  const cross = add("line", { y1: m.t, y2: H - m.b, stroke: "var(--baseline)", "stroke-width": 1, visibility: "hidden" });
  const dot = add("circle", { r: 4.5, fill: "var(--accent)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" });
  const tip = el("div", "tooltip");
  const tipDate = el("div", "t-date"); tip.appendChild(tipDate);
  const tipRow = el("div", "t-row");
  tipRow.appendChild(el("span", "t-key"));
  const tipVal = el("span", "t-val"); tipRow.appendChild(tipVal);
  const tipName = el("span", "t-name", opts.seriesName || ""); tipRow.appendChild(tipName);
  tip.appendChild(tipRow);
  container.appendChild(svg);
  container.appendChild(tip);

  const toIndex = clientX => {
    const r = svg.getBoundingClientRect();
    const px = (clientX - r.left) / r.width * W;
    const t = (px - m.l) / (W - m.l - m.r) * (points.length - 1);
    return Math.max(0, Math.min(points.length - 1, Math.round(t)));
  };
  svg.addEventListener("pointermove", ev => {
    const i = toIndex(ev.clientX), p = points[i];
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i));
    cross.setAttribute("visibility", "visible");
    dot.setAttribute("cx", X(i)); dot.setAttribute("cy", Y(p.y ?? 0));
    dot.setAttribute("visibility", "visible");
    tipDate.textContent = p.label || p.x;
    tipVal.textContent = opts.pct ? pct(p.y) : fmt(p.y);
    const r = svg.getBoundingClientRect();
    tip.style.display = "block";
    const w = tip.offsetWidth, xpx = X(i) / W * r.width;
    tip.style.left = Math.min(Math.max(4, xpx + 12), r.width - w - 4) + "px";
    tip.style.top = (Y(p.y ?? 0) / H * r.height - tip.offsetHeight - 10) + "px";
  });
  svg.addEventListener("pointerleave", () => {
    cross.setAttribute("visibility", "hidden");
    dot.setAttribute("visibility", "hidden");
    tip.style.display = "none";
  });
}

// ---------- assemble ----------
const posts = DATA.posts;
const subs = DATA.subscribers;
const traffic = DATA.traffic;
const statPosts = posts.filter(p => p.opens != null);

document.getElementById("meta").textContent =
  `updated ${DATA.generated_at}` + (DATA.stats_date ? ` · stats as of ${DATA.stats_date}` : "");

if (!statPosts.length) {
  const w = el("div", "warn",
    "No private stats found yet — run `python scripts/update.py` with a Substack cookie in .env. " +
    "Showing public data only (posts, likes, comments, restacks).");
  document.getElementById("warn").appendChild(w);
}

// KPI tiles
const tiles = document.getElementById("tiles");
function tile(label, value, delta, deltaUp) {
  const t = el("div", "tile");
  t.appendChild(el("div", "label", label));
  t.appendChild(el("div", "value", value));
  if (delta) t.appendChild(el("div", "delta" + (deltaUp ? " up" : ""), delta));
  tiles.appendChild(t);
}
if (subs.length) {
  const cur = subs[subs.length - 1].subscribers;
  const prior = subs[Math.max(0, subs.length - 31)].subscribers;
  tile("Subscribers", fmt(cur), `+${fmt(cur - prior)} in 30 days`, cur - prior > 0);
}
tile("Posts", fmt(posts.length));
if (statPosts.length) {
  const last12 = statPosts.slice(0, 12).map(p => p.open_rate).filter(v => v != null);
  tile("Open rate", pct(last12.reduce((a, b) => a + b, 0) / last12.length), "avg of last 12 posts");
  const lastViews = statPosts.slice(0, 12).map(p => p.views).filter(v => v != null);
  tile("Views per post", compact(lastViews.reduce((a, b) => a + b, 0) / lastViews.length), "avg of last 12 posts");
}
if (traffic.length) {
  const recent = traffic.slice(-30);
  tile("Site visits", compact(recent.reduce((a, b) => a + (b.visits || 0), 0)), "last 30 days");
}

// chart cards
const cards = document.getElementById("cards");
function chartCard(title, sub, wide) {
  const c = el("div", "card" + (wide ? " wide" : ""));
  c.appendChild(el("h2", null, title));
  if (sub) c.appendChild(el("div", "sub", sub));
  const wrap = el("div", "chart");
  c.appendChild(wrap);
  cards.appendChild(c);
  return wrap;
}

const month = d => d.slice(0, 7);
if (subs.length) {
  lineChart(
    chartCard("Subscribers", "daily total since the beginning", true),
    subs.map(d => ({ x: month(d.date), label: d.date, y: d.subscribers })),
    { seriesName: "subscribers" }
  );
}

// per-post trends, oldest -> newest
const chron = statPosts.slice().reverse();
if (chron.length) {
  lineChart(chartCard("Open rate by post", "each point is a post"),
    chron.map(p => ({ x: month(p.post_date), label: p.title, y: p.open_rate })),
    { pct: true, seriesName: "open rate", area: false });
  lineChart(chartCard("Views by post", "each point is a post"),
    chron.map(p => ({ x: month(p.post_date), label: p.title, y: p.views })),
    { seriesName: "views", area: false });
  lineChart(chartCard("New subscribers within a day of posting", "each point is a post"),
    chron.map(p => ({ x: month(p.post_date), label: p.title, y: p.signups_within_1_day })),
    { seriesName: "1-day signups", area: false });
}
if (traffic.length) {
  lineChart(chartCard("Site traffic", "daily visits"),
    traffic.map(d => ({ x: month(d.date), label: d.date, y: d.visits })),
    { seriesName: "visits" });
}

// subscriber acquisition sources (from the audience export)
if (DATA.sub_sources && DATA.sub_sources.length) {
  const srcCard = el("div", "card");
  srcCard.appendChild(el("h2", null, "Where subscribers came from"));
  srcCard.appendChild(el("div", "sub", "all time, from the subscriber export"));
  const bars = el("div", "bars");
  const top = DATA.sub_sources.slice(0, 9);
  const otherN = DATA.sub_sources.slice(9).reduce((a, s) => a + s.subscribers, 0);
  if (otherN) top.push({ source: "other", subscribers: otherN });
  const maxN = top[0].subscribers;
  for (const s of top) {
    const row = el("div", "bar-row");
    row.appendChild(el("span", "b-label", s.source));
    const track = el("div", "b-track");
    const fill = el("div", "b-fill");
    fill.style.width = (s.subscribers / maxN * 100).toFixed(1) + "%";
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("span", "b-val", compact(s.subscribers)));
    bars.appendChild(row);
  }
  srcCard.appendChild(bars);
  cards.appendChild(srcCard);
}

// ---------- posts table ----------
const tableCard = el("div", "card wide");
tableCard.appendChild(el("h2", null, "Posts"));
tableCard.appendChild(el("div", "sub", "click a column to sort"));
const twrap = el("div", "tablewrap");
tableCard.appendChild(twrap);
cards.appendChild(tableCard);

const COLS = [
  { key: "post_date", label: "Date" },
  { key: "title", label: "Title" },
  { key: "deliveries", label: "Deliveries", fmt: compact },
  { key: "opens", label: "Opens", fmt: compact },
  { key: "open_rate", label: "Open rate", fmt: pct },
  { key: "views", label: "Views", fmt: compact },
  { key: "signups_within_1_day", label: "1-day signups", fmt: fmt },
  { key: "likes", label: "Likes", fmt: fmt },
  { key: "comments", label: "Comments", fmt: fmt },
  { key: "restacks", label: "Restacks", fmt: fmt },
  { key: "wordcount", label: "Words", fmt: fmt },
];
let sortKey = "post_date", sortDir = -1;

function renderTable() {
  twrap.replaceChildren();
  const table = el("table");
  const thead = el("thead"), hr = el("tr");
  for (const c of COLS) {
    const th = el("th", null, c.label + (sortKey === c.key ? (sortDir < 0 ? " ↓" : " ↑") : ""));
    th.addEventListener("click", () => {
      sortDir = sortKey === c.key ? -sortDir : -1;
      sortKey = c.key;
      renderTable();
    });
    hr.appendChild(th);
  }
  thead.appendChild(hr);
  table.appendChild(thead);

  const rows = posts.slice().sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  const tbody = el("tbody");
  for (const p of rows) {
    const tr = el("tr");
    for (const c of COLS) {
      const td = el("td");
      if (c.key === "title") {
        td.className = "title";
        const a = el("a", null, p.title);
        a.href = p.canonical_url || "#";
        a.target = "_blank";
        td.appendChild(a);
      } else {
        td.textContent = c.fmt ? c.fmt(p[c.key]) : (p[c.key] ?? "–");
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  twrap.appendChild(table);
}
renderTable();
</script>
</body>
</html>
"""


def build_dashboard():
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH} — run build_db.py first")
        return 1

    data = fetch_data()
    payload = {
        **data,
        "generated_at": date.today().isoformat(),
        "stats_date": None,
    }
    # surface when stats were last fetched, if ever
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        row = con.execute("SELECT max(fetched_date) FROM post_stats_history").fetchone()
        payload["stats_date"] = str(row[0]) if row and row[0] else None
    finally:
        con.close()

    html = TEMPLATE.replace("__PUB_NAME__", PUB_NAME).replace(
        "/*__DATA__*/", json.dumps(payload, ensure_ascii=False, default=str)
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Dashboard written to {OUT_PATH} ({len(data['posts'])} posts, "
          f"{len(data['subscribers'])} subscriber days, {len(data['traffic'])} traffic days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build_dashboard())
