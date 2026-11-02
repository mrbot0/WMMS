/* Activity: what is running now, step by step, what is scheduled next and what ran recently. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  function duration(start, end) {
    var s = Math.max(0, Math.round(((end || Date.now() / 1000) - start)));
    return s >= 3600 ? Math.floor(s / 3600) + " h " + Math.round((s % 3600) / 60) + " min" : s >= 60 ? Math.floor(s / 60) + " min " + (s % 60) + " s" : s + " s";
  }
  function when(epoch) { return UI.formatDate(new Date(epoch * 1000).toISOString()); }
  function title(App, id) { var a = App.action(id); return a ? a.title : id; }

  function stepsOf(App, job) {
    return '<ol class="steps">' + job.titles.map(function (id, i) {
      var r = job.results[i], cls = r ? (r.status === "error" ? "failed" : "done") : (job.active && i === job.results.length ? "current" : "");
      var dot = r ? UI.icon(r.status === "error" ? "x" : "check") : "";
      return '<li class="' + cls + '"><span class="step-dot">' + dot + '</span><span class="grow"><span class="cell-title">' + esc(title(App, id)) + "</span>" +
        (r && r.note ? '<br><span class="cell-sub">' + esc(r.note) + "</span>" : "") + "</span>" +
        (r ? UI.statusBadge(r.status) + ' <span class="cell-sub">' + r.seconds + " s</span>" : cls === "current" ? '<span class="badge badge-status-running">Running</span>' : '<span class="badge">Waiting</span>') + "</li>";
    }).join("") + "</ol>";
  }

  function runningCard(App, job) {
    var pct = Math.round(100 * job.done / Math.max(1, job.total));
    var current = job.current === "restore_point" ? "Creating a restore point" : job.current ? title(App, job.current) : "Starting…";
    return UI.card("Run in progress · " + (UI.ORIGIN_LABEL[job.origin] || job.origin), '<div class="job-status"><span class="spinner"></span><strong>' + esc(current) + "</strong></div>" +
      '<div class="big-progress"><div style="width:' + Math.max(3, pct) + '%"></div></div><div class="muted small">' + job.done + " of " + job.total + " actions · " + pct + "% · running for " +
      duration(job.started) + "</div>" + '<div class="grid grid-3-2" style="margin:16px 0 0"><div>' + stepsOf(App, job) + '</div><div><div class="log-head">Latest output</div><pre class="log" style="min-height:140px">' +
      esc(job.log.join("\n")) + "</pre></div></div>", '<button class="btn btn-sm" data-open-drawer>' + UI.icon("performance") + "Full log</button>");
  }

  function taskCard(task) {
    return UI.card(task.title, '<div class="job-status"><span class="spinner"></span><strong>' + esc(task.current || "Collecting data…") + "</strong></div>" +
      '<div class="big-progress' + (task.total <= 1 ? " indeterminate" : "") + '"><div style="width:' + Math.round(100 * task.done / Math.max(1, task.total)) + '%"></div></div>' +
      '<div class="muted small">' + (task.total > 1 ? task.done + " of " + task.total + " steps · " : "") + "running for " + duration(task.started) + "</div>");
  }

  window.Pages.activity = {
    title: "Activity",
    render: function (el, App) {
      var stopped = false, timer = null;
      App.setSubtitle("Runs and scans in progress, upcoming schedules and recent operations");
      function draw(a) {
        var activeJobs = a.jobs.filter(function (j) { return j.active; }), activeTasks = a.tasks.filter(function (t) { return t.active; });
        var today = new Date(); today.setHours(0, 0, 0, 0);
        var recent = a.jobs.filter(function (j) { return !j.active; }).map(function (j) {
          var errors = j.results.filter(function (r) { return r.status === "error"; }).length;
          return { kind: "run", start: j.started, end: j.finished, title: j.titles.length === 1 ? title(App, j.titles[0]) : j.titles.length + " actions · " + title(App, j.titles[0]) + "…",
            status: errors ? "error" : j.results.some(function (r) { return r.status === "preview"; }) ? "preview" : "ok", sub: (UI.ORIGIN_LABEL[j.origin] || j.origin) + " run", id: j.id };
        }).concat(a.tasks.filter(function (t) { return !t.active; }).map(function (t) {
          return { kind: "scan", start: t.started, end: t.finished, title: t.title, status: t.status, sub: "Scan" };
        })).sort(function (x, y) { return y.start - x.start; });
        var doneToday = recent.filter(function (r) { return r.start * 1000 >= today.getTime(); });
        var failed = doneToday.filter(function (r) { return r.status === "error"; }).length;

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("In progress", Components.num(activeJobs.length + activeTasks.length), activeJobs.length + " run(s), " + activeTasks.length + " scan(s)", activeJobs.length + activeTasks.length ? "info" : "ok") +
          UI.kpi("Completed today", Components.num(doneToday.length - failed), "Runs and scans", "ok") +
          UI.kpi("Failed today", Components.num(failed), failed ? "Open History for details" : "No failures", failed ? "error" : "ok") +
          UI.kpi("Next schedule", a.schedules.length ? esc(UI.formatDate(a.schedules[0].next_run)) : "—", a.schedules.length ? esc(a.schedules[0].title) : "Nothing planned", "info") + "</div>";

        var running = activeJobs.map(function (j) { return '<div class="grid">' + runningCard(App, j) + "</div>"; }).join("") +
          (activeTasks.length ? '<div class="grid grid-2">' + activeTasks.map(taskCard).join("") + "</div>" : "");
        if (!running) {
          running = '<section class="card"><div class="empty-state" style="padding:36px 20px">' + UI.icon("activity") + "<h2>Nothing is running</h2>" +
            "<p>Start a playbook, apply an improvement or scan an area: progress appears here step by step.</p>" +
            '<div class="page-actions" style="justify-content:center"><a class="btn btn-primary" href="#/playbooks">' + UI.icon("playbooks") + 'Open playbooks</a><a class="btn" href="#/recommendations">' +
            UI.icon("recommendations") + "Review improvements</a></div></div></section>";
        }

        var timeline = recent.length ? '<ul class="timeline">' + recent.slice(0, 30).map(function (r) {
          return "<li>" + UI.statusIcon(r.status === "ok" || r.status === "preview" ? "ok" : r.status === "error" ? "error" : "warning") + '<div><div class="cell-title">' + esc(r.title) +
            '</div><div class="cell-sub">' + esc(r.sub) + " · " + esc(when(r.start)) + " · took " + duration(r.start, r.end) + "</div></div>" + UI.statusBadge(r.status) + "</li>";
        }).join("") + "</ul>" : '<p class="empty">No operation in this session yet. Older runs are in History.</p>';

        var upcoming = a.schedules.length ? '<ul class="check-list">' + a.schedules.map(function (s) {
          return "<li>" + '<span class="status-icon skipped">' + UI.icon("clock") + '</span><span class="grow"><span class="cell-title">' + esc(s.title) + '</span><br><span class="cell-sub">' +
            esc(UI.formatDate(s.next_run)) + "</span></span></li>";
        }).join("") + "</ul>" : '<p class="empty">No upcoming schedule. Create one from any action.</p>';

        el.innerHTML = UI.pageHeader("Activity", "Updates every 1.5 seconds", '<a class="btn" href="#/history">' + UI.icon("history") + "Open history</a>") + kpis +
          '<div class="section-title">' + UI.icon("performance") + "Running now</div>" + running +
          '<div class="section-title">' + UI.icon("history") + "Recent operations</div>" +
          '<div class="grid grid-2-1">' + UI.card("This session", '<div class="scroll-area">' + timeline + "</div>") + UI.card("Up next", upcoming, '<a class="btn btn-sm" href="#/schedules">Schedules</a>') + "</div>";
        var drawerBtn = el.querySelector("[data-open-drawer]");
        if (drawerBtn) drawerBtn.addEventListener("click", App.openDrawer);
      }
      function tick() {
        if (stopped) return;
        API.get("/activity").then(function (a) { if (!stopped) draw(a); }).catch(function (e) {
          if (!stopped) el.innerHTML = UI.errorBox(e);
        }).then(function () { if (!stopped) timer = setTimeout(tick, 1500); });
      }
      App.onLeave(function () { stopped = true; clearTimeout(timer); });
      return API.get("/activity").then(function (a) { draw(a); timer = setTimeout(tick, 1500); });
    }
  };
})();
