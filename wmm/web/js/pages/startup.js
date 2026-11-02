/* Startup & Apps: startup entries with on/off switches, installed applications and third-party tasks. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  window.Pages.startup = {
    title: "Startup & Apps",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/startup").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "startup");
        var items = d.items || [], apps = d.apps || [], tasks = d.tasks || [];
        var enabled = items.filter(function (i) { return i.enabled; }).length;
        var sized = apps.filter(function (a) { return a.size_mb; });
        var totalMb = sized.reduce(function (a, x) { return a + x.size_mb; }, 0);
        App.setSubtitle("What starts with Windows and what is installed");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Startup score", Components.num(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Startup programs", Components.num(enabled) + " <small>/ " + items.length + " on</small>", (items.length - enabled) + " turned off", enabled > 12 ? "warning" : enabled > 8 ? "info" : "ok") +
          UI.kpi("Installed applications", Components.num(apps.length), totalMb ? UI.formatBytes(totalMb * 1048576) + " reported size" : "", "info") +
          UI.kpi("Third-party tasks", Components.num(tasks.length), tasks.filter(function (t) { return t.state === "Ready" || t.state === "Running"; }).length + " active", tasks.length > 30 ? "warning" : "info") + "</div>";

        var publishers = {};
        apps.forEach(function (a) { var p = a.publisher || "Unknown"; publishers[p] = (publishers[p] || 0) + 1; });
        var top = Object.keys(publishers).sort(function (a, b) { return publishers[b] - publishers[a]; }).slice(0, 6);
        var others = apps.length - top.reduce(function (a, p) { return a + publishers[p]; }, 0);
        var pubSeries = top.map(function (p, i) { return { label: p, value: publishers[p], color: Charts.PALETTE[i] }; });
        if (others > 0) pubSeries.push({ label: "Others", value: others, color: "#B4BCC6" });
        var pubChart = '<div class="chart-row">' + Charts.donut(pubSeries, { center: apps.length, sub: "apps" }) + Charts.legend(pubSeries) + "</div>";

        var years = {};
        apps.forEach(function (a) { if (a.installed) { var y = a.installed.slice(0, 4); years[y] = (years[y] || 0) + 1; } });
        var yearChart = Charts.bars(Object.keys(years).sort().slice(-8).map(function (y) { return { label: y, value: years[y], color: "#2E9D8F" }; }),
          { title: "Applications installed per year", empty: "No install dates" });
        var biggest = Charts.hbars(sized.slice().sort(function (a, b) { return b.size_mb - a.size_mb; }).slice(0, 8).map(function (a, i) {
          return { label: a.name, value: a.size_mb * 1048576, color: Charts.PALETTE[i % Charts.PALETTE.length] };
        }), { format: UI.formatBytes, empty: "No size information" });

        el.innerHTML = parts.header + parts.errors + kpis +
          '<div class="grid">' + UI.card("Startup programs", '<div id="startup-table"></div>', '<span class="muted small">Same switch as Task Manager › Startup apps</span>' +
            '<button class="btn btn-sm btn-primary" data-run="startup.optimize">' + UI.icon("bolt") + "Optimize startup</button>", "card-flush") + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" +
          '<div class="grid grid-3">' + UI.card("Publishers", pubChart) + UI.card("Installs per year", yearChart) + UI.card("Largest applications", biggest) + "</div>" +
          '<div class="grid">' + UI.card("Installed applications", '<div id="apps-table"></div>', "", "card-flush") + "</div>" +
          '<div class="grid">' + UI.card("Third-party scheduled tasks", '<div id="tasks-table"></div>', "", "card-flush") + "</div>" +
          '<div class="grid grid-2">' + parts.trend + parts.runs + "</div>";

        Components.dataTable(el.querySelector("#startup-table"), {
          rows: items, exportName: "wmm-startup", placeholder: "Search startup programs…", sort: "name", pageSize: 15,
          filters: [{ key: "enabled", label: "All states", options: [["true", "On"], ["false", "Off"]] }],
          columns: [
            { key: "enabled", title: "On", sortable: false, value: function (r) { return r.enabled ? "On" : "Off"; },
              render: function (r) { return '<label class="switch" title="Turn on or off"><input type="checkbox" data-startup="' + esc(r.id) + '"' + (r.enabled ? " checked" : "") + '><span></span></label>'; } },
            { key: "name", title: "Program", render: function (r) { return '<span class="cell-title">' + esc(r.name) + "</span>"; } },
            { key: "location", title: "Location", render: function (r) { return '<span class="cell-sub">' + esc(r.location) + "</span>"; } },
            { key: "command", title: "Command", render: function (r) { return '<span class="cell-mono">' + esc(r.command) + "</span>"; } }
          ],
          after: function (box) {
            box.querySelectorAll("[data-startup]").forEach(function (input) {
              input.addEventListener("change", function () {
                input.disabled = true;
                API.post("/startup/" + input.getAttribute("data-startup") + "/toggle", { enabled: input.checked }).then(function () {
                  var item = items.filter(function (i) { return i.id === input.getAttribute("data-startup"); })[0];
                  if (item) item.enabled = input.checked;
                  UI.toast((item ? item.name : "Entry") + (input.checked ? " will start with Windows." : " will no longer start with Windows."), "ok");
                  Components.notifications.add("Startup entry changed", (item ? item.name : "") + (input.checked ? " turned on" : " turned off"), "ok");
                  input.disabled = false;
                }, function (e) {
                  UI.toast(e.message, "error");
                  input.checked = !input.checked;
                  input.disabled = false;
                });
              });
            });
          }
        });
        Components.dataTable(el.querySelector("#apps-table"), {
          rows: apps, exportName: "wmm-installed-apps", placeholder: "Search applications or publishers…", sort: "name", pageSize: 12,
          columns: [
            { key: "name", title: "Application", render: function (r) { return '<span class="cell-title">' + esc(r.name) + "</span>"; } },
            { key: "publisher", title: "Publisher" },
            { key: "version", title: "Version", render: function (r) { return '<span class="cell-mono">' + esc(r.version || "—") + "</span>"; } },
            { key: "installed", title: "Installed", render: function (r) { return r.installed ? esc(UI.formatDate(r.installed, false)) : "—"; } },
            { key: "size_mb", title: "Size", cls: "num", render: function (r) { return r.size_mb ? esc(UI.formatBytes(r.size_mb * 1048576)) : "—"; } }
          ]
        });
        Components.dataTable(el.querySelector("#tasks-table"), {
          rows: tasks, exportName: "wmm-scheduled-tasks", placeholder: "Search tasks…", sort: "name", pageSize: 10,
          columns: [
            { key: "name", title: "Task", render: function (r) { return '<span class="cell-title">' + esc(r.name) + "</span>"; } },
            { key: "path", title: "Folder", render: function (r) { return '<span class="cell-mono">' + esc(r.path) + "</span>"; } },
            { key: "state", title: "State", render: function (r) { return '<span class="badge' + (r.state === "Disabled" ? "" : " badge-status-ok") + '">' + esc(r.state) + "</span>"; } },
            { key: "author", title: "Author" }
          ]
        });
        UI.bindArea(el, "startup", function () { self.render(el, App); });
      });
    }
  };
})();
