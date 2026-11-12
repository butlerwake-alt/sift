/* Latest uploads from the SIFT YouTube channel. Renders only when SHOW_VIDEOS is true. */
(function () {
  "use strict";

  function cfg() {
    return window.SIFT_CONFIG || {};
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null && text !== "") node.textContent = text;
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function videoIdFrom(entry) {
    var nodes = entry.getElementsByTagName("yt:videoId");
    if (nodes.length && nodes[0].textContent) return nodes[0].textContent.trim();
    var idNode = entry.getElementsByTagName("id")[0];
    if (idNode && idNode.textContent) {
      var match = idNode.textContent.match(/yt:video:([A-Za-z0-9_-]{6,})/);
      if (match) return match[1];
    }
    var link = entry.querySelector("link[rel='alternate']") || entry.getElementsByTagName("link")[0];
    var href = link && link.getAttribute("href");
    if (!href) return "";
    var query = href.match(/[?&]v=([A-Za-z0-9_-]{6,})/);
    return query ? query[1] : "";
  }

  function embed(id, title) {
    var frame = document.createElement("iframe");
    frame.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id);
    frame.title = title || "YouTube video";
    frame.loading = "lazy";
    frame.setAttribute("allowfullscreen", "");
    frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    frame.setAttribute("allow", "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share");
    return frame;
  }

  function playlist(channelId) {
    var uploads = "UU" + String(channelId || "").slice(2);
    var frame = document.createElement("iframe");
    frame.className = "video-playlist";
    frame.src = "https://www.youtube-nocookie.com/embed/videoseries?list=" + encodeURIComponent(uploads);
    frame.title = "Latest uploads from " + (cfg().YT_HANDLE || "the SIFT channel");
    frame.loading = "lazy";
    frame.setAttribute("allowfullscreen", "");
    frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    frame.setAttribute("allow", "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share");
    return frame;
  }

  function shell(root) {
    clear(root);
    var head = el("div", "section-head");
    var h = el("h2", "fold-dup", "Latest from the channel");
    var p = el("p");
    p.append(document.createTextNode("Embeds load from the public "));
    var link = el("a", "", cfg().YT_HANDLE || "YouTube channel");
    link.href = cfg().YT_SHORTS_URL || "https://www.youtube.com/@SIFTstrategies/shorts";
    link.rel = "noopener noreferrer";
    link.target = "_blank";
    p.append(link);
    p.append(document.createTextNode(". Shorts open in the Shorts tab. Nothing here is a paper result."));
    head.append(h, p);
    root.append(head);
    return root;
  }

  function paintEntries(root, entries) {
    shell(root);
    var grid = el("div", "video-grid");
    entries.forEach(function (entry) {
      var card = el("article", "video-card");
      card.append(embed(entry.id, entry.title));
      card.append(el("p", "video-title", entry.title));
      if (entry.published) card.append(el("p", "meta", entry.published));
      grid.append(card);
    });
    root.append(grid);
  }

  function paintPlaylist(root, note) {
    shell(root);
    root.append(playlist(cfg().YT_CHANNEL_ID));
    root.append(el("p", "meta", note));
  }

  function renderVideos() {
    if (cfg().SHOW_VIDEOS !== true) return;
    var root = document.getElementById("videos-root");
    if (!root || root.dataset.ready === "1") return;
    root.dataset.ready = "1";
    var channel = cfg().YT_CHANNEL_ID;
    if (!channel) {
      root.append(el("p", "meta", "No channel id is configured."));
      return;
    }
    var feed = "https://www.youtube.com/feeds/videos.xml?channel_id=" + encodeURIComponent(channel);
    fetch(feed)
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.text();
      })
      .then(function (xml) {
        var doc = new DOMParser().parseFromString(xml, "text/xml");
        var entries = Array.prototype.slice.call(doc.getElementsByTagName("entry")).slice(0, 6).map(function (entry) {
          var titleNode = entry.getElementsByTagName("title")[0];
          var published = entry.getElementsByTagName("published")[0];
          return {
            id: videoIdFrom(entry),
            title: titleNode ? titleNode.textContent : "Video",
            published: published ? published.textContent.slice(0, 10) : ""
          };
        }).filter(function (entry) { return entry.id; });
        if (!entries.length) throw new Error("empty");
        paintEntries(root, entries);
      })
      .catch(function () {
        paintPlaylist(root, "The feed could not be read from this page, so this is the channel’s public uploads playlist. Use the Shorts tab for vertical posts only.");
      });
  }

  window.renderVideos = renderVideos;
})();
