/* Interactive building blocks: data tables, tooltips, command palette, notifications,
   keyboard shortcuts, theme, skeletons and number animations. */
(function () {
  "use strict";
  var esc = UI.esc;

  function store(key, value) {
    try {
      if (value === undefined) return JSON.parse(localStorage.getItem("wmm." + key) || "null");
      localStorage.setItem("wmm." + key, JSON.stringify(value));
    } catch (e) { /* storage unavailable: settings last for this page only */ }
    return null;
  }

  /* ---------- data table ---------- */

  function csvCell(value) {
    var text = String(value == null ? "" : value);
    if (/^[=+\-@]/.test(text)) text = "'" + text;  // keep spreadsheets from evaluating formulas
    return /[",\n;]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function downloadText(name, text, type) {
    var url = URL.createObjectURL(new Blob([text], { type: type || "text/csv;charset=utf-8" }));
    var a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  /* columns: [{key, title, render(row), value(row) for sort/search/csv, cls, sortable}] */
  function dataTable(el, options) {
    var state = { query: "", sort: options.sort || null, desc: !!options.desc, page: 0, filters: {}, size: store("pageSize") || options.pageSize || 10 };
    var value = function (col, row) { return col.value ? col.value(row) : row[col.key]; };

    function rows() {
      var q = state.query.toLowerCase();
      var list = options.rows.filter(function (row) {
        for (var key in state.filters) {
          if (state.filters[key] && String(row[key]) !== state.filters[key]) return false;
        }
        if (!q) return true;
        return options.columns.some(function (c) { return String(value(c, row) == null ? "" : value(c, row)).toLowerCase().indexOf(q) >= 0; });
      });
      if (state.sort) {
        var col = options.columns.filter(function (c) { return c.key === state.sort; })[0];
        list = list.slice().sort(function (a, b) {
          var x = value(col, a), y = value(col, b);
          if (x == null) return 1;
          if (y == null) return -1;
          var r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: "base" });
          return state.desc ? -r : r;
        });
      }
      return list;
    }

    function draw() {
      var size = state.size;
      var list = rows(), pages = Math.max(1, Math.ceil(list.length / size));
      state.page = Math.min(state.page, pages - 1);
      var shown = list.slice(state.page * size, state.page * size + size);
      var bar = "";
      if (options.search !== false || options.filters || options.exportName) {
        bar = '<div class="dt-bar">' + (options.search !== false
          ? '<label class="dt-search">' + UI.icon("search") + '<span class="sr-only">Search</span><input type="search" placeholder="' + esc(options.placeholder || "Search…") + '" value="' + esc(state.query) + '"></label>' : "") +
          (options.filters || []).map(function (f) {
            return '<select data-filter="' + esc(f.key) + '" aria-label="' + esc(f.label) + '"><option value="">' + esc(f.label) + "</option>" + f.options.map(function (o) {
              return '<option value="' + esc(o[0]) + '"' + (state.filters[f.key] === o[0] ? " selected" : "") + ">" + esc(o[1]) + "</option>";
            }).join("") + "</select>";
          }).join("") + '<span style="flex:1"></span>' + (options.tools || "") +
          (options.exportName ? '<button class="btn btn-sm" type="button" data-copy title="Copy the filtered rows">Copy</button><button class="btn btn-sm" type="button" data-export>' +
            UI.icon("download") + "CSV</button>" : "") + "</div>";
      }
      var head = "<thead><tr>" + options.columns.map(function (c) {
        var sortable = c.sortable !== false && c.title;
        var mark = state.sort === c.key ? (state.desc ? "▼" : "▲") : "▲▼";
        return '<th class="' + (c.cls || "") + (sortable ? " sortable" : "") + (state.sort === c.key ? " sorted" : "") + '"' +
          (sortable ? ' data-sort="' + esc(c.key) + '" tabindex="0" aria-sort="' + (state.sort === c.key ? (state.desc ? "descending" : "ascending") : "none") + '"' : "") + ">" +
          esc(c.title || "") + (sortable ? '<span class="sort">' + mark + "</span>" : "") + "</th>";
      }).join("") + "</tr></thead>";
      var body = shown.length ? shown.map(function (row) {
        return "<tr>" + options.columns.map(function (c) {
          var v = c.render ? c.render(row) : esc(value(c, row) == null ? "—" : value(c, row));
          return '<td class="' + (c.cls || "") + '">' + v + "</td>";
        }).join("") + "</tr>";
      }).join("") : '<tr><td colspan="' + options.columns.length + '"><p class="empty">' + esc(options.empty || "Nothing to show.") + "</p></td></tr>";
      var foot = list.length > 10 || options.alwaysFoot ? '<div class="dt-foot"><span>' + (list.length ? (state.page * size + 1) + "–" + Math.min(list.length, (state.page + 1) * size) + " of " : "") + list.length +
        (list.length !== options.rows.length ? " (filtered from " + options.rows.length + ")" : "") + '</span><span class="dt-pages">' +
        '<label class="dt-size">Rows <select data-size aria-label="Rows per page">' + [10, 25, 50, 100].map(function (n) {
          return '<option value="' + n + '"' + (n === size ? " selected" : "") + ">" + n + "</option>";
        }).join("") + "</select></label>" +
        '<button class="btn btn-sm" type="button" data-page="-1"' + (state.page ? "" : " disabled") + ">Previous</button>" +
        '<button class="btn btn-sm" type="button" data-page="1"' + (state.page < pages - 1 ? "" : " disabled") + ">Next</button></span></div>" : "";
      var hadFocus = document.activeElement && el.contains(document.activeElement) && document.activeElement.type === "search";
      el.innerHTML = bar + '<div class="table-wrap"><table class="table">' + head + "<tbody>" + body + "</tbody></table></div>" + foot;
      if (hadFocus) {
        var input = el.querySelector('input[type="search"]');
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
      }
      if (options.after) options.after(el);
    }

    el.addEventListener("input", function (e) {
      if (e.target.type === "search") { state.query = e.target.value; state.page = 0; draw(); }
    });
    el.addEventListener("change", function (e) {
      if (e.target.hasAttribute && e.target.hasAttribute("data-size")) {
        state.size = Number(e.target.value);
        state.page = 0;
        store("pageSize", state.size);
        draw();
        return;
      }
      var key = e.target.getAttribute && e.target.getAttribute("data-filter");
      if (key) { state.filters[key] = e.target.value; state.page = 0; draw(); }
    });
    function sortBy(th) {
      var key = th.getAttribute("data-sort");
      if (state.sort === key) state.desc = !state.desc; else { state.sort = key; state.desc = false; }
      draw();
    }
    el.addEventListener("click", function (e) {
      var th = e.target.closest("[data-sort]");
      if (th) { sortBy(th); return; }
      var page = e.target.closest("[data-page]");
      if (page) { state.page += Number(page.getAttribute("data-page")); draw(); return; }
      if (e.target.closest("[data-copy]")) {
        var cols = options.columns.filter(function (c) { return c.title && c.csv !== false; });
        var tsv = [cols.map(function (c) { return c.title; }).join("\t")].concat(rows().map(function (row) {
          return cols.map(function (c) { var v = value(c, row); return v == null ? "" : String(v).replace(/[\t\n]/g, " "); }).join("\t");
        })).join("\n");
        (navigator.clipboard ? navigator.clipboard.writeText(tsv) : Promise.reject()).then(function () { UI.toast("Rows copied: paste them in Excel or a ticket.", "ok"); },
          function () { UI.toast("The clipboard is not available in this browser.", "warning"); });
        return;
      }
      if (e.target.closest("[data-export]")) {
        var list = rows();
        var cols = options.columns.filter(function (c) { return c.title && c.csv !== false; });
        var text = cols.map(function (c) { return csvCell(c.title); }).join(",") + "\n" + list.map(function (row) {
          return cols.map(function (c) { return csvCell(value(c, row)); }).join(",");
        }).join("\n");
        downloadText(options.exportName + ".csv", String.fromCharCode(0xFEFF) + text);
      }
    });
    el.addEventListener("keydown", function (e) {
      var th = e.target.closest && e.target.closest("[data-sort]");
      if (th && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); sortBy(th); }
    });
    draw();
    return { redraw: draw, setRows: function (r) { options.rows = r; draw(); } };
  }

  /* ---------- tooltips ---------- */

  var tip = null;
  document.addEventListener("mouseover", function (e) {
    var target = e.target.closest && e.target.closest("[data-tip]");
    if (!target) { if (tip) tip.hidden = true; return; }
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; tip.setAttribute("role", "tooltip"); document.body.appendChild(tip); }
    tip.textContent = target.getAttribute("data-tip");
    tip.hidden = false;
  });
  document.addEventListener("mousemove", function (e) {
    if (tip && !tip.hidden) { tip.style.left = e.clientX + "px"; tip.style.top = e.clientY + "px"; }
  });

  /* ---------- number animation ---------- */

  function countUp(root) {
    // Counting numbers follow the animation level (Settings › Appearance), which also covers reduced motion.
    var reduce = window.FX ? FX.level() === "off" : window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    Array.prototype.forEach.call(root.querySelectorAll("[data-count]"), function (el) {
      var target = Number(el.getAttribute("data-count"));
      if (!isFinite(target) || reduce) return;
      var decimals = (String(target).split(".")[1] || "").length, start = performance.now();
      (function frame(now) {
        var p = Math.min(1, (now - start) / 700), eased = 1 - Math.pow(1 - p, 3);
        el.textContent = (target * eased).toFixed(decimals);
        if (p < 1) requestAnimationFrame(frame);
      })(start);
    });
  }
  function num(value, decimals) {
    if (value == null || !isFinite(value)) return "—";
    var v = decimals != null ? Number(value).toFixed(decimals) : String(value);
    return '<span data-count="' + v + '">' + v + "</span>";
  }

  /* ---------- skeleton ---------- */

  function skeleton() {
    return '<div class="skeleton-grid"><div class="skeleton" style="height:44px;width:40%"></div>' +
      '<div class="grid grid-4" style="margin:0">' + [1, 2, 3, 4].map(function () { return '<div class="skeleton" style="height:104px"></div>'; }).join("") + "</div>" +
      '<div class="grid grid-2-1" style="margin:0"><div class="skeleton" style="height:280px"></div><div class="skeleton" style="height:280px"></div></div>' +
      '<div class="skeleton" style="height:220px"></div></div>';
  }

  /* ---------- theme ---------- */

  var theme = {
    get: function () { return store("theme") || "system"; },
    set: function (value) {
      store("theme", value);
      if (value === "system") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", value);
      var btn = document.getElementById("btn-theme");
      if (btn) btn.innerHTML = UI.icon(theme.isDark() ? "sun" : "moon");
    },
    isDark: function () {
      var t = theme.get();
      return t === "dark" || (t === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    },
    toggle: function () { theme.set(theme.isDark() ? "light" : "dark"); }
  };
  theme.set(theme.get());

  /* ---------- notifications ---------- */

  var notifications = {
    list: function () { return store("notifications") || []; },
    add: function (title, text, tone) {
      var list = notifications.list();
      list.unshift({ title: title, text: text || "", tone: tone || "info", time: new Date().toISOString(), unread: true });
      store("notifications", list.slice(0, 40));
      notifications.badge();
    },
    unread: function () { return notifications.list().filter(function (n) { return n.unread; }).length; },
    badge: function () {
      var el = document.getElementById("notif-count");
      if (!el) return;
      var n = notifications.unread();
      el.textContent = n > 9 ? "9+" : String(n);
      el.hidden = !n;
    },
    toggle: function () {
      var panel = document.getElementById("notif-panel");
      if (!panel.hidden) { panel.hidden = true; return; }
      var list = notifications.list();
      panel.innerHTML = '<div class="popover-head"><span>Notifications</span><button class="btn btn-sm btn-ghost" type="button" data-clear>Clear</button></div>' +
        (list.length ? list.map(function (n) {
          return '<div class="notif' + (n.unread ? " unread" : "") + '">' + UI.statusIcon(n.tone === "error" ? "error" : n.tone === "warning" ? "warning" : "ok") +
            '<div><div class="cell-title">' + esc(n.title) + '</div><div class="cell-sub">' + esc(n.text) + '</div><div class="notif-time">' + esc(UI.relative(n.time)) + "</div></div></div>";
        }).join("") : '<p class="empty" style="padding:14px">No notifications yet. Results of runs and scans appear here.</p>');
      panel.hidden = false;
      store("notifications", list.map(function (n) { n.unread = false; return n; }));
      notifications.badge();
      panel.querySelector("[data-clear]").addEventListener("click", function () { store("notifications", []); panel.hidden = true; notifications.badge(); });
    }
  };
  document.addEventListener("click", function (e) {
    var panel = document.getElementById("notif-panel");
    if (panel && !panel.hidden && !panel.contains(e.target) && !e.target.closest("#btn-notif")) panel.hidden = true;
  });

  /* ---------- command palette ---------- */

  var palette = {
    items: function () { return window.App ? App.commands() : []; },
    open: function () {
      if (document.querySelector(".palette")) return;
      var back = document.createElement("div");
      back.className = "modal-backdrop";
      back.style.alignItems = "flex-start";
      var box = document.createElement("div");
      box.className = "palette";
      box.setAttribute("role", "dialog");
      box.setAttribute("aria-label", "Command palette");
      box.innerHTML = '<input type="text" placeholder="Search pages, actions and commands…" aria-label="Search commands"><ul role="listbox"></ul>' +
        '<div class="palette-foot"><span><span class="kbd">↑</span> <span class="kbd">↓</span> navigate</span><span><span class="kbd">Enter</span> open</span><span><span class="kbd">Esc</span> close</span></div>';
      document.body.appendChild(back);
      document.body.appendChild(box);
      var input = box.querySelector("input"), ul = box.querySelector("ul"), active = 0, shown = [];
      function close() { back.remove(); box.remove(); }
      function render() {
        // Every word must match, in any order ("dns flush" finds "Flush DNS and ARP caches").
        var words = input.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
        var recent = store("recentCommands") || [];
        var items = palette.items();
        if (!words.length) {
          items = recent.map(function (title) {
            var found = items.filter(function (it) { return it.title === title; })[0];
            return found ? Object.assign({}, found, { group: "Recent commands" }) : null;
          }).filter(Boolean).concat(items);
        }
        shown = items.filter(function (it) {
          var text = (it.title + " " + (it.keywords || "") + " " + it.group + " " + (it.sub || "")).toLowerCase();
          return words.every(function (w) { return text.indexOf(w) >= 0; });
        }).slice(0, 40);
        active = Math.min(active, Math.max(0, shown.length - 1));
        var group = "", html = "";
        shown.forEach(function (it, i) {
          if (it.group !== group) { group = it.group; html += '<div class="palette-group">' + esc(group) + "</div>"; }
          html += '<li role="option" data-i="' + i + '"' + (i === active ? ' class="active" aria-selected="true"' : "") + ">" + UI.icon(it.icon || "play") +
            '<span class="grow">' + esc(it.title) + (it.sub ? ' <span class="kind">· ' + esc(it.sub) + "</span>" : "") + "</span>" + (it.badge || "") + "</li>";
        });
        ul.innerHTML = html || '<p class="empty" style="padding:12px">No match.</p>';
        var el = ul.querySelector(".active");
        if (el) el.scrollIntoView({ block: "nearest" });
      }
      function run(i) {
        var it = shown[i];
        if (!it) return;
        if (it.group !== "Pages" && it.group !== "Recent pages") {
          store("recentCommands", [it.title].concat((store("recentCommands") || []).filter(function (t) { return t !== it.title; })).slice(0, 5));
        }
        close();
        it.run();
      }
      input.addEventListener("input", function () { active = 0; render(); });
      input.addEventListener("keydown", function (e) {
        if (e.key === "ArrowDown") { active = Math.min(shown.length - 1, active + 1); render(); e.preventDefault(); }
        else if (e.key === "ArrowUp") { active = Math.max(0, active - 1); render(); e.preventDefault(); }
        else if (e.key === "Enter") { run(active); e.preventDefault(); }
        else if (e.key === "Escape") close();
      });
      ul.addEventListener("click", function (e) { var li = e.target.closest("li"); if (li) run(Number(li.getAttribute("data-i"))); });
      back.addEventListener("click", close);
      render();
      input.focus();
    }
  };

  /* ---------- keyboard shortcuts ---------- */

  var GOTO = { d: "dashboard", r: "recommendations", p: "performance", c: "cleanup", s: "storage", a: "startup", v: "services", k: "toolbox",
    l: "events", m: "processes", w: "registry", y: "hardware",
    i: "integrity", e: "security", u: "updates", n: "network", x: "activity", z: "actions", b: "playbooks", t: "schedules", h: "history", o: "reports", ",": "settings" };
  var pendingG = 0;

  function shortcutsHelp() {
    var rows = [["Ctrl K  or  /", "Command palette"], ["?", "This help"], ["Shift T", "Toggle light / dark theme"], ["Shift S", "Scan all areas"],
      ["Shift R", "Refresh the page"], ["Shift C", "Collapse or expand all cards"], ["Esc", "Close dialogs"]];
    Object.keys(GOTO).forEach(function (k) { rows.push(["G then " + k.toUpperCase(), "Go to " + UI.esc((window.App && App.pageTitle(GOTO[k])) || GOTO[k])]); });
    UI.modal("Keyboard shortcuts", '<div class="shortcuts">' + rows.map(function (r) {
      return "<div><span>" + r[1] + '</span><span class="kbd">' + esc(r[0]) + "</span></div>";
    }).join("") + "</div>", [{ label: "Close", cls: "btn-primary" }]);
  }

  document.addEventListener("keydown", function (e) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); palette.open(); return; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey || document.querySelector(".modal-backdrop")) return;
    if (store("noKeyShortcuts")) return;  // Settings › Behaviour: only Ctrl K stays, for screen readers and speech input
    if (e.key === "/") { e.preventDefault(); palette.open(); return; }
    if (e.key === "?") { e.preventDefault(); shortcutsHelp(); return; }
    if (e.key === "T" && e.shiftKey) { theme.toggle(); return; }
    if (e.key.toLowerCase() === "g") { pendingG = Date.now(); return; }
    if (pendingG && Date.now() - pendingG < 1200 && GOTO[e.key.toLowerCase()]) {
      location.hash = "#/" + GOTO[e.key.toLowerCase()];
      pendingG = 0;
    }
  });

  /* ---------- back to top, density ---------- */

  var scroller = document.getElementById("scroller"), toTop = document.getElementById("to-top");
  if (scroller && toTop) {
    scroller.addEventListener("scroll", function () { toTop.hidden = scroller.scrollTop < 500; }, { passive: true });
    toTop.addEventListener("click", function () { scroller.scrollTo({ top: 0 }); });
  }
  var density = {
    get: function () { return store("density") || "comfortable"; },
    set: function (value) { store("density", value); document.body.classList.toggle("density-compact", value === "compact"); }
  };
  density.set(density.get());

  /* ---------- report viewer ---------- */

  /* Shows the text output of one or more tools: find with highlighted matches, copy (plain or Markdown), download, print. */
  function reportViewer(title, text, sub) {
    var body = '<div class="viewer">' + (sub ? '<p class="muted small" style="margin:0 0 10px">' + esc(sub) + "</p>" : "") +
      '<div class="viewer-bar"><label class="dt-search">' + UI.icon("search") + '<span class="sr-only">Find in output</span>' +
      '<input type="search" data-find placeholder="Find in output…"></label><span class="muted small" data-hits></span><span class="grow"></span>' +
      '<button type="button" class="btn btn-sm" data-v="copy">' + UI.icon("download") + "Copy</button>" +
      '<button type="button" class="btn btn-sm" data-v="md" title="Copy as a Markdown block for a ticket">Markdown</button>' +
      '<button type="button" class="btn btn-sm" data-v="save">' + UI.icon("download") + "Download</button>" +
      '<button type="button" class="btn btn-sm" data-v="print">' + UI.icon("print") + "Print</button></div>" +
      '<pre class="log viewer-log" tabindex="0"></pre></div>';
    var done = UI.modal(title, body, [{ label: "Close", cls: "btn-primary" }]);
    var wrap = document.querySelector("#modal-root .modal-backdrop:last-child");
    if (!wrap) return done;
    wrap.querySelector(".modal").classList.add("modal-wide");
    var pre = wrap.querySelector(".viewer-log"), find = wrap.querySelector("[data-find]"), hits = wrap.querySelector("[data-hits]");
    function draw() {
      var q = find.value.trim();
      if (!q) { pre.textContent = text || "(no output)"; hits.textContent = ""; return; }
      var parts = String(text).split(new RegExp("(" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi"));
      pre.innerHTML = parts.map(function (p, i) { return i % 2 ? "<mark>" + esc(p) + "</mark>" : esc(p); }).join("");
      var n = (parts.length - 1) / 2;
      hits.textContent = n ? n + " match" + (n > 1 ? "es" : "") : "No match";
      var first = pre.querySelector("mark");
      if (first) first.scrollIntoView({ block: "center" });
    }
    find.addEventListener("input", draw);
    wrap.querySelector(".viewer-bar").addEventListener("click", function (e) {
      var b = e.target.closest("[data-v]");
      if (!b) return;
      var v = b.getAttribute("data-v"), name = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      if (v === "copy") App.copyText(text, "Output");
      if (v === "md") App.copyText("**" + title + "**" + (sub ? " — " + sub : "") + "\n\n```\n" + text + "\n```\n", "Markdown");
      if (v === "save") downloadText("wmm-" + name + ".txt", text, "text/plain;charset=utf-8");
      if (v === "print") { document.body.classList.add("printing-viewer"); window.print(); document.body.classList.remove("printing-viewer"); }
    });
    draw();
    return done;
  }

  /* Opens the stored output of one history run. */
  function showRunOutput(runId, title) {
    return API.get("/history/runs/" + runId + "/log").then(function (r) { return reportViewer(title || "Output", r.log || ""); },
      function (e) { UI.toast(e.message, "error"); });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-output]");
    if (!b) return;
    e.preventDefault();
    var card = b.closest("[data-id]"), a = card && window.App && App.action(card.getAttribute("data-id"));
    showRunOutput(b.getAttribute("data-output"), a ? a.title : b.getAttribute("data-title"));
  });

  /* ---------- what's new ---------- */

  function whatsNew(force) {
    return API.get("/changelog").then(function (c) {
      var seen = store("seenVersion");
      store("seenVersion", c.version);
      // First visit ever: nothing is "new" yet. After an upgrade, or on request, show the notes.
      if (!force && (!seen || seen === c.version)) return null;
      var r = c.releases[0];
      return UI.modal("What's new in " + r.version, '<p class="modal-text"><strong>' + esc(r.title) + '</strong> <span class="muted small">· ' + esc(r.date) + "</span></p>" +
        '<ul class="whatsnew-hl">' + r.highlights.map(function (h) { return "<li>" + UI.icon("sparkle") + "<span>" + esc(h) + "</span></li>"; }).join("") + "</ul>" +
        (r.changes.length ? '<details class="whatsnew-more"><summary>All ' + r.changes.length + " improvements</summary><ul>" +
          r.changes.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></details>" : ""),
        [{ label: "Open the Toolbox", cls: "btn-ghost", value: function () { return "toolbox"; } }, { label: "Got it", cls: "btn-primary" }]
      ).then(function (v) { if (v === "toolbox") location.hash = "#/toolbox"; });
    }, function () { return null; });
  }

  /* ---------- favicon progress ---------- */

  var faviconLink = document.querySelector('link[rel="icon"]'), faviconBase = faviconLink && faviconLink.href, faviconLast = null;
  /* Draws the progress of a run around the app icon in the browser tab; null restores the plain icon. */
  function faviconProgress(pct) {
    if (!faviconLink) return;
    var key = pct == null ? null : Math.round(pct / 5) * 5;  // redraw only every 5%
    if (key === faviconLast) return;
    faviconLast = key;
    if (key == null) { faviconLink.href = faviconBase; return; }
    var c = document.createElement("canvas");
    c.width = c.height = 64;
    var g = c.getContext("2d");
    g.fillStyle = "#0F6CBD";
    g.beginPath(); g.arc(32, 32, 24, 0, 2 * Math.PI); g.fill();
    g.lineWidth = 7; g.lineCap = "round";
    g.strokeStyle = "rgba(15,108,189,.25)"; g.beginPath(); g.arc(32, 32, 28, 0, 2 * Math.PI); g.stroke();
    g.strokeStyle = "#2E9D8F"; g.beginPath(); g.arc(32, 32, 28, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * key / 100); g.stroke();
    g.fillStyle = "#fff"; g.font = "bold 22px Segoe UI, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(String(key), 32, 33);
    faviconLink.href = c.toDataURL("image/png");
  }

  window.Components = {
    density: density,
    dataTable: dataTable, downloadText: downloadText, countUp: countUp, num: num, skeleton: skeleton,
    theme: theme, notifications: notifications, palette: palette, shortcutsHelp: shortcutsHelp, store: store,
    reportViewer: reportViewer, showRunOutput: showRunOutput, whatsNew: whatsNew, faviconProgress: faviconProgress
  };
})();
