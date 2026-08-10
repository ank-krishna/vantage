"""Embedded dashboard HTML — served as a single endpoint, no static files needed."""

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>marketstore — live</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  :root {
    --bg-primary: #0a0a0f;
    --bg-secondary: #12121a;
    --bg-card: #16161f;
    --bg-card-hover: #1a1a25;
    --bg-elevated: #1e1e2a;
    --border: #252535;
    --border-subtle: #1e1e2e;
    --text-primary: #e8e8ef;
    --text-secondary: #8888a0;
    --text-muted: #555568;
    --accent: #6366f1;
    --accent-dim: rgba(99, 102, 241, 0.12);
    --accent-glow: rgba(99, 102, 241, 0.25);
    --green: #22c55e;
    --green-dim: rgba(34, 197, 94, 0.12);
    --red: #ef4444;
    --red-dim: rgba(239, 68, 68, 0.12);
    --amber: #f59e0b;
    --amber-dim: rgba(245, 158, 11, 0.12);
    --cyan: #06b6d4;
    --cyan-dim: rgba(6, 182, 212, 0.12);
    --radius: 12px;
    --radius-sm: 8px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
    --shadow-lg: 0 8px 32px rgba(0,0,0,0.5);
    --transition: 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', -apple-system, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    overflow-x: hidden;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Top bar ── */
  .topbar {
    position: sticky; top: 0; z-index: 100;
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 32px; height: 56px;
    background: rgba(10, 10, 15, 0.85);
    backdrop-filter: blur(20px) saturate(1.4);
    border-bottom: 1px solid var(--border-subtle);
  }
  .topbar .logo {
    display: flex; align-items: center; gap: 10px;
    font-weight: 600; font-size: 15px; letter-spacing: -0.3px;
  }
  .topbar .logo .dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent-glow);
    animation: pulse-dot 2s ease-in-out infinite;
  }
  @keyframes pulse-dot {
    0%, 100% { opacity: 1; box-shadow: 0 0 8px var(--accent-glow); }
    50% { opacity: 0.6; box-shadow: 0 0 16px var(--accent-glow); }
  }
  .topbar .status-pill {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 100px;
    font-size: 12px; font-weight: 500;
    background: var(--bg-elevated); border: 1px solid var(--border);
    color: var(--text-secondary);
  }
  .topbar .status-pill .status-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--text-muted);
    transition: background var(--transition);
  }
  .topbar .status-pill.connected .status-dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .topbar .status-pill.connected { color: var(--green); border-color: rgba(34,197,94,0.2); }

  .topbar-actions { display: flex; gap: 8px; align-items: center; }
  .btn {
    padding: 6px 16px; border-radius: 8px; border: 1px solid var(--border);
    background: var(--bg-elevated); color: var(--text-primary);
    font: 500 13px 'Inter', sans-serif; cursor: pointer;
    transition: all var(--transition);
  }
  .btn:hover { background: var(--bg-card-hover); border-color: var(--accent); }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn.primary:hover { background: #5558e6; }
  .btn.danger { border-color: rgba(239,68,68,0.3); color: var(--red); }
  .btn.danger:hover { background: var(--red-dim); }

  /* ── Ticker input ── */
  .ticker-input-group {
    display: flex; align-items: center; gap: 6px;
  }
  .ticker-input {
    width: 110px; padding: 6px 12px; border-radius: 8px;
    border: 1px solid var(--border); background: var(--bg-elevated);
    color: var(--text-primary); font: 500 13px 'JetBrains Mono', monospace;
    outline: none; text-transform: uppercase; letter-spacing: 0.5px;
    transition: all var(--transition);
  }
  .ticker-input::placeholder { color: var(--text-muted); font-family: 'Inter', sans-serif; font-weight: 400; text-transform: none; letter-spacing: 0; }
  .ticker-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
  .ticker-remove {
    position: absolute; top: 8px; right: 8px;
    width: 22px; height: 22px; border-radius: 6px;
    border: none; background: transparent;
    color: var(--text-muted); font-size: 14px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: all var(--transition); opacity: 0;
  }
  .ticker-card:hover .ticker-remove { opacity: 1; }
  .ticker-remove:hover { background: var(--red-dim); color: var(--red); }

  /* ── Layout ── */
  .container { max-width: 1400px; margin: 0 auto; padding: 24px 32px; }

  /* ── Stat row ── */
  .stat-row {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
    margin-bottom: 24px;
  }
  .stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 20px 24px;
    transition: all var(--transition);
  }
  .stat-card:hover { border-color: var(--border); transform: translateY(-1px); box-shadow: var(--shadow-md); }
  .stat-label { font-size: 12px; font-weight: 500; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
  .stat-value { font-size: 28px; font-weight: 700; letter-spacing: -1px; font-family: 'JetBrains Mono', monospace; }
  .stat-sub { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }

  /* ── Ticker grid ── */
  .section-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px;
  }
  .section-title { font-size: 14px; font-weight: 600; color: var(--text-secondary); letter-spacing: -0.2px; }

  .ticker-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px;
    margin-bottom: 32px;
  }
  .ticker-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 20px 24px;
    transition: all var(--transition);
    cursor: default;
    position: relative;
    overflow: hidden;
  }
  .ticker-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    opacity: 0; transition: opacity var(--transition);
  }
  .ticker-card:hover { border-color: var(--border); box-shadow: var(--shadow-md); }
  .ticker-card:hover::before { opacity: 1; }
  .ticker-card.flash { animation: card-flash 0.6s ease-out; }
  @keyframes card-flash {
    0% { border-color: var(--accent); box-shadow: 0 0 20px var(--accent-dim); }
    100% { border-color: var(--border-subtle); box-shadow: none; }
  }

  .ticker-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
  .ticker-sym { font-size: 18px; font-weight: 700; letter-spacing: -0.5px; }
  .ticker-price {
    font-family: 'JetBrains Mono', monospace;
    font-size: 22px; font-weight: 600; letter-spacing: -0.5px;
  }
  .ticker-price.up { color: var(--green); }
  .ticker-price.down { color: var(--red); }

  .ticker-meta { display: flex; gap: 16px; margin-bottom: 16px; }
  .ticker-meta-item { font-size: 11px; color: var(--text-muted); }
  .ticker-meta-item span { color: var(--text-secondary); font-weight: 500; }

  /* Feature bars */
  .feature-list { display: flex; flex-direction: column; gap: 8px; }
  .feature-row { display: flex; align-items: center; gap: 10px; }
  .feature-name {
    font-size: 11px; font-family: 'JetBrains Mono', monospace;
    color: var(--text-muted); width: 140px; flex-shrink: 0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .feature-bar-track {
    flex: 1; height: 4px; background: var(--bg-elevated);
    border-radius: 2px; overflow: hidden; position: relative;
  }
  .feature-bar-fill {
    position: absolute; top: 0; left: 50%; height: 100%;
    border-radius: 2px; transition: all 0.4s ease-out;
    min-width: 2px;
  }
  .feature-val {
    font-size: 11px; font-family: 'JetBrains Mono', monospace;
    color: var(--text-secondary); width: 64px; text-align: right; flex-shrink: 0;
  }

  /* ── Prediction panel ── */
  .predict-row { display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }
  .predict-card {
    flex: 1; min-width: 200px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 20px 24px;
  }
  .predict-ticker { font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; }
  .predict-prob {
    font-family: 'JetBrains Mono', monospace;
    font-size: 32px; font-weight: 700; letter-spacing: -1px;
  }
  .predict-prob.bullish { color: var(--green); }
  .predict-prob.bearish { color: var(--red); }
  .predict-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }

  /* ── Event log ── */
  .log-container {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .log-header { padding: 16px 24px; border-bottom: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; }
  .log-body { max-height: 300px; overflow-y: auto; padding: 8px 0; }
  .log-body::-webkit-scrollbar { width: 6px; }
  .log-body::-webkit-scrollbar-track { background: transparent; }
  .log-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  .log-entry {
    display: flex; align-items: center; gap: 12px;
    padding: 8px 24px; font-size: 12px;
    transition: background var(--transition);
    animation: log-in 0.3s ease-out;
  }
  .log-entry:hover { background: var(--bg-elevated); }
  @keyframes log-in {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .log-time { font-family: 'JetBrains Mono', monospace; color: var(--text-muted); width: 80px; flex-shrink: 0; }
  .log-ticker {
    font-family: 'JetBrains Mono', monospace; font-weight: 600;
    color: var(--accent); width: 48px; flex-shrink: 0;
  }
  .log-msg { color: var(--text-secondary); flex: 1; }

  .empty-state {
    text-align: center; padding: 48px 24px; color: var(--text-muted); font-size: 13px;
  }
  .empty-state .icon { font-size: 32px; margin-bottom: 12px; opacity: 0.4; }

  /* ── Responsive ── */
  @media (max-width: 768px) {
    .stat-row { grid-template-columns: repeat(2, 1fr); }
    .ticker-grid { grid-template-columns: 1fr; }
    .container { padding: 16px; }
    .topbar { padding: 0 16px; }
  }
</style>
</head>
<body>

<div class="topbar">
  <div class="logo">
    <div class="dot"></div>
    <span>marketstore</span>
  </div>
  <div class="topbar-actions">
    <div class="ticker-input-group">
      <input type="text" class="ticker-input" id="ticker-input" placeholder="Add ticker" maxlength="5"
        onkeydown="if(event.key==='Enter')addTicker()">
      <button class="btn" onclick="addTicker()" style="padding:6px 10px">+</button>
    </div>
    <div class="status-pill" id="status-pill">
      <div class="status-dot"></div>
      <span id="status-text">disconnected</span>
    </div>
    <button class="btn primary" id="btn-start" onclick="startFeed()">Start Feed</button>
    <button class="btn danger" id="btn-stop" onclick="stopFeed()" style="display:none">Stop</button>
  </div>
</div>

<div class="container">

  <!-- Stats -->
  <div class="stat-row">
    <div class="stat-card">
      <div class="stat-label">Tickers Tracked</div>
      <div class="stat-value" id="stat-tickers">0</div>
      <div class="stat-sub">active symbols</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Ticks</div>
      <div class="stat-value" id="stat-ticks">0</div>
      <div class="stat-sub">since feed start</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Feature Updates</div>
      <div class="stat-value" id="stat-features">0</div>
      <div class="stat-sub">vectors computed</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Provider</div>
      <div class="stat-value" id="stat-provider" style="font-size:20px">—</div>
      <div class="stat-sub">data source</div>
    </div>
  </div>

  <!-- Model predictions -->
  <div class="section-header">
    <div class="section-title">Model Predictions</div>
    <div class="section-title" style="font-size:11px;color:var(--text-muted)">P(next day up) from online features</div>
  </div>
  <div class="predict-row" id="predict-row"></div>

  <!-- Live tickers -->
  <div class="section-header">
    <div class="section-title">Live Quotes & Features</div>
  </div>
  <div class="ticker-grid" id="ticker-grid">
    <div class="empty-state">
      <div class="icon">&#9889;</div>
      <div>Start the live feed to see real-time market data</div>
    </div>
  </div>

  <!-- Event log -->
  <div class="log-container">
    <div class="log-header">
      <div class="section-title">Event Log</div>
      <button class="btn" onclick="clearLog()" style="padding:4px 10px;font-size:11px">Clear</button>
    </div>
    <div class="log-body" id="log-body">
      <div class="empty-state" style="padding:24px">Waiting for events...</div>
    </div>
  </div>

</div>

<script>
const FEATURE_NAMES = ["rolling_5d_volatility", "rolling_20d_return", "volume_zscore", "price_momentum_10d"];
const FEATURE_RANGES = {
  rolling_5d_volatility: [0, 0.05],
  rolling_20d_return: [-0.15, 0.15],
  volume_zscore: [-3, 3],
  price_momentum_10d: [-0.15, 0.15],
};
const FEATURE_COLORS = {
  rolling_5d_volatility: "#6366f1",
  rolling_20d_return: "#22c55e",
  volume_zscore: "#06b6d4",
  price_momentum_10d: "#f59e0b",
};

let tickerData = {};
let featureUpdateCount = 0;
let totalTicks = 0;
let sse = null;
let pollInterval = null;

function formatNum(n, decimals = 2) {
  if (n == null) return "—";
  return Number(n).toFixed(decimals);
}

function formatPrice(n) {
  if (n == null) return "—";
  return "$" + Number(n).toFixed(2);
}

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
}

function addLog(ticker, msg) {
  const body = document.getElementById("log-body");
  if (body.querySelector(".empty-state")) body.innerHTML = "";
  const now = new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const el = document.createElement("div");
  el.className = "log-entry";
  el.innerHTML = `<span class="log-time">${now}</span><span class="log-ticker">${ticker}</span><span class="log-msg">${msg}</span>`;
  body.prepend(el);
  while (body.children.length > 200) body.removeChild(body.lastChild);
}

function clearLog() {
  document.getElementById("log-body").innerHTML = '<div class="empty-state" style="padding:24px">Waiting for events...</div>';
}

function featureBar(name, value) {
  const [lo, hi] = FEATURE_RANGES[name] || [-1, 1];
  const range = hi - lo;
  const norm = Math.max(0, Math.min(1, (value - lo) / range));  // 0..1
  const center = Math.max(0, Math.min(1, (0 - lo) / range));
  const pctCenter = center * 100;
  const pctVal = norm * 100;
  const width = Math.abs(pctVal - pctCenter);
  const left = Math.min(pctVal, pctCenter);
  const color = FEATURE_COLORS[name] || "#6366f1";

  return `<div class="feature-row">
    <span class="feature-name">${name.replace(/_/g, " ")}</span>
    <div class="feature-bar-track">
      <div class="feature-bar-fill" style="left:${left}%;width:${width}%;background:${color}"></div>
    </div>
    <span class="feature-val">${formatNum(value, 4)}</span>
  </div>`;
}

function renderTicker(tk) {
  const d = tickerData[tk];
  if (!d) return "";
  const priceClass = d.features?.rolling_20d_return > 0 ? "up" : d.features?.rolling_20d_return < 0 ? "down" : "";
  const featureHtml = d.features
    ? FEATURE_NAMES.map(f => featureBar(f, d.features[f] || 0)).join("")
    : '<div style="color:var(--text-muted);font-size:12px;padding:8px 0">Accumulating bars...</div>';

  return `<div class="ticker-card" id="card-${tk}">
    <button class="ticker-remove" onclick="removeTicker('${tk}')" title="Remove ${tk}">&times;</button>
    <div class="ticker-top">
      <div class="ticker-sym">${tk}</div>
      <div class="ticker-price ${priceClass}">${formatPrice(d.price)}</div>
    </div>
    <div class="ticker-meta">
      <div class="ticker-meta-item">Vol <span>${d.volume ? Math.round(d.volume).toLocaleString() : "—"}</span></div>
      <div class="ticker-meta-item">Ticks <span>${d.tick_count || 0}</span></div>
      <div class="ticker-meta-item">Updated <span>${formatTime(d.last_update)}</span></div>
    </div>
    <div class="feature-list">${featureHtml}</div>
  </div>`;
}

function renderPrediction(tk) {
  const d = tickerData[tk];
  if (!d || !d.prediction) return "";
  const p = d.prediction;
  const cls = p >= 0.5 ? "bullish" : "bearish";
  const label = p >= 0.5 ? "bullish" : "bearish";
  return `<div class="predict-card">
    <div class="predict-ticker">${tk}</div>
    <div class="predict-prob ${cls}">${(p * 100).toFixed(1)}%</div>
    <div class="predict-label">${label}</div>
  </div>`;
}

function renderAll() {
  const tickers = Object.keys(tickerData).sort();
  document.getElementById("stat-tickers").textContent = tickers.length;
  document.getElementById("stat-ticks").textContent = totalTicks.toLocaleString();
  document.getElementById("stat-features").textContent = featureUpdateCount.toLocaleString();

  const grid = document.getElementById("ticker-grid");
  grid.innerHTML = tickers.length ? tickers.map(renderTicker).join("") : '<div class="empty-state"><div class="icon">&#9889;</div><div>Start the live feed to see real-time market data</div></div>';

  const predRow = document.getElementById("predict-row");
  const predHtml = tickers.filter(tk => tickerData[tk].prediction != null).map(renderPrediction).join("");
  predRow.innerHTML = predHtml || '<div class="empty-state" style="padding:24px;width:100%">Predictions will appear after features are computed</div>';
}

function flashCard(tk) {
  const el = document.getElementById("card-" + tk);
  if (el) { el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
}

async function addTicker() {
  const input = document.getElementById("ticker-input");
  const raw = input.value.trim().toUpperCase();
  if (!raw || raw.length > 5) return;
  input.value = "";

  // Already tracking?
  if (tickerData[raw]) {
    addLog("SYS", `${raw} is already being tracked`);
    flashCard(raw);
    return;
  }

  try {
    const r = await fetch("/live/subscribe", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify([raw]),
    });
    if (!r.ok) {
      const err = await r.json();
      addLog("SYS", `Failed to add ${raw}: ${err.detail || "error"}`);
      return;
    }
    tickerData[raw] = {};
    addLog("SYS", `Subscribed to ${raw}`);
    renderAll();
    // Fetch data for it after a short delay
    setTimeout(async () => {
      await pollStatus();
      await fetchFeatures();
      await fetchPredictions();
    }, 2000);
  } catch (e) {
    addLog("SYS", `Failed to add ${raw}: ${e.message}`);
  }
}

async function removeTicker(tk) {
  try {
    await fetch("/live/subscribe/" + tk, { method: "DELETE" });
    delete tickerData[tk];
    addLog("SYS", `Removed ${tk}`);
    renderAll();
  } catch (e) {
    addLog("SYS", `Failed to remove ${tk}: ${e.message}`);
  }
}

async function pollStatus() {
  try {
    const r = await fetch("/live/status");
    const data = await r.json();
    const pill = document.getElementById("status-pill");
    const txt = document.getElementById("status-text");
    document.getElementById("stat-provider").textContent = data.provider || "—";

    if (data.status === "running") {
      pill.className = "status-pill connected";
      txt.textContent = "live";
      document.getElementById("btn-start").style.display = "none";
      document.getElementById("btn-stop").style.display = "";
    } else {
      pill.className = "status-pill";
      txt.textContent = data.status || "stopped";
    }

    for (const [tk, info] of Object.entries(data.tickers || {})) {
      if (!tickerData[tk]) tickerData[tk] = {};
      // Map status fields to what the renderer expects
      if (info.last_price != null) tickerData[tk].price = info.last_price;
      if (info.last_volume != null) tickerData[tk].volume = info.last_volume;
      tickerData[tk].last_update = info.last_update;
      tickerData[tk].tick_count = info.tick_count;
      tickerData[tk].bars_accumulated = info.bars_accumulated;
      tickerData[tk].features_ready = info.features_ready;
      totalTicks = Math.max(totalTicks, Object.values(data.tickers).reduce((s, t) => s + (t.tick_count || 0), 0));
    }
    renderAll();
  } catch (e) {}
}

async function fetchFeatures() {
  for (const tk of Object.keys(tickerData)) {
    try {
      const r = await fetch("/live/features/" + tk);
      if (r.ok) {
        const data = await r.json();
        tickerData[tk].features = data.features;
      }
    } catch (e) {}
  }
  renderAll();
}

async function fetchPredictions() {
  for (const tk of Object.keys(tickerData)) {
    try {
      const r = await fetch("/predict/" + tk);
      const data = await r.json();
      if (data.p_up != null) {
        tickerData[tk].prediction = data.p_up;
      }
    } catch (e) {}
  }
  renderAll();
}

function connectSSE() {
  if (sse) sse.close();
  sse = new EventSource("/live/stream");
  sse.addEventListener("connected", () => {
    addLog("SYS", "SSE stream connected");
  });
  sse.addEventListener("feature_update", (e) => {
    const data = JSON.parse(e.data);
    const tk = data.ticker;
    if (!tickerData[tk]) tickerData[tk] = {};
    tickerData[tk].features = data.features;
    tickerData[tk].last_update = data.timestamp;
    featureUpdateCount++;
    addLog(tk, FEATURE_NAMES.map(f => `${f.split("_").pop()}=${formatNum(data.features[f],4)}`).join("  "));
    renderAll();
    flashCard(tk);
    // Refresh prediction for this ticker
    fetch("/predict/" + tk).then(r => r.json()).then(d => {
      if (d.p_up != null) { tickerData[tk].prediction = d.p_up; renderAll(); }
    }).catch(() => {});
  });
  sse.onerror = () => {
    addLog("SYS", "SSE connection lost, reconnecting...");
  };
}

async function startFeed() {
  try {
    const r = await fetch("/live/start", { method: "POST" });
    const data = await r.json();
    addLog("SYS", `Feed started (${data.provider})`);
    document.getElementById("btn-start").style.display = "none";
    document.getElementById("btn-stop").style.display = "";
    connectSSE();
    pollInterval = setInterval(pollStatus, 3000);
    setInterval(fetchFeatures, 10000);
    setTimeout(() => { fetchFeatures(); fetchPredictions(); }, 3000);
    setInterval(fetchPredictions, 30000);
  } catch (e) {
    addLog("SYS", "Failed to start feed: " + e.message);
  }
}

async function stopFeed() {
  try {
    await fetch("/live/stop", { method: "POST" });
    addLog("SYS", "Feed stopped");
  } catch (e) {}
  if (sse) sse.close();
  if (pollInterval) clearInterval(pollInterval);
  document.getElementById("btn-start").style.display = "";
  document.getElementById("btn-stop").style.display = "none";
  document.getElementById("status-pill").className = "status-pill";
  document.getElementById("status-text").textContent = "stopped";
}

// Initial load: eagerly fetch all available data
async function initialLoad() {
  // 1. Get ticker list from health
  try {
    const h = await fetch("/health");
    const health = await h.json();
    for (const tk of (health.tickers || [])) tickerData[tk] = {};
  } catch (e) {}

  // 2. Get live status (prices, tick counts)
  await pollStatus();

  // 3. Fetch features and predictions for all tickers
  await Promise.all([fetchFeatures(), fetchPredictions()]);

  renderAll();

  // If feed is already running, connect SSE and start polling
  try {
    const r = await fetch("/live/status");
    const data = await r.json();
    if (data.status === "running") {
      connectSSE();
      pollInterval = setInterval(pollStatus, 3000);
      setInterval(fetchPredictions, 30000);
      setInterval(fetchFeatures, 10000);
      addLog("SYS", "Reconnected to running feed");
    }
  } catch (e) {}
}

initialLoad();
</script>
</body>
</html>
"""
