/* Cleanup: recoverable space by category, drives and space freed over time. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var DAY = 86400e3;

  window.Pages.cleanup = {
    title: "Cleanup",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/cleanup").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "cleanup");
        var cats = (d.categories || []).slice().sort(function (a, b) { return b.bytes - a.bytes; });
        var c = (d.volumes || []).filter(function (x) { return x.letter === "C"; })[0] || (d.volumes || [])[0] || {};
        var cFree = c.total_gb ? Math.round(100 * c.free_gb / c.total_gb) : null;
        var recent = v.runs.filter(function (r) { return Date.now() - new Date(r.started).getTime() < 30 * DAY; });
        var freed = recent.reduce(function (a, r) { return a + (r.bytes_freed || 0); }, 0);
        var files = cats.reduce(function (a, x) { return a + (x.files || 0); }, 0);
        // What C: would have free if everything recoverable were cleaned (most caches live on C:).
        var after = c.total_gb ? Math.min(100, Math.round(100 * (c.free_gb + (d.recoverable_bytes || 0) / 1073741824) / c.total_gb)) : null;
        App.setSubtitle("Recoverable space and storage health");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Cleanup score", String(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Recoverable", esc(UI.formatBytes(d.recoverable_bytes)), files.toLocaleString() + " files in " + cats.filter(function (x) { return x.bytes; }).length + " categories", d.recoverable_bytes > 2 * 1073741824 ? "warning" : "info") +
          UI.kpi("Free on C:", c.free_gb != null ? esc(c.free_gb) + " <small>GB</small>" : "—", cFree != null ? cFree + "% free" + (after != null && after > cFree ? " · " + after + "% after cleanup" : "") : "",
            cFree == null ? "" : cFree < 15 ? "error" : cFree < 25 ? "warning" : "ok") +
          UI.kpi("Freed in 30 days", esc(UI.formatBytes(freed)), recent.length + " cleanup run(s)", "info") + "</div>";

        var byCategory = Charts.hbars(cats.map(function (x) { return { label: x.name, value: x.bytes }; }),
          { format: UI.formatBytes, title: "Recoverable space by category" });
        var drives = (d.volumes || []).map(function (x) {
          var used = Math.round((x.total_gb - x.free_gb) * 10) / 10, p = x.total_gb ? Math.round(100 * used / x.total_gb) : 0;
          return "<li><span class=\"legend-label\"><strong>" + esc(x.letter) + ':</strong> ' + esc(x.health || "") + '</span><div class="bar-inline" style="flex:1.4"><div style="width:' + p +
            "%;background:" + (100 - p < 15 ? "#C42B1C" : 100 - p < 25 ? "#C27C0E" : "#0F6CBD") + '"></div></div><span class="legend-value">' + esc(x.free_gb) + " / " + esc(x.total_gb) + " GB free</span></li>";
        }).join("");
        var cSeries = c.total_gb ? [{ label: "Used", value: Math.round((c.total_gb - c.free_gb) * 10) / 10, color: "#0F6CBD" },
          { label: "Recoverable", value: Math.round(d.recoverable_bytes / 1073741824 * 10) / 10, color: "#C27C0E" },
          { label: "Free", value: c.free_gb, color: "#9CC5EA" }] : [];
        if (cSeries.length) cSeries[0].value = Math.max(0, Math.round((cSeries[0].value - cSeries[1].value) * 10) / 10);
        var gb = function (x) { return x + " GB"; };
        var storage = cSeries.length ? '<div class="chart-row">' + Charts.donut(cSeries, { center: (100 - cFree) + "%", sub: "used on C:", format: gb }) +
          Charts.legend(cSeries, { format: gb }) + "</div>" : Charts.empty("No volume data");
        storage += drives ? '<ul class="legend" style="margin-top:14px">' + drives + "</ul>" : "";

        var freedRuns = v.runs.filter(function (r) { return r.status === "ok"; }).slice(0, 12).reverse();
        var freedChart = Charts.bars(freedRuns.map(function (r) {
          return { label: new Date(r.started).toLocaleDateString(undefined, { day: "2-digit", month: "short" }), value: r.bytes_freed || 0, color: "#2E9D8F" };
        }), { format: UI.formatBytes, empty: "No cleanup run yet", title: "Space freed per run" });

        el.innerHTML = parts.header + parts.errors + kpis +
          '<div class="grid grid-2-1">' + UI.card("Recoverable space by category", byCategory) + UI.card("Storage", storage) + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" + '<div class="grid">' + parts.actions + "</div>" +
          '<div class="grid grid-3">' + UI.card("Space freed per run", freedChart) + parts.trend + UI.card("Score", parts.score) + "</div>" +
          '<div class="grid">' + parts.runs + "</div>";
        UI.bindArea(el, "cleanup", function () { self.render(el, App); });
      });
    }
  };
})();
