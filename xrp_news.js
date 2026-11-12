/* Drop-in renderer for data/xrp_news.json. Safe to include on news.html
   or to call from another page after the JSON has been fetched. */
(function (global) {
  "use strict";

  var DATA_URL = "data/xrp_news.json";
  var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null && text !== "") node.textContent = text;
    return node;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatDate(iso) {
    if (!iso) return "";
    var p = String(iso).slice(0, 10).split("-");
    if (p.length !== 3) return iso;
    var y = +p[0], m = +p[1], d = +p[2];
    if (!y || !m) return iso;
    return MONTHS[m - 1] + " " + d + ", " + y;
  }

  function formatStamp(iso) {
    if (!iso) return "Last updated: —";
    var dt = new Date(iso);
    if (isNaN(dt.getTime())) return "Last updated: —";
    try {
      var fmt = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/New_York",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit"
      });
      return "Last updated: " + fmt.format(dt) + " ET";
    } catch (e) {
      return "Last updated: " + iso;
    }
  }

  function statusClass(status) {
    if (status === "Confirmed") return "is-confirmed";
    if (status === "Reported") return "is-reported";
    return "is-rumor";
  }

  function chipClass(status) {
    if (status === "Confirmed") return "chip chip-confirmed";
    if (status === "Reported") return "chip chip-reported";
    return "chip chip-rumor";
  }

  function renderItem(item) {
    var li = el("li", "xrp-item " + statusClass(item.status));
    var top = el("div", "xrp-item-top");
    var time = el("time", "", formatDate(item.date));
    if (item.date) time.setAttribute("datetime", item.date);
    top.appendChild(time);
    top.appendChild(el("span", chipClass(item.status), item.status));
    li.appendChild(top);
    li.appendChild(el("h2", "", item.headline || ""));
    if (item.summary) li.appendChild(el("p", "", item.summary));
    var sources = Array.isArray(item.sources) ? item.sources : [];
    if (sources.length) {
      var ul = el("ul", "xrp-sources");
      sources.forEach(function (src) {
        if (!src || !src.url) return;
        var sli = document.createElement("li");
        var a = document.createElement("a");
        a.href = src.url;
        a.rel = "noopener noreferrer";
        a.target = "_blank";
        a.textContent = src.name || "Source";
        sli.appendChild(a);
        ul.appendChild(sli);
      });
      li.appendChild(ul);
    }
    li.setAttribute("data-status", item.status || "");
    return li;
  }

  function applyFilter(root, status) {
    var items = root.querySelectorAll(".xrp-item");
    var shown = 0;
    items.forEach(function (node) {
      var match = status === "all" || node.getAttribute("data-status") === status;
      node.hidden = !match;
      if (match) shown += 1;
    });
    var empty = root.querySelector(".xrp-empty-filter");
    if (!shown) {
      if (!empty) {
        empty = el("p", "xrp-empty xrp-empty-filter", "No items in this category for the current window.");
        root.appendChild(empty);
      }
      empty.hidden = false;
    } else if (empty) {
      empty.hidden = true;
    }
  }

  function paint(data, mount) {
    mount.innerHTML = "";
    var items = (data && Array.isArray(data.items)) ? data.items : [];
    if (!items.length) {
      mount.appendChild(el("p", "xrp-empty", "No verified items in the current window."));
      return;
    }
    var list = el("ul", "xrp-list");
    list.setAttribute("id", "xrp-news-list");
    items.forEach(function (item) {
      list.appendChild(renderItem(item));
    });
    mount.appendChild(list);

    var stamp = document.getElementById("stamp-when");
    if (stamp) stamp.textContent = formatStamp(data.generated_at);
  }

  function bindFilters(mount) {
    var buttons = document.querySelectorAll(".xrp-filter");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (other) {
          var on = other === btn;
          other.classList.toggle("is-on", on);
          other.setAttribute("aria-pressed", on ? "true" : "false");
        });
        applyFilter(mount, btn.getAttribute("data-filter") || "all");
      });
    });
  }

  function renderXrpNews(opts) {
    opts = opts || {};
    var mount = document.getElementById(opts.mountId || "xrp-news-root");
    var url = opts.url || DATA_URL;
    if (!mount) return;
    fetch(url, { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("Could not load news (" + res.status + ")");
        return res.json();
      })
      .then(function (data) {
        paint(data, mount);
        bindFilters(mount);
      })
      .catch(function (err) {
        mount.innerHTML = "";
        mount.appendChild(el("p", "xrp-error", "The news list could not be loaded. Please try again later."));
        console.error(err);
      });
  }

  global.renderXrpNews = renderXrpNews;
})(typeof window !== "undefined" ? window : this);
