/* Console shell: grouped navigation, top bar, status bar, activity drawer and shared actions. */
(function () {
  "use strict";
  var esc = UI.esc;
  var NAV = [
    ["Overview", [["dashboard", "Dashboard"], ["recommendations", "Recommendations"]]],
    ["Optimize", [["performance", "Performance"], ["cleanup", "Cleanup"], ["storage", "Storage"], ["startup", "Startup & Apps"], ["services", "Services"]]],
    ["Health", [["integrity", "System Integrity"], ["security", "Security"], ["updates", "Updates & Drivers"], ["network", "Network"]]],
    ["Operations", [["actions", "Actions"], ["activity", "Activity"], ["playbooks", "Playbooks"], ["schedules", "Schedules"], ["history", "History"], ["reports", "Reports"]]],
    ["", [["support", "Support"], ["settings", "Settings"]]]
  ];
  var PSEUDO_ACTIONS = { "startup.toggle": { id: "startup.toggle", title: "Startup entry changed", area: "startup", risk: "moderate" } };
  var state = { info: null, actions: {}, page: null, job: null, poll: null, rendering: 0, scores: {}, scanned: {}, leave: [], scanning: false, connected: true,
    scrollPos: {}, playbooks: [] };

  function current() {
    var name = (location.hash || "").replace(/^#\/?/, "").split("?")[0];
    return window.Pages[name] ? name : "dashboard";
  }
  function groupOf(page) {
    for (var i = 0; i < NAV.length; i++) {
      for (var j = 0; j < NAV[i][1].length; j++) if (NAV[i][1][j][0] === page) return NAV[i][0];
    }
    return "";
  }

  function renderNav() {
    var page = current();
    document.getElementById("nav").innerHTML = NAV.map(function (group) {
      return (group[0] ? '<div class="nav-group">' + esc(group[0]) + "</div>" : '<div class="nav-group" aria-hidden="true">&nbsp;</div>') + group[1].map(function (item) {
        var score = state.scores[item[0]];
        var chip = item[0] in state.scores
          ? '<span class="nav-score ' + (score == null ? "none" : UI.tone(score)) + '" title="Score">' + (score == null ? "–" : score) + "</span>" : "";
        if (item[0] === "activity" && state.activeCount) chip = '<span class="nav-live" title="Operations in progress">' + state.activeCount + "</span>";
        return '<a href="#/' + item[0] + '" class="nav-item' + (item[0] === page ? " active" : "") + '"' + (item[0] === page ? ' aria-current="page"' : "") +
          ' title="' + esc(item[1]) + '">' + UI.icon(item[0]) + '<span class="nav-label">' + esc(item[1]) + "</span>" + chip + "</a>";
      }).join("");
    }).join("");
  }

  function renderChrome() {
    var info = state.info;
    if (!info) return;
    document.getElementById("topbar-meta").innerHTML =
      '<span class="meta-item" title="Machine ID: ' + esc(info.machine_id) + '"><span class="meta-label">Device</span>' + esc(info.hostname) + "</span>" +
      '<span class="pill ' + (info.preview ? "pill-info" : info.admin ? "pill-ok" : "pill-warning") + '">' +
      (info.preview ? "Preview mode" : info.admin ? "Administrator" : "Read-only") + "</span>";
    document.getElementById("sidebar-meta").innerHTML = "Version " + esc(info.version) + "<br>Local agent · 127.0.0.1";
    var banner = "";
    var bannerBtn = function (attr, label) { return '<button class="btn btn-sm" type="button" ' + attr + ' style="margin-left:auto">' + label + "</button>"; };
    if (!API.hasToken()) {
      banner = '<div class="banner banner-warning">' + UI.icon("info") + "<span><strong>This window is not connected.</strong> It can show data but cannot run or schedule actions.</span>" +
        bannerBtn("data-request-access", "Request access") + "</div>";
    } else if (info.preview) {
      banner = '<div class="banner banner-info">' + UI.icon("info") + "<span><strong>Preview mode.</strong> Actions are simulated and nothing on this PC is changed. Schedules are disabled.</span>" +
        bannerBtn("data-elevate", "Restart with full rights") + "</div>";
    } else if (!info.admin) {
      banner = '<div class="banner banner-warning">' + UI.icon("info") + "<span><strong>Read-only.</strong> Windows denies changes without administrator rights.</span>" +
        bannerBtn("data-elevate", "Restart as administrator") + "</div>";
    }
    document.getElementById("banner").innerHTML = banner;
    // The power button exists only for a connected administrator console.
    document.getElementById("btn-power").hidden = !(info.admin && !info.preview && API.hasToken());
    renderStatus();
  }

  function renderStatus() {
    var info = state.info || {};
    var times = Object.keys(state.scanned).map(function (k) { return state.scanned[k]; }).filter(Boolean).sort();
    var running = state.job && state.job.active;
    document.getElementById("statusbar").innerHTML =
      '<span class="st"><span class="led' + (state.connected ? "" : " off") + '"></span>' + (state.connected ? "Agent connected" : "Agent not reachable") + "</span>" +
      '<span class="st">' + (info.preview ? "Preview mode" : info.admin ? "Administrator" : "Read-only") + "</span>" +
      (state.health ? '<a class="st" href="#/settings" title="Health check">' + '<span class="led' + (state.health.summary.error ? " off" : "") + '"' +
        (state.health.summary.warning && !state.health.summary.error ? ' style="background:var(--warning);box-shadow:0 0 0 3px var(--warning-soft)"' : "") + "></span>Health: " +
        (state.health.summary.error ? state.health.summary.error + " failed" : state.health.summary.warning ? state.health.summary.warning + " warnings" : "all checks passed") + "</a>" : "") +
      '<span class="st">Oldest area scan: ' + esc(times.length ? UI.relative(times[0]) : "never") + "</span>" +
      (state.scanning ? '<span class="st"><span class="led busy"></span>Scanning all areas…</span>' : "") +
      (running ? '<a class="st" href="#/activity"><span class="led busy"></span>Run in progress · ' + Math.round(state.job.percent || 0) + "% (" + state.job.done + "/" + state.job.total + ")</a>" : "") +
      '<span class="grow"></span><span class="st"><span class="kbd">Ctrl K</span> commands</span><span class="st"><span class="kbd">?</span> shortcuts</span>' +
      '<button type="button" class="st st-copy" data-copy-id title="Copy the machine ID">' + esc(info.machine_id || "") + "</button>";
  }

  function refreshScores() {
    return API.get("/dashboard").then(function (d) {
      state.scores = {};
      UI.AREAS.forEach(function (a) { state.scores[a] = d.scores[a]; });
      state.scores.dashboard = d.scores.overall;
      state.scanned = d.scanned;
      renderNav();
      renderStatus();
      return d;
    }, function () { return null; });
  }

  function render() {
    var name = current();
    var page = window.Pages[name];
    var token = ++state.rendering;
    state.leave.splice(0).forEach(function (fn) { try { fn(); } catch (e) { /* page already gone */ } });
    state.page = name;
    renderNav();
    var group = groupOf(name);
    document.getElementById("crumbs").innerHTML = "<span>Windows Maintenance Manager</span>" + (group ? "<span>" + esc(group) + "</span>" : "");
    var area = UI.AREAS.indexOf(name);
    document.getElementById("page-title").innerHTML = '<span class="title-icon"' + (area >= 0 ? ' style="color:' + Charts.PALETTE[area % Charts.PALETTE.length] + '"' : "") + ">" +
      UI.icon(name) + "</span>" + esc(page.title);
    document.getElementById("page-sub").textContent = "";
    updateTitle();
    var content = document.getElementById("content");
    var scroller = document.getElementById("scroller");
    // Each page keeps its own scroll position; a refresh of the same page keeps the current one.
    if (state.lastPage && state.lastPage !== name) state.scrollPos[state.lastPage] = scroller.scrollTop;
    var restore = state.lastPage !== name ? state.scrollPos[name] || 0 : scroller.scrollTop;
    var arriving = state.lastPage !== name;  // refreshes of the same page do not replay the entrance
    state.lastPage = name;
    Components.store("lastPage", name);
    content.innerHTML = Components.skeleton();
    Promise.resolve().then(function () { return page.render(content, App); }).then(function () {
      if (token !== state.rendering) return;
      Components.countUp(content);
      if (arriving) FX.pageEnter(content);
      scroller.scrollTop = restore;
      if (area >= 0) fixButton(content, name, token);
    }).catch(function (error) {
      if (token === state.rendering) content.innerHTML = UI.errorBox(error);
    });
  }

  /* Area pages: one button applies every one-click improvement found for that area. */
  function fixButton(content, area, token) {
    API.get("/recommendations").then(function (r) {
      var ids = order(r.items.filter(function (x) { return x.area === area && x.action_id && state.actions[x.action_id]; })
        .map(function (x) { return x.action_id; }).filter(function (id, i, list) { return list.indexOf(id) === i; }));
      var bar = content.querySelector(".page-actions");
      if (!ids.length || !bar || token !== state.rendering) return;
      bar.insertAdjacentHTML("afterbegin", UI.button("Fix recommended (" + ids.length + ")", 'data-fix-area title="Apply the one-click improvements of this area"', "", "sparkle"));
      bar.querySelector("[data-fix-area]").addEventListener("click", function () { runActions(ids); });
    }, function () { /* the button is optional */ });
  }
  /* DISM before SFC, like the playbooks. */
  function order(ids) {
    var rank = function (x) { return x === "integrity.dism" ? 0 : x === "integrity.sfc" ? 1 : 2; };
    return ids.slice().sort(function (a, b) { return rank(a) - rank(b); });
  }

  /* The browser tab shows the run percentage, so progress is visible from other tabs too. */
  function updateTitle() {
    var page = window.Pages[state.page], job = state.job && state.job.active ? state.job : null;
    var pct = job ? (job.percent != null ? job.percent : 100 * job.done / Math.max(1, job.total)) : null;
    document.title = (pct != null ? Math.round(pct) + "% · " : "") + (page ? page.title : "") + " · Windows Maintenance Manager";
  }

  function onLeave(fn) { state.leave.push(fn); }

  /* Thin progress line under the top bar, visible on every page. */
  function updateProgress() {
    var bar = document.getElementById("top-progress");
    var job = state.job && state.job.active ? state.job : null;
    bar.classList.toggle("indeterminate", !job && (state.scanning || state.tasksActive > 0));
    bar.firstChild.style.width = job ? Math.max(3, job.percent != null ? job.percent : Math.round(100 * job.done / Math.max(1, job.total))) + "%" : (state.scanning || state.tasksActive ? "" : "0");
  }

  function pollActivity() {
    API.get("/activity").then(function (a) {
      var tasks = a.tasks.filter(function (t) { return t.active; }).length;
      var jobs = a.jobs.filter(function (j) { return j.active; }).length;
      var changed = state.activeCount !== tasks + jobs;
      state.tasksActive = tasks;
      state.activeCount = tasks + jobs;
      if (changed) renderNav();
      updateProgress();
    }, function () { /* the status bar shows connectivity */ });
  }
  function isCurrent(name) { return state.page === name; }

  /* ---------- activity drawer ---------- */

  function openDrawer() { document.getElementById("drawer").hidden = false; renderDrawer(); }
  function closeDrawer() { document.getElementById("drawer").hidden = true; }

  function renderDrawer() {
    var body = document.getElementById("drawer-body");
    var job = state.job;
    if (!job) {
      body.innerHTML = '<p class="empty">No run in this session. Recent runs are listed in History.</p>';
      return;
    }
    var pct = job.percent != null ? job.percent : (job.total ? Math.round(100 * job.done / job.total) : 0);
    var title = job.current && action(job.current) ? action(job.current).title : job.current === "restore_point" ? "Creating a restore point" : "";
    var shape = (job.id || "") + "|" + job.results.length + "|" + job.active;
    // Same job and same results: only move the bar and append the log, so the animation keeps gliding.
    if (body.getAttribute("data-shape") === shape) {
      body.querySelector(".progress > div").style.width = Math.max(2, pct) + "%";
      body.querySelector("[data-pct]").innerHTML = pct.toFixed(pct < 10 ? 1 : 0) + "%" + (job.estimated ? "<small>estimated</small>" : "");
      body.querySelector("[data-current]").textContent = title;
      var log = body.querySelector(".log"), stickLog = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
      log.textContent = job.log.slice(-400).join("\n");
      if (stickLog) log.scrollTop = log.scrollHeight;
      return;
    }
    body.setAttribute("data-shape", shape);
    var logEl = body.querySelector(".log");
    var stick = !logEl || logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 20;
    body.innerHTML =
      '<div class="job-status">' + (job.active ? '<span class="spinner"></span><strong>Running</strong> <span data-current>' + esc(title) + "</span>" : UI.statusIcon("ok") + "<strong>Completed</strong><span data-current hidden></span>") + "</div>" +
      '<div class="progress' + (job.active ? "" : " done") + '"><div style="width:' + Math.max(2, pct) + '%"></div></div>' +
      '<div class="progress-meta"><span class="pct" data-pct>' + pct.toFixed(pct < 10 ? 1 : 0) + "%" + (job.estimated ? "<small>estimated</small>" : "") +
      '</span><span class="muted small">' + job.done + " of " + job.total + " actions</span></div>" +
      '<ul class="job-results">' + job.results.map(function (r) {
        var a = action(r.action_id);
        return "<li>" + UI.statusBadge(r.status) + "<span>" + esc(a ? a.title : r.action_id) + '</span><span class="muted small">' +
          esc(r.note || "") + (r.bytes_freed ? " · freed " + UI.formatBytes(r.bytes_freed) : "") + "</span></li>";
      }).join("") + "</ul>" +
      '<div class="log-head">Live log<span class="grow"></span><button class="btn btn-sm btn-ghost" type="button" data-log="copy">' + UI.icon("download") + "Copy</button>" +
      '<button class="btn btn-sm btn-ghost" type="button" data-log="save">' + UI.icon("download") + "Download</button></div>" +
      '<pre class="log">' + esc(job.log.slice(-400).join("\n")) + "</pre>";
    logEl = body.querySelector(".log");
    if (stick) logEl.scrollTop = logEl.scrollHeight;
  }

  function follow(jobId, areas) {
    clearInterval(state.poll);
    document.getElementById("activity-dot").hidden = false;
    openDrawer();
    state.poll = setInterval(function () {
      API.get("/runs/" + jobId).then(function (job) {
        state.job = job;
        renderDrawer();
        renderStatus();
        updateProgress();
        updateTitle();
        if (!job.active) {
          clearInterval(state.poll);
          document.getElementById("activity-dot").hidden = true;
          var errors = job.results.filter(function (r) { return r.status === "error"; }).length;
          var freed = job.results.reduce(function (a, r) { return a + (r.bytes_freed || 0); }, 0);
          var text = job.results.length + " action(s)" + (freed ? ", " + UI.formatBytes(freed) + " freed" : "") + (errors ? ", " + errors + " failed" : "");
          UI.toast((errors ? errors + " action(s) failed." : "Run completed: " + text + ".") + " Details in Activity.", errors ? "error" : "ok");
          Components.notifications.add(errors ? "Run finished with errors" : "Run completed", text, errors ? "error" : "ok");
          desktopNotify(errors ? "Run finished with errors" : "Run completed", text);
          if (!errors) FX.confetti();
          refreshAreas(areas || areasOf(job.results.map(function (r) { return r.action_id; })));
        }
      }).catch(function (error) {
        clearInterval(state.poll);
        UI.toast(error.message, "error");
      });
    }, 1000);
  }

  function areasOf(ids) {
    var set = {};
    ids.forEach(function (id) { set[id.split(".")[0]] = true; });
    return Object.keys(set);
  }

  function refreshAreas(areas) {
    Promise.all(areas.map(function (a) { return API.post("/areas/" + a + "/scan"); })).then(function () {
      refreshScores();
      render();
    }, function () { render(); });
  }

  /* ---------- shared actions ---------- */

  function action(id) { return state.actions[id] || PSEUDO_ACTIONS[id]; }

  /* Confirmation listing every step in run order, its risk and the estimated total time. */
  function confirmRun(list, risky) {
    var total = list.reduce(function (s, a) { return s + (a.minutes || 0); }, 0);
    var body = '<p class="modal-text">' + (risky.length ? "A restore point is created first, then the actions run in this order:" : "The actions run in this order:") + "</p>" +
      '<ol class="confirm-steps">' + list.map(function (a) {
        return "<li><span class=\"grow\"><span class=\"cell-title\">" + esc(a.title) + "</span>" + (a.risk !== "safe" && a.warning ? '<br><span class="cell-sub">' + esc(a.warning) + "</span>" : "") +
          "</span>" + UI.riskBadge(a.risk) + '<span class="badge">' + esc(UI.duration(a.minutes)) + "</span></li>";
      }).join("") + "</ol>" +
      '<p class="muted small">Estimated time: ' + esc(UI.duration(total)) + ". You can follow every step in Activity.</p>";
    var danger = risky.some(function (a) { return a.risk === "high"; });
    return UI.modal(list.length === 1 ? list[0].title : "Run " + list.length + " actions", body, [
      { label: "Cancel", cls: "btn-ghost" },
      { label: "Run now", cls: danger ? "btn-danger" : "btn-primary", value: function () { return true; } }
    ]).then(function (v) { return v === true; });
  }

  function runActions(ids) {
    var list = ids.map(action).filter(Boolean);
    var risky = list.filter(function (a) { return a.risk !== "safe"; });
    // Safe actions start at once; anything else, or a batch, is confirmed with its steps.
    var ask = risky.length || list.length > 2 ? confirmRun(list, risky) : Promise.resolve(true);
    return ask.then(function (ok) {
      if (!ok) return null;
      return API.post("/runs", { actions: ids, confirmed: risky.length > 0 }).then(function (r) {
        state.job = { active: true, done: 0, total: ids.length, results: [], log: [], current: null };
        follow(r.id, areasOf(ids));
        return r.id;
      });
    }).catch(function (error) { UI.toast(error.message, "error"); });
  }

  function runSafe(area) {
    return API.post("/runs/safe", area ? { area: area } : {}).then(function (r) {
      UI.toast("Running " + r.actions.length + " safe action(s).", "info");
      state.job = { active: true, done: 0, total: r.actions.length, results: [], log: [], current: null };
      follow(r.id, areasOf(r.actions));
    }).catch(function (error) { UI.toast(error.message, "error"); });
  }

  function schedule(actionId) {
    var a = state.actions[actionId];
    if (!a) return Promise.resolve();
    return UI.scheduleDialog(a).then(function (value) {
      if (!value) return null;
      if (a.risk !== "safe" && !value.confirmed) {
        UI.toast("Tick the confirmation box to schedule an action that is not safe.", "warning");
        return null;
      }
      if (value.kind === "weekly" && !value.days) {
        UI.toast("Choose at least one day.", "warning");
        return null;
      }
      value.action_id = actionId;
      return API.post("/schedules", value).then(function () {
        UI.toast("Schedule created in Windows Task Scheduler.", "ok");
        Components.notifications.add("Schedule created", a.title, "ok");
        if (state.page === "schedules") render();
      });
    }).catch(function (error) { UI.toast(error.message, "error"); });
  }

  function scanAll() {
    if (state.scanning) return Promise.resolve();
    var btn = document.getElementById("btn-scan");
    btn.disabled = true;
    btn.classList.add("busy");
    state.scanning = true;
    renderStatus();
    updateProgress();
    UI.toast("Scanning all areas. This takes one to three minutes.", "info");
    return API.post("/scan").then(function () {
      UI.toast("Scan completed.", "ok");
      Components.notifications.add("Full scan completed", "All areas were scanned.", "ok");
      FX.confetti({ count: 90 });
      return refreshScores();
    }).catch(function (error) { UI.toast(error.message, "error"); }).then(function () {
      state.scanning = false;
      btn.disabled = false;
      btn.classList.remove("busy");
      updateProgress();
      render();
    });
  }

  function setSubtitle(text) { document.getElementById("page-sub").textContent = text || ""; }

  /* ---------- access and rights ---------- */

  var accessOpen = false;
  function requestAccess() {
    if (accessOpen) return Promise.resolve();
    accessOpen = true;
    return UI.modal("Connect this window",
      '<p class="modal-text">This browser window is not connected to the agent, so it cannot run or schedule actions. ' +
      "This happens when the console is opened without the link from the Windows Maintenance Manager window, in a new tab or after the agent restarted.</p>" +
      '<div class="callout callout-info">' + UI.icon("info") + "<div>Click <strong>Request access</strong>: a confirmation appears on the desktop of this PC. Click <strong>Yes</strong> there to connect.</div></div>",
      [{ label: "Not now", cls: "btn-ghost" }, { label: "Request access", cls: "btn-primary", value: function () { return true; } }]
    ).then(function (ok) {
      accessOpen = false;
      if (!ok) return;
      UI.toast("Waiting for confirmation on the desktop of this PC…", "info");
      return API.post("/pair").then(function (r) {
        API.setToken(r.token);
        UI.toast("This window is connected.", "ok");
        renderChrome();
      }, function (e) { UI.toast(e.message, "error"); });
    });
  }

  function restartAsAdmin() {
    return API.post("/agent/elevate").then(function () {
      UI.modal("Restarting as administrator",
        '<p class="modal-text">Approve the Windows prompt (UAC). The console restarts with administrator rights and opens in a new browser tab, already connected.</p>' +
        '<p class="muted small">You can close this tab afterwards.</p>', [{ label: "OK", cls: "btn-primary" }]);
    }).catch(function (e) { UI.toast(e.message, "error"); });
  }

  /* Power button: stops every WMM process on this PC (other consoles, scheduled runs, this agent). */
  function powerOff() {
    var running = state.job && state.job.active;
    return UI.modal("Stop Windows Maintenance Manager",
      '<p class="modal-text">Every Windows Maintenance Manager process on this PC is stopped: this console, other open consoles and scheduled runs ' +
      "in progress, together with the commands they started (DISM, CHKDSK, Windows Update…).</p>" +
      (running ? '<div class="callout callout-error">' + UI.icon("alert") + "<div><strong>A run is in progress.</strong> It is interrupted where it is: " +
        "an action stopped halfway may leave its change incomplete. The restore point created before it stays available.</div></div>" : "") +
      '<div class="callout callout-info">' + UI.icon("info") + "<div>Schedules stay registered in Task Scheduler and run at their time. " +
      "Start the console again with start_wmm.bat.</div></div>",
      [{ label: "Cancel", cls: "btn-ghost" }, { label: "Stop everything", cls: "btn-danger", value: function () { return true; } }]
    ).then(function (ok) {
      if (!ok) return;
      return API.post("/agent/shutdown").then(function (r) {
        state.stopped = true;
        clearInterval(state.poll);
        var screen = document.createElement("div");
        screen.className = "offline";
        screen.innerHTML = '<section class="card stopped-card"><span class="stopped-icon">' + UI.icon("power") + "</span>" +
          '<h2 style="margin:14px 0 6px">Windows Maintenance Manager is stopped</h2><p class="muted">' +
          (r.stopped_processes ? r.stopped_processes + " other process(es) stopped. " : "") +
          (r.run_interrupted ? "The run in progress was interrupted. " : "") +
          "You can close this tab. Start the console again with start_wmm.bat.</p></section>";
        document.body.appendChild(screen);
        document.title = "Stopped · Windows Maintenance Manager";
      }, function (e) { UI.toast(e.message, "error"); });
    });
  }
  document.getElementById("btn-power").addEventListener("click", powerOff);

  var adminOpen = false;
  function needAdmin() {
    if (adminOpen) return;
    adminOpen = true;
    UI.modal("Administrator rights are needed",
      '<p class="modal-text">The agent runs without administrator rights, so Windows denies the changes this action makes.</p>' +
      '<div class="callout callout-info">' + UI.icon("shield") + "<div><strong>Restart as administrator</strong> asks Windows for permission (UAC) and reopens the console with full rights.</div></div>",
      [{ label: "Cancel", cls: "btn-ghost" }, { label: "Restart as administrator", cls: "btn-primary", value: function () { return true; } }]
    ).then(function (ok) { adminOpen = false; if (ok) restartAsAdmin(); });
  }
  window.addEventListener("wmm-unauthorized", requestAccess);
  window.addEventListener("wmm-need-admin", needAdmin);
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-request-access]")) requestAccess();
    if (e.target.closest("[data-elevate]")) restartAsAdmin();
  });

  function pageTitle(name) { return window.Pages[name] ? window.Pages[name].title : name; }

  function commands() {
    var list = [];
    (Components.store("recentPages") || []).forEach(function (p) {
      if (window.Pages[p]) list.push({ group: "Recent pages", title: window.Pages[p].title, icon: p, run: function () { location.hash = "#/" + p; } });
    });
    (Components.store("favorites") || []).forEach(function (id) {
      var a = state.actions[id];
      if (a) list.push({ group: "Favorite actions", title: a.title, sub: UI.AREA_LABEL[a.area], icon: "play", badge: UI.riskBadge(a.risk), run: function () { runActions([id]); } });
    });
    NAV.forEach(function (g) {
      g[1].forEach(function (item) {
        list.push({ group: "Pages", title: item[1], icon: item[0], keywords: g[0], run: function () { location.hash = "#/" + item[0]; } });
      });
    });
    list.push({ group: "Commands", title: "Scan all areas", icon: "refresh", run: scanAll });
    list.push({ group: "Commands", title: "Apply all safe actions", icon: "bolt", run: function () { runSafe(null); } });
    list.push({ group: "Commands", title: "Toggle light / dark theme", icon: "moon", run: Components.theme.toggle });
    list.push({ group: "Commands", title: "Export full report", icon: "download", run: function () { Report.download("full"); } });
    list.push({ group: "Commands", title: "Keyboard shortcuts", icon: "keyboard", run: Components.shortcutsHelp });
    list.push({ group: "Commands", title: "Show activity", icon: "performance", run: openDrawer });
    list.push({ group: "Commands", title: "Collapse or expand all cards", icon: "dashboard", run: toggleCards });
    list.push({ group: "Commands", title: "Copy the machine ID", icon: "download", run: function () { if (state.info) copyText(state.info.machine_id, "Machine ID"); } });
    list.push({ group: "Commands", title: "Open the user guide", icon: "support", keywords: "help faq", run: function () { location.hash = "#/support"; } });
    if (state.info && state.info.admin && !state.info.preview && API.hasToken()) {
      list.push({ group: "Commands", title: "Stop Windows Maintenance Manager", icon: "power", keywords: "shutdown quit exit kill power off", run: powerOff });
    }
    state.playbooks.forEach(function (b) {
      list.push({ group: "Playbooks", title: "Run playbook: " + b.title, sub: b.actions.length + " actions", icon: "playbooks", keywords: b.description,
        run: function () { runActions(b.actions); } });
    });
    var toggle = function (title, key, apply) {
      list.push({ group: "Preferences", title: title, icon: "settings", run: function () {
        var on = !Components.store(key);
        Components.store(key, on);
        if (apply) apply(on);
        UI.toast(title + ": " + (on ? "on" : "off") + ".", "info");
      } });
    };
    toggle("Compact sidebar", "sidebar", function (on) { document.body.classList.toggle("sidebar-collapsed", on); });
    toggle("Desktop notifications", "desktopNotify", function (on) {
      if (on && "Notification" in window && Notification.permission === "default") Notification.requestPermission();
    });
    FX.LEVELS.forEach(function (level) {
      list.push({ group: "Preferences", title: "Animations: " + level, icon: "sparkle", keywords: "motion effects confetti", run: function () {
        FX.set(level);
        UI.toast("Animations: " + level + ".", "ok");
      } });
    });
    list.push({ group: "Preferences", title: "Compact density", icon: "settings", run: function () {
      Components.density.set(Components.density.get() === "compact" ? "comfortable" : "compact");
    } });
    list.push({ group: "Preferences", title: "Dashboard auto-refresh", icon: "settings", run: function () {
      var on = Components.store("dashAuto") === false;
      Components.store("dashAuto", on);
      UI.toast("Dashboard auto-refresh: " + (on ? "on" : "off") + ".", "info");
    } });
    Object.keys(state.actions).forEach(function (id) {
      var a = state.actions[id];
      list.push({ group: "Run an action", title: a.title, sub: UI.AREA_LABEL[a.area], icon: "play", keywords: a.description + " " + id,
        badge: UI.riskBadge(a.risk), run: function () { runActions([id]); } });
    });
    Object.keys(state.actions).forEach(function (id) {
      var a = state.actions[id];
      list.push({ group: "Schedule an action", title: "Schedule: " + a.title, sub: UI.AREA_LABEL[a.area], icon: "clock", keywords: id,
        run: function () { schedule(id); } });
    });
    return list;
  }

  /* ---------- boot ---------- */

  document.addEventListener("click", function (e) {
    var run = e.target.closest("[data-run]");
    if (run) { e.preventDefault(); runActions([run.getAttribute("data-run")]); return; }
    var sch = e.target.closest("[data-schedule]");
    if (sch) { e.preventDefault(); schedule(sch.getAttribute("data-schedule")); }
  });
  document.getElementById("btn-scan").addEventListener("click", scanAll);
  document.getElementById("btn-search").addEventListener("click", Components.palette.open);
  document.getElementById("btn-theme").addEventListener("click", Components.theme.toggle);
  document.getElementById("btn-notif").addEventListener("click", Components.notifications.toggle);
  document.getElementById("btn-activity").addEventListener("click", function () {
    if (document.getElementById("drawer").hidden) openDrawer(); else closeDrawer();
  });
  document.getElementById("drawer-close").addEventListener("click", closeDrawer);
  document.getElementById("btn-collapse").addEventListener("click", function () {
    var collapsed = document.body.classList.toggle("sidebar-collapsed");
    Components.store("sidebar", collapsed);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeDrawer(); });
  if (Components.store("sidebar")) document.body.classList.add("sidebar-collapsed");
  window.addEventListener("hashchange", render);
  Components.notifications.badge();

  var App = window.App = {
    openDrawer: openDrawer, follow: follow, pollActivity: pollActivity, requestAccess: requestAccess, restartAsAdmin: restartAsAdmin,
    state: state, render: render, isCurrent: isCurrent, onLeave: onLeave, runActions: runActions, runSafe: runSafe, schedule: schedule,
    scanAll: scanAll, setSubtitle: setSubtitle, action: action, commands: commands, pageTitle: pageTitle, refreshScores: refreshScores,
    order: order, copyText: copyText, saveText: saveText, toggleCards: toggleCards
  };

  setInterval(pollActivity, 4000);

  /* Live CPU/RAM in the top bar (light: one request every 3 s, paused while the tab is hidden). */
  var liveSince = 0;
  setInterval(function () {
    if (document.hidden) return;
    API.get("/live?since=" + liveSince).then(function (r) {
      if (!r.samples.length) return;
      var s = r.samples[r.samples.length - 1];
      liveSince = s.t;
      document.getElementById("live-mini").innerHTML = "CPU <b>" + Math.round(s.cpu) + "%</b> RAM <b>" + s.memory_pct + "%</b>";
    }, function () { /* offline overlay handles it */ });
  }, 3000);

  /* Connection lost: overlay with automatic reconnection. */
  var offline = null;
  function checkConnection() {
    API.get("/agent/info").then(function (info) {
      state.info = info; state.connected = true;
      if (offline) { offline.remove(); offline = null; UI.toast("Agent reachable again.", "ok"); renderChrome(); }
      renderStatus();
    }, function () {
      state.connected = false;
      renderStatus();
      if (!offline && !state.stopped) {  // stopped on purpose: the stopped screen stays
        offline = document.createElement("div");
        offline.className = "offline";
        offline.innerHTML = '<section class="card"><span class="spinner" style="width:28px;height:28px"></span><h2 style="margin:14px 0 6px">Agent not reachable</h2>' +
          '<p class="muted">The Windows Maintenance Manager window may be closed or restarting. Reconnecting automatically…</p></section>';
        document.body.appendChild(offline);
      }
    });
  }
  setInterval(checkConnection, offline ? 3000 : 10000);
  setInterval(function () { if (offline) checkConnection(); }, 3000);

  document.getElementById("btn-print").addEventListener("click", function () { window.print(); });
  document.addEventListener("keydown", function (e) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
    if (typing || e.ctrlKey || e.metaKey || e.altKey || !e.shiftKey || document.querySelector(".modal-backdrop")) return;
    if (e.key === "R") { render(); UI.toast("Page refreshed.", "info"); }
    if (e.key === "S") scanAll();
    if (e.key === "C") toggleCards();
  });

  /* Collapses every card of the page, or expands them all when they are already collapsed. */
  function toggleCards() {
    var cards = document.querySelectorAll("#content .card[data-card]");
    if (!cards.length) return;
    var collapse = Array.prototype.some.call(cards, function (c) { return !c.classList.contains("collapsed"); });
    cards.forEach(function (c) {
      c.classList.toggle("collapsed", collapse);
      var b = c.querySelector("[data-collapse]");
      if (b) b.setAttribute("aria-expanded", String(!collapse));
    });
  }

  function copyText(text, what) {
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () { UI.toast(what + " copied.", "ok"); },
      function () { UI.toast("The clipboard is not available in this browser.", "warning"); });
  }
  function saveText(text, name) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-copy-id]") && state.info) copyText(state.info.machine_id, "Machine ID");
    var log = e.target.closest("[data-log]");
    if (log && state.job) {
      var text = state.job.log.join("\n");
      if (log.getAttribute("data-log") === "copy") copyText(text, "Log");
      else saveText(text, "wmm-run-" + (state.job.id || "log") + ".txt");
    }
  });

  /* Recent pages for the command palette. */
  window.addEventListener("hashchange", function () {
    var recent = (Components.store("recentPages") || []).filter(function (p) { return p !== current(); });
    recent.unshift(current());
    Components.store("recentPages", recent.slice(0, 5));
  });

  /* Appearance saved in Settings. */
  (function () {
    var accent = Components.store("accent"), font = Components.store("fontSize");
    if (accent && accent !== "blue") document.documentElement.setAttribute("data-accent", accent);
    if (font && font !== "normal") document.body.classList.add("font-" + font);
  })();

  function desktopNotify(title, text) {
    if (!Components.store("desktopNotify") || !("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
    try { new Notification(title, { body: text }); } catch (e) { /* not supported */ }
  }
  setInterval(function () {
    API.get("/agent/info").then(function (info) { state.info = info; state.connected = true; renderStatus(); },
      function () { state.connected = false; renderStatus(); });
  }, 20000);

  Promise.all([API.get("/agent/info"), API.get("/actions")]).then(function (results) {
    state.info = results[0];
    results[1].actions.forEach(function (a) { state.actions[a.id] = a; });
    renderChrome();
    // Reopen the page used last, unless the address already names one.
    var last = Components.store("lastPage");
    if (!/^#\/\w/.test(location.hash) && last && window.Pages[last] && last !== "dashboard") history.replaceState(null, "", "#/" + last);
    render();
    API.get("/playbooks").then(function (p) { state.playbooks = p.playbooks; }, function () { /* palette works without them */ });
    refreshScores();
    API.get("/health").then(function (h) { state.health = h; renderStatus(); }, function () { /* shown in Settings */ });
    // A token from a previous agent run is rejected here: the 403 opens the reconnect dialog.
    if (API.hasToken()) API.post("/agent/token-check").catch(function () { renderChrome(); });
    return API.get("/runs/current").then(function (r) {
      if (r.active && r.id) follow(r.id);
    });
  }).catch(function (error) {
    state.connected = false;
    document.getElementById("content").innerHTML = UI.errorBox(error);
  });
})();
