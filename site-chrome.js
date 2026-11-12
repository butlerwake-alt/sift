/* Shared nav, mobile accordions, and research-only copy. Presentation only. */
(function () {
  "use strict";

  var bound = false;
  var mobileQuery = window.matchMedia("(max-width: 768px)");

  function isMobile() {
    return mobileQuery.matches;
  }

  function reducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function slug(value) {
    var text = String(value || "section").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    return text.slice(0, 48) || "section";
  }

  function setInert(el, on) {
    if (!el) return;
    try {
      el.inert = !!on;
    } catch (err) {
      if (on) el.setAttribute("aria-hidden", "true");
      else el.removeAttribute("aria-hidden");
    }
  }

  function foldButton(fold) {
    return fold.querySelector(":scope > .fold-heading .fold-toggle, :scope > .fold-toggle");
  }

  function foldBody(fold) {
    return fold.querySelector(":scope > .fold-body");
  }

  function closeFold(fold) {
    fold.classList.remove("is-open");
    var btn = foldButton(fold);
    if (btn) btn.setAttribute("aria-expanded", "false");
    if (isMobile()) setInert(foldBody(fold), true);
  }

  function forceOpen(fold) {
    fold.classList.add("is-open");
    var btn = foldButton(fold);
    if (btn) btn.setAttribute("aria-expanded", "true");
    setInert(foldBody(fold), false);
  }

  function openFold(fold, opts) {
    opts = opts || {};
    var group = fold.getAttribute("data-fold-group");
    if (group) {
      document.querySelectorAll('.fold[data-fold-group="' + group + '"]').forEach(function (other) {
        if (other !== fold) closeFold(other);
      });
    }
    forceOpen(fold);
    if (opts.hash && fold.id) {
      if (location.hash !== "#" + fold.id) {
        history.replaceState(null, "", "#" + fold.id);
      }
    }
    if (opts.scroll) {
      fold.scrollIntoView({ block: "start", behavior: reducedMotion() ? "auto" : "smooth" });
    }
  }

  function wrapFoldTitles() {
    var used = {};
    document.querySelectorAll("[data-fold-title]").forEach(function (el) {
      if (el.closest(".fold")) return;
      var title = el.getAttribute("data-fold-title") || "Section";
      var base = el.getAttribute("data-fold-id") || slug(title);
      var id = base;
      var n = 2;
      while (used[id] || document.getElementById(id)) {
        id = base + "-" + n;
        n += 1;
      }
      used[id] = true;
      var fold = document.createElement("section");
      fold.className = "fold";
      fold.id = id;
      fold.setAttribute("data-fold-group", el.getAttribute("data-fold-group") || "page");
      var heading = document.createElement("h2");
      heading.className = "fold-heading";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "fold-toggle";
      btn.setAttribute("aria-expanded", "false");
      btn.setAttribute("aria-controls", id + "-panel");
      var name = document.createElement("span");
      name.className = "fold-name";
      name.textContent = title;
      var sum = document.createElement("span");
      sum.className = "fold-sum";
      sum.textContent = el.getAttribute("data-fold-sum") || "";
      var chev = document.createElement("span");
      chev.className = "fold-chevron";
      chev.setAttribute("aria-hidden", "true");
      btn.append(name, sum, chev);
      heading.append(btn);
      var body = document.createElement("div");
      body.className = "fold-body";
      body.id = id + "-panel";
      var inner = document.createElement("div");
      inner.className = "fold-inner";
      el.parentNode.insertBefore(fold, el);
      inner.appendChild(el);
      var next = fold.nextElementSibling;
      while (next && next.classList.contains("fold-attach")) {
        var take = next;
        next = next.nextElementSibling;
        inner.appendChild(take);
      }
      body.appendChild(inner);
      fold.append(heading, body);
    });
  }

  function refresh() {
    var mobile = isMobile();
    document.querySelectorAll(".fold").forEach(function (fold) {
      if (!mobile) {
        forceOpen(fold);
        return;
      }
      if (fold.dataset.foldInit === "1") return;
      if (fold.id && location.hash === "#" + fold.id) openFold(fold, { scroll: true });
      else closeFold(fold);
      fold.dataset.foldInit = "1";
    });
    openHashedDrawer();
  }

  function openHashedDrawer() {
    if (!isMobile() || !location.hash) return;
    var target = document.getElementById(location.hash.slice(1));
    if (!target || !target.classList.contains("drawer") || target.dataset.drawerInit === "1") return;
    openDrawer(target, { scroll: true });
    target.dataset.drawerInit = "1";
  }

  function closeDrawers(group, except) {
    document.querySelectorAll('.drawer[data-drawer-group="' + group + '"]').forEach(function (row) {
      if (row === except) return;
      row.classList.remove("is-open");
      var btn = row.querySelector(":scope > .row-toggle");
      if (btn) btn.setAttribute("aria-expanded", "false");
    });
  }

  function openDrawer(row, opts) {
    opts = opts || {};
    var group = row.getAttribute("data-drawer-group");
    if (group) closeDrawers(group, row);
    row.classList.add("is-open");
    var btn = row.querySelector(":scope > .row-toggle");
    if (btn) btn.setAttribute("aria-expanded", "true");
    if (opts.hash && row.id && location.hash !== "#" + row.id) history.replaceState(null, "", "#" + row.id);
    if (opts.scroll) row.scrollIntoView({ block: "start", behavior: reducedMotion() ? "auto" : "smooth" });
  }

  function toggleDrawer(row) {
    if (row.classList.contains("is-open")) {
      row.classList.remove("is-open");
      var btn = row.querySelector(":scope > .row-toggle");
      if (btn) btn.setAttribute("aria-expanded", "false");
      if (row.id && location.hash === "#" + row.id) history.replaceState(null, "", location.pathname + location.search);
      return;
    }
    openDrawer(row, { hash: true });
  }

  function copyText(text) {
    return new Promise(function (resolve, reject) {
      function fallback() {
        var area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.left = "-999px";
        document.body.appendChild(area);
        area.select();
        try {
          var ok = document.execCommand("copy");
          area.remove();
          if (ok) resolve();
          else reject(new Error("copy"));
        } catch (err) {
          area.remove();
          reject(err);
        }
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(resolve, fallback);
      } else {
        fallback();
      }
    });
  }

  function bind() {
    document.addEventListener("click", function (event) {
      var foldBtn = event.target.closest(".fold-toggle");
      if (foldBtn && isMobile()) {
        var fold = foldBtn.closest(".fold");
        if (!fold) return;
        if (fold.classList.contains("is-open")) {
          closeFold(fold);
          if (fold.id && location.hash === "#" + fold.id) {
            history.replaceState(null, "", location.pathname + location.search);
          }
        } else {
          openFold(fold, { hash: true });
        }
        return;
      }
      var rowBtn = event.target.closest(".row-toggle");
      if (rowBtn && isMobile()) {
        var row = rowBtn.closest(".drawer");
        if (row) toggleDrawer(row);
      }
    });

    var nav = document.querySelector(".site-nav");
    var navBtn = nav && nav.querySelector(".nav-toggle");
    var panel = document.getElementById("site-menu");
    if (nav && navBtn && panel) {
      navBtn.addEventListener("click", function () {
        var open = nav.classList.toggle("is-open");
        navBtn.setAttribute("aria-expanded", open ? "true" : "false");
      });
      panel.addEventListener("click", function (event) {
        if (event.target.closest("a")) {
          nav.classList.remove("is-open");
          navBtn.setAttribute("aria-expanded", "false");
        }
      });
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          nav.classList.remove("is-open");
          navBtn.setAttribute("aria-expanded", "false");
        }
      });
    }

    var topLink = document.querySelector(".to-top");
    if (topLink) {
      var showTop = function () { topLink.classList.toggle("is-on", window.scrollY > 480); };
      window.addEventListener("scroll", showTop, { passive: true });
      showTop();
      topLink.addEventListener("click", function (event) {
        if (reducedMotion()) return;
        event.preventDefault();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }

    window.addEventListener("hashchange", function () {
      if (!isMobile()) return;
      var id = location.hash.slice(1);
      if (!id) return;
      var node = document.getElementById(id);
      if (node && node.classList.contains("fold")) openFold(node, { scroll: true });
      else if (node && node.classList.contains("drawer")) openDrawer(node, { scroll: true });
    });

    if (mobileQuery.addEventListener) {
      mobileQuery.addEventListener("change", function () {
        document.querySelectorAll(".fold").forEach(function (fold) {
          delete fold.dataset.foldInit;
        });
        refresh();
      });
    }
  }

  function init() {
    wrapFoldTitles();
    if (!bound) {
      bind();
      bound = true;
    }
    refresh();
  }

  window.siftChrome = {
    refresh: refresh,
    wrap: function () {
      wrapFoldTitles();
      refresh();
    },
    copyText: copyText
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
