/* Categories: the sidebar groups, their hub pages (#/cat-…) with every child page, and the category grid on the dashboard. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  var CATEGORIES = [
    { id: "overview", title: "Overview", icon: "dashboard", text: "The state of this PC at a glance and the improvements worth doing first.",
      pages: [["dashboard", "Dashboard", "Overall health, live system, key figures and this visit."],
        ["recommendations", "Recommendations", "Every improvement found by the scans, sorted by impact, with one-click fixes."]] },
    { id: "optimize", title: "Optimize", icon: "bolt", text: "Make the PC faster and free space: performance, cleanup, disks, startup and services.",
      pages: [["performance", "Performance", "Memory, CPU, power plans, visual effects and 80+ speed tools."],
        ["cleanup", "Cleanup", "Temporary files, caches, crash dumps and obsolete Windows components."],
        ["storage", "Storage", "Where the space goes, disk health, SMART and 30+ disk tools."],
        ["startup", "Startup & Apps", "Programs that start with Windows and the installed applications."],
        ["services", "Services", "Unnecessary services, with a backup of every change."]] },
    { id: "health", title: "Health", icon: "shield", text: "Keep Windows sound and safe: system files, security, updates, drivers and network.",
      pages: [["integrity", "System Integrity", "DISM, SFC, disk checks, crashes, reliability and the event log."],
        ["security", "Security", "Defender, firewall, BitLocker, TPM, Secure Boot and hardening."],
        ["updates", "Updates & Drivers", "Pending updates, drivers, devices with problems and app updates."],
        ["network", "Network", "Adapters, latency, DNS, Wi-Fi and network repairs."]] },
    { id: "system", title: "System", icon: "cpu", text: "Look inside Windows: event logs, running processes and services, and the registry.",
      pages: [["events", "Event Viewer", "Critical, hardware, application and service events, filterable and live."],
        ["processes", "Task Manager", "Every process and service with live usage; end, prioritize or start them."],
        ["registry", "Registry", "Browse, search and edit the registry, with a backup before every change."]] },
    { id: "operations", title: "Operations", icon: "play", text: "Run, combine, schedule and document the maintenance work.",
      pages: [["toolbox", "Toolbox", "Every tool by area: fixes and read-only reports."],
        ["actions", "Actions", "The whole catalog with filters, favorites and multi-select runs."],
        ["activity", "Activity", "Runs and scans in progress, with their live log."],
        ["playbooks", "Playbooks", "Ready-made sequences: quick tune-up, full maintenance, repair, hardening."],
        ["schedules", "Schedules", "Maintenance that runs on its own through Windows Task Scheduler."],
        ["history", "History", "Every run with its result, freed space and log."],
        ["reports", "Reports", "Branded reports for the customer, as PDF, HTML, CSV or JSON."]] },
    { id: "help", title: "Help & settings", icon: "support", text: "User guide, troubleshooting, appearance, installation and start-up options.",
      pages: [["support", "Support", "User guide, FAQ, troubleshooting and diagnostics for support."],
        ["settings", "Settings", "Report branding, appearance, guides, start-up and installation."]] }
  ];

  function byId(id) { return CATEGORIES.filter(function (c) { return c.id === id; })[0] || null; }
  function categoryOf(page) {
    if (page.indexOf("cat-") === 0) return byId(page.slice(4));
    for (var i = 0; i < CATEGORIES.length; i++) {
      for (var j = 0; j < CATEGORIES[i].pages.length; j++) if (CATEGORIES[i].pages[j][0] === page) return CATEGORIES[i];
    }
    return null;
  }
  function isArea(page) { return UI.AREAS.indexOf(page) >= 0; }
  function scoreChip(score) {
    return score == null ? '<span class="hub-score none" title="Not scanned yet">–</span>' : '<span class="hub-score ' + UI.tone(score) + '" title="Score">' + score + "</span>";
  }
  function average(cat, scores) {
    var list = cat.pages.map(function (p) { return scores[p[0]]; }).filter(function (s) { return s != null && isFinite(s); });
    return list.length ? Math.round(list.reduce(function (a, b) { return a + b; }, 0) / list.length) : null;
  }
  function iconColor(page) {
    var i = UI.AREAS.indexOf(page);
    return i >= 0 ? ' style="color:' + Charts.PALETTE[i % Charts.PALETTE.length] + '"' : "";
  }

  /* The category grid of the dashboard: every category with its child pages. */
  function overview(scores) {
    return '<div class="hub-grid">' + CATEGORIES.map(function (c) {
      var avg = average(c, scores);
      return '<section class="card hub-card"><a class="hub-card-head" href="#/cat-' + c.id + '"><span class="hub-icon">' + UI.icon(c.icon) + "</span>" +
        '<span class="grow"><strong>' + esc(c.title) + '</strong><span class="cell-sub">' + esc(c.text) + "</span></span>" + (avg != null ? scoreChip(avg) : "") +
        UI.icon("chevron") + '</a><ul class="hub-links">' + c.pages.map(function (p) {
          return '<li><a href="#/' + p[0] + '"><span class="hub-link-icon"' + iconColor(p[0]) + ">" + UI.icon(p[0]) + "</span>" + esc(p[1]) +
            (isArea(p[0]) ? scoreChip(scores[p[0]]) : "") + "</a></li>";
        }).join("") + "</ul></section>";
    }).join("") + "</div>";
  }

  /* One hub page per category: what it is for, every child page with its state, and the top improvements of its areas. */
  CATEGORIES.forEach(function (c) {
    window.Pages["cat-" + c.id] = {
      title: c.title,
      hub: true,
      render: function (el, App) {
        App.setSubtitle(c.pages.length + " pages");
        // Scores are loaded here too: right after a reload the hub can render before the shell has them.
        return Promise.all([API.get("/recommendations").catch(function () { return { items: [] }; }), App.refreshScores()]).then(function (all) {
          var r = all[0];
          var scores = App.state.scores || {}, areas = c.pages.map(function (p) { return p[0]; }).filter(isArea);
          var recs = r.items.filter(function (x) { return areas.indexOf(x.area) >= 0; });
          var avg = average(c, scores), high = recs.filter(function (x) { return x.impact === "high"; }).length;
          var tools = Object.keys(App.state.actions).filter(function (id) { return areas.indexOf(App.state.actions[id].area) >= 0; }).length;
          var oldest = areas.map(function (a) { return App.state.scanned[a]; }).filter(Boolean).sort()[0];
          var kpis = areas.length ? '<div class="grid grid-4">' +
            UI.kpi("Category score", avg != null ? Components.num(avg) : "—", areas.length + " areas", avg != null ? UI.tone(avg) : "") +
            UI.kpi("Open improvements", Components.num(recs.length), high + " high impact", recs.length ? (high ? "error" : "warning") : "ok") +
            UI.kpi("Tools", Components.num(tools), "Fixes and reports in these areas", "info") +
            UI.kpi("Oldest scan", esc(oldest ? UI.relative(oldest) : "never"), "Scan again for fresh data", "info") + "</div>" : "";
          el.innerHTML = '<section class="card hub-hero"><span class="hub-icon hub-icon-lg">' + UI.icon(c.icon) + '</span><div class="grow"><h2>' + esc(c.title) + "</h2><p>" + esc(c.text) + "</p></div>" +
            (areas.length ? '<div class="hub-hero-actions">' + UI.button("Scan these areas", 'id="hub-scan"', "", "refresh") +
              (recs.some(function (x) { return x.action_id && x.risk === "safe"; }) ? UI.button("Apply safe fixes", 'id="hub-safe"', "btn-primary", "bolt") : "") + "</div>" : "") +
            "</section>" + kpis + '<div class="section-title">' + UI.icon(c.icon) + 'Pages in this category<span class="extra">' + c.pages.length + "</span></div>" +
            '<div class="hub-pages">' + c.pages.map(function (p) {
              var page = p[0], sub = isArea(page) ? (App.state.scanned[page] ? "Scanned " + UI.relative(App.state.scanned[page]) : "Not scanned yet") : "";
              var n = recs.filter(function (x) { return x.area === page; }).length;
              return '<a class="card hub-page" href="#/' + page + '"><span class="hub-page-icon"' + iconColor(page) + ">" + UI.icon(page) + "</span>" +
                '<span class="grow"><strong>' + esc(p[1]) + '</strong><span class="cell-sub">' + esc(p[2]) + "</span>" +
                (sub ? '<span class="hub-page-meta">' + esc(sub) + (n ? " · " + n + " improvement" + (n > 1 ? "s" : "") : "") + "</span>" : "") + "</span>" +
                (isArea(page) ? scoreChip(scores[page]) : "") + '<span class="hub-open">' + UI.icon("chevron") + "</span></a>";
            }).join("") + "</div>" +
            (recs.length ? '<div class="grid">' + UI.card("Top improvements in " + c.title, UI.recommendations(recs.slice(0, 5), { showArea: true }),
              '<a class="btn btn-sm" href="#/recommendations">All recommendations</a>') + "</div>" : "");
          Components.countUp(el);
          var scan = el.querySelector("#hub-scan");
          if (scan) scan.addEventListener("click", function () {
            scan.disabled = true;
            scan.classList.add("busy");
            Promise.all(areas.map(function (a) { return API.post("/areas/" + a + "/scan"); })).then(function () {
              UI.toast(c.title + " scanned.", "ok");
              return App.refreshScores();
            }, function (e) { UI.toast(e.message, "error"); }).then(function () { App.render(); });
          });
          var safe = el.querySelector("#hub-safe");
          if (safe) safe.addEventListener("click", function () {
            App.runActions(App.order(recs.filter(function (x) { return x.action_id && x.risk === "safe"; }).map(function (x) { return x.action_id; })
              .filter(function (id, i, list) { return list.indexOf(id) === i; })));
          });
        });
      }
    };
  });

  /* Previous / next page inside the same category, shown at the bottom of every page. */
  function pager(page) {
    var c = categoryOf(page);
    if (!c || page.indexOf("cat-") === 0) return "";
    var ids = c.pages.map(function (p) { return p[0]; }), i = ids.indexOf(page), prev = c.pages[i - 1], next = c.pages[i + 1];
    return '<nav class="page-pager" aria-label="More in ' + esc(c.title) + '">' +
      (prev ? '<a href="#/' + prev[0] + '" class="pager-prev"><span class="cell-sub">Previous</span>' + esc(prev[1]) + "</a>" : "<span></span>") +
      '<a href="#/cat-' + c.id + '" class="pager-up">' + UI.icon(c.icon) + "All of " + esc(c.title) + "</a>" +
      (next ? '<a href="#/' + next[0] + '" class="pager-next"><span class="cell-sub">Next</span>' + esc(next[1]) + "</a>" : "<span></span>") + "</nav>";
  }

  window.Hubs = { CATEGORIES: CATEGORIES, categoryOf: categoryOf, byId: byId, overview: overview, pager: pager };
})();
