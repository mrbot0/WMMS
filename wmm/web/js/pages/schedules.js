/* Schedules registered in Windows Task Scheduler. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var KIND = { once: "Once", daily: "Daily", weekly: "Weekly" };
  var SYNC = { ok: ["ok", "In sync"], missing: ["error", "Task missing"], path_changed: ["warning", "Program moved"] };

  function when(s) {
    var t = s.at.split("T")[1];
    if (s.kind === "once") return UI.formatDate(s.at);
    if (s.kind === "daily") return "Every day at " + t;
    return s.days.split(",").map(function (d) { return d.charAt(0) + d.slice(1).toLowerCase(); }).join(", ") + " at " + t;
  }

  var DAYS = { MON: "Mon", TUE: "Tue", WED: "Wed", THU: "Thu", FRI: "Fri", SAT: "Sat", SUN: "Sun" };
  function when(s) {
    var at = s.at.replace("T", " ");
    return s.kind === "once" ? "Once on " + at : s.kind === "daily" ? "Every day at " + at.slice(11)
      : "Every " + s.days.split(",").map(function (d) { return DAYS[d] || d; }).join(", ") + " at " + at.slice(11);
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
    UI.scheduleDialog({ title: s.name, description: "Batch script " + s.file, risk: "moderate",
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
    render: function (el, App) {
      var self = this;
      var rerender = function () { self.render(el, App); };
      return Promise.all([API.get("/schedules"), API.get("/scripts").catch(function () { return { scripts: [] }; })]).then(function (both) {
        var data = both[0], scriptList = both[1].scripts || [];
        var list = data.schedules;
        var enabled = list.filter(function (s) { return s.enabled; });
        var next = enabled.map(function (s) { return s.next_run; }).filter(Boolean).sort()[0];
        var issues = list.filter(function (s) { return s.sync !== "ok"; }).length;
        App.setSubtitle("Actions that run automatically, even when the console is closed");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Schedules", String(list.length), enabled.length + " enabled", "info") +
          UI.kpi("Next run", next ? esc(UI.formatDate(next)) : "—", next ? esc(UI.relative(next)).replace(" ago", "") : "Nothing planned", next ? "ok" : "") +
          UI.kpi("Last failures", String(list.filter(function (s) { return s.last_status === "error"; }).length), "Schedules whose last run failed", list.some(function (s) { return s.last_status === "error"; }) ? "error" : "ok") +
          UI.kpi("Out of sync", String(issues), "Compared with Task Scheduler", issues ? "warning" : "ok") + "</div>";

        var byArea = UI.AREAS.map(function (a, i) {
          return { label: UI.AREA_LABEL[a], value: list.filter(function (s) { return s.area === a; }).length, color: Charts.PALETTE[i % Charts.PALETTE.length] };
        }).filter(function (s) { return s.value; });
        var table = UI.table(
          [{ title: "Enabled" }, { title: "Action" }, { title: "Risk" }, { title: "When" }, { title: "Next run" }, { title: "Last run" }, { title: "Task Scheduler" }, { title: "", cls: "actions" }],
          list.map(function (s) {
            var sync = SYNC[s.sync] || ["skipped", s.sync];
            return [
              '<label class="switch" title="Enable or disable"><input type="checkbox" data-toggle="' + s.id + '"' + (s.enabled ? " checked" : "") + "><span></span></label>",
              '<div class="cell-title">' + esc(s.title) + '</div><div class="cell-sub">' + esc(UI.AREA_LABEL[s.area] || s.area) + " · " + esc(KIND[s.kind]) + "</div>",
              UI.riskBadge(s.risk), esc(when(s)), s.next_run ? esc(UI.formatDate(s.next_run)) : '<span class="cell-sub">—</span>',
              s.last_run ? UI.statusBadge(s.last_status) + ' <span class="cell-sub">' + esc(UI.relative(s.last_run)) + "</span>" : '<span class="cell-sub">Not run yet</span>',
              '<span class="badge badge-status-' + sync[0] + '">' + esc(sync[1]) + "</span>",
              (s.sync !== "ok" ? '<button class="btn btn-sm" data-resync="' + s.id + '">' + UI.icon("refresh") + "Resync</button>" : "") +
                '<button class="btn btn-sm" data-delete="' + s.id + '">' + UI.icon("trash") + "Delete</button>"
            ];
          }), "No schedules yet. Use Schedule on any action or recommendation, or create one here.");

        var inst = data.installation || { protected: true };
        var install = UI.installCallout(inst);
        el.innerHTML = UI.pageHeader("Schedules", "Registered in Windows Task Scheduler › WindowsMaintenanceManager",
          UI.hint("Schedules are Windows tasks that run as SYSTEM, even when nobody is signed in and the console is closed. " +
            "Actions that are not safe create a restore point first.") +
          UI.button("New schedule", 'id="new-schedule"', "btn-primary", "clock")) + install + kpis +
          '<div class="grid grid-2-1">' + UI.card("Scheduled actions", table) +
          UI.card("Schedules by area", '<div class="chart-row">' + Charts.donut(byArea, { center: list.length, sub: "schedules", empty: "No schedules" }) + Charts.legend(byArea) + "</div>" +
            '<div class="callout">' + UI.icon("info") + "<div>Scheduled runs use the SYSTEM account, so they work when nobody is signed in. Actions that are not safe always create a restore point first.</div></div>") + "</div>" +
          '<div class="grid">' + UI.card("Scheduled scripts", scriptsTable(scriptList),
            '<span class="muted small">' + scriptList.filter(function (s) { return s.schedule; }).length + " of " + scriptList.length + " scripts</span>" +
            '<a class="btn btn-sm" href="#/scripts">' + UI.icon("scripts") + "Scripts</a>", "card-flush") + "</div>";

        el.querySelector("#new-schedule").addEventListener("click", function () {
          UI.modal("New schedule", '<p class="modal-text">What should run at the scheduled time?</p>',
            [{ label: "Cancel", cls: "btn-ghost" }, { label: "A script", cls: "", value: function () { return "script"; } },
              { label: "A maintenance action", cls: "btn-primary", value: function () { return "action"; } }]).then(function (what) {
            if (what === "action") pickAction(App).then(function (id) { if (id) App.schedule(id).then(rerender); });
            if (what === "script") pickScript(scriptList).then(function (s) { if (s) scheduleScript(s, rerender); });
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
