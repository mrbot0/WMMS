/* Security: posture checklist, Microsoft Defender, BitLocker, accounts and restore points. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  function onOff(value, good) {
    if (value == null) return ["skipped", "Unknown"];
    return value === good ? ["ok", value ? "On" : "Off"] : ["error", value ? "On" : "Off"];
  }

  window.Pages.security = {
    title: "Security",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/security").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "security"), def = d.defender || {};
        var fwOff = (d.firewall || []).filter(function (f) { return !f.enabled; });
        var c = (d.bitlocker || []).filter(function (b) { return String(b.mount).toUpperCase().indexOf("C") === 0; })[0];
        var lastPoint = (d.restore_points || [])[0];
        App.setSubtitle("Protection, hardening and recovery readiness");

        var checks = [
          ["Real-time protection", onOff(def.realtime, true)], ["Firewall (all profiles)", fwOff.length ? ["error", "Off: " + fwOff.map(function (f) { return f.name; }).join(", ")] : (d.firewall || []).length ? ["ok", "On"] : ["skipped", "Unknown"]],
          ["User Account Control", onOff(d.uac && d.uac.enabled, true)], ["SmartScreen", d.smartscreen == null ? ["skipped", "Unknown"] : d.smartscreen === "Off" ? ["error", "Off"] : ["ok", String(d.smartscreen)]],
          ["Secure Boot", onOff(d.secure_boot, true)], ["TPM", d.tpm == null ? ["skipped", "Unknown"] : d.tpm.present ? (d.tpm.ready ? ["ok", "Ready"] : ["warning", "Present, not ready"]) : ["error", "Not found"]],
          ["BitLocker on C:", c ? (c.protection === "On" ? ["ok", "Protected"] : ["warning", "Not protected"]) : ["skipped", "Unknown"]],
          ["SMBv1 protocol", d.smb1 == null ? ["skipped", "Unknown"] : d.smb1 ? ["error", "Enabled"] : ["ok", "Disabled"]],
          ["Remote Desktop", d.rdp_enabled == null ? ["skipped", "Unknown"] : d.rdp_enabled ? ["warning", "Enabled"] : ["ok", "Disabled"]],
          ["Guest account", d.guest_enabled == null ? ["skipped", "Unknown"] : d.guest_enabled ? ["error", "Enabled"] : ["ok", "Disabled"]]
        ];
        var passed = checks.filter(function (x) { return x[1][0] === "ok"; }).length;
        var known = checks.filter(function (x) { return x[1][0] !== "skipped"; }).length;

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Security score", Components.num(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Controls passed", Components.num(passed) + " <small>/ " + known + "</small>", (checks.length - known) + " not readable", passed === known ? "ok" : "warning") +
          UI.kpi("Signatures", def.signature_age_days != null ? Components.num(def.signature_age_days) + " <small>days old</small>" : "—",
            def.quick_scan_age_days != null ? "Last quick scan " + def.quick_scan_age_days + " days ago" : "No scan recorded", UI.toneOf(def.signature_age_days, 2, 4, true)) +
          UI.kpi("Restore points", Components.num((d.restore_points || []).length), lastPoint ? "Latest " + UI.relative(lastPoint.created) : "None available", lastPoint ? "info" : "warning") + "</div>";

        var posture = UI.checklist(checks.map(function (x) { return [x[0], x[1][0], x[1][1]]; }));
        var passChart = '<div class="chart-row">' + Charts.donut([
          { label: "Passed", value: passed, color: "#107C41" }, { label: "Issues", value: known - passed, color: "#C42B1C" }, { label: "Unknown", value: checks.length - known, color: "#B4BCC6" }
        ], { center: known ? Math.round(100 * passed / known) + "%" : "–", sub: "passed" }) + Charts.legend([
          { label: "Passed", value: passed, color: "#107C41" }, { label: "Issues", value: known - passed, color: "#C42B1C" }, { label: "Unknown", value: checks.length - known, color: "#B4BCC6" }
        ]) + "</div>";

        var defender = UI.definition([
          ["Real-time protection", def.realtime == null ? "Unknown" : def.realtime ? "On" : "Off"], ["Antivirus", def.antivirus == null ? "Unknown" : def.antivirus ? "Enabled" : "Disabled"],
          ["Signature age", def.signature_age_days != null ? esc(def.signature_age_days) + " days" : null], ["Quick scan", def.quick_scan_age_days != null ? esc(def.quick_scan_age_days) + " days ago" : null],
          ["Full scan", def.full_scan_age_days != null && def.full_scan_age_days < 4000 ? esc(def.full_scan_age_days) + " days ago" : "Never"], ["Tamper protection", def.tamper == null ? "Unknown" : def.tamper ? "On" : "Off"],
          ["Engine", esc(def.engine || "")], ["Mode", esc(def.mode || "")]
        ]) + '<div class="page-actions" style="margin-top:14px"><button class="btn btn-sm btn-primary" data-run="security.quick_scan">' + UI.icon("play") + "Quick scan</button>" +
          '<button class="btn btn-sm" data-run="security.update_signatures">' + UI.icon("download") + "Update signatures</button></div>";

        var bitlocker = UI.table([{ title: "Volume" }, { title: "Protection" }, { title: "Encrypted", cls: "num" }],
          (d.bitlocker || []).map(function (b) {
            return [esc(b.mount), b.protection === "On" ? '<span class="badge badge-status-ok">On</span>' : '<span class="badge badge-status-warning">' + esc(b.protection || "Off") + "</span>",
              b.encrypted != null ? esc(b.encrypted) + "%" : "—"];
          }), "BitLocker information is not available (requires administrator).");
        var admins = (d.admins || []).length ? '<ul class="check-list">' + d.admins.map(function (a) { return "<li>" + UI.statusIcon("ok") + '<span class="grow">' + esc(a) + "</span></li>"; }).join("") + "</ul>"
          : '<p class="empty">Not readable.</p>';
        var points = UI.table([{ title: "Restore point" }, { title: "Created" }, { title: "Type" }],
          (d.restore_points || []).slice(0, 8).map(function (p) { return ['<span class="cell-title">' + esc(p.description) + "</span>", esc(UI.formatDate(p.created)), esc(p.type || "")]; }),
          "No restore points (run as administrator to list them).") +
          '<div class="page-actions" style="padding:12px 18px 6px"><button class="btn btn-sm" data-run="security.restore_point">' + UI.icon("shield") + "Create restore point</button></div>";

        el.innerHTML = parts.header + parts.errors + kpis +
          '<div class="grid grid-2-1">' + UI.card("Security posture", posture) + '<div class="stack">' + UI.card("Controls", passChart) + UI.card("Score", parts.score) + "</div></div>" +
          '<div class="grid grid-2">' + UI.card("Microsoft Defender", defender) + UI.card("Restore points", points, "", "card-flush") + "</div>" +
          '<div class="grid grid-2">' + UI.card("BitLocker", bitlocker, "", "card-flush") + UI.card("Local administrators", admins) + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" + '<div class="grid">' + parts.actions + "</div>" +
          '<div class="grid grid-2">' + parts.trend + parts.runs + "</div>";
        UI.bindArea(el, "security", function () { self.render(el, App); });
      });
    }
  };
})();
