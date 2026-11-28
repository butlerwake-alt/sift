(() => {
  "use strict";

  const get = (id) => document.getElementById("market-" + id);
  const money = new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 2
  });
  const smallPrice = new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", minimumFractionDigits: 4, maximumFractionDigits: 6
  });
  const dateFormat = new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC"
  });
  const date = (value) => dateFormat.format(new Date(value + "T00:00:00Z"));
  const price = (value) => (value < 1 ? smallPrice : money).format(value);
  const percent = (value) => (value > 0 ? "+" : "") + value.toFixed(2) + "%";
  const change = (first, last) => (last / first - 1) * 100;
  const dayMs = 86400000;
  const storageKey = "sift.market.watchlist.v1";
  let watchlist = new Set();
  let assets;
  let selected;
  let filter = "all";
  let range = 30;
  let visiblePoints = [];

  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (Array.isArray(saved)) watchlist = new Set(saved);
  } catch {
    // The watchlist remains usable in memory when storage is unavailable.
  }

  function node(tag, text, className) {
    const element = document.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  function updateSave() {
    const saved = watchlist.has(selected);
    get("save").textContent = saved ? "★ Saved" : "☆ Watch";
    get("save").setAttribute("aria-pressed", saved);
    get("save").setAttribute("aria-label", "Watch " + selected);
  }

  function updateSelection() {
    for (const button of get("list").querySelectorAll("button")) {
      button.setAttribute("aria-current", String(button.dataset.symbol === selected));
    }
  }

  function renderList() {
    const search = get("search").value.trim().toLowerCase();
    const matches = Object.entries(assets).filter(([symbol, asset]) => {
      const matchesFilter = filter === "all"
        || (filter === "stocks" && asset.kind !== "crypto")
        || (filter === "crypto" && asset.kind === "crypto")
        || (filter === "saved" && watchlist.has(symbol));
      return matchesFilter && (symbol + " " + asset.name).toLowerCase().includes(search);
    });
    const list = get("list");
    list.replaceChildren();
    for (const [symbol, asset] of matches) {
      const button = node("button", "");
      button.type = "button";
      button.dataset.symbol = symbol;
      const label = node("span", "", "market-asset");
      label.append(node("strong", symbol), node("small", asset.name));
      const last = asset.points.at(-1);
      const previous = asset.points.at(-2);
      const move = last && previous ? change(previous[1], last[1]) : null;
      const quote = node("span", last ? price(last[1]) : "Unavailable", "market-number market-quote");
      if (last) quote.append(node("small", date(last[0])));
      button.append(
        label,
        quote,
        node("span", move === null ? "—" : percent(move), "market-number " +
          (move > 0 ? "market-up" : move < 0 ? "market-down" : ""))
      );
      const item = node("li", "");
      item.append(button);
      list.append(item);
    }
    updateSelection();
    const empty = get("empty");
    empty.hidden = matches.length > 0;
    empty.textContent = filter === "saved" && !watchlist.size
      ? "Your watchlist is empty. Select an asset and choose Watch."
      : "No assets match your search.";
  }

  function drawChart() {
    const canvas = get("chart");
    if (visiblePoints.length < 2 || canvas.hidden) return;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(ratio, ratio);
    const theme = getComputedStyle(canvas);
    const values = visiblePoints.map(([, value]) => value);
    const firstTime = Date.parse(visiblePoints[0][0]);
    const lastTime = Date.parse(visiblePoints.at(-1)[0]);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = (max - min || min * .01) * .12;
    const low = Math.max(0, min - padding);
    const high = max + padding;
    ctx.font = "11px monospace";
    const labelWidth = Math.max(ctx.measureText(price(high)).width, ctx.measureText(price(low)).width);
    const left = labelWidth + 9;
    const right = width - 8;
    const top = 12;
    const bottom = height - 22;
    const y = (value) => bottom - (value - low) / (high - low) * (bottom - top);
    ctx.strokeStyle = theme.getPropertyValue("--chart-grid").trim();
    ctx.fillStyle = theme.getPropertyValue("--muted").trim();
    ctx.textBaseline = "middle";
    for (let i = 0; i <= 4; i++) {
      const value = low + (high - low) * i / 4;
      const level = y(value);
      ctx.beginPath();
      ctx.moveTo(left, level);
      ctx.lineTo(right, level);
      ctx.stroke();
      ctx.fillText(price(value), 0, level);
    }
    ctx.fillText(visiblePoints[0][0], left, height - 7);
    ctx.textAlign = "right";
    ctx.fillText(visiblePoints.at(-1)[0], right, height - 7);
    ctx.beginPath();
    visiblePoints.forEach(([day, value], index) => {
      const x = left + (Date.parse(day) - firstTime) / (lastTime - firstTime) * (right - left);
      if (index === 0) ctx.moveTo(x, y(value));
      else ctx.lineTo(x, y(value));
    });
    ctx.strokeStyle = theme.getPropertyValue("--teal").trim();
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.stroke();
  }

  function renderChart() {
    const asset = assets[selected];
    const last = asset.points.at(-1);
    get("symbol").textContent = selected + " · " + asset.name;
    get("price").textContent = last ? price(last[1]) : "Close unavailable";
    const cutoff = last ? Date.parse(last[0]) - (range - 1) * dayMs : 0;
    visiblePoints = asset.points.filter(([day]) => Date.parse(day) >= cutoff);
    const first = visiblePoints[0];
    const chart = get("chart");
    chart.hidden = visiblePoints.length < 2;
    get("range-summary").textContent = chart.hidden ? "Too few closes for this chart."
      : date(first[0]) + " – " + date(last[0]) + " · " + percent(change(first[1], last[1])) + " over chart period";

    const crypto = asset.kind === "crypto";
    const source = node("a", crypto ? "Coinbase Exchange" : "Nasdaq");
    source.href = crypto ? "https://api.exchange.coinbase.com/products/" + selected + "-USD/candles?granularity=86400"
      : "https://www.nasdaq.com/market-activity/" + (asset.kind === "etf" ? "etf/" : "stocks/")
        + selected.toLowerCase() + "/historical";
    get("source").replaceChildren(
      last ? "Close of " + date(last[0]) + (crypto ? " (UTC day)" : " (US session)") + " · " : "",
      source
    );
    const age = last && Date.now() - Date.parse(last[0]);
    get("note").textContent = age > (crypto ? 3 : 5) * dayMs
      ? "Data may be stale. Check the closing date before using this price."
      : "Change in Market watch is versus the previous recorded close.";
    updateSave();
    drawChart();
  }

  function selectButton(id, button) {
    for (const control of get(id).querySelectorAll("button")) {
      control.setAttribute("aria-pressed", String(control === button));
    }
  }

  async function initialize() {
    try {
      const response = await fetch("data/markets.json", { signal: AbortSignal.timeout(10000) });
      if (!response.ok) throw new Error("Market snapshot unavailable");
      ({ assets } = await response.json());
      selected = Object.keys(assets).find((symbol) => assets[symbol].points.length);
      if (!selected) throw new Error("No recorded closes");
      get("dashboard").hidden = false;
      get("load").hidden = true;
      renderList();
      renderChart();
    } catch {
      get("dashboard").hidden = true;
      get("load").hidden = false;
      get("load").textContent = "Market prices are temporarily unavailable. Paper research is available below.";
      return;
    }

    get("list").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-symbol]");
      if (!button) return;
      selected = button.dataset.symbol;
      updateSelection();
      renderChart();
      if (window.matchMedia("(max-width: 820px)").matches) {
        get("symbol").tabIndex = -1;
        get("symbol").focus();
      }
    });
    get("search").addEventListener("input", renderList);
    get("filters").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-filter]");
      if (!button) return;
      filter = button.dataset.filter;
      selectButton("filters", button);
      renderList();
    });
    get("ranges").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-range]");
      if (!button) return;
      range = Number(button.dataset.range);
      selectButton("ranges", button);
      renderChart();
    });
    get("save").addEventListener("click", () => {
      if (watchlist.has(selected)) watchlist.delete(selected);
      else watchlist.add(selected);
      try {
        localStorage.setItem(storageKey, JSON.stringify([...watchlist]));
      } catch {
        get("note").textContent = "Browser storage is unavailable. Your changes last until this page closes.";
      }
      updateSave();
      if (filter === "saved") renderList();
    });
    new ResizeObserver(drawChart).observe(get("chart"));
    new MutationObserver(drawChart).observe(document.documentElement, {
      attributes: true, attributeFilter: ["data-theme"]
    });
  }

  initialize();
})();
