/* Storage: drives, largest folders and files, caches, Windows.old and restore point storage. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  window.Pages.storage = {
    title: "Storage",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/storage").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "storage");
        var cats = d.categories || [];
        var caches = cats.reduce(function (a, c) { return a + (c.bytes || 0); }, 0);
        var shadow = (d.shadow || []).reduce(function (a, s) { return a + (s.used_gb || 0); }, 0);
        var used = (d.volumes || []).reduce(function (a, x) { return a + (x.total_gb - x.free_gb); }, 0);
        var total = (d.volumes || []).reduce(function (a, x) { return a + x.total_gb; }, 0);
        App.setSubtitle("Where the space goes and how to get it back");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Storage score", Components.num(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Used across drives", Components.num(Math.round(used)) + " <small>/ " + Math.round(total) + " GB</small>", (d.volumes || []).length + " volume(s)", total && used / total > 0.85 ? "warning" : "info") +
          UI.kpi("Caches and reports", esc(UI.formatBytes(caches)), "Browsers, error reports, thumbnails", caches > 1073741824 ? "warning" : "info") +
          UI.kpi("Windows.old / restore points", esc(UI.formatBytes(d.windows_old_bytes || 0)) + " <small>/ " + shadow.toFixed(1) + " GB</small>",
            d.storage_sense ? "Storage Sense on" : d.storage_sense === false ? "Storage Sense off" : "Storage Sense unknown", d.windows_old_bytes ? "warning" : "info") + "</div>";

        var drives = UI.table([{ title: "Drive" }, { title: "Health" }, { title: "Used" }, { title: "Free", cls: "num" }, { title: "Size", cls: "num" }],
          (d.volumes || []).map(function (x) {
            var p = x.total_gb ? Math.round(100 * (x.total_gb - x.free_gb) / x.total_gb) : 0;
            return ['<span class="cell-title">' + esc(x.letter) + ":</span>", UI.statusBadge(x.health === "Healthy" ? "ok" : "error").replace(/>[^<]*</, ">" + esc(x.health || "Unknown") + "<"),
              '<div style="display:flex;gap:8px;align-items:center"><div class="bar-inline" style="flex:1"><div style="width:' + p + "%;background:" + (p > 85 ? "#C42B1C" : p > 75 ? "#C27C0E" : "#0F6CBD") + '"></div></div>' + p + "%</div>",
              esc(x.free_gb) + " GB", esc(x.total_gb) + " GB"];
          }), "No volume information.");
        var disks = UI.table([{ title: "Physical disk" }, { title: "Type" }, { title: "Health" }, { title: "Wear", cls: "num" }, { title: "Temp.", cls: "num" }],
          (d.disks || []).map(function (x) {
            return ['<span class="cell-title">' + esc(x.name) + "</span>", esc(x.media), UI.statusBadge(x.health === "Healthy" ? "ok" : "error").replace(/>[^<]*</, ">" + esc(x.health || "Unknown") + "<"),
              x.wear != null ? esc(x.wear) + "%" : "—", x.temperature != null ? esc(x.temperature) + " °C" : "—"];
          }), "No disk information.");

        var folders = (d.folders || []).filter(function (f) { return f.bytes > 0; });
        var folderChart = Charts.hbars(folders.slice(0, 10).map(function (f, i) { return { label: f.name, value: f.bytes, color: Charts.PALETTE[i % Charts.PALETTE.length] }; }),
          { format: UI.formatBytes, empty: "No folder data" }) + (d.profile_complete === false ? '<p class="muted small">The profile is very large: sizes are a minimum.</p>' : "");
        var catChart = Charts.hbars(cats.map(function (c) { return { label: c.name, value: c.bytes }; }), { format: UI.formatBytes });

        var shadowTable = UI.table([{ title: "Volume" }, { title: "Used", cls: "num" }, { title: "Allocated", cls: "num" }, { title: "Maximum", cls: "num" }],
          (d.shadow || []).map(function (s) { return [esc(s.volume || "?") + ":", esc(s.used_gb) + " GB", esc(s.allocated_gb) + " GB", esc(s.max_gb) + " GB"]; }),
          "No restore point storage reported (run as administrator to read it).");

        el.innerHTML = parts.header + parts.errors + kpis +
          '<div class="grid grid-2">' + UI.card("Volumes", drives, "", "card-flush") + UI.card("Physical disks", disks, "", "card-flush") + "</div>" +
          '<div class="grid grid-2">' + UI.card("Largest folders in the user profile", folderChart) + UI.card("Caches and reports", catChart) + "</div>" +
          '<div class="grid">' + UI.card("Largest files in the user profile", '<div id="big-files"></div>', "", "card-flush") + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" + '<div class="grid">' + parts.actions + "</div>" +
          '<div class="grid grid-3">' + UI.card("Restore point storage", shadowTable, "", "card-flush") + parts.trend + UI.card("Score", parts.score) + "</div>" +
          '<div class="grid">' + parts.runs + "</div>";
        Components.dataTable(el.querySelector("#big-files"), {
          rows: d.files || [], exportName: "wmm-largest-files", placeholder: "Search files…", pageSize: 10, sort: "bytes", desc: true,
          columns: [
            { key: "name", title: "File", value: function (r) { return r.path.split("\\").pop(); }, render: function (r) { return '<span class="cell-title">' + esc(r.path.split("\\").pop()) + "</span>"; } },
            { key: "path", title: "Folder", value: function (r) { return r.path.slice(0, r.path.lastIndexOf("\\")); },
              render: function (r) { return '<span class="cell-mono">' + esc(r.path.slice(0, r.path.lastIndexOf("\\"))) + "</span>"; } },
            { key: "bytes", title: "Size", cls: "num", render: function (r) { return esc(UI.formatBytes(r.bytes)); } }
          ]
        });
        UI.bindArea(el, "storage", function () { self.render(el, App); });
      });
    }
  };
})();
