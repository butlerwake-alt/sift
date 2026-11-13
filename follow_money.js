/* Renders follow_money.html from data/follow_money.json (public disclosures, refreshed daily). Research only. No returns. */
(function () {
  "use strict";

  var DATA_URL = "data/follow_money.json";
  var STORE_KEY = "sift.followMoney.v1";

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null && text !== "") node.textContent = text;
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function loadFollow() {
    try {
      var parsed = JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function saveFollow(rows) {
    localStorage.setItem(STORE_KEY, JSON.stringify(rows));
  }

  function followId(sectionId, entity) {
    return sectionId + ":" + String(entity || "").toLowerCase().replace(/\s+/g, "-");
  }

  function isFollowed(rows, id) {
    return rows.some(function (row) { return row.id === id; });
  }

  function version() {
    var src = (document.querySelector('script[src*="follow_money.js"]') || {}).src || "";
    return (src.match(/[?&]v=([^&]+)/) || [])[1] || "1";
  }

  var NFA = "Research only, not financial advice. Place any trade yourself at your own broker.";

  function copyWithStatus(btn, text, statusNode) {
    var chrome = window.siftChrome;
    var label = btn.textContent;
    var done = function () {
      btn.textContent = "Copied ✓";
      btn.classList.add("is-copied");
      if (statusNode) statusNode.textContent = "Copied ✓ Research only.";
      setTimeout(function () { btn.textContent = label; btn.classList.remove("is-copied"); }, 1800);
    };
    var fail = function () { if (statusNode) statusNode.textContent = "Could not copy. Select the text on the card instead."; else btn.textContent = "Copy failed"; };
    if (chrome && chrome.copyText) chrome.copyText(text).then(done, fail);
    else fail();
  }

  function copyButton(text, label, statusNode) {
    var btn = el("button", "text-btn copy-btn", label || "Copy");
    btn.type = "button";
    btn.addEventListener("click", function (event) {
      event.stopPropagation();
      copyWithStatus(btn, text, statusNode);
    });
    return btn;
  }

  function linesFor(cards) {
    return cards.filter(function (c) { return c.copy_line; }).map(function (c) { return c.copy_line; });
  }

  function csvFor(section) {
    var rows = (section.cards || []).filter(function (c) { return c.csv && Object.keys(c.csv).length; });
    if (!rows.length) return "";
    var cols = Object.keys(rows[0].csv);
    var esc = function (v) {
      var t = v == null ? "" : String(v);
      return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
    };
    var out = [cols.join(",")];
    rows.forEach(function (c) { out.push(cols.map(function (k) { return esc(c.csv[k]); }).join(",")); });
    out.push("");
    out.push(esc(NFA));
    return out.join("\n");
  }

  function cardNode(section, card, rows) {
    var article = el("article", "signal-card drawer");
    article.setAttribute("data-drawer-group", "fm-" + section.id);
    article.id = card.id;
    var toggle = el("button", "row-toggle");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    var weight = (card.weights || []).length ? " · " + card.weights.join(", ") : "";
    if (card.sample) toggle.append(el("span", "chip chip-sample", "Sample"));
    else if (card.sector) toggle.append(el("span", "chip chip-sector", card.sector));
    toggle.append(el("span", "row-name", section.id === "funds" || section.id === "insiders" || section.id === "crypto" ? card.what + " · " + card.action + weight : card.what + " · " + card.action));
    toggle.append(el("span", "row-pnl", card.public_date && card.public_date !== "—" ? (section.public_label || "Public") + " " + card.public_date : ""));
    toggle.append(el("span", "fold-chevron"));
    toggle.lastChild.setAttribute("aria-hidden", "true");

    var body = el("div", "drawer-body");
    var desk = el("div", "drawer-desk signal-desk");
    if (card.sample) desk.append(el("span", "chip chip-sample", "Sample"));
    else if (card.sector) desk.append(el("span", "chip chip-sector", card.sector));
    desk.append(el("strong", "", card.who));
    body.append(desk);

    var dl = el("dl", "signal-facts");
    [
      ["Who", card.who],
      ["What", card.what + " · " + card.action],
      ["When public", (section.public_label || "Public") + ": " + card.public_date],
      [section.as_of_label || "As of", card.trade_date],
      ["Detail", card.detail],
      ["Why it matters", card.why],
      ["Confidence", card.confidence],
      ["Caveats", card.caveats]
    ].forEach(function (pair) {
      if (pair[1] == null || pair[1] === "") return;
      var wrap = el("div");
      wrap.append(el("dt", "", pair[0]));
      wrap.append(el("dd", "", pair[1]));
      dl.append(wrap);
    });
    if (card.source_url && !card.sample) {
      var wrap = el("div");
      wrap.append(el("dt", "", "Source"));
      var dd = el("dd");
      var a = el("a", "", "Open the original filing");
      a.href = card.source_url;
      a.rel = "noopener noreferrer";
      a.target = "_blank";
      dd.append(a);
      wrap.append(dd);
      dl.append(wrap);
    }
    body.append(dl);
    if (card.copy_line) {
      var row = el("div", "copy-actions");
      row.append(el("code", "copy-line", card.copy_line));
      row.append(copyButton(card.copy_line + "\n" + NFA, "Copy"));
      body.append(row);
    }
    article.append(toggle, body);
    return article;
  }

  function followButton(section, entity, rows) {
    var id = followId(section.id, entity);
    var btn = el("button", "follow-btn" + (isFollowed(rows, id) ? " is-on" : ""));
    btn.type = "button";
    btn.setAttribute("data-follow-id", id);
    btn.setAttribute("data-follow-label", entity);
    btn.setAttribute("data-follow-section", section.id);
    btn.textContent = isFollowed(rows, id) ? "Following" : "Follow";
    btn.setAttribute("aria-pressed", isFollowed(rows, id) ? "true" : "false");
    return btn;
  }

  function listText(section, cards, title) {
    var lines = [title || ("SIFT Follow the Money: " + section.title), NFA, "Disclosure lag: " + section.lag, ""];
    linesFor(cards || section.cards || []).forEach(function (line) { lines.push(line); });
    lines.push("");
    lines.push("Source: " + section.source_url);
    return lines.join("\n");
  }

  function renderList(mount) {
    var rows = loadFollow();
    clear(mount);
    if (!rows.length) {
      mount.append(el("p", "fm-empty", "Nothing followed yet. Follow is saved in this browser only."));
      return;
    }
    var ul = el("ul", "follow-items");
    rows.forEach(function (row) {
      var li = el("li");
      li.append(el("span", "", row.label + " · " + row.section));
      var remove = el("button", "follow-btn is-on", "Remove");
      remove.type = "button";
      remove.setAttribute("data-follow-id", row.id);
      remove.setAttribute("data-follow-remove", "1");
      li.append(remove);
      ul.append(li);
    });
    mount.append(ul);
  }

  var currentDoc = null;

  function paint(doc) {
    var root = document.getElementById("fm-root");
    if (!root) return;
    currentDoc = doc;
    clear(root);
    var rows = loadFollow();

    var jump = el("nav", "fm-jump");
    jump.setAttribute("aria-label", "Streams");
    doc.sections.forEach(function (section) {
      var link = el("a", "", section.title);
      link.href = "#" + section.id;
      jump.append(link);
    });
    root.append(jump);

    var coverage = el("section", "fold");
    coverage.id = "coverage";
    coverage.setAttribute("data-fold-group", "follow");
    coverage.append(foldHeading("Coverage and freshness", doc.coverage.freshness, "coverage-panel"));
    var coverageBody = el("div", "fold-body");
    coverageBody.id = "coverage-panel";
    var coverageInner = el("div", "fold-inner coverage-box");
    coverageInner.append(el("p", "", doc.coverage.publication_label));
    coverageInner.append(el("p", "", doc.coverage.freshness));
    var gaps = el("ul", "coverage-gaps");
    (doc.coverage.gaps || []).forEach(function (gap) {
      gaps.append(el("li", "", gap));
    });
    coverageInner.append(gaps);
    coverageBody.append(coverageInner);
    coverage.append(coverageBody);
    root.append(coverage);

    doc.sections.forEach(function (section) {
      var block = el("section", "fold");
      block.id = section.id;
      block.setAttribute("data-fold-group", "follow");
      block.append(foldHeading(section.title, section.summary, section.id + "-panel"));
      var body = el("div", "fold-body");
      body.id = section.id + "-panel";
      var inner = el("div", "fold-inner");
      inner.append(el("p", "stream-blurb", section.blurb));
      var source = el("p", "stream-source");
      source.append(document.createTextNode(section.source_name + ". "));
      var sourceLink = el("a", "", "Source");
      sourceLink.href = section.source_url;
      sourceLink.rel = "noopener noreferrer";
      sourceLink.target = "_blank";
      source.append(sourceLink);
      inner.append(source);
      inner.append(el("p", "stream-lag", "Disclosure lag: " + section.lag));
      var asOf = el("p", "stream-asof");
      if (section.stale) asOf.append(el("span", "chip chip-stale", "Stale"));
      var stamp = section.retrieved_at ? "Retrieved " + String(section.retrieved_at).slice(0, 10) : "";
      var newest = section.as_of ? "Newest record " + section.as_of : "";
      asOf.append(document.createTextNode([newest, stamp, section.stale_note || ""].filter(Boolean).join(" · ")));
      if (asOf.textContent) inner.append(asOf);
      if (section.note) inner.append(el("p", "stream-lag", section.note));
      inner.append(el("p", "fm-nfa", "Not financial advice. Research only. If you act on anything here, place the trade yourself at your own broker."));

      var groups = new Map();
      (section.cards || []).forEach(function (card) {
        var key = card.entity || card.who;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(card);
      });
      groups.forEach(function (cards, entity) {
        var group = el("div", "entity");
        var head = el("div", "entity-head");
        head.append(el("h3", "", entity));
        var tools = el("div", "entity-tools");
        if (linesFor(cards).length) tools.append(copyButton(listText(section, cards, entity + " (" + section.title + ")"), section.id === "funds" ? "Copy all + weights" : "Copy all"));
        tools.append(followButton(section, entity, rows));
        head.append(tools);
        group.append(head);
        cards.forEach(function (card) {
          group.append(cardNode(section, card, rows));
        });
        inner.append(group);
      });

      var actions = el("div", "copy-actions");
      var status = el("p", "copy-status");
      status.setAttribute("role", "status");
      if (linesFor(section.cards || []).length) actions.append(copyButton(listText(section), "Copy the whole list", status));
      var csv = csvFor(section);
      if (csv) {
        var dl = el("a", "text-btn", "Download CSV");
        dl.href = "data:text/csv;charset=utf-8," + encodeURIComponent(csv);
        dl.download = "sift_follow_money_" + section.id + ".csv";
        actions.append(dl);
      }
      actions.append(status);
      inner.append(actions);
      inner.append(el("p", "how-note", "Not financial advice. Copy buttons give you plain text to research or paper-trade; SIFT places no orders. If you trade, do it yourself at your own broker and start small. The lag above is part of the list, and copying a disclosed name is not the same as copying a result."));
      body.append(inner);
      block.append(body);
      root.append(block);
    });

    var follow = el("section", "fold");
    follow.id = "follow-list";
    follow.setAttribute("data-fold-group", "follow");
    follow.append(foldHeading("Follow list", "Saved in this browser only", "follow-list-panel"));
    var followBody = el("div", "fold-body");
    followBody.id = "follow-list-panel";
    var followInner = el("div", "fold-inner");
    followInner.append(el("p", "", "Bookmarks for entities on this page. Nothing is uploaded."));
    var listMount = el("div");
    listMount.id = "follow-list-items";
    followInner.append(listMount);
    followBody.append(followInner);
    follow.append(followBody);
    root.append(follow);
    renderList(listMount);
    if (window.siftChrome) window.siftChrome.refresh();
  }

  function foldHeading(title, summary, controls) {
    var heading = el("h2", "fold-heading");
    var btn = el("button", "fold-toggle");
    btn.type = "button";
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-controls", controls);
    btn.append(el("span", "fold-name", title));
    btn.append(el("span", "fold-sum", summary));
    var chev = el("span", "fold-chevron");
    chev.setAttribute("aria-hidden", "true");
    btn.append(chev);
    heading.append(btn);
    return heading;
  }

  function renderFollowMoney() {
    var root = document.getElementById("fm-root");
    if (!root) return;
    root.addEventListener("click", function (event) {
      var btn = event.target.closest(".follow-btn");
      if (!btn || !currentDoc) return;
      var id = btn.getAttribute("data-follow-id");
      if (!id) return;
      var saved = loadFollow();
      if (btn.getAttribute("data-follow-remove") === "1" || isFollowed(saved, id)) {
        saved = saved.filter(function (row) { return row.id !== id; });
      } else {
        saved.push({
          id: id,
          label: btn.getAttribute("data-follow-label") || id,
          section: btn.getAttribute("data-follow-section") || ""
        });
      }
      saveFollow(saved);
      paint(currentDoc);
    });
    var src = (document.querySelector('script[src*="follow_money.js"]') || {}).src || "";
    var file = DATA_URL + (src.indexOf("?") >= 0 ? src.slice(src.indexOf("?")) : "");
    fetch(file, { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(paint)
      .catch(function () {
        clear(root);
        root.append(el("p", "fm-error", "The feed could not be loaded. Try again in a minute."));
      });
  }

  window.renderFollowMoney = renderFollowMoney;
})();
