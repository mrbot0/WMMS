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
      return API.get("/schedules").then(function (data) {
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
        var install = inst.protected ? "" :
          '<div class="callout callout-warning">' + UI.icon("shield") + "<div><strong>Install the suite to enable schedules.</strong> " +
          "Scheduled actions run as SYSTEM, so the program and Python must not be writable by standard users. This copy is not protected (" +
          esc(inst.writable.join(", ")) + "). Run this command once in an administrator prompt, then start the console from " +
          "<code>C:\\Program Files\\WindowsMaintenanceManager\\start_wmm.bat</code>:" +
          '<pre class="log" style="min-height:0;margin-top:8px">' + esc(inst.command) + "</pre>" +
          "If Python itself is listed, install Python for all users first.</div></div>";
        el.innerHTML = UI.pageHeader("Schedules", "Registered in Windows Task Scheduler › WindowsMaintenanceManager",
          UI.button("New schedule", 'id="new-schedule"', "btn-primary", "clock")) + install + kpis +
          '<div class="grid grid-2-1">' + UI.card("Scheduled actions", table) +
          UI.card("Schedules by area", '<div class="chart-row">' + Charts.donut(byArea, { center: list.length, sub: "schedules", empty: "No schedules" }) + Charts.legend(byArea) + "</div>" +
            '<div class="callout">' + UI.icon("info") + "<div>Scheduled runs use the SYSTEM account, so they work when nobody is signed in. Actions that are not safe always create a restore point first.</div></div>") + "</div>";

        el.querySelector("#new-schedule").addEventListener("click", function () {
          pickAction(App).then(function (id) { if (id) App.schedule(id).then(rerender); });
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
