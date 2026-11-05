/* Standalone HTML reports with embedded SVG charts: download, print to PDF, preview. */
(function () {
  "use strict";
  var esc = UI.esc;
  var AREAS = UI.AREAS;
  var SCOPE_LABEL = { dashboard: "Executive Summary", full: "Full Maintenance", visit: "Before / After" };
  AREAS.forEach(function (a) { SCOPE_LABEL[a] = UI.AREA_LABEL[a]; });

  var CSS = [
    "*{box-sizing:border-box}body{margin:0;background:#fff;color:#1B2733;font:13px/1.5 'Segoe UI',system-ui,sans-serif}",
    ".page{max-width:980px;margin:0 auto;padding:36px 40px 48px}",
    ".head{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:3px solid #0F6CBD;padding-bottom:16px;margin-bottom:22px}",
    ".brand{display:flex;gap:12px;align-items:center}.brand svg{width:40px;height:40px}.brand b{display:block;font-size:16px}.brand span{color:#55606B}",
    "h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px;padding-bottom:6px;border-bottom:1px solid #E1E5EA}h3{font-size:14px;margin:16px 0 8px}",
    ".meta{text-align:right;color:#55606B;font-size:12px}.meta b{color:#1B2733}",
    ".scores{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;text-align:center}.scores .chart{max-width:180px;margin:0 auto}",
    ".summary{background:#F3F6FA;border-radius:8px;padding:14px 16px;margin:14px 0}",
    ".kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0}.kpi{border:1px solid #E1E5EA;border-radius:8px;padding:10px 12px}",
    ".kpi small{display:block;color:#55606B;font-size:11px;text-transform:uppercase;letter-spacing:.4px;font-weight:600}.kpi b{font-size:20px}",
    ".two{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}",
    "table{width:100%;border-collapse:collapse;font-size:12px;margin:6px 0}th{text-align:left;color:#7A8590;font-size:10.5px;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #CBD2DA;padding:6px 8px}",
    "td{border-bottom:1px solid #E9ECEF;padding:6px 8px;vertical-align:top}.num{text-align:right}",
    ".b{display:inline-block;font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:4px;background:#EEF1F4;color:#55606B}",
    ".b-ok,.b-safe{background:#E6F4EC;color:#107C41}.b-warning,.b-moderate,.b-medium{background:#FFF4DE;color:#A86400}.b-error,.b-high{background:#FDECEA;color:#C42B1C}.b-low{background:#E8F1FB;color:#0F6CBD}",
    ".legend{list-style:none;padding:0;margin:0}.legend li{display:flex;gap:8px;align-items:center;margin:4px 0}.swatch{width:10px;height:10px;border-radius:3px;display:inline-block}",
    ".legend-label{flex:1;color:#55606B}.legend-value{font-weight:600}.legend-value small{color:#7A8590;margin-left:4px}.chart-row{display:flex;gap:16px;align-items:center}.chart-row>.chart{flex:0 0 160px}",
    ".notes{white-space:pre-wrap;border-left:3px solid #0F6CBD;padding:8px 14px;background:#F7F9FB}",
    ".muted{color:#55606B}.foot{margin-top:36px;padding-top:12px;border-top:1px solid #E1E5EA;color:#7A8590;font-size:11px;display:flex;justify-content:space-between;gap:20px}",
    ".cover{min-height:88vh;display:flex;flex-direction:column;justify-content:space-between;padding:56px 8px 24px;break-after:page;border-bottom:1px solid #E1E5EA;margin-bottom:28px}",
    ".cover .company{font-size:15px;font-weight:600;color:#0F6CBD;letter-spacing:.4px;text-transform:uppercase}",
    ".cover h1{font-size:40px;line-height:1.1;margin:18px 0 8px}.cover .lead{font-size:16px;color:#55606B;max-width:620px}",
    ".cover .facts{display:grid;grid-template-columns:repeat(2,1fr);gap:14px 30px;max-width:620px;margin-top:40px}.cover .facts small{display:block;color:#7A8590;text-transform:uppercase;font-size:10.5px;letter-spacing:.5px;font-weight:600}",
    ".cover .score{display:flex;align-items:center;gap:24px;margin-top:40px}.cover .score .chart{width:220px}",
    ".up{color:#107C41;font-weight:600}.down{color:#C42B1C;font-weight:600}.same{color:#7A8590}",
    ".area-scores{display:grid;grid-template-columns:repeat(3,1fr);gap:8px 20px;margin:14px 0}.area-scores div{display:flex;justify-content:space-between;border-bottom:1px solid #E9ECEF;padding:5px 0}",
    "section{break-inside:avoid-page}@media print{.page{padding:0}h2{break-after:avoid}@page{margin:14mm}}"
  ].join("\n");

  var LOGO = '<svg viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#0F6CBD"/><path d="M8 9h7v7H8zM17 9h7v7h-7zM8 18h7v7H8zM17 18h7v7h-7z" fill="#fff"/></svg>';

  function badge(value, label) { return '<span class="b b-' + esc(value) + '">' + esc(label || value) + "</span>"; }
  function title(id) { var a = window.App && App.action(id); return a ? a.title : id; }

  function recTable(list) {
    if (!list.length) return '<p class="muted">No improvements needed.</p>';
    return "<table><thead><tr><th>Improvement</th><th>Reason</th><th>Impact</th><th>Risk</th></tr></thead><tbody>" + list.map(function (r) {
      return "<tr><td><b>" + esc(r.title) + "</b></td><td>" + esc(r.reason) + "</td><td>" + badge(r.impact) + "</td><td>" + badge(r.risk, UI.RISK_LABEL[r.risk]) + "</td></tr>";
    }).join("") + "</tbody></table>";
  }
  // The before/after check of a fix as a report badge (2.7): the proof that it worked, with both readings.
  var VERDICT = { fixed: ["ok", "Fixed"], already_ok: ["ok", "Already fine"], applied: ["ok", "Applied"], already_set: ["skipped", "Already set"],
    freed: ["ok", "Space freed"], nothing_freed: ["skipped", "Nothing to free"], changed: ["skipped", "Changed"], unchanged: ["warning", "Nothing changed"],
    not_fixed: ["warning", "Not fixed"], worse: ["error", "Worse than before"], unknown: ["skipped", "Not verified"] };
  function verdict(r) {
    var v = r.verify, m = v && VERDICT[v.verdict];
    return m ? badge(m[0], m[1]) : '<span class="muted">—</span>';
  }
  function runTable(runs) {
    if (!runs.length) return '<p class="muted">No actions were run in this period.</p>';
    return "<table><thead><tr><th>Date</th><th>Action</th><th>Origin</th><th>Result</th><th>Check</th><th>Note</th><th class=\"num\">Freed</th></tr></thead><tbody>" + runs.map(function (r) {
      return "<tr><td>" + esc(UI.formatDate(r.started)) + "</td><td>" + esc(title(r.action_id)) + "</td><td>" + esc(UI.ORIGIN_LABEL[r.origin] || r.origin) + "</td><td>" +
        badge(r.status, UI.STATUS_LABEL[r.status]) + "</td><td>" + verdict(r) + "</td><td>" + esc(r.note || "") + '</td><td class="num">' +
        (r.bytes_freed ? UI.formatBytes(r.bytes_freed) : "—") + "</td></tr>";
    }).join("") + "</tbody></table>";
  }
  /* Evidence of the visit: every fix whose effect was measured, with the reading before and after, and what can be undone. */
  function evidence(runs) {
    var checked = runs.filter(function (r) { return r.verify && r.verify.verdict; });
    if (!checked.length) return "";
    var good = checked.filter(function (r) { return /^(fixed|already_ok|applied|freed)$/.test(r.verify.verdict); }).length;
    var bad = checked.filter(function (r) { return /^(not_fixed|worse|unchanged)$/.test(r.verify.verdict); }).length;
    var undoable = runs.filter(function (r) { return r.undo_count && !r.undone; });
    return "<section><h2>Evidence: before and after</h2>" +
      kpis([["Fixes checked", String(checked.length)], ["Confirmed", String(good)], ["To look at", String(bad)], ["Can be undone", String(undoable.length)]]) +
      "<table><thead><tr><th>Action</th><th>What was measured</th><th>Before</th><th>After</th><th>Check</th></tr></thead><tbody>" + checked.map(function (r) {
        return "<tr><td>" + esc(title(r.action_id)) + "</td><td>" + esc(r.verify.label || "") + "</td><td>" + esc(r.verify.before == null ? "—" : r.verify.before) +
          "</td><td>" + esc(r.verify.after == null ? "—" : r.verify.after) + "</td><td>" + verdict(r) + "</td></tr>";
      }).join("") + "</tbody></table>" +
      (undoable.length ? '<p class="muted">These changes can be put back one by one from History › Undo, without a restore point: ' +
        undoable.map(function (r) { return esc(title(r.action_id)); }).join(", ") + ".</p>" : "") + "</section>";
  }
  function kpis(items) {
    return '<div class="kpis">' + items.map(function (k) { return '<div class="kpi"><small>' + esc(k[0]) + "</small><b>" + k[1] + "</b></div>"; }).join("") + "</div>";
  }
  function trend(view, area) {
    return Charts.line([{ name: UI.AREA_LABEL[area], points: view.trend.map(function (p) { return { x: p.created, y: p.score }; }) }], { min: 0, max: 100, height: 170 });
  }

  var SECTIONS = {
    cleanup: function (v) {
      var d = v.data, c = (d.volumes || []).filter(function (x) { return x.letter === "C"; })[0] || {};
      var cats = (d.categories || []).slice().sort(function (a, b) { return b.bytes - a.bytes; });
      return kpis([["Score", v.score + " / 100"], ["Recoverable", UI.formatBytes(d.recoverable_bytes)], ["Free on C:", c.free_gb != null ? c.free_gb + " GB" : "—"],
        ["Freed (listed runs)", UI.formatBytes(v.runs.reduce(function (a, r) { return a + (r.bytes_freed || 0); }, 0))]]) +
        '<div class="two"><div><h3>Recoverable space by category</h3>' + Charts.hbars(cats.map(function (x) { return { label: x.name, value: x.bytes }; }), { format: UI.formatBytes }) +
        "</div><div><h3>Score trend</h3>" + trend(v, "cleanup") + "</div></div>" +
        "<h3>Drives</h3><table><thead><tr><th>Drive</th><th class=\"num\">Free</th><th class=\"num\">Size</th><th class=\"num\">Free %</th><th>Health</th></tr></thead><tbody>" +
        (d.volumes || []).map(function (x) {
          return "<tr><td>" + esc(x.letter) + ':</td><td class="num">' + esc(x.free_gb) + ' GB</td><td class="num">' + esc(x.total_gb) + ' GB</td><td class="num">' +
            (x.total_gb ? Math.round(100 * x.free_gb / x.total_gb) : 0) + "%</td><td>" + esc(x.health || "") + "</td></tr>";
        }).join("") + "</tbody></table>";
    },
    integrity: function (v) {
      var d = v.data, st = d.stability || {}, sec = d.security || {};
      return kpis([["Score", v.score + " / 100"], ["Healthy disks", (d.disks || []).filter(function (x) { return x.health === "Healthy"; }).length + " of " + (d.disks || []).length],
        ["Events (30 days)", String((st.unexpected_shutdowns || 0) + (st.whea || 0) + (st.disk_errors || 0))], ["Restart pending", d.reboot_pending ? "Yes" : "No"]]) +
        "<h3>Disks</h3><table><thead><tr><th>Disk</th><th>Type</th><th>Health</th><th class=\"num\">Wear</th><th class=\"num\">Temp.</th><th class=\"num\">Read errors</th></tr></thead><tbody>" +
        (d.disks || []).map(function (x) {
          return "<tr><td>" + esc(x.name) + "</td><td>" + esc(x.media) + "</td><td>" + badge(x.health === "Healthy" ? "ok" : "error", x.health) + '</td><td class="num">' +
            (x.wear != null ? x.wear + "%" : "—") + '</td><td class="num">' + (x.temperature != null ? x.temperature + " °C" : "—") + '</td><td class="num">' + (x.read_errors != null ? x.read_errors : "—") + "</td></tr>";
        }).join("") + "</tbody></table>" +
        '<div class="two"><div><h3>Stability events · 30 days</h3>' + Charts.bars([
          { label: "Shutdowns", value: st.unexpected_shutdowns || 0, color: "#C27C0E" }, { label: "WHEA", value: st.whea || 0, color: "#C42B1C" },
          { label: "Disk errors", value: st.disk_errors || 0, color: "#8764B8" }, { label: "Crash dumps", value: st.dumps || 0, color: "#5C7080" }], { max: 5, height: 170 }) +
        "</div><div><h3>Security</h3><table><tbody>" +
        "<tr><td>Real-time protection</td><td>" + (sec.defender === true ? badge("ok", "On") : sec.defender === false ? badge("error", "Off") : badge("skipped", "Unknown")) + "</td></tr>" +
        "<tr><td>Antivirus signatures</td><td>" + esc(sec.signature_age_days != null ? sec.signature_age_days + " days old" : "Unknown") + "</td></tr>" +
        "<tr><td>Firewall</td><td>" + badge(sec.firewall_off ? "error" : "ok", sec.firewall_off ? "Off on a profile" : "On") + "</td></tr>" +
        "<tr><td>BitLocker (C:)</td><td>" + esc(sec.bitlocker || "Not read") + "</td></tr>" +
        "<tr><td>Firmware</td><td>" + esc(d.bios || "") + " " + esc(d.bios_date || "") + "</td></tr></tbody></table><h3>Score trend</h3>" + trend(v, "integrity") + "</div></div>";
    },
    services: function (v) {
      var d = v.data, t = d.totals || {};
      var series = [{ label: "Automatic", value: t.auto || 0, color: "#0F6CBD" }, { label: "Manual", value: t.manual || 0, color: "#2E9D8F" }, { label: "Disabled", value: t.disabled || 0, color: "#8A8886" }];
      return kpis([["Score", v.score + " / 100"], ["Installed", String(t.total || 0)], ["Running", String(t.running || 0)], ["Startup programs", String((d.startup || []).length)]]) +
        '<div class="two"><div><h3>Start types</h3><div class="chart-row">' + Charts.donut(series, { center: t.total || 0, sub: "services" }) + Charts.legend(series) +
        "</div></div><div><h3>Score trend</h3>" + trend(v, "services") + "</div></div>" +
        "<h3>Managed services</h3><table><thead><tr><th>Service</th><th>Start type</th><th>State</th></tr></thead><tbody>" +
        (d.managed || []).map(function (s) { return "<tr><td>" + esc(s.name) + "</td><td>" + esc(s.start) + "</td><td>" + (s.running ? "Running" : "Stopped") + "</td></tr>"; }).join("") +
        "</tbody></table>";
    }
  };

  function rows(head, list, empty) {
    if (!list.length) return '<p class="muted">' + esc(empty || "Nothing to report.") + "</p>";
    return "<table><thead><tr>" + head.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") + "</tr></thead><tbody>" +
      list.map(function (r) { return "<tr>" + r.map(function (c) { return "<td>" + c + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody></table>";
  }

  SECTIONS.performance = function (v) {
    var d = v.data, m = d.memory || {}, cpu = d.cpu || {};
    return kpis([["Score", v.score + " / 100"], ["Memory in use", (m.load_pct != null ? m.load_pct + "%" : "—")], ["Power plan", esc((d.power || {}).name || "—")],
      ["Uptime", d.uptime_hours != null ? Math.round(d.uptime_hours) + " h" : "—"]]) +
      '<div class="two"><div><h3>Hardware</h3>' + rows(["Item", "Value"], [["Processor", esc(cpu.name || "—")], ["Cores / threads", esc(cpu.cores) + " / " + esc(cpu.logical)],
        ["Memory", esc(m.total_gb) + " GB"], ["Page file", (d.pagefile || {}).automatic ? "Managed by Windows" : "Custom"]]) +
      "</div><div><h3>Memory by process (scan time)</h3>" + Charts.hbars(((d.processes || {}).memory || []).slice(0, 6).map(function (p) { return { label: p.name, value: p.mb, color: "#8764B8" }; }),
        { format: function (x) { return x + " MB"; } }) + "</div></div>";
  };
  SECTIONS.storage = function (v) {
    var d = v.data;
    return kpis([["Score", v.score + " / 100"], ["Caches", UI.formatBytes((d.categories || []).reduce(function (a, c) { return a + c.bytes; }, 0))],
      ["Windows.old", UI.formatBytes(d.windows_old_bytes || 0)], ["Storage Sense", d.storage_sense ? "On" : d.storage_sense === false ? "Off" : "—"]]) +
      '<div class="two"><div><h3>Largest folders in the user profile</h3>' + Charts.hbars((d.folders || []).slice(0, 8).map(function (f) { return { label: f.name, value: f.bytes }; }), { format: UI.formatBytes }) +
      "</div><div><h3>Largest files</h3>" + rows(["File", "Size"], (d.files || []).slice(0, 8).map(function (f) { return [esc(f.path.split("\\").pop()), UI.formatBytes(f.bytes)]; })) + "</div></div>";
  };
  SECTIONS.network = function (v) {
    var d = v.data;
    return kpis([["Score", v.score + " / 100"], ["Adapters up", String((d.adapters || []).filter(function (a) { return a.status === "Up"; }).length)],
      ["DNS lookup", d.dns_ms != null ? d.dns_ms + " ms" : "—"], ["Connections", d.connections != null ? String(d.connections) : "—"]]) +
      "<h3>Latency test</h3>" + rows(["Target", "Average", "Max", "Jitter", "Lost"], (d.targets || []).map(function (t) {
        return [esc(t.name) + " (" + esc(t.address) + ")", t.avg + " ms", t.max + " ms", t.jitter + " ms", badge(t.lost ? "error" : "ok", t.lost + "/" + t.sent)];
      })) + "<h3>Adapters</h3>" + rows(["Adapter", "Status", "Speed", "IPv4", "DNS"], (d.adapters || []).map(function (a) {
        return [esc(a.name), esc(a.status), esc(a.speed || "—"), esc((a.ipv4 || []).join(", ")), esc((a.dns || []).join(", "))];
      }));
  };
  SECTIONS.startup = function (v) {
    var d = v.data, on = (d.items || []).filter(function (i) { return i.enabled; });
    return kpis([["Score", v.score + " / 100"], ["Startup programs on", on.length + " / " + (d.items || []).length], ["Installed apps", String((d.apps || []).length)],
      ["Third-party tasks", String((d.tasks || []).length)]]) +
      "<h3>Programs that start with Windows</h3>" + rows(["Program", "Location", "State"], (d.items || []).map(function (i) {
        return [esc(i.name), esc(i.location), badge(i.enabled ? "ok" : "skipped", i.enabled ? "On" : "Off")];
      }), "No startup programs.");
  };
  SECTIONS.security = function (v) {
    var d = v.data, def = d.defender || {};
    var tri = function (x, good) { return x == null ? badge("skipped", "Unknown") : x === good ? badge("ok", x ? "On" : "Off") : badge("error", x ? "On" : "Off"); };
    return kpis([["Score", v.score + " / 100"], ["Signatures", def.signature_age_days != null ? def.signature_age_days + " days old" : "—"],
      ["Restore points", String((d.restore_points || []).length)], ["Administrators", String((d.admins || []).length)]]) +
      "<h3>Security posture</h3>" + rows(["Control", "State"], [
        ["Real-time protection", tri(def.realtime, true)], ["User Account Control", tri((d.uac || {}).enabled, true)], ["Secure Boot", tri(d.secure_boot, true)],
        ["SMBv1", d.smb1 == null ? badge("skipped", "Unknown") : d.smb1 ? badge("error", "Enabled") : badge("ok", "Disabled")],
        ["Remote Desktop", d.rdp_enabled == null ? badge("skipped", "Unknown") : d.rdp_enabled ? badge("warning", "Enabled") : badge("ok", "Disabled")],
        ["Firewall", (d.firewall || []).some(function (f) { return !f.enabled; }) ? badge("error", "Off on a profile") : badge("ok", "On")]
      ]);
  };
  SECTIONS.updates = function (v) {
    var d = v.data;
    return kpis([["Score", v.score + " / 100"], ["Pending updates", String((d.pending || []).length)], ["Devices with errors", String((d.problem_devices || []).length)],
      ["Restart required", d.reboot_required ? "Yes" : "No"]]) +
      "<h3>Pending updates</h3>" + rows(["Update", "Severity", "Size"], (d.pending || []).map(function (u) {
        return [esc(u.title), u.severity ? badge(u.severity === "Critical" ? "error" : "warning", u.severity) : "—", u.size_mb ? u.size_mb + " MB" : "—"];
      }), "Windows is up to date.") + "<h3>Devices with errors</h3>" + rows(["Device", "Error code"], (d.problem_devices || []).map(function (x) { return [esc(x.name), esc(x.code)]; }), "All devices work correctly.");
  };

  function areaSection(view, area, number) {
    return "<section><h2>" + (number ? number + ". " : "") + esc(UI.AREA_LABEL[area]) + "</h2>" + SECTIONS[area](view) +
      "<h3>Recommended improvements</h3>" + recTable(view.recommendations) + "<h3>Recent activity</h3>" + runTable(view.runs.slice(0, 10)) + "</section>";
  }

  function summary(dash) {
    var s = dash.system || {}, os = s.os || {}, mem = s.memory || {};
    var scanned = AREAS.filter(function (a) { return dash.scores[a] != null; });
    var scores = '<div class="area-scores">' + scanned.map(function (a) {
      var v = dash.scores[a];
      return "<div><span>" + esc(UI.AREA_LABEL[a]) + "</span>" + badge(v >= 80 ? "ok" : v >= 60 ? "warning" : "error", v + " / 100") + "</div>";
    }).join("") + "</div>";
    var weakest = scanned.slice().sort(function (a, b) { return dash.scores[a] - dash.scores[b]; })[0];
    var text = dash.scores.overall == null ? "No area has been scanned yet." : "Overall health is <b>" + dash.scores.overall + "/100</b> across " + scanned.length + " areas. " +
      dash.open_issues + " improvement(s) are recommended" +
      (dash.open_issues && weakest ? "; the area that needs most attention is <b>" + esc(UI.AREA_LABEL[weakest]) + "</b> (" + dash.scores[weakest] + "/100)." : ".");
    return "<section><h2>Executive summary</h2>" + '<div class="summary">' + text + "</div>" + scores +
      "<h3>System</h3><table><tbody>" + [
        ["Operating system", (os.name || "") + " " + (os.build ? "build " + os.build : "")], ["Processor", os.cpu], ["Motherboard / firmware", (os.board || "") + " · " + (os.bios || "") + " " + (os.bios_date || "")],
        ["Memory", mem.total_gb != null ? mem.free_gb + " GB free of " + mem.total_gb + " GB" : ""], ["Graphics", (s.gpu || {}).name], ["Uptime", os.uptime_hours != null ? os.uptime_hours + " hours" : ""]
      ].map(function (r) { return "<tr><td style=\"width:220px\" class=\"muted\">" + esc(r[0]) + "</td><td>" + esc(r[1] || "—") + "</td></tr>"; }).join("") + "</tbody></table>" +
      "<h3>Top recommended improvements</h3>" + recTable(dash.recommendations) + "</section>";
  }

  /* Score of an area at a moment: the last scan before it, else the first scan after it (the baseline of this visit). */
  function scoreAt(trend, when) {
    var before = null, after = null;
    (trend || []).forEach(function (p) {
      var t = new Date(p.created).getTime();
      if (t <= when) before = p.score; else if (after == null) after = p.score;
    });
    return before != null ? before : after;
  }
  function delta(a, b) {
    if (a == null || b == null) return '<span class="same">—</span>';
    var d = b - a;
    return d > 0 ? '<span class="up">+' + d + "</span>" : d < 0 ? '<span class="down">' + d + "</span>" : '<span class="same">0</span>';
  }
  function average(list) {
    var v = list.filter(function (x) { return x != null; });
    return v.length ? Math.round(v.reduce(function (a, b) { return a + b; }, 0) / v.length) : null;
  }
  function visitBody(since, dash, history) {
    var when = since.getTime();
    var rows = AREAS.map(function (a) {
      var trend = history.trends[a] || [], last = trend.length ? trend[trend.length - 1].score : dash.scores[a];
      return { area: a, before: scoreAt(trend, when), after: last };
    }).filter(function (r) { return r.before != null || r.after != null; });
    var runs = history.runs.filter(function (r) { return new Date(r.started).getTime() >= when && r.status !== "preview"; });
    var ok = runs.filter(function (r) { return r.status === "ok" || r.status === "warning"; });
    var failed = runs.filter(function (r) { return r.status === "error"; });
    var freed = runs.reduce(function (s, r) { return s + (r.bytes_freed || 0); }, 0);
    var programs = runs.filter(function (r) { return /^apps\.(uninstall|store_remove|update|leftovers|remove_entry)$/.test(r.action_id) && r.status === "ok"; });
    var avgBefore = average(rows.map(function (r) { return r.before; })), avgAfter = average(rows.map(function (r) { return r.after; }));
    // The sentence mixes numbers and bold text, so the dictionary cannot translate it: it is written in both languages here.
    var it = window.I18N && I18N.lang() === "it", quando = esc(since.toLocaleString(it ? "it-IT" : undefined));
    var lead = avgBefore == null
      ? (it ? "Non è ancora stata fatta una scansione: scansiona il PC per misurare il risultato della manutenzione."
        : "No scan was made yet: scan the PC to measure the result of the maintenance.")
      : it
        ? "La salute media è passata da <b>" + avgBefore + "</b> a <b>" + avgAfter + "</b> (" + delta(avgBefore, avgAfter) + ") dal " + quando + ". " +
          ok.length + (ok.length === 1 ? " operazione completata" : " operazioni completate") + (failed.length ? ", " + failed.length + " con errori" : "") +
          (freed ? ", " + UI.formatBytes(freed) + " di spazio liberato" : "") + "."
        : "Average health went from <b>" + avgBefore + "</b> to <b>" + avgAfter + "</b> (" + delta(avgBefore, avgAfter) + ") since " + quando + ". " +
          ok.length + " operation(s) completed" + (failed.length ? ", " + failed.length + " with errors" : "") + (freed ? ", " + UI.formatBytes(freed) + " of disk space freed" : "") + ".";
    var byArea = {};
    ok.forEach(function (r) { (byArea[r.area] = byArea[r.area] || []).push(r); });
    var done = Object.keys(byArea).map(function (a) {
      return "<h3>" + esc(UI.AREA_LABEL[a] || a) + " (" + byArea[a].length + ")</h3>" + runTable(byArea[a]);
    }).join("") || '<p class="muted">No change was made in this period.</p>';
    return "<section><h2>Result of the maintenance</h2><div class=\"summary\">" + lead + "</div>" +
      kpis([["Health before", avgBefore != null ? avgBefore + " / 100" : "—"], ["Health after", avgAfter != null ? avgAfter + " / 100" : "—"],
        ["Operations done", String(ok.length)], ["Space freed", freed ? UI.formatBytes(freed) : "—"]]) +
      "<table><thead><tr><th>Area</th><th class=\"num\">Before</th><th class=\"num\">After</th><th class=\"num\">Change</th></tr></thead><tbody>" +
      rows.map(function (r) {
        return "<tr><td>" + esc(UI.AREA_LABEL[r.area]) + '</td><td class="num">' + (r.before != null ? r.before : "—") + '</td><td class="num">' +
          (r.after != null ? r.after : "—") + '</td><td class="num">' + delta(r.before, r.after) + "</td></tr>";
      }).join("") + "</tbody></table></section>" +
      (programs.length ? "<section><h2>Programs</h2>" + runTable(programs) + "</section>" : "") +
      "<section><h2>What was done</h2>" + done + "</section>" + evidence(ok) +
      (failed.length ? "<section><h2>Operations with errors</h2>" + runTable(failed) + "</section>" : "") +
      "<section><h2>Still recommended</h2>" + recTable(dash.recommendations || []) + "</section>";
  }

  function build(scope, options) {
    options = options || {};
    if (scope === "visit") {
      var since = options.since ? new Date(options.since) : new Date(new Date().setHours(0, 0, 0, 0));
      return Promise.all([API.get("/agent/info"), API.get("/settings"), API.get("/dashboard"), API.get("/history?limit=5000")]).then(function (r) {
        return wrap(scope, r[0], r[1], options, r[2].scores.overall, visitBody(since, r[2], r[3]) +
          (options.notes ? "<section><h2>Technician notes</h2><div class=\"notes\">" + esc(options.notes) + "</div></section>" : ""));
      });
    }
    var withSummary = scope === "dashboard" || scope === "full";
    var first = [API.get("/agent/info"), API.get("/settings"), withSummary ? API.get("/dashboard") : Promise.resolve(null)];
    return Promise.all(first).then(function (r) {
      var info = r[0], settings = r[1], dash = r[2];
      // The full report covers the areas already scanned: building it never starts a slow scan.
      var areas = scope === "full" ? AREAS.filter(function (a) { return dash.scores[a] != null; }) : AREAS.indexOf(scope) >= 0 ? [scope] : [];
      return Promise.all(areas.map(function (a) { return API.get("/areas/" + a); }).concat([withSummary ? API.get("/history?limit=50") : Promise.resolve(null)])).then(function (rest) {
        var history = rest.pop(), views = {};
        areas.forEach(function (a, n) { views[a] = rest[n]; });
        var body = "";
        if (dash) body += summary(dash);
        areas.forEach(function (a, n) { body += areaSection(views[a], a, scope === "full" ? n + 1 : 0); });
        if (history && scope === "dashboard") body += "<section><h2>Recent activity</h2>" + runTable(history.runs.slice(0, 15)) + "</section>";
        if (options.notes) body += "<section><h2>Technician notes</h2><div class=\"notes\">" + esc(options.notes) + "</div></section>";
        var score = dash && dash.scores.overall != null ? dash.scores.overall : views[scope] ? views[scope].score : null;
        return wrap(scope, info, settings, options, score, body);
      });
    });
  }

  // 2.12: the sections the user left out of the report (by their title).
  function dropSections(body, hide) {
    if (!hide || !hide.length || !window.DOMParser) return body;
    var doc = new DOMParser().parseFromString("<div>" + body + "</div>", "text/html"), root = doc.body.firstChild;
    Array.prototype.slice.call(root.querySelectorAll("section")).forEach(function (s) {
      var h = s.querySelector("h2");
      if (h && hide.indexOf(h.textContent.trim()) >= 0) s.remove();
    });
    return root.innerHTML;
  }

  function wrap(scope, info, settings, options, score, body) {
        body = dropSections(body, options.hide);
        var technician = options.technician || settings.technician;
        var now = new Date();
        var cover = '<div class="cover"><div><div class="brand">' + LOGO + "<div><b>Windows Maintenance Manager</b><span>" + esc(SCOPE_LABEL[scope]) + " report</span></div></div></div><div>" +
          (settings.company ? '<div class="company">' + esc(settings.company) + "</div>" : "") + "<h1>" + esc(SCOPE_LABEL[scope]) + " report</h1>" +
          '<div class="lead">Windows maintenance assessment of <b>' + esc(info.hostname) + "</b>." + (settings.report_header ? "<br>" + esc(settings.report_header) : "") + "</div>" +
          (score != null ? '<div class="score">' + Charts.gauge(score, { label: "Health" }) + '<div><b style="font-size:18px">Health score ' + score + '/100</b><br><span class="muted">80 or more is healthy.</span></div></div>' : "") +
          '<div class="facts"><div><small>Device</small>' + esc(info.hostname) + "</div><div><small>Generated</small>" + esc(now.toLocaleString()) + "</div>" +
          "<div><small>Technician</small>" + esc(technician || "—") + "</div><div><small>Machine ID</small>" + esc(info.machine_id) + "</div></div></div>" +
          '<div class="muted small">' + esc(settings.report_footer || "") + "</div></div>";
        var head = '<div class="head"><div class="brand">' + LOGO + "<div><b>" + esc(settings.company || "Windows Maintenance Manager") + "</b><span>" + esc(SCOPE_LABEL[scope]) +
          ' report</span></div></div><div class="meta">Device <b>' + esc(info.hostname) + "</b><br>Generated " + esc(now.toLocaleString()) +
          (technician ? "<br>Technician <b>" + esc(technician) + "</b>" : "") + "</div></div>";
        var title = SCOPE_LABEL[scope] + " report · " + info.hostname;
        return "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>" + esc(title) +
          "</title><style>" + CSS + '</style></head><body><div class="page">' + cover + head + body +
          '<div class="foot"><span>' + esc(settings.report_footer || "Windows Maintenance Manager " + info.version) + "</span><span>" + esc(now.toLocaleDateString()) + "</span></div></div></body></html>";
  }

  function fileName(scope) {
    var d = new Date(), p = function (n) { return (n < 10 ? "0" : "") + n; };
    var host = (window.App && App.state.info ? App.state.info.hostname : "pc").replace(/[^A-Za-z0-9_-]/g, "");
    return "wmm-" + scope + "-" + host + "-" + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + "-" + p(d.getHours()) + p(d.getMinutes()) + ".html";
  }

  function download(scope, options) {
    UI.toast("Preparing the report…", "info");
    return translated(scope, options).then(function (html) {
      var url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
      var a = document.createElement("a");
      a.href = url;
      a.download = fileName(scope);
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    }).catch(function (e) { UI.toast(e.message, "error"); });
  }

  function print(scope, options) {
    var win = window.open("", "_blank");
    if (!win) { UI.toast("Allow pop-ups for this page to print the report.", "warning"); return Promise.resolve(); }
    win.document.write("<p style=\"font-family:Segoe UI;padding:20px\">Preparing the report…</p>");
    return translated(scope, options).then(function (html) {
      win.document.open();
      win.document.write(html);
      win.document.close();
      setTimeout(function () { win.focus(); win.print(); }, 400);
    }).catch(function (e) { win.close(); UI.toast(e.message, "error"); });
  }

  /* The customer reads the report in the language of the console (Settings › Appearance › Language). */
  function translated(scope, options) {
    return build(scope, options).then(function (html) { return window.I18N ? I18N.translateHtml(html) : html; });
  }

  window.Report = { build: translated, download: download, print: print, SCOPE_LABEL: SCOPE_LABEL };
})();
