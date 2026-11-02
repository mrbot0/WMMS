/* Updates & Drivers: pending Windows updates, update history, problem devices and driver age. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var SEVERITY = { Critical: "error", Important: "warning", Moderate: "info", Low: "info" };

  window.Pages.updates = {
    title: "Updates & Drivers",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/updates").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "updates");
        var pending = d.pending || [], drivers = d.drivers || [], devices = d.problem_devices || [];
        var severe = pending.filter(function (u) { return u.severity === "Critical" || u.severity === "Important"; }).length;
        var size = pending.reduce(function (a, u) { return a + (u.size_mb || 0); }, 0);
        var old = drivers.filter(function (x) { return x.age_days > 1095; }).length;
        App.setSubtitle("Windows Update, device health and driver age");

        var kpis = '<div class="grid grid-5">' +
          UI.kpi("Updates score", Components.num(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Pending updates", Components.num(pending.length), d.search_ok === false ? "Windows Update not reachable" : size ? Math.round(size) + " MB to download" : "Up to date", pending.length ? "warning" : "ok") +
          UI.kpi("Critical / important", Components.num(severe), "Security updates waiting", severe ? "error" : "ok") +
          UI.kpi("Devices with errors", Components.num(devices.length), "Reported by Device Manager", devices.length ? "error" : "ok") +
          UI.kpi("Drivers older than 3 years", Components.num(old) + " <small>/ " + drivers.length + "</small>", "Third-party drivers", old ? "warning" : "ok") + "</div>";

        var buckets = [["< 1 year", 0, 365], ["1-3 years", 365, 1095], ["3-5 years", 1095, 1825], ["> 5 years", 1825, 1e9]].map(function (b, i) {
          return { label: b[0], value: drivers.filter(function (x) { return x.age_days != null && x.age_days >= b[1] && x.age_days < b[2]; }).length, color: ["#107C41", "#0F6CBD", "#C27C0E", "#C42B1C"][i] };
        });
        var providers = {};
        drivers.forEach(function (x) { providers[x.provider] = (providers[x.provider] || 0) + 1; });
        var provSeries = Object.keys(providers).sort(function (a, b) { return providers[b] - providers[a]; }).slice(0, 6).map(function (p, i) { return { label: p, value: providers[p], color: Charts.PALETTE[i] }; });

        var history = UI.table([{ title: "Update" }, { title: "Date" }, { title: "Result" }], (d.history || []).map(function (h) {
          var tone = h.result === "succeeded" ? "ok" : h.result === "failed" || h.result === "aborted" ? "error" : "warning";
          return ['<span class="cell-title">' + esc(h.title) + "</span>", esc(UI.formatDate(h.date)), '<span class="badge badge-status-' + tone + '">' + esc(h.result) + "</span>"];
        }), "No update history available.");
        var deviceTable = UI.table([{ title: "Device" }, { title: "Class" }, { title: "Error code", cls: "num" }], devices.map(function (x) {
          return ['<span class="cell-title">' + esc(x.name) + "</span>", esc(x.class || "—"), '<span class="badge badge-status-error">' + esc(x.code) + "</span>"];
        }), "All devices work correctly.");

        el.innerHTML = parts.header + parts.errors + kpis +
          '<div class="grid">' + UI.card("Pending updates", '<div id="pending-table"></div>',
            '<button class="btn btn-sm" data-run="updates.scan">' + UI.icon("refresh") + 'Check now</button><button class="btn btn-sm btn-primary" data-run="updates.install">' + UI.icon("download") + "Install all</button>", "card-flush") + "</div>" +
          '<div class="grid grid-3">' + UI.card("Driver age", Charts.bars(buckets, { title: "Third-party drivers by age" })) +
          UI.card("Driver providers", '<div class="chart-row">' + Charts.donut(provSeries, { center: drivers.length, sub: "drivers", empty: "No drivers" }) + Charts.legend(provSeries) + "</div>") +
          UI.card("Score", parts.score) + "</div>" +
          '<div class="grid grid-2">' + UI.card("Devices with errors", deviceTable, "", "card-flush") + UI.card("Recent update history", history, "", "card-flush") + "</div>" +
          '<div class="grid">' + UI.card("Third-party drivers", '<div id="drivers-table"></div>', "", "card-flush") + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" + '<div class="grid">' + parts.actions + "</div>" +
          '<div class="grid grid-2">' + parts.trend + parts.runs + "</div>";

        Components.dataTable(el.querySelector("#pending-table"), {
          rows: pending, exportName: "wmm-pending-updates", placeholder: "Search updates…", pageSize: 8, empty: d.search_ok === false ? "Windows Update could not be searched." : "No pending updates.",
          columns: [
            { key: "title", title: "Update", render: function (r) { return '<span class="cell-title">' + esc(r.title) + '</span><div class="cell-sub">' + esc((r.categories || []).join(", ")) + "</div>"; } },
            { key: "kb", title: "KB", render: function (r) { return r.kb ? '<span class="cell-mono">KB' + esc(r.kb) + "</span>" : "—"; } },
            { key: "severity", title: "Severity", render: function (r) { return r.severity ? '<span class="badge badge-status-' + (SEVERITY[r.severity] || "info") + '">' + esc(r.severity) + "</span>" : '<span class="badge">Unrated</span>'; } },
            { key: "size_mb", title: "Size", cls: "num", render: function (r) { return r.size_mb ? esc(r.size_mb) + " MB" : "—"; } }
          ]
        });
        Components.dataTable(el.querySelector("#drivers-table"), {
          rows: drivers, exportName: "wmm-drivers", placeholder: "Search devices or providers…", sort: "age_days", desc: true, pageSize: 10,
          columns: [
            { key: "name", title: "Device", render: function (r) { return '<span class="cell-title">' + esc(r.name) + '</span><div class="cell-sub">' + esc(r.class || "") + "</div>"; } },
            { key: "provider", title: "Provider" },
            { key: "version", title: "Version", render: function (r) { return '<span class="cell-mono">' + esc(r.version) + "</span>"; } },
            { key: "date", title: "Date" },
            { key: "age_days", title: "Age", cls: "num", render: function (r) {
              if (r.age_days == null) return "—";
              var y = r.age_days / 365;
              return '<span class="badge badge-status-' + (y > 5 ? "error" : y > 3 ? "warning" : "ok") + '">' + (y >= 1 ? y.toFixed(1) + " years" : r.age_days + " days") + "</span>";
            } }
          ]
        });
        UI.bindArea(el, "updates", function () { self.render(el, App); });
      });
    }
  };
})();
