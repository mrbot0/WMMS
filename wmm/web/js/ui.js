/* Shared UI building blocks. Functions return HTML strings unless noted. */
(function () {
  "use strict";

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function formatBytes(n) {
    n = Number(n) || 0;
    var units = ["B", "KB", "MB", "GB", "TB"], i = 0;
    while (Math.abs(n) >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i < 2 ? Math.round(n) : n.toFixed(1)) + " " + units[i];
  }
  function formatDate(iso, withTime) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return esc(iso);
    return withTime === false ? d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })
      : d.toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  function relative(iso) {
    if (!iso) return "never";
    var s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " days ago";
  }
  function duration(minutes) {
    return minutes < 1 ? "< 1 min" : "~" + Math.round(minutes) + " min";
  }

  var ICONS = {
    dashboard: '<path d="M4 13h7V4H4zM13 20h7v-9h-7zM4 20h7v-5H4zM13 9h7V4h-7z"/>',
    cleanup: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    integrity: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5L16 9.5"/>',
    services: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    schedules: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18M12 14v3l2 1"/>',
    history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
    reports: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 17v-3M12 17v-6M16 17v-2"/>',
    play: '<path d="M7 5l12 7-12 7z"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    bolt: '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5"/>',
    print: '<path d="M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2M7 14h10v7H7z"/>',
    trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    performance: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    storage: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    network: '<path d="M2 9a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19.5" r="1"/>',
    startup: '<path d="M12 2v10M5.6 6.6a9 9 0 1 0 12.8 0"/>',
    security: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
    updates: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5M12 8v5l3 2"/>',
    recommendations: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z"/>',
    playbooks: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 5l1.5 1.5L7 4M3 11l1.5 1.5L7 10M3 17l1.5 1.5L7 16"/>',
    settings: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    bell: '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    collapse: '<path d="M15 18l-6-6 6-6"/>',
    check: '<path d="M20 6L9 17l-5-5"/>',
    x: '<path d="M18 6L6 18M6 6l12 12"/>',
    alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
    cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    memory: '<rect x="2" y="7" width="20" height="10" rx="2"/><path d="M6 7v10M10 7v10M14 7v10M18 7v10"/>',
    keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    compare: '<path d="M8 3v18M16 3v18M3 8h5M16 16h5"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    activity: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 9h6M7 13h10M7 17h4"/><circle cx="17" cy="9" r="1.5" fill="currentColor"/>',
    chevron: '<path d="M9 18l6-6-6-6"/>',
    explorer: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v5"/>',
    sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
    gauge: '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-6"/><circle cx="12" cy="18" r="1.4" fill="currentColor"/>'
  };
  ICONS.upload = '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>';
  ICONS.support ='<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5v.5"/>';
  ICONS.actions ='<circle cx="12" cy="12" r="9"/><path d="M10 8.5l5 3.5-5 3.5z"/>';
  ICONS.cleanup ='<path d="M3 21h18"/><path d="M14.5 3.5l6 6-9.5 9.5H5v-6z"/><path d="M11 7l6 6"/>';
  ICONS.services = '<rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6"/>';
  ICONS.integrity = '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5L16 9.5"/>';
  ICONS.dashboard = '<rect x="3" y="3" width="8" height="10" rx="2"/><rect x="13" y="3" width="8" height="6" rx="2"/><rect x="13" y="11" width="8" height="10" rx="2"/><rect x="3" y="15" width="8" height="6" rx="2"/>';
  function icon(name) {
    return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || "") + "</svg>";
  }

  function tone(score) { return score >= 80 ? "ok" : score >= 60 ? "warning" : "error"; }

  function kpi(title, value, sub, toneName, extra) {
    return '<div class="kpi' + (toneName ? " kpi-" + toneName : "") + '"><div class="kpi-title">' + esc(title) + '</div><div class="kpi-value">' + value +
      '</div><div class="kpi-sub">' + (sub || "") + "</div>" + (extra || "") + "</div>";
  }
  var CARD_ICONS = {
    "Score trend": "history", "Recent activity": "history", "Recommended improvements": "recommendations", "Optimization actions": "play",
    "Security": "security", "Storage": "storage", "System": "cpu", "Hardware": "cpu", "Network latency": "network", "Score": "dashboard"
  };
  function collapsedKeys() {
    try { return JSON.parse(localStorage.getItem("wmm.collapsed") || "{}"); } catch (e) { return {}; }
  }
  /* Cards can be collapsed with the chevron; the choice is remembered per page and title. */
  function card(title, body, tools, cls) {
    var key = (location.hash.replace(/^#\/?/, "").split("?")[0] || "dashboard") + "|" + title;
    var collapsed = !!collapsedKeys()[key];
    var iconName = CARD_ICONS[title];
    return '<section class="card ' + (cls || "") + (collapsed ? " collapsed" : "") + '" data-card="' + esc(key) + '"><header class="card-head"><h2>' +
      (iconName ? icon(iconName) : "") + esc(title) + '</h2><div class="card-tools">' + (tools || "") +
      '<button class="collapse-card" type="button" data-collapse aria-label="Collapse or expand" aria-expanded="' + !collapsed + '">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button></div></header>' +
      '<div class="card-body">' + body + "</div></section>";
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-collapse]");
    if (!btn) return;
    var section = btn.closest(".card"), key = section.getAttribute("data-card"), state = collapsedKeys();
    var collapsed = section.classList.toggle("collapsed");
    btn.setAttribute("aria-expanded", String(!collapsed));
    if (collapsed) state[key] = 1; else delete state[key];
    try { localStorage.setItem("wmm.collapsed", JSON.stringify(state)); } catch (err) { /* storage unavailable */ }
  });
  function table(columns, rows, empty) {
    if (!rows.length) return '<p class="empty">' + esc(empty || "Nothing to show.") + "</p>";
    return '<div class="table-wrap"><table class="table"><thead><tr>' + columns.map(function (c) {
      return '<th class="' + (c.cls || "") + '">' + esc(c.title) + "</th>";
    }).join("") + "</tr></thead><tbody>" + rows.map(function (row) {
      return "<tr>" + row.map(function (cell, i) { return '<td class="' + (columns[i].cls || "") + '">' + (cell == null ? "—" : cell) + "</td>"; }).join("") + "</tr>";
    }).join("") + "</tbody></table></div>";
  }
  function definition(items) {
    return '<dl class="deflist">' + items.map(function (item) {
      return "<div><dt>" + esc(item[0]) + "</dt><dd>" + (item[1] == null || item[1] === "" ? "—" : item[1]) + "</dd></div>";
    }).join("") + "</dl>";
  }

  var RISK_LABEL = { safe: "Safe", moderate: "Moderate", high: "High risk" };
  var STATUS_LABEL = { ok: "Success", warning: "Warning", error: "Error", skipped: "Skipped", preview: "Preview", running: "Running" };
  function riskBadge(risk) { return '<span class="badge badge-' + esc(risk) + '">' + esc(RISK_LABEL[risk] || risk) + "</span>"; }
  function statusBadge(status) { return '<span class="badge badge-status-' + esc(status) + '">' + esc(STATUS_LABEL[status] || status || "—") + "</span>"; }
  function impactBadge(impact) { return '<span class="badge badge-impact-' + esc(impact) + '">' + esc(impact.charAt(0).toUpperCase() + impact.slice(1)) + " impact</span>"; }

  function recommendations(list, options) {
    options = options || {};
    if (!list || !list.length) {
      return '<div class="all-good">' + icon("shield") + "<div><strong>No improvements needed</strong><span>This area is in good shape.</span></div></div>";
    }
    return '<ul class="recs">' + list.map(function (r) {
      var buttons = r.action_id
        ? '<button class="btn btn-sm btn-primary" data-run="' + esc(r.action_id) + '">' + icon("play") + "Apply</button>" +
          '<button class="btn btn-sm" data-schedule="' + esc(r.action_id) + '">' + icon("clock") + "Schedule</button>"
        : '<span class="muted small">Manual step</span>';
      return '<li class="rec rec-' + esc(r.impact) + '"><div class="rec-main"><div class="rec-title">' + esc(r.title) +
        (options.showArea ? ' <span class="muted small">· ' + esc(AREA_LABEL[r.area] || r.area) + "</span>" : "") +
        '</div><div class="rec-reason">' + esc(r.reason) + '</div><div class="rec-badges">' + impactBadge(r.impact) + riskBadge(r.risk) +
        '</div></div><div class="rec-actions">' + buttons + "</div></li>";
    }).join("") + "</ul>";
  }

  var AREA_LABEL = {
    cleanup: "Cleanup", integrity: "System Integrity", services: "Services", performance: "Performance", storage: "Storage",
    network: "Network", startup: "Startup & Apps", security: "Security", updates: "Updates & Drivers"
  };
  var AREAS = ["performance", "cleanup", "storage", "startup", "services", "integrity", "security", "updates", "network"];

  function statusIcon(tone) {
    return '<span class="status-icon ' + tone + '">' + icon(tone === "ok" ? "check" : tone === "skipped" ? "info" : tone === "warning" ? "alert" : "x") + "</span>";
  }
  /* A checklist row: [label, tone, value text, optional sub text]. */
  function checklist(rows) {
    return '<ul class="check-list">' + rows.map(function (r) {
      return "<li>" + statusIcon(r[1]) + '<span class="grow"><span class="cell-title">' + esc(r[0]) + "</span>" + (r[3] ? '<br><span class="cell-sub">' + esc(r[3]) + "</span>" : "") +
        '</span><span class="badge badge-status-' + (r[1] === "skipped" ? "skipped" : r[1]) + '">' + esc(r[2]) + "</span></li>";
    }).join("") + "</ul>";
  }
  function toneOf(value, warn, bad, higherIsWorse) {
    if (value == null) return "";
    return higherIsWorse ? (value >= bad ? "error" : value >= warn ? "warning" : "ok") : (value <= bad ? "error" : value <= warn ? "warning" : "ok");
  }

  function toast(message, toneName) {
    var root = document.getElementById("toasts");
    var el = document.createElement("div");
    el.className = "toast toast-" + (toneName || "info");
    el.textContent = message;
    // At most four toasts on screen: the oldest gives way to the newest.
    while (root.children.length >= 4) root.removeChild(root.firstChild);
    root.appendChild(el);
    var visible = Math.max(4200, String(message).length * 60);  // long errors need time to be read
    setTimeout(function () { el.classList.add("leaving"); }, visible);
    setTimeout(function () { el.remove(); }, visible + 400);
  }

  /* Opens a modal. `build(body)` fills the body element; resolves with the value passed to close(). */
  function modal(title, bodyHtml, buttons) {
    return new Promise(function (resolve) {
      var root = document.getElementById("modal-root");
      var previous = document.activeElement;
      var wrap = document.createElement("div");
      wrap.className = "modal-backdrop";
      wrap.innerHTML = '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header><h2 id="modal-title">' + esc(title) +
        '</h2></header><div class="modal-body">' + bodyHtml + '</div><footer class="modal-foot"></footer></div>';
      var foot = wrap.querySelector(".modal-foot");
      function close(value) {
        wrap.remove();
        document.removeEventListener("keydown", onKey);
        if (previous && previous.focus) previous.focus();
        resolve(value);
      }
      function onKey(e) { if (e.key === "Escape") close(null); }
      buttons.forEach(function (b) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn " + (b.cls || "");
        btn.textContent = b.label;
        btn.addEventListener("click", function () { close(b.value ? b.value(wrap) : null); });
        foot.appendChild(btn);
      });
      wrap.addEventListener("click", function (e) { if (e.target === wrap) close(null); });
      document.addEventListener("keydown", onKey);
      root.appendChild(wrap);
      var first = wrap.querySelector("input, select, .btn-primary, .btn-danger");
      if (first) first.focus();
    });
  }

  function confirm(title, text, options) {
    options = options || {};
    return modal(title, '<p class="modal-text">' + esc(text) + "</p>", [
      { label: "Cancel", cls: "btn-ghost" },
      { label: options.ok || "Confirm", cls: options.danger ? "btn-danger" : "btn-primary", value: function () { return true; } }
    ]).then(function (v) { return v === true; });
  }

  var DAYS = [["MON", "Mon"], ["TUE", "Tue"], ["WED", "Wed"], ["THU", "Thu"], ["FRI", "Fri"], ["SAT", "Sat"], ["SUN", "Sun"]];
  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function scheduleDialog(action) {
    var d = new Date(Date.now() + 3600e3);
    var date = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
    var warning = action.risk !== "safe"
      ? '<div class="callout callout-warning">' + icon("info") + "<div><strong>" + esc(RISK_LABEL[action.risk]) + " action.</strong> " + esc(action.warning) +
        ' A restore point is created before every run.<label class="check"><input type="checkbox" name="confirmed"> I understand and want to schedule this action</label></div></div>'
      : '<div class="callout">' + icon("shield") + "<div>Safe action: it runs unattended without confirmation.</div></div>";
    var body = '<p class="modal-text"><strong>' + esc(action.title) + "</strong><br><span class=\"muted\">" + esc(action.description) + "</span></p>" +
      '<form class="form" onsubmit="return false">' +
      '<label>Frequency<select name="kind"><option value="once">Once</option><option value="daily">Every day</option><option value="weekly">Every week</option></select></label>' +
      '<div class="form-row"><label>Start date<input type="date" name="date" value="' + date + '" required></label>' +
      '<label>Time<input type="time" name="time" value="03:00" required></label></div>' +
      '<fieldset class="days" hidden><legend>Days</legend>' + DAYS.map(function (day) {
        return '<label class="chip"><input type="checkbox" name="day" value="' + day[0] + '"' + (day[0] === "MON" ? " checked" : "") + "><span>" + day[1] + "</span></label>";
      }).join("") + "</fieldset>" + warning +
      '<p class="muted small">The schedule is registered in Windows Task Scheduler and runs even when this console is closed.</p></form>';
    var promise = modal("Schedule action", body, [
      { label: "Cancel", cls: "btn-ghost" },
      { label: "Create schedule", cls: "btn-primary", value: function (wrap) {
        var form = wrap.querySelector("form");
        var days = Array.prototype.map.call(form.querySelectorAll('input[name="day"]:checked'), function (i) { return i.value; });
        var confirmed = form.querySelector('input[name="confirmed"]');
        return {
          kind: form.kind.value, at: form.date.value + "T" + form.time.value, days: form.kind.value === "weekly" ? days.join(",") : "",
          confirmed: action.risk === "safe" ? false : !!(confirmed && confirmed.checked)
        };
      } }
    ]);
    var form = document.querySelector("#modal-root form");
    if (form) {
      form.kind.addEventListener("change", function () { form.querySelector(".days").hidden = form.kind.value !== "weekly"; });
    }
    return promise;
  }

  function loading(text) {
    return '<div class="loading"><span class="spinner"></span>' + esc(text || "Loading…") + "</div>";
  }
  function errorBox(error) {
    return '<div class="callout callout-error">' + icon("info") + "<div><strong>Something went wrong.</strong> " + esc(error && error.message || error) + "</div></div>";
  }
  function pageHeader(title, sub, buttons) {
    return '<div class="page-head"><div><div class="page-kicker">' + esc(sub || "") + '</div></div><div class="page-actions">' + (buttons || "") + "</div></div>";
  }
  function button(label, attrs, cls, iconName) {
    return '<button type="button" class="btn ' + (cls || "") + '" ' + (attrs || "") + ">" + (iconName ? icon(iconName) : "") + esc(label) + "</button>";
  }

  var ORIGIN_LABEL = { manual: "Manual", auto: "Automatic", schedule: "Scheduled" };

  function runsTable(runs, actionTitle, options) {
    options = options || {};
    return table(
      [{ title: "Date" }, { title: "Action" }, options.area ? { title: "Area" } : null, { title: "Origin" }, { title: "Result" }, { title: "Note" }, { title: "Freed", cls: "num" }]
        .filter(Boolean),
      runs.map(function (r) {
        var row = [formatDate(r.started), '<span class="cell-title">' + esc(actionTitle(r.action_id)) + "</span>"];
        if (options.area) row.push(esc(AREA_LABEL[r.area] || r.area));
        row.push(esc(ORIGIN_LABEL[r.origin] || r.origin), statusBadge(r.status), '<span class="cell-sub">' + esc(r.note || "") + "</span>",
          r.bytes_freed ? formatBytes(r.bytes_freed) : "—");
        return row;
      }),
      options.empty || "No actions have been run yet."
    );
  }

  /* Pieces shared by the Cleanup, System Integrity and Services pages. */
  function areaParts(view, area) {
    var title = function (id) { var a = window.App && App.action(id); return a ? a.title : id; };
    var hasSafe = view.actions.some(function (a) { return a.risk === "safe"; });
    var noActions = !view.actions.length;
    var header = pageHeader(AREA_LABEL[area], "Last scan " + relative(view.created) + " · " + formatDate(view.created),
      button("Scan", 'data-scan-area="' + area + '"', "", "refresh") +
      (hasSafe ? button("Apply safe actions", 'data-safe-area="' + area + '"', "", "bolt") : "") +
      button("Export report", 'data-export-area="' + area + '"', "btn-primary", "download"));
    var actionsTable = table(
      [{ title: "Action" }, { title: "Risk" }, { title: "Duration" }, { title: "Last run" }, { title: "", cls: "actions" }],
      view.actions.map(function (a) {
        var last = a.last_run ? statusBadge(a.last_run.status) + ' <span class="cell-sub">' + relative(a.last_run.finished || a.last_run.started) + "</span>" : '<span class="cell-sub">Never</span>';
        return ['<div class="cell-title">' + esc(a.title) + '</div><div class="cell-sub">' + esc(a.description) + "</div>", riskBadge(a.risk), esc(duration(a.minutes)), last,
          '<button class="btn btn-sm" data-run="' + esc(a.id) + '">' + icon("play") + 'Run</button><button class="btn btn-sm" data-schedule="' + esc(a.id) + '">' + icon("clock") + "Schedule</button>"];
      }));
    var trend = Charts.line([{ name: AREA_LABEL[area] + " score", points: view.trend.map(function (p) { return { x: p.created, y: p.score }; }) }], { min: 0, max: 100 });
    return {
      header: header,
      score: Charts.gauge(view.score, { label: AREA_LABEL[area] + " score" }),
      recommendations: card("Recommended improvements", recommendations(view.recommendations), '<span class="muted small">' + view.recommendations.length + " found</span>"),
      actions: noActions ? "" : card("Optimization actions", actionsTable, '<span class="muted small">' + view.actions.length + " actions</span>", "card-flush"),
      trend: card("Score trend", trend),
      runs: card("Recent activity", runsTable(view.runs.slice(0, 8), title)),
      errors: view.data.errors && view.data.errors.length
        ? '<div class="callout callout-error">' + icon("info") + "<div><strong>Scan incomplete: some data could not be read.</strong> " + esc(view.data.errors.join(" · ")) + "</div></div>" :
        (view.data.warnings && view.data.warnings.length
          ? '<div class="callout callout-warning">' + icon("info") + "<div>" + esc(view.data.warnings.join(" · ")) + "</div></div>" : "")
    };
  }

  function bindArea(el, area, rerender) {
    var scan = el.querySelector("[data-scan-area]");
    if (scan) scan.addEventListener("click", function () {
      scan.disabled = true;
      scan.classList.add("busy");
      API.post("/areas/" + area + "/scan").then(function () { UI.toast("Scan completed.", "ok"); rerender(); },
        function (e) { UI.toast(e.message, "error"); scan.disabled = false; scan.classList.remove("busy"); });
    });
    var safe = el.querySelector("[data-safe-area]");
    if (safe) safe.addEventListener("click", function () { App.runSafe(area); });
    var exp = el.querySelector("[data-export-area]");
    if (exp) exp.addEventListener("click", function () { Report.download(area); });
  }

  window.UI = {
    runsTable: runsTable, areaParts: areaParts, bindArea: bindArea, ORIGIN_LABEL: ORIGIN_LABEL,
    AREAS: AREAS, statusIcon: statusIcon, checklist: checklist, toneOf: toneOf,
    esc: esc, formatBytes: formatBytes, formatDate: formatDate, relative: relative, duration: duration, icon: icon, tone: tone,
    kpi: kpi, card: card, table: table, definition: definition, riskBadge: riskBadge, statusBadge: statusBadge, impactBadge: impactBadge,
    recommendations: recommendations, toast: toast, modal: modal, confirm: confirm, scheduleDialog: scheduleDialog,
    loading: loading, errorBox: errorBox, pageHeader: pageHeader, button: button,
    RISK_LABEL: RISK_LABEL, STATUS_LABEL: STATUS_LABEL, AREA_LABEL: AREA_LABEL
  };
})();
