/* Services: start types, managed non-essential services, backup and startup programs. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var GROUPS = { safe: "Non-essential", manual: "Vendor utilities", xbox: "Xbox & gaming", print: "Printing & scanning" };
  var START = { "auto": "Automatic", "delayed-auto": "Automatic (delayed)", demand: "Manual", disabled: "Disabled", boot: "Boot", system: "System" };

  window.Pages.services = {
    title: "Services",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/services").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "services"), t = d.totals || {};
        var managed = d.managed || [];
        var enabledSafe = managed.filter(function (s) { return s.group === "safe" && s.start !== "disabled"; }).length;
        App.setSubtitle("Windows services and startup programs");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Services score", String(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Running services", String(t.running || 0), "of " + (t.total || 0) + " installed", "info") +
          UI.kpi("Non-essential enabled", String(enabledSafe), "Telemetry, maps, demo and similar", enabledSafe ? "warning" : "ok") +
          UI.kpi("Startup programs", String((d.startup || []).length), (d.backup_count || 0) + " service(s) in the restore backup", (d.startup || []).length > 15 ? "warning" : "ok") +
          "</div>";

        var startSeries = [
          { label: "Automatic", value: t.auto || 0, color: "#0F6CBD" },
          { label: "Manual", value: t.manual || 0, color: "#2E9D8F" },
          { label: "Disabled", value: t.disabled || 0, color: "#8A8886" }
        ];
        var other = (t.total || 0) - startSeries.reduce(function (a, s) { return a + s.value; }, 0);
        if (other > 0) startSeries.push({ label: "Boot / system", value: other, color: "#8764B8" });
        var startTypes = '<div class="chart-row">' + Charts.donut(startSeries, { center: t.total || 0, sub: "services" }) + Charts.legend(startSeries) + "</div>";
        var stateSeries = [{ label: "Running", value: t.running || 0, color: "#107C41" }, { label: "Stopped", value: t.stopped || 0, color: "#C8CDD2" }];
        var states = '<div class="chart-row">' + Charts.donut(stateSeries, { center: t.running || 0, sub: "running" }) + Charts.legend(stateSeries) + "</div>";

        var groups = Object.keys(GROUPS).map(function (g) {
          var list = managed.filter(function (s) { return s.group === g; });
          return { label: GROUPS[g], value: list.filter(function (s) { return s.start !== "disabled"; }).length };
        });
        var groupChart = Charts.hbars(groups, { title: "Managed services still enabled by group" });

        var table = UI.table([{ title: "Service" }, { title: "Group" }, { title: "Start type" }, { title: "State" }],
          managed.map(function (s) {
            return ['<span class="cell-title">' + esc(s.name) + "</span>", esc(GROUPS[s.group] || s.group), esc(START[s.start] || s.start),
              s.running ? UI.statusBadge("ok").replace(/>[^<]*</, ">Running<") : '<span class="badge">Stopped</span>'];
          }), "None of the managed services is installed on this PC.");

        var startup = (d.startup || []).length
          ? '<div class="tag-list">' + d.startup.map(function (n) { return '<span class="badge">' + esc(n) + "</span>"; }).join("") + "</div>" +
            '<p class="muted small" style="margin-top:12px">Disable the ones you do not need in Task Manager › Startup apps.</p>'
          : '<p class="empty">No startup programs found.</p>';
        var backup = '<p class="muted" style="margin-top:0">' + (d.backup_count ? d.backup_count + " service(s) changed by this suite can be restored to their original start type." :
          "No service has been changed by this suite yet.") + ' <span class="muted small">' + (d.protected_present || 0) + " protected services (Defender, Windows Update, networking, audio…) are never modified.</span></p>" +
          (d.backup_count ? '<button class="btn" data-run="services.restore">' + UI.icon("refresh") + "Restore modified services</button>" : "");

        el.innerHTML = parts.header + parts.errors + kpis +
          '<div class="grid grid-3">' + UI.card("Start types", startTypes) + UI.card("Service state", states) + UI.card("Enabled by group", groupChart) + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" + '<div class="grid">' + parts.actions + "</div>" +
          '<div class="grid grid-2">' + UI.card("Managed services", table) + '<div class="grid" style="margin:0">' + UI.card("Restore backup", backup) + UI.card("Startup programs", startup) + "</div></div>" +
          '<div class="grid">' + UI.card("All services", '<div id="all-services"></div>', '<span class="muted small">' + (d.all || []).length + " installed</span>", "card-flush") + "</div>" +
          '<div class="grid grid-2">' + parts.trend + parts.runs + "</div>";
        Components.dataTable(el.querySelector("#all-services"), {
          rows: d.all || [], exportName: "wmm-services", placeholder: "Search services…", sort: "display",
          filters: [{ key: "state", label: "All states", options: [["Running", "Running"], ["Stopped", "Stopped"]] },
            { key: "start", label: "All start types", options: Object.keys(START).map(function (k) { return [k, START[k]]; }) }],
          columns: [
            { key: "display", title: "Service", render: function (r) { return '<div class="cell-title">' + esc(r.display) + '</div><div class="cell-mono">' + esc(r.name) + "</div>"; } },
            { key: "start", title: "Start type", value: function (r) { return START[r.start] || r.start; } },
            { key: "state", title: "State", render: function (r) { return r.state === "Running" ? '<span class="badge badge-status-ok">Running</span>' : '<span class="badge">' + esc(r.state) + "</span>"; } },
            { key: "protected", title: "Protected", value: function (r) { return r.protected ? "Yes" : ""; },
              render: function (r) { return r.protected ? '<span class="badge badge-status-info">' + UI.icon("shield") + "Never modified</span>" : ""; } }
          ]
        });
        UI.bindArea(el, "services", function () { self.render(el, App); });
      });
    }
  };
})();
