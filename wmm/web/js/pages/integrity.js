/* System Integrity: disks, stability events, security posture and repair checks. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var CHECKS = [["integrity.dism", "Windows image (DISM)"], ["integrity.sfc", "System files (SFC)"], ["integrity.disk_scan", "Online disk check (CHKDSK)"],
    ["integrity.trim", "SSD TRIM"], ["integrity.disk_repair", "Disk repair at reboot"]];

  window.Pages.integrity = {
    title: "System Integrity",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/integrity").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "integrity");
        var disks = d.disks || [], st = d.stability || {}, sec = d.security || {};
        var healthy = disks.filter(function (x) { return x.health === "Healthy"; }).length;
        var events = (st.unexpected_shutdowns || 0) + (st.whea || 0) + (st.disk_errors || 0);
        var age = d.bios_age_days;
        App.setSubtitle("Disk health, stability, security and Windows repair checks");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Integrity score", String(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Healthy disks", healthy + " <small>of " + disks.length + "</small>", disks.length ? disks.map(function (x) { return x.media; }).join(", ") : "No disk data", healthy === disks.length ? "ok" : "error") +
          UI.kpi("Critical events", String(events), "Last 30 days" + (d.reboot_pending ? " · restart pending" : ""), events ? (st.whea ? "error" : "warning") : "ok") +
          UI.kpi("Firmware age", age != null ? (age >= 365 ? (age / 365).toFixed(1) + " <small>years</small>" : age + " <small>days</small>") : "—", esc(d.bios || "") + (d.bios_date ? " · " + esc(d.bios_date) : ""), age > 730 ? "warning" : "ok") +
          "</div>";

        var diskTable = UI.table(
          [{ title: "Disk" }, { title: "Type" }, { title: "Health" }, { title: "Temperature", cls: "num" }, { title: "Wear" }, { title: "Power-on hours", cls: "num" }, { title: "Read errors", cls: "num" }],
          disks.map(function (x) {
            var wear = x.wear != null ? '<div style="display:flex;gap:8px;align-items:center"><div class="bar-inline" style="flex:1"><div style="width:' + Math.min(100, x.wear) + "%;background:" +
              (x.wear >= 80 ? "#C42B1C" : x.wear >= 50 ? "#C27C0E" : "#107C41") + '"></div></div>' + x.wear + "%</div>" : "—";
            return ['<span class="cell-title">' + esc(x.name) + "</span>", esc(x.media), UI.statusBadge(x.health === "Healthy" ? "ok" : "error").replace(/>[^<]*</, ">" + esc(x.health || "Unknown") + "<"),
              x.temperature != null ? esc(x.temperature) + " °C" : "—", wear, x.power_on_hours != null ? Number(x.power_on_hours).toLocaleString() : "—",
              x.read_errors != null ? esc(x.read_errors) : "—"];
          }), "No disk information. Run the console as administrator for SMART data.");

        var stability = Charts.hbars([
          { label: "Unexpected shutdowns", value: st.unexpected_shutdowns || 0, color: "#C27C0E" },
          { label: "WHEA hardware errors", value: st.whea || 0, color: "#C42B1C" },
          { label: "Disk errors", value: st.disk_errors || 0, color: "#8764B8" },
          { label: "Crash dumps", value: st.dumps || 0, color: "#5C7080" }
        ], { title: "Stability events in the last 30 days" }) + '<p class="muted small">Source: Windows System event log, last 30 days.</p>';

        var security = '<ul class="check-list">' + [
          ["Microsoft Defender real-time protection", sec.defender === true ? "ok" : sec.defender === false ? "error" : "skipped", sec.defender === true ? "On" : sec.defender === false ? "Off" : "Unknown"],
          ["Antivirus signatures", (sec.signature_age_days || 0) > 7 ? "warning" : "ok", sec.signature_age_days != null ? sec.signature_age_days + " days old" : "Unknown"],
          ["Windows Firewall", sec.firewall_off ? "error" : "ok", sec.firewall_off ? "Off on a profile" : "On"],
          ["BitLocker on C:", sec.bitlocker === "On" ? "ok" : "skipped", sec.bitlocker || "Not read"],
          ["Pending restart", d.reboot_pending ? "warning" : "ok", d.reboot_pending ? "Yes" : "No"]
        ].map(function (row) {
          return '<li><span class="grow">' + esc(row[0]) + '</span><span class="badge badge-status-' + row[1] + '">' + esc(row[2]) + "</span></li>";
        }).join("") + "</ul>";

        var checks = '<ul class="check-list">' + CHECKS.map(function (c) {
          var r = (d.checks || {})[c[0]];
          return '<li><span class="grow"><span class="cell-title">' + esc(c[1]) + '</span><br><span class="cell-sub">' +
            (r ? "Last run " + esc(UI.formatDate(r.finished || r.started)) + (r.note ? " · " + esc(r.note) : "") : "Never run from this console") + "</span></span>" +
            (r ? UI.statusBadge(r.status) : '<span class="badge">Not run</span>') + '<button class="btn btn-sm" data-run="' + c[0] + '">' + UI.icon("play") + "Run</button></li>";
        }).join("") + "</ul>";

        var events = UI.table([{ title: "Source" }, { title: "Log" }, { title: "Errors", cls: "num" }, { title: "Last" }, { title: "Latest message" }],
          ((d.events || {}).top || []).map(function (x) {
            return ['<span class="cell-title">' + esc(x.source) + "</span>", esc(x.log), '<span class="badge badge-status-' + (x.count > 50 ? "error" : "warning") + '">' + esc(x.count) + "</span>",
              esc(UI.formatDate(x.last)), '<span class="cell-sub">' + esc(x.message) + "</span>"];
          }), "No errors in the System and Application logs in the last 7 days.");
        var updates = (d.updates || []).length ? '<ul class="check-list">' + d.updates.map(function (u) { return "<li>" + esc(u) + "</li>"; }).join("") + "</ul>" : '<p class="empty">No update information.</p>';

        el.innerHTML = parts.header + parts.errors + kpis +
          '<div class="grid">' + UI.card("Disks", diskTable) + "</div>" +
          '<div class="grid grid-3">' + UI.card("Stability · 30 days", stability) + UI.card("Security", security) + UI.card("Repair checks", checks) + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" + '<div class="grid">' + parts.actions + "</div>" +
          '<div class="grid">' + UI.card("Event log · errors in the last 7 days", events, '<span class="muted small">' + ((d.events || {}).total || 0) + " errors</span>", "card-flush") + "</div>" +
          '<div class="grid grid-3">' + parts.trend + UI.card("Score", parts.score) + UI.card("Latest updates", updates) + "</div>" +
          '<div class="grid">' + parts.runs + "</div>";
        UI.bindArea(el, "integrity", function () { self.render(el, App); });
      });
    }
  };
})();
