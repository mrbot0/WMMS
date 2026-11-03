/* Console shell: grouped navigation, top bar, status bar, activity drawer and shared actions. */
(function () {
  "use strict";
  var esc = UI.esc;
  // The sidebar is built from the categories (hubs.js): [title, [[page, label]…], category id, icon].
  var NAV = Hubs.CATEGORIES.map(function (c) { return [c.title, c.pages.map(function (p) { return [p[0], p[1]]; }), c.id, c.icon]; });
  var PSEUDO_ACTIONS = {
    "startup.toggle": { id: "startup.toggle", title: "Startup entry changed", area: "startup", risk: "moderate" },
    "integrity.protect_install": { id: "integrity.protect_install", title: "Installation protected for schedules", area: "integrity", risk: "moderate" },
    "integrity.registry": { id: "integrity.registry", title: "Registry changed", area: "integrity", risk: "high" },
    "performance.end_process": { id: "performance.end_process", title: "Process ended", area: "performance", risk: "moderate" },
    "performance.process_priority": { id: "performance.process_priority", title: "Process priority changed", area: "performance", risk: "moderate" },
    "performance.start_process": { id: "performance.start_process", title: "Process started", area: "performance", risk: "moderate" },
    "services.control": { id: "services.control", title: "Service started, stopped or restarted", area: "services", risk: "moderate" },
    "scripts.run": { id: "scripts.run", title: "Script run", area: "scripts", risk: "moderate" },
    "scripts.schedule": { id: "scripts.schedule", title: "Script schedule changed", area: "scripts", risk: "moderate" },
    "scripts.shutdown_timer": { id: "scripts.shutdown_timer", title: "Shutdown timer", area: "scripts", risk: "moderate" },
    "integrity.schedule_test": { id: "integrity.schedule_test", title: "Scheduled task started (test)", area: "integrity", risk: "safe" },
    "hardware.monitor_tool": { id: "hardware.monitor_tool", title: "Sensor tool (LibreHardwareMonitor)", area: "performance", risk: "moderate" }
  };
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
    var page = current(), folded = Components.store("navFolded") || [];
    document.getElementById("nav").innerHTML = NAV.map(function (group) {
      // The category title opens its hub page; the chevron folds its pages away (remembered).
      var hub = "cat-" + group[2], isFolded = folded.indexOf(group[2]) >= 0 && group[1].every(function (i) { return i[0] !== page; });
      return '<div class="nav-group' + (page === hub ? " active" : "") + '"><a href="#/' + hub + '" class="nav-group-link"' + (page === hub ? ' aria-current="page"' : "") +
        ' title="Open ' + esc(group[0]) + '">' + esc(group[0]) + '</a><button type="button" class="nav-fold" data-fold="' + group[2] + '" aria-expanded="' + !isFolded +
        '" aria-label="' + (isFolded ? "Show" : "Hide") + " the pages of " + esc(group[0]) + '">' + UI.icon("chevron") + "</button></div>" +
        (isFolded ? "" : group[1].map(function (item) {
        var score = state.scores[item[0]];
        var chip = item[0] in state.scores
          ? '<span class="nav-score ' + (score == null ? "none" : UI.tone(score)) + '" title="Score">' + (score == null ? "–" : score) + "</span>" : "";
        if (item[0] === "activity" && state.activeCount) chip = '<span class="nav-live" title="Operations in progress">' + state.activeCount + "</span>";
        if (item[0] === "toolbox" && Object.keys(state.actions).length) chip = '<span class="nav-score none" title="Tools">' + Object.keys(state.actions).length + "</span>";
        return '<a href="#/' + item[0] + '" class="nav-item' + (item[0] === page ? " active" : "") + '"' + (item[0] === page ? ' aria-current="page"' : "") +
          ' title="' + esc(item[1]) + '">' + UI.icon(item[0]) + '<span class="nav-label">' + esc(item[1]) + "</span>" + chip + "</a>";
      }).join(""));
    }).join("");
    FX.navPill();
  }
  document.getElementById("nav").addEventListener("click", function (e) {
    var fold = e.target.closest("[data-fold]");
    if (!fold) return;
    var id = fold.getAttribute("data-fold"), list = Components.store("navFolded") || [], i = list.indexOf(id);
    if (i >= 0) list.splice(i, 1); else list.push(id);
    Components.store("navFolded", list);
    renderNav();
  });

  function renderChrome() {
    var info = state.info;
    if (!info) return;
    document.getElementById("topbar-meta").innerHTML =
      '<span class="meta-item device-name" title="Machine ID: ' + esc(info.machine_id) + '"><span class="meta-label">Device</span>' + esc(info.hostname) + "</span>" +
      '<span class="pill ' + (info.preview ? "pill-info" : info.admin ? "pill-ok" : "pill-warning") + '">' +
      (info.preview ? "Preview mode" : info.admin ? "Administrator" : "Read-only") + "</span>";
    document.getElementById("sidebar-meta").innerHTML = '<button type="button" class="version-link" data-whatsnew title="What\'s new">Version ' + esc(info.version) +
      "</button><br>Local agent · 127.0.0.1";
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
      '<span class="grow"></span>' + (info.version ? '<button type="button" class="st st-copy" data-whatsnew title="What\'s new">v' + esc(info.version) + " · " +
        Object.keys(state.actions).length + " tools</button>" : "") +
      '<span class="st"><span class="kbd">Ctrl K</span> commands</span><span class="st"><span class="kbd">?</span> shortcuts</span>' +
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
    var cat = Hubs.categoryOf(name);
    document.getElementById("crumbs").innerHTML = '<a href="#/dashboard">Windows Maintenance Manager</a>' +
      (cat && !page.hub ? '<a href="#/cat-' + cat.id + '">' + esc(cat.title) + "</a>" : "");
    var area = UI.AREAS.indexOf(name);
    document.getElementById("page-title").innerHTML = '<span class="title-icon"' + (area >= 0 ? ' style="color:' + Charts.PALETTE[area % Charts.PALETTE.length] + '"' : "") + ">" +
      UI.icon(page.hub && cat ? cat.icon : name) + "</span>" + esc(page.title);
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
    var loadingBar = document.getElementById("top-progress");
    loadingBar.classList.add("page-loading");
    Promise.resolve().then(function () { return page.render(content, App); }).then(function () {
      if (token !== state.rendering) return;
      loadingBar.classList.remove("page-loading");
      // First visit: a short "how this page works" tip; at the bottom, the neighbours in the same category.
      var tip = Guides.tip(name);
      if (tip) content.insertAdjacentHTML("afterbegin", tip);
      content.insertAdjacentHTML("beforeend", Hubs.pager(name));
      Components.countUp(content);
      if (arriving) {
        FX.pageEnter(content);
        content.focus({ preventScroll: true });  // screen readers and keyboard users start from the new page
        announce(page.title + " page");
      }
      scroller.scrollTop = restore;
      FX.reveal(content);
      if (area >= 0) fixButton(content, name, token);
    }).catch(function (error) {
      if (token !== state.rendering) return;
      loadingBar.classList.remove("page-loading");
      content.innerHTML = UI.errorBox(error);
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

  /* The browser tab shows the run percentage (title and icon), so progress is visible from other tabs too. */
  function updateTitle() {
    var page = window.Pages[state.page], job = state.job && state.job.active ? state.job : null;
    var pct = job ? (job.percent != null ? job.percent : 100 * job.done / Math.max(1, job.total)) : null;
    if (Components.store("titleProgress") === false) pct = null;  // Settings › Notifications: keep the tab title still
    document.title = (pct != null ? Math.round(pct) + "% · " : "") + (page ? page.title : "") + " · Windows Maintenance Manager";
    Components.faviconProgress(pct);
  }

  function onLeave(fn) { state.leave.push(fn); }

  /* Settings › Behaviour › Sound: two short tones when a run finishes (rising: success, falling: errors). */
  function chime(ok) {
    if (!Components.store("sound") || !window.AudioContext || quiet()) return;
    var peak = { low: 0.05, medium: 0.15, high: 0.4 }[Components.store("soundVolume") || "medium"] || 0.15;
    try {
      var ctx = new AudioContext();
      (ok ? [660, 880] : [440, 330]).forEach(function (f, i) {
        var o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime + i * 0.16;
        o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(peak, t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.15);
        o.connect(g).connect(ctx.destination);
        o.start(t);
        o.stop(t + 0.16);
      });
      setTimeout(function () { ctx.close(); }, 600);
    } catch (e) { /* audio not available */ }
  }

  /* Polite announcement for screen readers (page changes, finished runs). */
  function announce(text) {
    var live = document.getElementById("announcer");
    if (!live) return;
    live.textContent = "";
    setTimeout(function () { live.textContent = text; }, 50);
  }

  /* Thin progress line under the top bar, visible on every page. */
  function updateProgress() {
    var bar = document.getElementById("top-progress");
    var job = state.job && state.job.active ? state.job : null;
    bar.classList.toggle("indeterminate", !job && (state.scanning || state.tasksActive > 0));
    bar.firstChild.style.width = job ? Math.max(3, job.percent != null ? job.percent : Math.round(100 * job.done / Math.max(1, job.total))) + "%" : (state.scanning || state.tasksActive ? "" : "0");
  }

  function pollActivity() {
    if (document.hidden) return;  // resumed by visibilitychange
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
          esc(r.note || "") + (r.bytes_freed ? " · freed " + UI.formatBytes(r.bytes_freed) : "") + "</span>" +
          (r.run_id ? '<button type="button" class="btn btn-sm btn-ghost" data-output="' + esc(r.run_id) + '" data-title="' + esc(a ? a.title : r.action_id) +
            '" title="Output of this tool">' + UI.icon("reports") + "</button>" : "") + "</li>";
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
    if (Components.store("autoDrawer") !== false) openDrawer();
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
          var problems = job.results.some(function (r) { return r.status === "error" || r.status === "warning"; });
          if (problems || !Components.store("notifyProblemsOnly")) desktopNotify(errors ? "Run finished with errors" : "Run completed", text);
          // A run made only of reports exists to be read: its output opens at once (unless turned off in Settings).
          var onlyReports = job.results.length && job.results.every(function (r) { var a = action(r.action_id); return a && a.kind === "report"; });
          if (onlyReports && Components.store("autoOpenReports") !== false) {
            Components.reportViewer(job.results.length === 1 ? action(job.results[0].action_id).title : job.results.length + " diagnostics", job.log.join("\n"),
              "Finished " + UI.formatDate(new Date().toISOString()) + (state.info ? " on " + state.info.hostname : ""));
          } else if (!errors) FX.confetti();
          chime(!errors);
          speak(errors ? "Run finished with " + errors + " errors." : "Run completed.");
          flashTitle(errors ? "Errors" : "Done");
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

  function favorites() { return Components.store("favorites") || []; }
  function toggleFavorite(id) {
    var list = favorites(), i = list.indexOf(id);
    if (i >= 0) list.splice(i, 1); else list.push(id);
    Components.store("favorites", list);
    return i < 0;
  }

  /* Everything known about one tool, with run, schedule, favorite and its last output in one place. */
  function actionDetail(id) {
    var a = state.actions[id];
    if (!a) return Promise.resolve();
    return API.get("/history?area=" + a.area + "&limit=500").then(function (h) {
      return h.runs.filter(function (r) { return r.action_id === id; })[0] || null;
    }, function () { return null; }).then(function (r) {
      var fav = favorites().indexOf(id) >= 0;
      return UI.modal(a.title, '<p class="modal-text">' + esc(a.description) + "</p>" +
        (a.risk !== "safe" && a.warning ? '<div class="callout callout-warning">' + UI.icon("shield") + "<div>" + esc(a.warning) + " A restore point is created first.</div></div>" : "") +
        (a.kind === "report" ? '<div class="callout callout-info">' + UI.icon("reports") + "<div>Read-only report: it changes nothing on this PC. Its output opens when it finishes.</div></div>" : "") +
        UI.definition([["Area", esc(UI.AREA_LABEL[a.area])], ["Kind", UI.kindBadge(a.kind)], ["Risk", UI.riskBadge(a.risk)], ["Estimated time", esc(UI.duration(a.minutes))],
          ["Last run", r ? UI.statusBadge(r.status) + " " + esc(UI.relative(r.finished || r.started)) + (r.note ? " · " + esc(r.note) : "") : "Never"],
          ["Identifier", '<span class="cell-mono">' + esc(a.id) + "</span>"]]),
        [{ label: fav ? "Remove favorite" : "Add to favorites", cls: "btn-ghost", value: function () { return "fav"; } }]
          .concat(r ? [{ label: "Last output", cls: "", value: function () { return "output"; } }] : [])
          .concat([{ label: "Schedule", cls: "", value: function () { return "schedule"; } }, { label: "Run now", cls: "btn-primary", value: function () { return "run"; } }])
      ).then(function (v) {
        if (v === "run") runActions([id]);
        if (v === "schedule") schedule(id);
        if (v === "output") Components.showRunOutput(r.id, a.title);
        if (v === "fav") { var on = toggleFavorite(id); UI.toast(on ? "Added to favorites." : "Removed from favorites.", "ok"); render(); }
      });
    });
  }

  /* Confirmation listing every step in run order, its risk and the estimated total time. */
  function confirmRun(list, risky) {
    var total = list.reduce(function (s, a) { return s + (a.minutes || 0); }, 0);
    var body = '<p class="modal-text">' + (risky.length ? "A restore point is created first, then the actions run in this order:" : "The actions run in this order:") + "</p>" +
      '<ol class="confirm-steps">' + list.map(function (a) {
        return "<li><span class=\"grow\"><span class=\"cell-title\">" + esc(a.title) + "</span>" + (a.risk !== "safe" && a.warning ? '<br><span class="cell-sub">' + esc(a.warning) + "</span>" : "") +
          "</span>" + UI.riskBadge(a.risk) + '<span class="badge">' + esc(UI.duration(a.minutes)) + "</span></li>";
      }).join("") + "</ol>" +
      '<p class="muted small">Estimated time: ' + esc(UI.duration(total)) + ". You can follow every step in Activity. " +
      UI.hint("Safe actions run without asking. Moderate and high-risk actions are confirmed here and a System Restore point is created before them, " +
        "so Windows can go back if something goes wrong.") + "</p>";
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
    var ask = risky.length || list.length > 2 || Components.store("confirmSafe") ? confirmRun(list, risky) : Promise.resolve(true);
    var minutes = list.reduce(function (s, a) { return s + (a.minutes || 0); }, 0);
    return ask.then(function (ok) { return ok && batteryCheck(minutes); }).then(function (ok) { return ok && longRunCheck(minutes); }).then(function (ok) {
      if (!ok) return null;
      return API.post("/runs", { actions: ids, confirmed: risky.length > 0 }).then(function (r) {
        state.job = { active: true, done: 0, total: ids.length, results: [], log: [], current: null };
        follow(r.id, areasOf(ids));
        return r.id;
      });
    }).catch(function (error) { UI.toast(error.message, "error"); });
  }

  /* Settings › Maintenance: a run of 10 minutes or more on a laptop running on battery asks first. */
  var LONG_RUN_MINUTES = 10;
  function batteryCheck(minutes) {
    if (!Components.store("batteryWarn") || minutes < LONG_RUN_MINUTES || !navigator.getBattery) return Promise.resolve(true);
    return navigator.getBattery().then(function (b) {
      if (b.charging) return true;
      return UI.confirm("Running on battery", "This run takes about " + Math.round(minutes) + " minutes and the PC is not plugged in (" + Math.round(b.level * 100) +
        "% left). If the battery runs out, a repair can stop halfway. Plug in the charger or run it anyway.", { ok: "Run anyway" });
    }, function () { return true; });
  }

  /* Settings › Maintenance: runs longer than the chosen minutes ask first, so a long repair never starts by mistake. */
  function longRunCheck(minutes) {
    var limit = Components.store("longRunMinutes");
    if (!limit || minutes < limit) return Promise.resolve(true);
    return UI.confirm("Long run", "This run takes about " + Math.round(minutes) + " minutes (more than the " + limit + " minutes set in Settings). The PC stays usable, " +
      "but some steps may slow it down.", { ok: "Start it" });
  }

  /* Settings › Notifications: the result read aloud, for runs followed from across the room. */
  function speak(text) {
    if (!Components.store("speak") || quiet() || !window.speechSynthesis) return;
    try { speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(text)); } catch (e) { /* speech not available */ }
  }
  /* Settings › Notifications: the tab title blinks until the console is looked at again. */
  var flashTimer = null;
  function flashTitle(word) {
    if (!Components.store("flashTitle") || !document.hidden) return;
    var original = document.title, on = false;
    clearInterval(flashTimer);
    flashTimer = setInterval(function () { on = !on; document.title = on ? "● " + word + " · Windows Maintenance Manager" : original; }, 1000);
    var stop = function () { if (document.hidden) return; clearInterval(flashTimer); document.title = original; document.removeEventListener("visibilitychange", stop); };
    document.addEventListener("visibilitychange", stop);
  }

  /* Settings › Notifications: no sounds or desktop notifications between the two times (they may span midnight). */
  function quiet() {
    var q = Components.store("quietHours");
    if (!q || !q.on || !q.from || !q.to) return false;
    var d = new Date(), now = ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
    return q.from <= q.to ? now >= q.from && now < q.to : now >= q.from || now < q.to;
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

  /* "Fix automatically": protected Python (installed when missing), program in Program Files, schedules, restart. */
  function fixInstallation() {
    return UI.confirm("Fix the installation for schedules",
      "The console looks for a Python installed for all users and installs one when there is none (a few minutes; it needs the internet). " +
      "Then it moves the program to Program Files if needed, registers the schedules again and restarts with the protected Python in a new tab.",
      { ok: "Fix automatically" }).then(function (ok) {
      if (!ok) return;
      return API.post("/agent/protect").then(function () {
        var shown = UI.modal("Fixing the installation", '<div class="job-status"><span class="spinner"></span><strong data-step>Starting…</strong></div>' +
          '<pre class="log" data-plog style="min-height:180px;max-height:46vh;margin-top:10px"></pre>', [{ label: "Hide", cls: "btn-ghost" }]);
        var box = document.querySelector("#modal-root .modal-backdrop:last-child");
        var timer = setInterval(function () {
          API.get("/agent/protect").then(function (s) {
            if (box) {
              box.querySelector("[data-step]").textContent = s.active ? s.step : s.status === "ok" ? "Done" : "Failed";
              var log = box.querySelector("[data-plog]");
              log.textContent = s.log.join("\n");
              log.scrollTop = log.scrollHeight;
            }
            if (s.active) return;
            clearInterval(timer);
            if (s.status === "ok") {
              state.stopped = true;
              UI.toast("Fixed. The console restarts with the protected Python and opens in a new tab: you can close this one.", "ok");
              Components.notifications.add("Installation protected", s.note || "", "ok");
            } else {
              UI.toast("The installation could not be fixed: " + (s.note || "see the log") + ".", "error");
              if (box) box.querySelector(".spinner").remove();
            }
          }, function () { /* the agent is restarting */ });
        }, 1500);
        return shown;
      });
    }).catch(function (e) { UI.toast(e.message, "error"); });
  }
  document.addEventListener("click", function (e) { if (e.target.closest("[data-fix-install]")) fixInstallation(); });

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

  /* Windows Settings pages that open from the console (ms-settings: links, also on the Support page). */
  var WINDOWS_SETTINGS = [["windowsupdate", "Windows Update", "updates patches"], ["storagesense", "Storage", "disk space cleanup"],
    ["appsfeatures", "Installed apps", "uninstall programs"], ["startupapps", "Startup apps", "boot autostart"], ["powersleep", "Power and sleep", "battery energy"],
    ["display", "Display", "screen resolution monitor"], ["network-status", "Network status", "internet wifi ethernet"], ["windowsdefender", "Windows Security", "antivirus defender"],
    ["privacy", "Privacy", "permissions telemetry"], ["troubleshoot", "Troubleshoot", "fix problems"], ["recovery", "Recovery", "reset restore"], ["about", "About this PC", "system info"]];

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
      list.push({ group: "Categories", title: g[0], icon: g[3], keywords: "category hub " + g[1].map(function (i) { return i[1]; }).join(" "),
        run: function () { location.hash = "#/cat-" + g[2]; } });
    });
    NAV.forEach(function (g) {
      g[1].forEach(function (item) {
        list.push({ group: "Pages", title: item[1], icon: item[0], keywords: g[0], run: function () { location.hash = "#/" + item[0]; } });
      });
    });
    list.push({ group: "Help", title: "Guide for this page", icon: "support", keywords: "help how F1", run: function () { Guides.open(current()); } });
    list.push({ group: "Help", title: "Take the guided tour", icon: "sparkle", keywords: "help tour start onboarding", run: function () { Guides.tour(0); } });
    list.push({ group: "Help", title: "Show all page tips again", icon: "support", keywords: "help guides reset", run: function () {
      Guides.reset(); UI.toast("Page tips are back: each page shows its tip once.", "ok"); render(); } });
    list.push({ group: "Commands", title: "Scan all areas", icon: "refresh", run: scanAll });
    list.push({ group: "Commands", title: "Open the Toolbox", icon: "explorer", keywords: "tools diagnostics reports fixes", run: function () { location.hash = "#/toolbox"; } });
    list.push({ group: "Commands", title: "Run every diagnostic report", icon: "reports", keywords: "reports read-only check audit",
      run: function () { runActions(Object.keys(state.actions).filter(function (id) { return state.actions[id].kind === "report"; })); } });
    list.push({ group: "Commands", title: "What's new in this version", icon: "sparkle", keywords: "changelog release notes version", run: function () { Components.whatsNew(true); } });
    list.push({ group: "Commands", title: "Apply all safe actions", icon: "bolt", run: function () { runSafe(null); } });
    list.push({ group: "Commands", title: "Toggle light / dark theme", icon: "moon", run: Components.theme.toggle });
    list.push({ group: "Commands", title: "Export full report", icon: "download", run: function () { Report.download("full"); } });
    list.push({ group: "Commands", title: "Keyboard shortcuts", icon: "keyboard", run: Components.shortcutsHelp });
    list.push({ group: "Commands", title: "Show activity", icon: "performance", run: openDrawer });
    list.push({ group: "Commands", title: "Collapse or expand all cards", icon: "dashboard", run: toggleCards });
    list.push({ group: "Commands", title: "Copy the machine ID", icon: "download", run: function () { if (state.info) copyText(state.info.machine_id, "Machine ID"); } });
    var here = current();
    if (here !== "dashboard") {
      var isPinned = (Components.store("pinnedPages") || []).indexOf(here) >= 0;
      list.push({ group: "Commands", title: (isPinned ? "Unpin " : "Pin ") + pageTitle(here) + (isPinned ? " from" : " to") + " the dashboard", icon: "dashboard",
        keywords: "pin star favorite page", run: function () { togglePin(here); } });
    }
    list.push({ group: "Commands", title: "Copy a link to this page", icon: "copy", keywords: "url address share",
      run: function () { copyText(location.origin + "/#/" + here, "Link"); } });
    list.push({ group: "Preferences", title: "Privacy mode (hide serial numbers and IDs)", icon: "shield", keywords: "screen share mask blur serial mac", run: togglePrivacy });
    list.push({ group: "Preferences", title: "Clear recent commands and pages", icon: "x", keywords: "history palette forget",
      run: function () { Components.store("recentCommands", null); Components.store("recentPages", null); UI.toast("Recent commands and pages cleared.", "ok"); } });
    list.push({ group: "Commands", title: "Focus mode (hide the menu)", icon: "explorer", keywords: "fullscreen distraction sidebar hide F", run: function () { toggleFocus(); } });
    list.push({ group: "Commands", title: "Copy this page as text", icon: "copy", keywords: "clipboard content text export",
      run: function () { copyText(document.getElementById("content").innerText.replace(/\n{3,}/g, "\n\n").trim(), pageTitle(here)); } });
    (state.recentRuns || []).forEach(function (r) {
      var a = action(r.action_id);
      list.push({ group: "Recent runs", title: (a ? a.title : r.action_id), sub: UI.formatDate(r.started) + " · " + (UI.STATUS_LABEL[r.status] || r.status), icon: "history",
        keywords: "output log result", run: function () { Components.showRunOutput(r.id, a ? a.title : r.action_id); } });
    });
    WINDOWS_SETTINGS.forEach(function (w) {
      list.push({ group: "Windows settings", title: "Windows: " + w[1], icon: "settings", keywords: "ms-settings control panel " + w[2],
        run: function () { location.href = "ms-settings:" + w[0]; } });
    });
    ((window.Pages.settings || {}).sections || []).forEach(function (sct) {
      list.push({ group: "Settings", title: "Settings › " + sct[1], sub: sct[3], icon: sct[2], keywords: "preferences options " + sct[3],
        run: function () { Components.store("settingsSection", sct[0]); location.hash = "#/settings?s=" + sct[0]; if (current() === "settings") render(); } });
    });
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
    // Settings › Behaviour: the search can list pages and commands only, without the 200+ actions.
    if (Components.store("paletteActions") === false) return list;
    Object.keys(state.actions).forEach(function (id) {
      var a = state.actions[id];
      list.push({ group: "Run an action", title: a.title, sub: UI.AREA_LABEL[a.area] + (a.kind === "report" ? " · report" : ""), icon: a.kind === "report" ? "reports" : "play",
        keywords: a.description + " " + id,
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
    var reports = e.target.closest("[data-run-reports]");
    if (reports) { e.preventDefault(); runActions(reports.getAttribute("data-run-reports").split(",")); return; }
    if (e.target.closest("[data-whatsnew]")) { Components.whatsNew(true); return; }
    var detail = e.target.closest(".tool-card [data-detail]");
    if (detail && !App.isCurrent("toolbox") && !App.isCurrent("actions")) { actionDetail(detail.closest("[data-id]").getAttribute("data-id")); return; }
    var sch = e.target.closest("[data-schedule]");
    if (sch) { e.preventDefault(); schedule(sch.getAttribute("data-schedule")); }
  });
  document.getElementById("btn-scan").addEventListener("click", scanAll);
  document.getElementById("btn-search").addEventListener("click", Components.palette.open);
  document.getElementById("btn-theme").addEventListener("click", function (e) { FX.themeSwitch(Components.theme.toggle, e); });
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
    order: order, copyText: copyText, saveText: saveText, toggleCards: toggleCards, actionDetail: actionDetail,
    favorites: favorites, toggleFavorite: toggleFavorite, applyLook: function () { applyLook(); }, togglePrivacy: function () { togglePrivacy(); },
    quiet: function () { return quiet(); }, desktopNotify: function (t, x) { desktopNotify(t, x); }, chime: function (ok) { chime(ok); },
    speak: function (t) { speak(t); }, toggleFocus: function (on) { toggleFocus(on); }, windowsSettings: function () { return WINDOWS_SETTINGS; }
  };

  setInterval(pollActivity, 4000);

  /* Settings › Behaviour: scan everything at start when the oldest scan is older than the chosen days (administrator only). */
  function autoScan() {
    var days = Components.store("autoScanDays");
    if (!days || !state.info || !state.info.admin || state.info.preview) return;
    var times = UI.AREAS.map(function (a) { return state.scanned[a]; });
    var oldest = times.some(function (t) { return !t; }) ? 0 : Math.min.apply(null, times.map(function (t) { return new Date(t).getTime(); }));
    if (Date.now() - oldest < days * 86400e3) return;
    UI.toast("The last scan is older than " + days + " day" + (days > 1 ? "s" : "") + ": scanning every area now (Settings › Behaviour).", "info");
    scanAll();
  }

  /* Live CPU/RAM in the top bar (light: one request every 3 s by default, paused while the tab is hidden; Settings › Behaviour). */
  var liveSince = 0, liveTick = 0;
  setInterval(function () {
    var every = Components.store("liveInterval");
    if (every == null) every = 3;
    liveTick += 1;
    if (document.hidden || !every || liveTick % every > 0) return;
    API.get("/live?since=" + liveSince).then(function (r) {
      if (!r.samples.length) return;
      var s = r.samples[r.samples.length - 1];
      liveSince = s.t;
      // Amber from 75%, red from 90%: load is visible at a glance on every page.
      var level = function (v) { return v >= 90 ? "hot" : v >= 75 ? "warm" : ""; };
      var mini = document.getElementById("live-mini"), before = mini.textContent;
      mini.innerHTML = 'CPU <b class="' + level(s.cpu) + '">' + Math.round(s.cpu) + '%</b> RAM <b class="' + level(s.memory_pct) + '">' + s.memory_pct + "%</b>";
      if (before !== mini.textContent) { mini.classList.remove("tick"); void mini.offsetWidth; mini.classList.add("tick"); }
    }, function () { /* offline overlay handles it */ });
  }, 1000);  // a one-second tick; the request goes out every `liveInterval` seconds

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
  setInterval(function () { if (!document.hidden) checkConnection(); }, 10000);
  setInterval(function () { if (offline) checkConnection(); }, 3000);
  // Polling sleeps while the tab is hidden; coming back refreshes the state at once.
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) return;
    pollActivity();
    checkConnection();
  });

  document.getElementById("btn-print").addEventListener("click", function () { window.print(); });
  // The ? button and F1 open the guide of the current page (the user guide stays one click away inside it).
  document.getElementById("btn-help").addEventListener("click", function (e) { e.preventDefault(); Guides.open(current()); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "F1") { e.preventDefault(); if (!document.querySelector(".modal-backdrop")) Guides.open(current()); }
  });
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

  /* Appearance saved in Settings; Settings calls it again after every change. */
  var LOOK = { contrast: "high-contrast", cbSafe: "cb-safe", noBlur: "no-blur", wideText: "wide-text", underlineLinks: "underline-links", privacy: "privacy-mode",
    hideStatusbar: "no-statusbar", noTips: "no-tips", hideDevice: "hide-device", focusMode: "focus-mode" };
  // Values kept as attributes on <html>, read by the stylesheet (Settings › Appearance).
  var LOOK_ATTRS = { corners: "rounded", sidebarWidth: "normal", shadows: "soft", typeface: "system", pageWidth: "full" };
  function applyLook() {
    var accent = Components.store("accent"), font = Components.store("fontSize");
    Object.keys(LOOK).forEach(function (k) { document.body.classList.toggle(LOOK[k], !!Components.store(k)); });
    Object.keys(LOOK_ATTRS).forEach(function (k) {
      document.documentElement.setAttribute("data-" + k.replace(/[A-Z]/g, function (c) { return "-" + c.toLowerCase(); }), Components.store(k) || LOOK_ATTRS[k]);
    });
    document.getElementById("live-mini").hidden = !!Components.store("hideLiveMini");
    if (accent && accent !== "blue") document.documentElement.setAttribute("data-accent", accent);
    if (font && font !== "normal") document.body.classList.add("font-" + font);
  }
  applyLook();

  /* Privacy mode (Settings, Shift P, command palette): serial numbers, MAC addresses and IDs are blurred on screen. */
  function togglePrivacy() {
    var on = !Components.store("privacy");
    Components.store("privacy", on);
    applyLook();
    UI.toast(on ? "Privacy mode on: serial numbers, MAC addresses and IDs are hidden on screen." : "Privacy mode off.", "info");
  }
  /* Focus mode (F, command palette): only the page, without sidebar and top bar; Esc or F again leaves it. */
  function toggleFocus(force) {
    var on = typeof force === "boolean" ? force : !Components.store("focusMode");
    Components.store("focusMode", on);
    applyLook();
    if (on) UI.toast("Focus mode: press F or Esc to show the menu again.", "info");
  }
  /* [ and ]: previous and next page of the same category, like the links at the bottom of every page. */
  function stepPage(delta) {
    var c = Hubs.categoryOf(current());
    if (!c) return;
    var ids = c.pages.map(function (p) { return p[0]; }), i = ids.indexOf(current());
    var next = ids[i + delta];
    if (next) location.hash = "#/" + next;
  }
  document.addEventListener("keydown", function (e) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
    if (e.key === "Escape" && Components.store("focusMode") && !document.querySelector(".modal-backdrop")) { toggleFocus(false); return; }
    if (typing || e.ctrlKey || e.altKey || e.metaKey || Components.store("noKeyShortcuts") || document.querySelector(".modal-backdrop")) return;
    if (e.shiftKey && e.key === "P") togglePrivacy();
    if (!e.shiftKey && (e.key === "f" || e.key === "F")) toggleFocus();
    if (e.key === "[") stepPage(-1);
    if (e.key === "]") stepPage(1);
  });

  /* Pinned pages: the star in every page header, shown as a row on the dashboard. */
  function togglePin(page) {
    var list = (Components.store("pinnedPages") || []).filter(function (p) { return p !== page; });
    var on = list.length === (Components.store("pinnedPages") || []).length;
    if (on) list.push(page);
    Components.store("pinnedPages", list);
    document.querySelectorAll('[data-pin-page="' + page + '"]').forEach(function (b) {
      b.classList.toggle("pinned", on);
      b.textContent = on ? "★" : "☆";
      b.setAttribute("aria-pressed", String(on));
      b.title = on ? "Unpin from the dashboard" : "Pin to the dashboard";
      if (on) FX.burst(b);
    });
    UI.toast(pageTitle(page) + (on ? " pinned to the dashboard." : " unpinned."), "ok");
  }
  document.addEventListener("click", function (e) {
    var pin = e.target.closest("[data-pin-page]");
    if (pin) togglePin(pin.getAttribute("data-pin-page"));
  });

  /* Settings › Behaviour: closing the tab during a run asks first (the run itself goes on in the agent). */
  window.addEventListener("beforeunload", function (e) {
    if (Components.store("warnOnClose") === false || !(state.job && state.job.active)) return;
    e.preventDefault();
    e.returnValue = "";
  });

  /* Settings › Data and security: this window forgets its connection after a while without use. */
  var lastUse = Date.now();
  ["pointerdown", "keydown", "wheel"].forEach(function (ev) { document.addEventListener(ev, function () { lastUse = Date.now(); }, { passive: true }); });
  setInterval(function () {
    var minutes = Components.store("idleLock");
    if (!minutes || !API.hasToken() || Date.now() - lastUse < minutes * 60000) return;
    API.setToken("");
    renderChrome();
    UI.toast("This window was disconnected after " + minutes + " minutes without use. Use Request access to connect it again.", "warning");
  }, 30000);

  function desktopNotify(title, text) {
    if (!Components.store("desktopNotify") || !("Notification" in window) || Notification.permission !== "granted" || !document.hidden || quiet()) return;
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
    var start = Components.store("startPage") || "last", last = start === "last" ? Components.store("lastPage") : start;
    if (!/^#\/\w/.test(location.hash) && last && window.Pages[last] && last !== "dashboard") history.replaceState(null, "", "#/" + last);
    render();
    // After the release notes (if any), new users are offered the guided tour once.
    Components.whatsNew(false).then(function () {
      if (!Guides.shouldTour() || document.querySelector(".modal-backdrop")) return;
      UI.modal("Welcome to Windows Maintenance Manager", '<p class="modal-text">A one-minute tour shows how to scan this PC, fix what matters, explore the categories and automate the maintenance.</p>' +
        '<p class="muted small">You can take it later from the ? button or the command palette (Ctrl K).</p>',
        [{ label: "Not now", cls: "btn-ghost", value: function () { return "no"; } }, { label: "Start the tour", cls: "btn-primary", value: function () { return "yes"; } }]
      ).then(function (v) { if (v === "yes") Guides.tour(0); else Components.store("tourDone", true); });
    });
    API.get("/playbooks").then(function (p) { state.playbooks = p.playbooks; }, function () { /* palette works without them */ });
    refreshScores().then(autoScan);
    API.get("/history?limit=8").then(function (h) { state.recentRuns = h.runs; }, function () { /* palette works without them */ });
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
