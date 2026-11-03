/* Schedules registered in Windows Task Scheduler: actions, routines and scripts. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var KIND = { once: "Once", daily: "Daily", weekly: "Weekly", monthly: "Monthly", startup: "At startup", logon: "At sign-in" };
  var SYNC = { ok: ["ok", "In sync"], missing: ["error", "Task missing"], path_changed: ["warning", "Program moved"] };
  var GROUP_ICON = { "At startup": "power", "At sign-in": "user", "Every day": "clock", "Every week": "calendar", "Every month": "calendar", "Playbooks": "playbooks" };
  var when = UI.scheduleText;

  /* The suggested frequency of a routine as a schedule-like object, for UI.scheduleText. */
  function suggestedSchedule(sug) {
    sug = sug || { kind: "weekly", time: "12:00", days: "SAT" };
    var day = ("0" + (sug.day || 1)).slice(-2);
    return { kind: sug.kind, at: "2026-01-" + day + "T" + (sug.time || "00:00"), days: sug.days || "", delay: sug.delay || 0 };
  }

  /* Opens the schedule dialog with the routine's suggested frequency, then registers it. */
  function applyRoutine(r, done) {
    var risky = r.actions.filter(function (a) { return a.risk !== "safe"; });
    UI.scheduleDialog({
      label: "Apply routine", title: r.title, risk: r.risk, suggested: r.suggested || { kind: "weekly", time: "12:00", days: "SAT" },
      description: r.description + " (" + r.actions.length + " steps, about " + Math.max(1, Math.round(r.minutes)) + " min)",
      warning: risky.length ? "It includes: " + risky.map(function (a) { return a.title; }).join(", ") + "." : ""
    }).then(function (v) {
      if (!v) return;
      if (r.risk !== "safe" && !v.confirmed) { UI.toast("Tick the confirmation box to schedule a routine with steps that are not safe.", "warning"); return; }
      if (v.kind === "weekly" && !v.days) { UI.toast("Choose at least one day.", "warning"); return; }
      v.action_id = r.ref;
      API.post("/schedules", v).then(function () {
        UI.toast(r.title + ": " + when(v) + ".", "ok");
        Components.notifications.add("Routine scheduled", r.title + " · " + when(v), "ok");
        if (done) done();
      }, function (er) { UI.toast(er.message, "error"); });
    });
  }

  function routineCard(r) {
    var active = r.scheduled || [];
    return '<article class="routine-card' + (active.length ? " is-active" : "") + '">' +
      '<div class="routine-head"><span class="cell-title">' + esc(r.title) + "</span>" +
      (r.reports_only ? UI.kindBadge("report") : UI.riskBadge(r.risk)) + "</div>" +
      '<p class="routine-desc">' + esc(r.description) + "</p>" +
      '<div class="routine-when">' + UI.icon("clock") + esc(r.suggested ? when(suggestedSchedule(r.suggested)) : "Any frequency you choose") + "</div>" +
      '<details class="routine-steps"><summary>' + r.actions.length + " steps · ~" + Math.max(1, Math.round(r.minutes)) + " min</summary><ol>" +
      r.actions.map(function (a) { return "<li>" + esc(a.title) + (a.risk !== "safe" ? " " + UI.riskBadge(a.risk) : "") + "</li>"; }).join("") + "</ol></details>" +
      '<div class="routine-foot">' + (active.length ? '<span class="badge badge-status-ok">' + UI.icon("check") + (active.length > 1 ? active.length + " active" : "Active") + "</span>" : "<span></span>") +
      '<button class="btn btn-sm' + (active.length ? "" : " btn-primary") + '" data-apply="' + esc(r.ref) + '">' + UI.icon(active.length ? "plus" : "play") +
      (active.length ? "Add another" : "Apply") + "</button></div></article>";
  }

  function routinesBody(cat, tab) {
    var groups = cat.groups.concat(["Playbooks"]);
    var items = tab === "Playbooks" ? cat.playbooks : cat.routines.filter(function (r) { return r.group === tab; });
    return '<div class="tabs routine-tabs" role="tablist">' + groups.map(function (g) {
      var n = (g === "Playbooks" ? cat.playbooks : cat.routines.filter(function (r) { return r.group === g; })).length;
      return '<button class="tab' + (g === tab ? " active" : "") + '" role="tab" aria-selected="' + (g === tab) + '" data-routine-tab="' + esc(g) + '">' +
        UI.icon(GROUP_ICON[g] || "clock") + esc(g) + ' <span class="tab-count">' + n + "</span></button>";
    }).join("") + "</div>" +
      (tab === "Playbooks" ? '<p class="muted small routine-note">Any playbook can run as a routine: choose its frequency when you apply it.</p>' : "") +
      '<div class="routine-grid">' + items.map(routineCard).join("") + "</div>";
  }

  /* The next 7 days: every planned run of the enabled schedules and scripts, day by day. */
  var AGENDA_DAYS = 7;
  var WEEKDAY = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  function occurrences(s, from, to) {
    var at = new Date(s.at), out = [];
    if (isNaN(at)) return out;
    if (s.kind === "once") return at >= from && at < to ? [at] : out;
    for (var d = new Date(from.getFullYear(), from.getMonth(), from.getDate()); d < to; d.setDate(d.getDate() + 1)) {
      var t = new Date(d.getFullYear(), d.getMonth(), d.getDate(), at.getHours(), at.getMinutes());
      if (t < from || t < at) continue;
      if (s.kind === "daily" || (s.kind === "weekly" && (s.days || "").split(",").indexOf(WEEKDAY[t.getDay()]) >= 0) ||
          (s.kind === "monthly" && t.getDate() === at.getDate())) out.push(t);
    }
    return out;
  }
  function agenda(list, scripts) {
    var from = new Date(), to = new Date(from.getTime() + AGENDA_DAYS * 86400e3), rows = [], events = 0;
    list.filter(function (s) { return s.enabled; }).forEach(function (s) {
      if (s.kind === "startup" || s.kind === "logon") { events++; return; }
      occurrences(s, from, to).forEach(function (t) { rows.push({ t: t, title: s.title }); });
    });
    scripts.filter(function (s) { return s.schedule; }).forEach(function (s) {
      if (s.schedule.kind === "startup" || s.schedule.kind === "logon") { events++; return; }
      occurrences(s.schedule, from, to).forEach(function (t) { rows.push({ t: t, title: s.name + " (script)" }); });
    });
    rows.sort(function (a, b) { return a.t - b.t; });
    var lastDay = "";
    return (rows.length ? '<ul class="agenda">' + rows.slice(0, 40).map(function (r) {
      var day = r.t.toLocaleDateString(undefined, { weekday: "short", day: "2-digit", month: "short" });
      var show = day !== lastDay;
      lastDay = day;
      return '<li><span class="agenda-day">' + (show ? esc(day) : "") + '</span><span class="agenda-time">' + ("0" + r.t.getHours()).slice(-2) + ":" + ("0" + r.t.getMinutes()).slice(-2) +
        "</span><span>" + esc(r.title) + "</span></li>";
    }).join("") + "</ul>" : '<p class="empty">Nothing planned in the next ' + AGENDA_DAYS + " days.</p>") +
      (events ? '<p class="muted small" style="margin:10px 0 0">' + UI.icon("power") + " Plus " + events + " schedule" + (events === 1 ? "" : "s") + " at startup or sign-in.</p>" : "");
  }

  /* Scripts scheduled from here or from the Scripts page: same Task Scheduler folder, run as SYSTEM. */
  function scriptsTable(scripts) {
    var rows = scripts.filter(function (s) { return s.schedule; });
    return UI.table([{ title: "Script" }, { title: "When" }, { title: "Last run" }, { title: "", cls: "actions" }], rows.map(function (s) {
      var last = s.last_run;
      return ['<span class="cell-title">' + esc(s.name) + '</span><div class="cell-sub cell-mono">' + esc(s.file) + "</div>", esc(when(s.schedule)),
        last ? UI.statusBadge(last.status) + ' <span class="cell-sub">' + esc(UI.relative(last.finished || last.started)) + "</span>" : '<span class="cell-sub">Never</span>',
        '<span class="tm-actions"><button class="btn btn-sm" data-script-op="run" data-script-id="' + s.id + '">' + UI.icon("play") + "Run now</button>" +
        '<button class="btn btn-sm" data-script-op="change" data-script-id="' + s.id + '">' + UI.icon("clock") + "Change</button>" +
        '<button class="btn btn-sm btn-ghost" data-script-op="unschedule" data-script-id="' + s.id + '">' + UI.icon("x") + "Remove</button></span>"];
    }), scripts.length ? "No script is scheduled yet: use New schedule › A script." : "No scripts yet: add one in the Scripts page, then schedule it here.");
  }
  function pickScript(scripts) {
    if (!scripts.length) {
      return UI.confirm("No scripts yet", "Upload or write a script, or add a ready-made one (for example Shut down in N minutes) in the Scripts page first.",
        { ok: "Open Scripts" }).then(function (ok) { if (ok) location.hash = "#/scripts"; return null; });
    }
    return UI.modal("Schedule a script", '<form class="form" onsubmit="return false"><label>Script<select name="script">' + scripts.map(function (s) {
      return '<option value="' + esc(s.id) + '">' + esc(s.name) + (s.schedule ? " (now: " + esc(when(s.schedule)) + ")" : "") + "</option>";
    }).join("") + "</select></label></form>", [{ label: "Cancel", cls: "btn-ghost" }, { label: "Next", cls: "btn-primary", value: function (w) {
      return w.querySelector("select").value;
    } }]).then(function (id) { return scripts.filter(function (s) { return s.id === id; })[0] || null; });
  }
  function scheduleScript(s, done) {
    UI.scheduleDialog({ title: s.name, description: "Batch script " + s.file, risk: "moderate", suggested: s.schedule || null,
      warning: "The script runs as SYSTEM with full rights, even when nobody is signed in." }).then(function (v) {
      if (!v) return;
      if (!v.confirmed) { UI.toast("Tick the confirmation box to schedule a script.", "warning"); return; }
      if (v.kind === "weekly" && !v.days) { UI.toast("Choose at least one day.", "warning"); return; }
      API.post("/scripts/" + s.id + "/schedule", v).then(function (r) {
        UI.toast(r.preview ? "Preview mode: not scheduled (recorded in History)." : s.name + " scheduled: " + when(r.script ? r.script.schedule : v) + ".", r.preview ? "info" : "ok");
        done();
      }, function (er) { UI.toast(er.message, "error"); });
    });
  }

  function pickAction(App) {
    var options = Object.keys(App.state.actions).map(function (id) {
      var a = App.state.actions[id];
      return '<option value="' + esc(id) + '">' + esc(UI.AREA_LABEL[a.area] + " › " + a.title + " (" + UI.RISK_LABEL[a.risk] + ")") + "</option>";
    }).join("");
    return UI.modal("New schedule", '<form class="form" onsubmit="return false"><label>Action<select name="action">' + options + "</select></label></form>", [
      { label: "Cancel", cls: "btn-ghost" },
      { label: "Next", cls: "btn-primary", value: function (wrap) { return wrap.querySelector("select").value; } }
    ]);
  }

  window.Pages.schedules = {
    title: "Schedules",
    applyRoutine: applyRoutine,
    render: function (el, App) {
      var self = this;
      var rerender = function () { self.render(el, App); };
      return Promise.all([API.get("/schedules"), API.get("/scripts").catch(function () { return { scripts: [] }; }),
        API.get("/routines").catch(function () { return { routines: [], playbooks: [], groups: [] }; })]).then(function (all) {
        var data = all[0], scriptList = all[1].scripts || [], cat = all[2];
        var list = data.schedules;
        var enabled = list.filter(function (s) { return s.enabled; });
        var next = enabled.map(function (s) { return s.next_run; }).filter(Boolean).sort()[0];
        var issues = list.filter(function (s) { return s.sync !== "ok"; }).length;
        var routineCount = list.filter(function (s) { return s.routine; }).length;
        var onEvent = enabled.filter(function (s) { return s.kind === "startup" || s.kind === "logon"; }).length;
        App.setSubtitle("Actions and routines that run automatically, even when the console is closed");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Schedules", String(list.length), enabled.length + " enabled · " + routineCount + " routines", "info") +
          UI.kpi("Next run", next ? esc(UI.formatDate(next)) : (onEvent ? "At startup" : "—"),
            next ? esc(UI.relative(next)).replace(" ago", "") + (onEvent ? " · " + onEvent + " on startup/sign-in" : "") : (onEvent ? onEvent + " run on startup or sign-in" : "Nothing planned"), next || onEvent ? "ok" : "") +
          UI.kpi("Last failures", String(list.filter(function (s) { return s.last_status === "error"; }).length), "Schedules whose last run failed", list.some(function (s) { return s.last_status === "error"; }) ? "error" : "ok") +
          UI.kpi("Out of sync", String(issues), "Compared with Task Scheduler", issues ? "warning" : "ok") + "</div>";

        var byArea = UI.AREAS.map(function (a, i) {
          return { label: UI.AREA_LABEL[a], value: list.filter(function (s) { return s.area === a; }).length, color: Charts.PALETTE[i % Charts.PALETTE.length] };
        }).concat([{ label: "Routines", value: routineCount, color: "var(--accent)" }]).filter(function (s) { return s.value; });
        var table = UI.table(
          [{ title: "Enabled" }, { title: "Action or routine" }, { title: "Risk" }, { title: "When" }, { title: "Next run" }, { title: "Last run" }, { title: "Task Scheduler" }, { title: "", cls: "actions" }],
          list.map(function (s) {
            var sync = SYNC[s.sync] || ["skipped", s.sync];
            var sub = s.routine ? (s.routine === "playbook" ? "Playbook" : "Routine") + " · " + s.steps + " steps" : (UI.AREA_LABEL[s.area] || s.area);
            return [
              '<label class="switch" title="Enable or disable"><input type="checkbox" data-toggle="' + s.id + '"' + (s.enabled ? " checked" : "") + "><span></span></label>",
              '<div class="cell-title">' + (s.routine ? UI.icon("playbooks") : "") + esc(s.title) + '</div><div class="cell-sub">' + esc(sub) + " · " + esc(KIND[s.kind] || s.kind) + "</div>",
              UI.riskBadge(s.risk), esc(when(s)),
              s.next_run ? esc(UI.formatDate(s.next_run)) : '<span class="cell-sub">' + (s.kind === "startup" ? "Next startup" : s.kind === "logon" ? "Next sign-in" : "—") + "</span>",
              s.last_run ? UI.statusBadge(s.last_status) + ' <span class="cell-sub">' + esc(UI.relative(s.last_run)) + "</span>" : '<span class="cell-sub">Not run yet</span>',
              '<span class="badge badge-status-' + sync[0] + '">' + esc(sync[1]) + "</span>",
              '<button class="btn btn-sm" data-run-now="' + s.id + '" title="Run it now in this console, without waiting for its time">' + UI.icon("play") + "Run now</button>" +
                '<button class="btn btn-sm btn-ghost" data-dup="' + s.id + '" title="A second schedule of the same action or routine, at another time">' + UI.icon("plus") + "</button>" +
                (s.sync !== "ok" ? '<button class="btn btn-sm" data-resync="' + s.id + '">' + UI.icon("refresh") + "Resync</button>" : "") +
                '<button class="btn btn-sm" data-delete="' + s.id + '">' + UI.icon("trash") + "Delete</button>"
            ];
          }), "No schedules yet. Apply a suggested routine above, use Schedule on any action, or create one here.");

        var tab = Components.store("routineTab") || "At startup";
        if (tab !== "Playbooks" && cat.groups.indexOf(tab) < 0) tab = cat.groups[0] || "Playbooks";

        var inst = data.installation || { protected: true };
        var install = UI.installCallout(inst);
        el.innerHTML = UI.pageHeader("Schedules", "Registered in Windows Task Scheduler › WindowsMaintenanceManager",
          UI.hint("Schedules are Windows tasks that run as SYSTEM, even when nobody is signed in and the console is closed. " +
            "Routines run several actions in one go: at startup, at sign-in, every day, week or month. Actions that are not safe create a restore point first.") +
          (list.length ? UI.button(enabled.length ? "Pause all" : "Resume all", 'id="pause-all" title="' + (enabled.length ? "Disable every schedule, for example during a presentation or a trip" : "Enable every schedule again") + '"', "", enabled.length ? "clock" : "play") : "") +
          UI.button("New schedule", 'id="new-schedule"', "btn-primary", "clock")) + install + kpis +
          '<div class="grid">' + UI.card("Suggested routines", routinesBody(cat, tab),
            '<span class="muted small">' + cat.routines.length + " routines · " + cat.playbooks.length + " playbooks</span>", "routines-card") + "</div>" +
          '<div class="grid grid-2-1">' + UI.card("Scheduled actions and routines", table, list.length ? '<button type="button" class="btn btn-sm" id="sched-csv">' + UI.icon("download") + "CSV</button>" : "") +
          UI.card("Schedules by area", '<div class="chart-row">' + Charts.donut(byArea, { center: list.length, sub: "schedules", empty: "No schedules" }) + Charts.legend(byArea) + "</div>" +
            '<div class="callout">' + UI.icon("info") + "<div>Scheduled runs use the SYSTEM account, so they work when nobody is signed in. A startup routine runs before anyone signs in; a sign-in routine runs for every user.</div></div>") + "</div>" +
          '<div class="grid">' + UI.card("Next 7 days", agenda(list, scriptList)) + "</div>" +
          '<div class="grid">' + UI.card("Scheduled scripts", scriptsTable(scriptList),
            '<span class="muted small">' + scriptList.filter(function (s) { return s.schedule; }).length + " of " + scriptList.length + " scripts</span>" +
            '<a class="btn btn-sm" href="#/scripts">' + UI.icon("scripts") + "Scripts</a>", "card-flush") + "</div>";

        // Tabs: what to schedule (routines), what is scheduled, when it runs, and the scripts; figures and warnings stay above.
        if (Components.store("pageTabs") !== false) {
          UI.pageTabs(el, "schedules", [
            { id: "routines", label: "Routines", icon: "playbooks", match: UI.hasCard("Suggested routines") },
            { id: "scheduled", label: "Scheduled", icon: "clock", match: UI.hasCard("Scheduled actions and routines") },
            { id: "calendar", label: "Next 7 days", icon: "calendar", match: UI.hasCard("Next 7 days") },
            { id: "scripts", label: "Scripts", icon: "scripts", match: UI.hasCard("Scheduled scripts") }
          ], { sharedHead: true });
        }
        var routinesEl = el.querySelector('[data-card$="|Suggested routines"] .card-body') || el.querySelector('[data-card$="|Suggested routines"]');
        routinesEl.addEventListener("click", function (e) {
          var t = e.target.closest("[data-routine-tab]");
          if (t) {
            tab = t.getAttribute("data-routine-tab");
            Components.store("routineTab", tab);
            routinesEl.innerHTML = routinesBody(cat, tab);
            return;
          }
          var b = e.target.closest("[data-apply]");
          if (!b) return;
          var ref = b.getAttribute("data-apply");
          var r = cat.routines.concat(cat.playbooks).filter(function (x) { return x.ref === ref; })[0];
          if (!r) return;
          if (!inst.protected) { UI.toast("Protect the installation first (Fix automatically above): routines run as SYSTEM.", "warning"); return; }
          applyRoutine(r, rerender);
        });

        el.querySelector("#new-schedule").addEventListener("click", function () {
          UI.modal("New schedule", '<p class="modal-text">What should run automatically?</p>',
            [{ label: "Cancel", cls: "btn-ghost" }, { label: "A script", cls: "", value: function () { return "script"; } },
              { label: "A routine", cls: "", value: function () { return "routine"; } },
              { label: "A maintenance action", cls: "btn-primary", value: function () { return "action"; } }]).then(function (what) {
            if (what === "action") pickAction(App).then(function (id) { if (id) App.schedule(id).then(rerender); });
            if (what === "script") pickScript(scriptList).then(function (s) { if (s) scheduleScript(s, rerender); });
            if (what === "routine") el.querySelector('[data-card$="|Suggested routines"]').scrollIntoView({ behavior: "smooth", block: "start" });
          });
        });
        el.querySelector('[data-card$="|Scheduled scripts"]').addEventListener("click", function (e) {
          var b = e.target.closest("[data-script-op]");
          if (!b || b.disabled) return;
          var s = scriptList.filter(function (x) { return x.id === b.getAttribute("data-script-id"); })[0];
          if (!s) return;
          var op = b.getAttribute("data-script-op");
          if (op === "change") { scheduleScript(s, rerender); return; }
          API.post("/scripts/" + s.id + "/" + op).then(function (r) {
            if (r.preview) { UI.toast("Preview mode: recorded in History, nothing changed.", "info"); return; }
            UI.toast(op === "run" ? s.name + " is running: its output is in Scripts." : "Schedule removed.", "ok");
            rerender();
          }, function (er) { UI.toast(er.message, "error"); });
        });
        el.querySelectorAll("[data-toggle]").forEach(function (input) {
          input.addEventListener("change", function () {
            API.patch("/schedules/" + input.getAttribute("data-toggle"), { enabled: input.checked })
              .then(function () { UI.toast(input.checked ? "Schedule enabled." : "Schedule disabled.", "ok"); rerender(); })
              .catch(function (e) { UI.toast(e.message, "error"); input.checked = !input.checked; });
          });
        });
        el.querySelectorAll("[data-delete]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            UI.confirm("Delete schedule", "The task is removed from Windows Task Scheduler. Past runs stay in History.", { ok: "Delete", danger: true }).then(function (ok) {
              if (!ok) return;
              API.del("/schedules/" + btn.getAttribute("data-delete")).then(function () { UI.toast("Schedule deleted.", "ok"); rerender(); },
                function (e) { UI.toast(e.message, "error"); });
            });
          });
        });
        el.querySelectorAll("[data-run-now]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var s = list.filter(function (x) { return String(x.id) === btn.getAttribute("data-run-now"); })[0];
            if (!s) return;
            var r = cat.routines.concat(cat.playbooks).filter(function (x) { return x.ref === s.action_id; })[0];
            var ids = r ? r.actions.map(function (a) { return a.id; }) : [s.action_id];
            App.runActions(App.order(ids));
          });
        });
        var csv = el.querySelector("#sched-csv");
        if (csv) csv.addEventListener("click", function () {
          var cell = function (v) { v = String(v == null ? "" : v); return /[",\n;]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
          var rows = [["title", "runs", "frequency", "enabled", "next_run", "last_run", "last_status", "task_scheduler"]].concat(list.map(function (s) {
            return [s.title, s.action_id, when(s), s.enabled ? "yes" : "no", s.next_run || "", s.last_run || "", s.last_status || "", s.sync];
          }));
          Components.downloadText("wmm-schedules.csv", String.fromCharCode(0xFEFF) + rows.map(function (r) { return r.map(cell).join(","); }).join("\n"), "text/csv;charset=utf-8");
        });
        el.querySelectorAll("[data-dup]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var s = list.filter(function (x) { return String(x.id) === btn.getAttribute("data-dup"); })[0];
            if (!s) return;
            UI.scheduleDialog({ label: "Duplicate schedule", title: s.title, description: "Same " + (s.routine ? "routine" : "action") + ", a new time. Now: " + when(s) + ".",
              risk: s.risk, suggested: { kind: s.kind, time: s.at.slice(11, 16), days: s.days, delay: s.delay } }).then(function (v) {
              if (!v) return;
              if (s.risk !== "safe" && !v.confirmed) { UI.toast("Tick the confirmation box to schedule something that is not safe.", "warning"); return; }
              if (v.kind === "weekly" && !v.days) { UI.toast("Choose at least one day.", "warning"); return; }
              v.action_id = s.action_id;
              API.post("/schedules", v).then(function () { UI.toast("Second schedule created: " + when(v) + ".", "ok"); rerender(); }, function (er) { UI.toast(er.message, "error"); });
            });
          });
        });
        var pause = el.querySelector("#pause-all");
        if (pause) pause.addEventListener("click", function () {
          var on = !enabled.length, targets = list.filter(function (s) { return s.enabled !== on; });
          pause.disabled = true;
          Promise.all(targets.map(function (s) { return API.patch("/schedules/" + s.id, { enabled: on }).then(function () { return 1; }, function () { return 0; }); }))
            .then(function (done) {
              var ok = done.reduce(function (a, b) { return a + b; }, 0);
              UI.toast((on ? "Resumed " : "Paused ") + ok + " of " + targets.length + " schedules." + (ok < targets.length ? " The others need administrator rights." : ""), ok === targets.length ? "ok" : "warning");
              rerender();
            });
        });
        el.querySelectorAll("[data-resync]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            API.post("/schedules/" + btn.getAttribute("data-resync") + "/resync").then(function () { UI.toast("Task registered again.", "ok"); rerender(); },
              function (e) { UI.toast(e.message, "error"); });
          });
        });
      });
    }
  };
})();
