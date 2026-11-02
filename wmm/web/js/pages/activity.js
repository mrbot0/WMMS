/* Activity: what is running now, step by step with the real percentage, what is scheduled next
   and what ran recently. The structure is drawn once; progress, steps and log are updated in place
   so the animated bars glide instead of restarting. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var kind = "all";  // filter of the session timeline: all, run or scan

  function duration(start, end) {
    var s = Math.max(0, Math.round(((end || Date.now() / 1000) - start)));
    return s >= 3600 ? Math.floor(s / 3600) + " h " + Math.round((s % 3600) / 60) + " min" : s >= 60 ? Math.floor(s / 60) + " min " + (s % 60) + " s" : s + " s";
  }
  function when(epoch) { return UI.formatDate(new Date(epoch * 1000).toISOString()); }
  function title(App, id) { var a = App.action(id); return a ? a.title : id; }

  function stepState(job, i) {
    var r = job.results[i];
    if (r) return r.status === "error" ? "failed" : "done";
    return job.active && i === job.results.length ? "current" : "";
  }
  function stepRight(job, i) {
    var r = job.results[i];
    if (r) return UI.statusBadge(r.status) + ' <span class="cell-sub">' + r.seconds + " s</span>";
    if (stepState(job, i) === "current") {
      return '<span class="badge badge-status-running">' + (job.step_percent != null ? job.step_percent.toFixed(0) + "%" : "Running") + "</span>";
    }
    return '<span class="badge">Waiting</span>';
  }

  function jobCard(App, job) {
    return UI.card("Run in progress · " + (UI.ORIGIN_LABEL[job.origin] || job.origin),
      '<div class="job-status"><span class="spinner"></span><strong data-f="current"></strong></div>' +
      '<div class="big-progress" data-f="bar"><div style="width:0%"></div></div>' +
      '<div class="progress-meta"><span class="pct" data-f="pct">0%</span><span class="muted small" data-f="meta"></span></div>' +
      '<div class="grid grid-3-2" style="margin:16px 0 0"><ol class="steps">' + job.titles.map(function (id, i) {
        return '<li data-step="' + i + '"><span class="step-dot"></span><span class="grow"><span class="cell-title">' + esc(title(App, id)) +
          '</span><br><span class="cell-sub" data-note></span></span><span data-right></span></li>';
      }).join("") + '</ol><div><div class="log-head">Latest output</div><pre class="log" style="min-height:140px" data-f="log"></pre></div></div>',
      '<button class="btn btn-sm" data-open-drawer>' + UI.icon("performance") + "Full log</button>").replace('class="card ', 'data-job="' + job.id + '" class="card ');
  }

  function patchJob(App, box, job) {
    var current = job.current === "restore_point" ? "Creating a restore point" : job.current ? title(App, job.current) : "Starting…";
    box.querySelector('[data-f="current"]').textContent = current;
    box.querySelector('[data-f="bar"] > div').style.width = Math.max(2, job.percent) + "%";
    box.querySelector('[data-f="pct"]').innerHTML = job.percent.toFixed(job.percent < 10 ? 1 : 0) + "%" + (job.estimated ? "<small>estimated</small>" : "");
    box.querySelector('[data-f="meta"]').textContent = job.done + " of " + job.total + " actions · running for " + duration(job.started);
    job.titles.forEach(function (_, i) {
      var li = box.querySelector('[data-step="' + i + '"]');
      var state = stepState(job, i);
      if (li.className !== state) {
        li.className = state;
        li.querySelector(".step-dot").innerHTML = state === "done" ? UI.icon("check") : state === "failed" ? UI.icon("x") : "";
      }
      li.querySelector("[data-right]").innerHTML = stepRight(job, i);
      var r = job.results[i];
      li.querySelector("[data-note]").textContent = r && r.note ? r.note : "";
    });
    var log = box.querySelector('[data-f="log"]'), text = job.log.join("\n");
    if (log.textContent !== text) { log.textContent = text; log.scrollTop = log.scrollHeight; }
  }

  function taskCard(task) {
    return UI.card(task.title, '<div class="job-status"><span class="spinner"></span><strong data-f="current"></strong></div>' +
      '<div class="big-progress' + (task.total <= 1 ? " indeterminate" : "") + '" data-f="bar"><div style="width:0%"></div></div>' +
      '<div class="progress-meta"><span class="pct" data-f="pct"></span><span class="muted small" data-f="meta"></span></div>').replace('class="card ', 'data-task="' + task.id + '" class="card ');
  }
  function patchTask(box, task) {
    var pct = Math.round(100 * task.done / Math.max(1, task.total));
    box.querySelector('[data-f="current"]').textContent = task.current || "Collecting data…";
    box.querySelector('[data-f="bar"] > div').style.width = pct + "%";
    box.querySelector('[data-f="pct"]').textContent = task.total > 1 ? pct + "%" : "";
    box.querySelector('[data-f="meta"]').textContent = (task.total > 1 ? task.done + " of " + task.total + " steps · " : "") + "running for " + duration(task.started);
  }

  window.Pages.activity = {
    title: "Activity",
    render: function (el, App) {
      var stopped = false, timer = null, shape = "";
      App.setSubtitle("Runs and scans in progress, upcoming schedules and recent operations");

      function structure(a, activeJobs, activeTasks) {
        var today = new Date(); today.setHours(0, 0, 0, 0);
        var recent = a.jobs.filter(function (j) { return !j.active; }).map(function (j) {
          var errors = j.results.filter(function (r) { return r.status === "error"; }).length;
          return { start: j.started, end: j.finished, title: j.titles.length === 1 ? title(App, j.titles[0]) : j.titles.length + " actions · " + title(App, j.titles[0]) + "…",
            status: errors ? "error" : j.results.some(function (r) { return r.status === "preview"; }) ? "preview" : "ok", sub: (UI.ORIGIN_LABEL[j.origin] || j.origin) + " run",
            kind: "run", ids: j.titles };
        }).concat(a.tasks.filter(function (t) { return !t.active; }).map(function (t) {
          return { start: t.started, end: t.finished, title: t.title, status: t.status, sub: "Scan", kind: "scan" };
        })).sort(function (x, y) { return y.start - x.start; });
        var doneToday = recent.filter(function (r) { return r.start * 1000 >= today.getTime(); });
        var failed = doneToday.filter(function (r) { return r.status === "error"; }).length;
        var kpis = '<div class="grid grid-4">' +
          UI.kpi("In progress", String(activeJobs.length + activeTasks.length), activeJobs.length + " run(s), " + activeTasks.length + " scan(s)", activeJobs.length + activeTasks.length ? "info" : "ok") +
          UI.kpi("Completed today", String(doneToday.length - failed), "Runs and scans", "ok") +
          UI.kpi("Failed today", String(failed), failed ? "Open History for details" : "No failures", failed ? "error" : "ok") +
          UI.kpi("Next schedule", a.schedules.length ? esc(UI.formatDate(a.schedules[0].next_run)) : "—", a.schedules.length ? esc(a.schedules[0].title) : "Nothing planned", "info") + "</div>";
        var running = activeJobs.map(function (j) { return '<div class="grid">' + jobCard(App, j) + "</div>"; }).join("") +
          (activeTasks.length ? '<div class="grid grid-2">' + activeTasks.map(taskCard).join("") + "</div>" : "");
        if (!running) {
          var start = function (attr, area, iconName, title, sub) {
            return '<button type="button" class="start-card" ' + attr + ' data-area="' + area + '"><span class="tile-icon">' + UI.icon(iconName) + "</span><span><b>" +
              esc(title) + '</b><span class="sub">' + esc(sub) + "</span></span></button>";
          };
          running = '<section class="card idle"><div class="idle-art"><div class="idle-ring"><span>' + UI.icon("activity") + "</span></div>" +
            "<h2>Nothing is running</h2><p>The agent is ready. Start something on the right: every step, its real percentage and the live output appear here.</p>" +
            '<p class="muted small"><span class="led"></span>Agent idle · ' + (a.schedules.length ? "next schedule " + esc(UI.formatDate(a.schedules[0].next_run)) : "no schedule planned") + "</p></div>" +
            '<div class="start-grid">' +
            start('data-start="quick"', "cleanup", "bolt", "Quick tune-up", "Safe cleanup and optimization, no restart") +
            start('data-start="scan"', "performance", "refresh", "Scan all areas", "Assess the nine areas in about a minute") +
            start('data-href="#/actions"', "services", "actions", "Browse actions", "All maintenance actions, run or schedule") +
            start('data-href="#/playbooks"', "integrity", "playbooks", "Open playbooks", "Full maintenance, repair, security…") +
            "</div></section>";
        }
        var filtered = recent.filter(function (r) { return kind === "all" || r.kind === kind; });
        var timeline = filtered.length ? '<ul class="timeline">' + filtered.slice(0, 30).map(function (r) {
          return "<li>" + UI.statusIcon(r.status === "ok" || r.status === "preview" ? "ok" : r.status === "error" ? "error" : "warning") + '<div><div class="cell-title">' + esc(r.title) +
            '</div><div class="cell-sub">' + esc(r.sub) + " · " + esc(when(r.start)) + " · took " + duration(r.start, r.end) + "</div></div>" + UI.statusBadge(r.status) +
            (r.ids ? '<button class="btn btn-sm btn-ghost" type="button" data-again="' + esc(r.ids.join(",")) + '" title="Run the same actions again">' + UI.icon("refresh") + "Run again</button>" : "") + "</li>";
        }).join("") + "</ul>" : '<p class="empty">' + (recent.length ? "No operation of this kind in this session." : "No operation in this session yet. Older runs are in History.") + "</p>";
        var kinds = '<span class="btn-group" role="group">' + [["all", "All"], ["run", "Runs"], ["scan", "Scans"]].map(function (k) {
          return '<button type="button" class="btn btn-sm' + (kind === k[0] ? " active" : "") + '" data-kind="' + k[0] + '">' + k[1] + "</button>";
        }).join("") + "</span>";
        var upcoming = a.schedules.length ? '<ul class="check-list">' + a.schedules.map(function (s) {
          return '<li><span class="status-icon skipped">' + UI.icon("clock") + '</span><span class="grow"><span class="cell-title">' + esc(s.title) + '</span><br><span class="cell-sub">' +
            esc(UI.formatDate(s.next_run)) + "</span></span></li>";
        }).join("") + "</ul>" : '<p class="empty">No upcoming schedule. Create one from any action.</p>';
        el.innerHTML = UI.pageHeader("Activity", "Live: updates every second", '<a class="btn" href="#/history">' + UI.icon("history") + "Open history</a>") + kpis +
          '<div class="section-title">' + UI.icon("performance") + "Running now</div>" + running +
          '<div class="section-title">' + UI.icon("history") + "Recent operations</div>" +
          '<div class="grid grid-2-1">' + UI.card("This session", '<div class="scroll-area">' + timeline + "</div>", kinds) + UI.card("Up next", upcoming, '<a class="btn btn-sm" href="#/schedules">Schedules</a>') + "</div>";
        el.querySelectorAll("[data-kind]").forEach(function (b) {
          b.addEventListener("click", function () { kind = b.getAttribute("data-kind"); shape = ""; structure(a, activeJobs, activeTasks); });
        });
        el.querySelectorAll("[data-again]").forEach(function (b) {
          b.addEventListener("click", function () { App.runActions(b.getAttribute("data-again").split(",")); });
        });
        var drawerBtn = el.querySelector("[data-open-drawer]");
        if (drawerBtn) drawerBtn.addEventListener("click", App.openDrawer);
        el.querySelectorAll("[data-href]").forEach(function (b) { b.addEventListener("click", function () { location.hash = b.getAttribute("data-href"); }); });
        var scan = el.querySelector('[data-start="scan"]');
        if (scan) scan.addEventListener("click", App.scanAll);
        var quick = el.querySelector('[data-start="quick"]');
        if (quick) quick.addEventListener("click", function () {
          API.get("/playbooks").then(function (p) {
            var book = p.playbooks.filter(function (b) { return b.id === "quick"; })[0];
            if (book) App.runActions(book.actions);
          });
        });
      }

      function draw(a) {
        var activeJobs = a.jobs.filter(function (j) { return j.active; }), activeTasks = a.tasks.filter(function (t) { return t.active; });
        // Redraw only when the set of operations changes; otherwise patch values in place.
        var key = activeJobs.map(function (j) { return j.id; }).join() + "|" + activeTasks.map(function (t) { return t.id; }).join() + "|" + a.jobs.length + "|" + a.tasks.length;
        if (key !== shape) { shape = key; structure(a, activeJobs, activeTasks); }
        activeJobs.forEach(function (j) { var box = el.querySelector('[data-job="' + j.id + '"]'); if (box) patchJob(App, box, j); });
        activeTasks.forEach(function (t) { var box = el.querySelector('[data-task="' + t.id + '"]'); if (box) patchTask(box, t); });
      }
      function tick() {
        if (stopped) return;
        API.get("/activity").then(function (a) { if (!stopped) draw(a); }).catch(function () { /* reconnect banner handles it */ })
          .then(function () { if (!stopped) timer = setTimeout(tick, 1000); });
      }
      App.onLeave(function () { stopped = true; clearTimeout(timer); });
      return API.get("/activity").then(function (a) { draw(a); timer = setTimeout(tick, 1000); });
    }
  };
})();
