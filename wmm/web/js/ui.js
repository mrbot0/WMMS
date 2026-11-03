/* Shared UI building blocks. Functions return HTML strings unless noted. */
(function () {
  "use strict";

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* Preferences read on every call (Settings › Behaviour › Formats); storage may be unavailable. */
  function pref(key) { try { return JSON.parse(localStorage.getItem("wmm." + key)); } catch (e) { return null; } }

  function formatBytes(n) {
    n = Number(n) || 0;
    var base = pref("sizeUnits") === "decimal" ? 1000 : 1024;  // decimal: the sizes printed on drive boxes
    var units = ["B", "KB", "MB", "GB", "TB"], i = 0;
    while (Math.abs(n) >= base && i < units.length - 1) { n /= base; i++; }
    return (i < 2 ? Math.round(n) : n.toFixed(1)) + " " + units[i];
  }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function formatDate(iso, withTime) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return esc(iso);
    var style = pref("dateStyle") || "short", clock = pref("timeFormat") || "system";
    var day = style === "iso" ? d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate())
      : style === "numeric" ? d.toLocaleDateString(undefined, { day: "2-digit", month: "2-digit", year: "numeric" })
        : d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
    if (withTime === false) return day;
    var time = d.toLocaleTimeString(undefined, clock === "system" ? { hour: "2-digit", minute: "2-digit" }
      : { hour: "2-digit", minute: "2-digit", hour12: clock === "12" });
    return day + ", " + time;
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
  ICONS.power = '<path d="M12 3v9M6.4 6.6a8 8 0 1 0 11.2 0"/>';
  ICONS.scripts = '<path d="M4 4h16v16H4z"/><path d="M8 9l3 3-3 3M13 15h3"/>';
  ICONS.events ='<path d="M4 4h16v16H4z"/><path d="M8 9h8M8 13h5M8 17h3"/><circle cx="17" cy="16" r="2.5" fill="currentColor" stroke="none"/>';
  ICONS.processes = '<rect x="3" y="4" width="18" height="14" rx="2"/><path d="M7 14l3-4 3 3 4-5M8 21h8"/>';
  ICONS.registry = '<path d="M4 5h6v6H4zM14 5h6v6h-6zM4 15h6v4H4z"/><path d="M7 11v4M17 11v3h-7"/>';
  ICONS.toolbox ='<rect x="3" y="8" width="18" height="12" rx="2"/><path d="M8 8V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18M10 13v2h4v-2"/>';
  ICONS.upload ='<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>';
  ICONS.support ='<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5v.5"/>';
  ICONS.actions ='<circle cx="12" cy="12" r="9"/><path d="M10 8.5l5 3.5-5 3.5z"/>';
  ICONS.cleanup ='<path d="M3 21h18"/><path d="M14.5 3.5l6 6-9.5 9.5H5v-6z"/><path d="M11 7l6 6"/>';
  ICONS.services = '<rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6"/>';
  ICONS.integrity = '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5L16 9.5"/>';
  ICONS.dashboard = '<rect x="3" y="3" width="8" height="10" rx="2"/><rect x="13" y="3" width="8" height="6" rx="2"/><rect x="13" y="11" width="8" height="10" rx="2"/><rect x="3" y="15" width="8" height="6" rx="2"/>';
  ICONS.user = '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>';
  ICONS.calendar = '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/>';
  ICONS.plus = '<path d="M12 5v14M5 12h14"/>';
  ICONS.thermometer = '<path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0z"/><path d="M12 9v7"/>';
  ICONS.fan = '<circle cx="12" cy="12" r="2"/><path d="M12 10c0-4 1-7 4-7 2 0 3 2 2 4l-4 4M14 12c4 0 7 1 7 4 0 2-2 3-4 2l-4-4M12 14c0 4-1 7-4 7-2 0-3-2-2-4l4-4M10 12c-4 0-7-1-7-4 0-2 2-3 4-2l4 4"/>';
  ICONS.hardware = '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>';
  ICONS.copy = '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>';
  ICONS.globe = '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>';
  function icon(name) {
    return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || "") + "</svg>";
  }

  function tone(score) { return score >= 80 ? "ok" : score >= 60 ? "warning" : "error"; }

  function kpi(title, value, sub, toneName, extra) {
    // A name instead of a number (a power plan, an event source): smaller type that may wrap, full text on hover.
    var plain = String(value).replace(/<[^>]*>/g, "").trim(), long = plain.length > 12 && !/^[\d.,\s%]+/.test(plain);
    return '<div class="kpi' + (toneName ? " kpi-" + toneName : "") + '"><div class="kpi-title">' + esc(title) + '</div><div class="kpi-value' + (long ? " kpi-value-text" : "") + '"' +
      (long ? ' title="' + esc(plain) + '"' : "") + ">" + value +
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
  /* A small "i" next to a control: the explanation shows on hover and focus, and as a toast on click (touch screens). */
  function hint(text) {
    return '<button type="button" class="hint-dot" data-tip="' + esc(text) + '" data-hint="' + esc(text) + '" aria-label="' + esc(text) + '">i</button>';
  }
  document.addEventListener("click", function (e) {
    var h = e.target.closest && e.target.closest("[data-hint]");
    if (h) { e.preventDefault(); e.stopPropagation(); toast(h.getAttribute("data-hint"), "info"); }
  }, true);
  /* Reports only read the PC; fixes change it. */
  function kindBadge(kind) {
    return kind === "report" ? '<span class="badge badge-report" title="Read-only: changes nothing">' + icon("reports") + "Report</span>"
      : '<span class="badge badge-fix" title="Changes a setting or deletes files">' + icon("bolt") + "Fix</span>";
  }
  /* One tool card: title, description, badges, last run and the run / schedule buttons. */
  function toolCard(a, last, options) {
    options = options || {};
    return '<div class="action-card tool-card kind-' + esc(a.kind || "fix") + (options.picked ? " picked" : "") + '" data-id="' + esc(a.id) + '" tabindex="0">' +
      '<div class="action-top">' + (options.pick ? '<input type="checkbox" data-pick aria-label="Select ' + esc(a.title) + '"' + (options.picked ? " checked" : "") + ">" : "") +
      '<span class="tool-icon">' + icon(a.kind === "report" ? "reports" : a.area) + '</span><button type="button" class="cell-title grow link-btn" data-detail title="Details">' + esc(a.title) + "</button>" +
      (options.star != null ? '<button type="button" class="star' + (options.star ? " on" : "") + '" data-star title="' + (options.star ? "Remove from favorites" : "Add to favorites") +
        '" aria-pressed="' + options.star + '">★</button>' : "") + "</div>" +
      '<div class="cell-sub">' + esc(a.description) + "</div>" +
      '<div class="action-foot">' + kindBadge(a.kind) + (a.kind === "report" ? "" : riskBadge(a.risk)) + '<span class="badge">' + icon("clock") + esc(duration(a.minutes)) + "</span>" +
      (last ? statusBadge(last.status) + '<span class="cell-sub">' + esc(relative(last.finished || last.started)) + "</span>" : '<span class="cell-sub">Never run</span>') +
      '<span class="grow"></span>' + (last && last.id && a.kind === "report" ? '<button class="btn btn-sm btn-ghost" type="button" data-output="' + esc(last.id) + '" title="Last output">' + icon("reports") + "</button>" : "") +
      '<button class="btn btn-sm" data-run="' + esc(a.id) + '">' + icon("play") + 'Run</button><button class="btn btn-sm" data-schedule="' + esc(a.id) + '" title="Schedule" aria-label="Schedule ' +
      esc(a.title) + '">' + icon("clock") + "</button></div></div>";
  }
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

  var TOAST_ICON = { ok: "check", error: "x", warning: "alert", info: "info" };
  function toast(message, toneName) {
    // Settings › Behaviour › Messages: "problems" keeps only warnings and errors on screen.
    if (pref("toastLevel") === "problems" && (toneName === "ok" || toneName === "info" || !toneName)) return;
    var root = document.getElementById("toasts");
    var el = document.createElement("div");
    el.className = "toast toast-" + (toneName || "info");
    el.innerHTML = '<span class="toast-icon">' + icon(TOAST_ICON[toneName] || "info") + '</span><span class="toast-text"></span>';
    el.querySelector(".toast-text").textContent = message;
    el.title = "Click to dismiss";
    el.addEventListener("click", function () { el.classList.add("leaving"); setTimeout(function () { el.remove(); }, 300); });
    // At most four toasts on screen: the oldest gives way to the newest.
    while (root.children.length >= 4) root.removeChild(root.firstChild);
    root.appendChild(el);
    var speed = { short: 0.6, normal: 1, long: 1.8 }[window.Components ? Components.store("toastSpeed") || "normal" : "normal"] || 1;
    var visible = Math.max(4200, String(message).length * 60) * speed;  // long errors need time to be read
    // A thin bar shows the time left; hovering pauses it so a long message can be read calmly.
    el.style.setProperty("--life", visible + "ms");
    var timers = [];
    function arm(ms) {
      timers = [setTimeout(function () { el.classList.add("leaving"); }, ms), setTimeout(function () { el.remove(); }, ms + 400)];
    }
    el.addEventListener("mouseenter", function () { timers.forEach(clearTimeout); el.classList.add("paused"); });
    el.addEventListener("mouseleave", function () { el.classList.remove("paused"); arm(2500); });
    arm(visible);
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

  var DAY_NAME = { MON: "Mon", TUE: "Tue", WED: "Wed", THU: "Thu", FRI: "Fri", SAT: "Sat", SUN: "Sun" };
  var KINDS = [["once", "Once"], ["daily", "Every day"], ["weekly", "Every week"], ["monthly", "Every month"],
    ["startup", "At every startup"], ["logon", "At every sign-in"]];
  var EVENT_KINDS = { startup: 1, logon: 1 };

  /* The frequency of a schedule (actions, routines and scripts) in plain words. */
  function scheduleText(s) {
    if (!s) return "Not scheduled";
    var at = s.at.replace("T", " "), t = at.slice(11), delay = +s.delay || 0;
    var after = delay ? ", after " + delay + " min" : "";
    if (s.kind === "startup") return "At every startup" + after;
    if (s.kind === "logon") return "At every sign-in" + after;
    if (s.kind === "once") return "Once on " + at;
    if (s.kind === "daily") return "Every day at " + t;
    if (s.kind === "monthly") return "Every month on day " + (+at.slice(8, 10)) + " at " + t;
    return "Every " + (s.days || "").split(",").map(function (d) { return DAY_NAME[d] || d; }).join(", ") + " at " + t;
  }

  /* action: {title, description, risk, warning, suggested: {kind, time, days, day, delay}, label} */
  function scheduleDialog(action) {
    var sug = action.suggested || {};
    var d = new Date(Date.now() + 3600e3);
    if (sug.kind === "monthly" && sug.day) {
      var m = new Date(d.getFullYear(), d.getMonth(), sug.day);
      if (m < new Date()) m = new Date(d.getFullYear(), d.getMonth() + 1, sug.day);
      d = m;
    }
    var date = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
    var kind = sug.kind || "once", selDays = (sug.days || "MON").split(",");
    // Settings › Maintenance: default time and wait when the action brings no suggestion of its own.
    // "Once" starts an hour from now (rounded to the quarter): a fixed time of day would often be in the past already.
    // The other frequencies use Settings › Maintenance, or midday, when most PCs are on (at night many are off or asleep).
    var soon = new Date(Math.ceil((Date.now() + 3600e3) / 900e3) * 900e3), soonTime = pad(soon.getHours()) + ":" + pad(soon.getMinutes());
    if (!sug.time) sug = Object.assign({}, sug, { time: kind === "once" ? soonTime : pref("defaultTime") || "12:00" });
    if (sug.delay == null && pref("defaultDelay") != null) sug = Object.assign({}, sug, { delay: pref("defaultDelay") });
    var warning = action.risk !== "safe"
      ? '<div class="callout callout-warning">' + icon("info") + "<div><strong>" + esc(RISK_LABEL[action.risk]) + " action.</strong> " + esc(action.warning) +
        ' A restore point is created before every run.<label class="check"><input type="checkbox" name="confirmed"> I understand and want to schedule this action</label></div></div>'
      : '<div class="callout">' + icon("shield") + "<div>Safe action: it runs unattended without confirmation.</div></div>";
    var body = '<p class="modal-text"><strong>' + esc(action.title) + "</strong><br><span class=\"muted\">" + esc(action.description) + "</span></p>" +
      '<form class="form" onsubmit="return false">' +
      '<label>Frequency<select name="kind">' + KINDS.map(function (k) {
        return '<option value="' + k[0] + '"' + (k[0] === kind ? " selected" : "") + ">" + k[1] + "</option>";
      }).join("") + "</select></label>" +
      '<div class="form-row"><label><span class="date-label">Start date</span><input type="date" name="date" value="' + date + '" required></label>' +
      '<label class="time-field">Time<input type="time" name="time" value="' + esc(sug.time || "03:00") + '" required></label>' +
      '<label class="delay-field" hidden>Wait after the event<select name="delay">' + [0, 1, 2, 5, 10, 15, 30, 60].map(function (n) {
        return '<option value="' + n + '"' + (n === (+sug.delay || 0) ? " selected" : "") + ">" + (n ? n + " min" : "No wait") + "</option>";
      }).join("") + "</select></label></div>" +
      '<fieldset class="days" hidden><legend>Days</legend>' + DAYS.map(function (day) {
        return '<label class="chip"><input type="checkbox" name="day" value="' + day[0] + '"' + (selDays.indexOf(day[0]) >= 0 ? " checked" : "") + "><span>" + day[1] + "</span></label>";
      }).join("") + "</fieldset>" +
      '<p class="muted small kind-note"></p>' + warning +
      '<p class="muted small">The schedule is registered in Windows Task Scheduler and runs even when this console is closed.</p></form>';
    var promise = modal(action.label || "Schedule action", body, [
      { label: "Cancel", cls: "btn-ghost" },
      { label: "Create schedule", cls: "btn-primary", value: function (wrap) {
        var form = wrap.querySelector("form");
        var days = Array.prototype.map.call(form.querySelectorAll('input[name="day"]:checked'), function (i) { return i.value; });
        var confirmed = form.querySelector('input[name="confirmed"]');
        var k = form.kind.value, ev = !!EVENT_KINDS[k];
        return {
          kind: k, at: form.date.value + "T" + (ev ? "00:00" : form.time.value), days: k === "weekly" ? days.join(",") : "",
          delay: ev ? +form.delay.value : 0,
          confirmed: action.risk === "safe" ? false : !!(confirmed && confirmed.checked)
        };
      } }
    ]);
    var form = document.querySelector("#modal-root form");
    if (form) {
      var NOTES = {
        startup: "Runs a little after Windows starts, before anyone signs in. The wait lets the PC finish starting.",
        logon: "Runs when any user signs in. A short wait keeps the desktop responsive.",
        monthly: "Runs on the day of the start date every month (days 1 to 28, so no month is skipped)."
      };
      var now = new Date(), today = now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
      var sync = function () {
        var k = form.kind.value, ev = !!EVENT_KINDS[k];
        if (ev && form.date.value > today) form.date.value = today;  // a startup routine is active from today unless chosen otherwise
        if (k === "once" && new Date(form.date.value + "T" + form.time.value) < new Date()) {
          form.date.value = soon.getFullYear() + "-" + pad(soon.getMonth() + 1) + "-" + pad(soon.getDate());
          form.time.value = soonTime;
        }
        form.querySelector(".days").hidden = k !== "weekly";
        form.querySelector(".time-field").hidden = ev;
        form.querySelector(".delay-field").hidden = !ev;
        form.querySelector(".date-label").textContent = ev ? "Active from" : k === "monthly" ? "First run (sets the day)" : "Start date";
        form.querySelector(".kind-note").textContent = NOTES[k] || "";
      };
      form.kind.addEventListener("change", sync);
      sync();
    }
    return promise;
  }

  /* Why schedules are disabled on this copy, in plain words, with the automatic fix. */
  function installCallout(inst) {
    if (!inst || inst.protected) return "";
    var cause = !inst.python_protected && inst.program_protected
      ? "The program is protected, but the console runs with a Python that standard users can change (<code>" + esc(inst.python) + "</code>). " +
        "Scheduled actions run as SYSTEM, so a per-user Python, such as the Microsoft Store one, is not safe for them and may not start at all."
      : !inst.program_protected && inst.python_protected
        ? "The program runs from a folder that standard users can change (<code>" + esc(inst.writable[0] || "") + "</code>). Scheduled actions run as SYSTEM, so it must live in Program Files."
        : "Both the program folder and the Python it runs with can be changed by standard users. Scheduled actions run as SYSTEM, so neither is safe for them.";
    var fix = "<strong>Fix automatically</strong> uses a Python installed for all users, or installs one (winget or the signed python.org installer), " +
      "moves the program to Program Files if needed, registers the schedules again and restarts the console with it.";
    return '<div class="callout callout-warning install-callout">' + icon("shield") + "<div><strong>Schedules are disabled on this copy.</strong> " + cause +
      '<p class="small" style="margin:8px 0 10px">' + fix + "</p>" +
      (inst.can_fix ? button("Fix automatically", "data-fix-install", "btn-primary btn-sm", "bolt")
        : '<span class="muted small">Restart the console as administrator to fix it.</span>') + "</div></div>";
  }

  function loading(text) {
    return '<div class="loading"><span class="spinner"></span>' + esc(text || "Loading…") + "</div>";
  }
  function errorBox(error) {
    return '<div class="callout callout-error">' + icon("info") + "<div><strong>Something went wrong.</strong> " + esc(error && error.message || error) + "</div></div>";
  }
  /* Every page header ends with a star that pins the page to the dashboard (Extras.togglePin). */
  function pageHeader(title, sub, buttons) {
    var page = (location.hash.replace(/^#\/?/, "").split("?")[0] || "dashboard");
    var pinned = (pref("pinnedPages") || []).indexOf(page) >= 0;
    var pin = page === "dashboard" ? "" : '<button type="button" class="btn btn-ghost pin-page' + (pinned ? " pinned" : "") + '" data-pin-page="' + esc(page) +
      '" aria-pressed="' + pinned + '" title="' + (pinned ? "Unpin from the dashboard" : "Pin to the dashboard") + '">' + (pinned ? "★" : "☆") + "</button>";
    return '<div class="page-head"><div><div class="page-kicker">' + esc(sub || "") + '</div></div><div class="page-actions">' + (buttons || "") + pin + "</div></div>";
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
    // "Apply safe actions" only where a safe fix exists: reports are never part of it.
    var hasSafe = view.actions.some(function (a) { return a.risk === "safe" && a.kind !== "report"; });
    var noActions = !view.actions.length;
    var reportIds = view.actions.filter(function (a) { return a.kind === "report"; }).map(function (a) { return a.id; });
    lastViews[area] = view;
    var ageDays = view.created ? (Date.now() - new Date(view.created).getTime()) / 86400e3 : 0;
    var stale = ageDays >= STALE_DAYS ? '<div class="callout callout-warning stale-scan">' + icon("clock") + "<div><strong>This scan is " + Math.floor(ageDays) +
      " days old.</strong> The figures below may no longer match the PC.</div>" + button("Scan now", 'data-scan-area="' + area + '"', "btn-sm btn-primary", "refresh") + "</div>" : "";
    // Change since the previous scan, from the score trend.
    var tr = view.trend || [], delta = tr.length > 1 ? tr[tr.length - 1].score - tr[tr.length - 2].score : 0;
    var change = delta ? " · " + (delta > 0 ? "▲ +" : "▼ ") + delta + " since the previous scan" : "";
    var header = pageHeader(AREA_LABEL[area], "Last scan " + relative(view.created) + " · " + formatDate(view.created) + change,
      button("Copy summary", 'data-copy-area="' + area + '" title="Score, improvements and recent runs as text, for a ticket"', "", "copy") +
      button("", 'data-save-area="' + area + '" title="Download the summary as a .txt file" aria-label="Download the summary"', "", "download") +
      button("Scan", 'data-scan-area="' + area + '"', "", "refresh") +
      (hasSafe ? button("Apply safe actions", 'data-safe-area="' + area + '" title="Runs every safe fix of this area at once; reports and risky actions are left out"', "", "bolt") : "") +
      button("Export report", 'data-export-area="' + area + '"', "btn-primary", "download"));
    var group = function (label, iconName, hint, list) {
      return list.length ? '<div class="section-title">' + icon(iconName) + esc(label) + '<span class="extra">' + esc(hint) + "</span></div>" +
        '<div class="action-grid">' + list.map(function (a) { return toolCard(a, a.last_run); }).join("") + "</div>" : "";
    };
    var actionsTable = group("Fixes", "bolt", "Change settings or delete files; non-safe ones ask first and create a restore point.",
      view.actions.filter(function (a) { return a.kind !== "report"; })) +
      group("Diagnostics", "reports", "Read-only reports: nothing on the PC changes.", view.actions.filter(function (a) { return a.kind === "report"; }));
    var trend = Charts.line([{ name: AREA_LABEL[area] + " score", points: view.trend.map(function (p) { return { x: p.created, y: p.score }; }) }], { min: 0, max: 100 });
    return {
      header: header,
      score: Charts.gauge(view.score, { label: AREA_LABEL[area] + " score" }),
      recommendations: card("Recommended improvements", recommendations(view.recommendations), '<span class="muted small">' + view.recommendations.length + " found</span>"),
      actions: noActions ? "" : card("Optimization actions", actionsTable, '<span class="muted small">' + view.actions.length + " tools</span>" +
        (reportIds.length ? '<button type="button" class="btn btn-sm" data-run-reports="' + esc(reportIds.join(",")) + '">' + icon("reports") + "Run all diagnostics</button>" : "") +
        '<a class="btn btn-sm btn-ghost" href="#/toolbox?area=' + area + '">' + icon("explorer") + "Toolbox</a>"),
      trend: card("Score trend", trend),
      runs: card("Recent activity", runsTable(view.runs.slice(0, 8), title), '<a class="btn btn-sm" href="#/history?area=' + area + '">' + icon("history") + "All runs of this area</a>"),
      errors: stale + (view.data.errors && view.data.errors.length
        ? '<div class="callout callout-error">' + icon("info") + "<div><strong>Scan incomplete: some data could not be read.</strong> " + esc(view.data.errors.join(" · ")) + "</div></div>" :
        (view.data.warnings && view.data.warnings.length
          ? '<div class="callout callout-warning">' + icon("info") + "<div>" + esc(view.data.warnings.join(" · ")) + "</div></div>" : ""))
    };
  }

  var STALE_DAYS = 7;
  var lastViews = {};
  /* The area as plain text: score, open improvements and the latest runs. */
  function areaSummary(area) {
    var v = lastViews[area];
    if (!v) return "";
    var title = function (id) { var a = window.App && App.action(id); return a ? a.title : id; };
    var lines = [AREA_LABEL[area] + " · score " + v.score + "/100 · scanned " + formatDate(v.created)];
    if (v.recommendations.length) {
      lines.push("", "Open improvements:");
      v.recommendations.forEach(function (r) { lines.push("- [" + (r.impact || "").toUpperCase() + "] " + r.title + (r.reason ? ": " + r.reason : "")); });
    } else lines.push("", "No open improvements.");
    if (v.runs.length) {
      lines.push("", "Recent runs:");
      v.runs.slice(0, 8).forEach(function (r) { lines.push("- " + formatDate(r.started) + " · " + title(r.action_id) + " · " + (STATUS_LABEL[r.status] || r.status)); });
    }
    return lines.join("\n");
  }

  /* Tabs for long pages: the page's blocks are grouped in order (overview first, detail last) and one group is shown.
     groups: [{id, label, icon, match(node) -> bool}]. A block that matches no group stays in the group before it;
     with options.sharedHead the blocks before the first match (figures, warnings) stay visible above the tabs.
     Children of an element marked data-tab-host are grouped one by one; data-tab-group="id" assigns a block directly. */
  function pageTabs(container, key, groups, options) {
    options = options || {};
    if (!container || window.matchMedia("print").matches) return;
    // Drawn again (a page that reloads part of itself): the old bar goes, the blocks are grouped afresh.
    Array.prototype.slice.call(container.querySelectorAll(".page-tabs")).forEach(function (b) { b.remove(); });
    var nodes = [];
    Array.prototype.forEach.call(container.children, function (n) {
      if (n.classList.contains("page-head") || n.classList.contains("page-pager") || n.classList.contains("page-tabs")) return;
      if (n.hasAttribute("data-tab-host")) Array.prototype.forEach.call(n.children, function (c) { nodes.push(c); }); else nodes.push(n);
    });
    var current = options.sharedHead ? null : groups[0].id, owner = [], anchor = null;
    nodes.forEach(function (n) {
      var direct = n.getAttribute("data-tab-group");
      var hit = direct ? direct : (groups.filter(function (g) { return g.match && g.match(n); })[0] || {}).id;
      if (hit) current = hit;
      if (!current && !anchor) return;  // shared head: stays above the tabs
      if (!anchor) anchor = n;
      owner.push([n, current || groups[0].id]);
    });
    if (!owner.length) return;
    var used = groups.filter(function (g) { return owner.some(function (o) { return o[1] === g.id; }); });
    if (used.length < 2) return;  // one group only: no tabs needed
    var active = pref("tab." + key);
    if (!used.some(function (g) { return g.id === active; })) active = used[0].id;
    var bar = document.createElement("div");
    bar.className = "tabs page-tabs";
    bar.setAttribute("role", "tablist");
    bar.innerHTML = used.map(function (g) {
      return '<button type="button" role="tab" class="tab" data-page-tab="' + g.id + '" aria-selected="' + (g.id === active) + '" tabindex="' + (g.id === active ? 0 : -1) + '">' +
        (g.icon ? icon(g.icon) : "") + "<span>" + esc(g.label) + "</span></button>";
    }).join("");
    anchor.parentNode.insertBefore(bar, anchor);
    function show(id) {
      active = id;
      try { localStorage.setItem("wmm.tab." + key, JSON.stringify(id)); } catch (e) { /* storage unavailable */ }
      owner.forEach(function (o) { o[0].classList.toggle("tab-hidden", o[1] !== id); });
      bar.querySelectorAll("[data-page-tab]").forEach(function (b) {
        var on = b.getAttribute("data-page-tab") === id;
        b.setAttribute("aria-selected", String(on));
        b.tabIndex = on ? 0 : -1;
      });
      if (window.FX && FX.pageEnter) owner.forEach(function (o) { if (o[1] === id) FX.pageEnter(o[0]); });
    }
    bar.addEventListener("click", function (e) { var b = e.target.closest("[data-page-tab]"); if (b) show(b.getAttribute("data-page-tab")); });
    bar.addEventListener("keydown", function (e) {
      var tabs = Array.prototype.slice.call(bar.querySelectorAll("[data-page-tab]")), i = tabs.indexOf(document.activeElement);
      var next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
      if (i < 0 || next == null) return;
      e.preventDefault();
      var t = tabs[(next + tabs.length) % tabs.length];
      t.focus();
      show(t.getAttribute("data-page-tab"));
    });
    show(active);
    return { show: show };
  }
  function hasCard(title) { return function (n) { return !!n.querySelector('[data-card$="|' + title + '"]') || (n.getAttribute("data-card") || "").slice(-title.length - 1) === "|" + title; }; }
  /* The tabs of every area page: what the area looks like, what to improve, the tools, what happened. */
  var AREA_TABS = [
    { id: "overview", label: "Overview", icon: "dashboard" },
    { id: "improve", label: "Improvements", icon: "recommendations", match: hasCard("Recommended improvements") },
    { id: "tools", label: "Tools", icon: "toolbox", match: hasCard("Optimization actions") },
    { id: "history", label: "History", icon: "history", match: function (n) { return hasCard("Score trend")(n) || hasCard("Recent activity")(n); } }
  ];

  function bindArea(el, area, rerender) {
    if (pref("pageTabs") !== false) pageTabs(el, "area", AREA_TABS);
    el.querySelectorAll("[data-scan-area]").forEach(function (scan) {
      scan.addEventListener("click", function () {
        scan.disabled = true;
        scan.classList.add("busy");
        API.post("/areas/" + area + "/scan").then(function () { UI.toast("Scan completed.", "ok"); rerender(); },
          function (e) { UI.toast(e.message, "error"); scan.disabled = false; scan.classList.remove("busy"); });
      });
    });
    var copy = el.querySelector("[data-copy-area]");
    if (copy) copy.addEventListener("click", function () { App.copyText(areaSummary(area), AREA_LABEL[area] + " summary"); });
    var save = el.querySelector("[data-save-area]");
    if (save) save.addEventListener("click", function () {
      App.saveText(areaSummary(area), "wmm-" + area + "-" + new Date().toISOString().slice(0, 10) + ".txt");
    });
    var safe = el.querySelector("[data-safe-area]");
    if (safe) safe.addEventListener("click", function () { App.runSafe(area); });
    var exp = el.querySelector("[data-export-area]");
    if (exp) exp.addEventListener("click", function () { Report.download(area); });
  }

  window.UI = {
    runsTable: runsTable, areaParts: areaParts, bindArea: bindArea, areaSummary: areaSummary, ORIGIN_LABEL: ORIGIN_LABEL, pref: pref,
    pageTabs: pageTabs, hasCard: hasCard,
    AREAS: AREAS, statusIcon: statusIcon, checklist: checklist, toneOf: toneOf,
    esc: esc, formatBytes: formatBytes, formatDate: formatDate, relative: relative, duration: duration, icon: icon, tone: tone,
    kpi: kpi, card: card, table: table, definition: definition, riskBadge: riskBadge, statusBadge: statusBadge, impactBadge: impactBadge,
    kindBadge: kindBadge, toolCard: toolCard, installCallout: installCallout, hint: hint,
    recommendations: recommendations, toast: toast, modal: modal, confirm: confirm, scheduleDialog: scheduleDialog, scheduleText: scheduleText,
    loading: loading, errorBox: errorBox, pageHeader: pageHeader, button: button,
    RISK_LABEL: RISK_LABEL, STATUS_LABEL: STATUS_LABEL, AREA_LABEL: AREA_LABEL
  };
})();
