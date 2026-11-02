/* Dashboard: overall health, quick actions, the nine areas, live system, key figures and insights. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var REFRESH_MS = 60000;
  var QUICK = [
    ["playbook:quick", "Quick tune-up", "bolt", "cleanup", true],
    ["performance.free_memory", "Free standby memory", "memory", "performance"],
    ["network.flush_dns", "Flush DNS cache", "network", "network"],
    ["security.update_signatures", "Update signatures", "security", "security"],
    ["performance.restart_explorer", "Restart Explorer", "explorer", "services"],
    ["security.restore_point", "Create restore point", "shield", "integrity"]
  ];

  function volumeC(system) {
    var vols = system.volumes || [];
    return vols.filter(function (v) { return v.letter === "C"; })[0] || vols[0] || {};
  }
  function verdict(score) {
    if (score == null) return ["Not assessed yet", "Run a full scan to assess this PC."];
    if (score >= 85) return ["This PC is in good shape", "Only minor improvements are suggested."];
    if (score >= 65) return ["This PC needs attention", "Some areas have issues worth fixing during this visit."];
    return ["This PC needs maintenance", "Several areas have significant problems."];
  }
  function section(iconName, text, extra) {
    return '<div class="section-title">' + UI.icon(iconName) + esc(text) + (extra ? '<span class="extra">' + extra + "</span>" : "") + "</div>";
  }

  window.Pages.dashboard = {
    title: "Dashboard",
    render: function (el, App) {
      return Promise.all([API.get("/dashboard"), API.get("/activity")]).then(function (r) {
        var d = r[0], act = r[1];
        var s = d.system || {}, os = s.os || {}, mem = s.memory || {}, st = s.stability || {}, h = d.highlights || {};
        var c = volumeC(s), cFree = c.total_gb ? Math.round(100 * c.free_gb / c.total_gb) : null;
        var memFree = mem.total_gb ? Math.round(100 * mem.free_gb / mem.total_gb) : null;
        var scanned = UI.AREAS.filter(function (a) { return d.scores[a] != null; });
        App.setSubtitle(os.name ? os.name + " · build " + os.build : "");

        if (!scanned.length) {
          el.innerHTML = '<section class="card"><div class="empty-state">' + UI.icon("dashboard") +
            "<h2>Welcome to Windows Maintenance Manager</h2><p>Run the first full scan to assess performance, storage, security, updates, network and more. " +
            "It takes one to three minutes and changes nothing on this PC.</p>" +
            '<button class="btn btn-primary btn-lg" id="first-scan" type="button">' + UI.icon("refresh") + "Run the first full scan</button></div></section>";
          el.querySelector("#first-scan").addEventListener("click", App.scanAll);
          return;
        }

        var v = verdict(d.scores.overall), byImpact = d.issues_by_impact || {};
        var auto = Components.store("dashAuto") !== false;
        var toolbar = '<div class="dash-toolbar"><span>Updated ' + esc(new Date().toLocaleTimeString()) + " · oldest area scan " +
          esc(UI.relative(scanned.map(function (a) { return d.scanned[a]; }).sort()[0])) + '</span><label><span class="switch"><input type="checkbox" id="dash-auto"' + (auto ? " checked" : "") +
          '><span></span></span>Auto-refresh every minute</label></div>';

        var quick = '<div class="quick-grid">' + QUICK.map(function (q) {
          return '<button type="button" class="quick' + (q[4] ? " quick-primary" : "") + '" data-quick="' + q[0] + '" data-area="' + q[3] + '"><span class="tile-icon">' + UI.icon(q[2]) +
            "</span><span>" + esc(q[1]) + "</span></button>";
        }).join("") + "</div>";
        var hero = '<section class="card hero"><div>' + Charts.gauge(d.scores.overall, { label: "Overall health" }) + '</div><div><div class="hero-title">' + esc(v[0]) +
          '</div><div class="hero-text">' + esc(v[1]) + " " + scanned.length + " of " + UI.AREAS.length + " areas assessed.</div>" +
          '<div class="hero-chips"><span class="pill pill-' + (byImpact.high ? "warning" : "ok") + '">' + (byImpact.high || 0) + " high impact</span>" +
          '<span class="pill pill-info">' + (byImpact.medium || 0) + " medium</span><span class=\"pill pill-info\">" + (byImpact.low || 0) + " low</span></div>" +
          '<div class="hero-meta"><div><b>' + d.open_issues + "</b>open improvements</div><div><b>" + (d.activity || []).length + "</b>actions recorded</div><div><b>" +
          act.schedules.length + "</b>upcoming schedules</div></div></div>" +
          '<div class="hero-actions"><div class="kpi-title" style="margin-bottom:4px">Quick actions</div>' + quick + "</div></section>";

        var tiles = '<div class="tiles">' + UI.AREAS.map(function (a) {
          var score = d.scores[a], tone = score == null ? "none" : UI.tone(score);
          var trend = (d.trends[a] || []).map(function (p) { return p.score; });
          var issues = d.recommendations.filter(function (x) { return x.area === a; });
          var color = score == null ? "var(--border-strong)" : Charts.scoreTone(score);
          return '<a class="tile" href="#/' + a + '" data-area="' + a + '"><div class="tile-head"><span class="tile-icon">' + UI.icon(a) + '</span><span class="tile-name-wrap"><span class="tile-name">' +
            esc(UI.AREA_LABEL[a]) + '</span><span class="tile-sub">' + (d.scanned[a] ? "Scanned " + esc(UI.relative(d.scanned[a])) : "Not scanned yet") + "</span></span>" +
            '<span class="tile-score ' + tone + '">' + (score == null ? "—" : Components.num(score)) + "</span></div>" +
            '<div class="tile-bar"><div style="width:' + (score || 0) + "%;background:" + color + '"></div></div>' +
            '<div class="tile-foot"><span class="tile-issue">' + (issues.length ? esc(issues[0].title) : score == null ? "Scan to assess" : "No open issues") + "</span>" +
            Charts.sparkline(trend, { color: color }) + "</div></a>";
        }).join("") + "</div>";

        var live = '<div class="mini-live">' + [["cpu", "Processor", "cpu", "#2563EB"], ["mem", "Memory", "memory", "#7C3AED"], ["disk", "Disk", "storage", "#D97706"], ["net", "Network", "network", "#0E9F6E"]].map(function (k) {
          return '<section class="card live-card"><div class="live-head"><span class="kpi-title">' + UI.icon(k[2]) + esc(k[1]) + '</span><span class="badge badge-status-info">Live</span></div>' +
            '<div class="live-value" id="dl-' + k[0] + '">–</div><div class="live-sub" id="dl-' + k[0] + '-sub">Waiting for data…</div><div class="live-chart" id="dl-' + k[0] + '-chart"></div></section>';
        }).join("") + "</div>";

        var kpis = '<div class="grid grid-6">' +
          UI.kpi("Free on C:", c.free_gb != null ? Components.num(c.free_gb) + " <small>GB</small>" : "—", cFree != null ? cFree + "% of " + esc(c.total_gb) + " GB" : "", UI.toneOf(cFree, 25, 15)) +
          UI.kpi("Free memory", mem.free_gb != null ? Components.num(mem.free_gb) + " <small>GB</small>" : "—", memFree != null ? memFree + "% of " + esc(mem.total_gb) + " GB" : "", UI.toneOf(memFree, 20, 10)) +
          UI.kpi("Uptime", os.uptime_hours != null ? (os.uptime_hours >= 48 ? Components.num(Math.round(os.uptime_hours / 24)) + " <small>days</small>" : Components.num(os.uptime_hours) + " <small>h</small>") : "—",
            s.reboot_pending ? "Restart pending" : "No restart pending", s.reboot_pending || os.uptime_hours >= 168 ? "warning" : "info") +
          UI.kpi("Recoverable", h.recoverable_bytes != null ? esc(UI.formatBytes(h.recoverable_bytes)) : "—", "Temporary files and caches", "info") +
          UI.kpi("Pending updates", h.pending_updates != null ? Components.num(h.pending_updates) : "—", h.pending_updates == null ? "Scan Updates & Drivers" : "Windows Update", h.pending_updates ? "warning" : h.pending_updates == null ? "" : "ok") +
          UI.kpi("Startup programs", h.startup_enabled != null ? Components.num(h.startup_enabled) : (os.startup_items != null ? Components.num(os.startup_items) : "—"),
            h.security_issues + " security finding(s)", h.startup_enabled > 12 ? "warning" : "info") + "</div>";

        var keyAreas = ["performance", "storage", "security", "updates"].filter(function (a) { return (d.trends[a] || []).length; });
        if (!keyAreas.length) keyAreas = scanned.slice(0, 4);
        var trendSeries = keyAreas.map(function (a) {
          return { name: UI.AREA_LABEL[a], color: Charts.PALETTE[UI.AREAS.indexOf(a) % Charts.PALETTE.length], points: (d.trends[a] || []).map(function (p) { return { x: p.created, y: p.score }; }) };
        });
        var trend = Charts.line(trendSeries, { min: 0, max: 100, height: 230 }) + '<div class="series-key">' + trendSeries.map(function (t) {
          return '<span><span class="swatch" style="background:' + t.color + '"></span>' + esc(t.name) + "</span>";
        }).join("") + "</div>";
        var counts = {};
        (d.activity || []).forEach(function (x) { var k = String(x.started).slice(0, 10); counts[k] = (counts[k] || 0) + 1; });
        var heat = Charts.heatmap(counts, { weeks: 22 }) + '<p class="muted small" style="margin:10px 0 0">' + (d.activity || []).length + " actions recorded on this device.</p>";

        var areaScores = Charts.hbars(scanned.map(function (a) { return { label: UI.AREA_LABEL[a], value: d.scores[a], color: Charts.scoreTone(d.scores[a]) }; })
          .sort(function (x, y) { return x.value - y.value; }), { format: function (x) { return x + " / 100"; } });

        var sec = s.security || {};
        var health = UI.checklist([
          ["Real-time protection", sec.defender === true ? "ok" : sec.defender === false ? "error" : "skipped", sec.defender === true ? "On" : sec.defender === false ? "Off" : "Unknown"],
          ["Firewall", sec.firewall_off ? "error" : "ok", sec.firewall_off ? "Off on a profile" : "On"],
          ["Unexpected shutdowns (30 days)", st.unexpected_shutdowns ? "warning" : "ok", String(st.unexpected_shutdowns || 0)],
          ["Hardware errors (WHEA)", st.whea ? "error" : "ok", String(st.whea || 0)],
          ["Pending restart", s.reboot_pending ? "warning" : "ok", s.reboot_pending ? "Yes" : "No"]
        ]);
        var storageSeries = c.total_gb ? [{ label: "Used", value: Math.round((c.total_gb - c.free_gb) * 10) / 10, color: "#2563EB" }, { label: "Free", value: c.free_gb, color: "#9CC5EA" }] : [];
        var gb = function (x) { return x + " GB"; };
        var storage = storageSeries.length ? '<div class="chart-row">' + Charts.donut(storageSeries, { center: (100 - cFree) + "%", sub: "used on C:", format: gb }) +
          Charts.legend(storageSeries, { format: gb }) + "</div>" : Charts.empty("No volume data");
        var network = (h.network || []).length ? Charts.hbars(h.network.map(function (t) {
          return { label: t.name + (t.lost ? " (" + t.lost + " lost)" : ""), value: t.avg, color: t.lost ? "#C42B1C" : "#0E9F6E" };
        }), { format: function (x) { return x + " ms"; } }) : '<p class="empty">Scan the Network area to measure latency.</p>';
        var info = UI.definition([
          ["Operating system", esc(os.name) + (os.build ? " (" + esc(os.build) + ")" : "")], ["Processor", esc(os.cpu)],
          ["Motherboard", esc(os.board)], ["Firmware", esc(os.bios) + (os.bios_date ? " · " + esc(os.bios_date) : "")],
          ["Graphics", esc((s.gpu || {}).name)], ["Memory", mem.total_gb != null ? esc(mem.total_gb) + " GB" : null]
        ]);
        var upcoming = act.schedules.length ? '<ul class="check-list">' + act.schedules.slice(0, 4).map(function (x) {
          return '<li><span class="status-icon skipped">' + UI.icon("clock") + '</span><span class="grow"><span class="cell-title">' + esc(x.title) + '</span><br><span class="cell-sub">' +
            esc(UI.formatDate(x.next_run)) + "</span></span></li>";
        }).join("") + "</ul>" : '<p class="empty">No upcoming schedule.</p>';
        var title = function (id) { var a = App.action(id); return a ? a.title : id; };

        el.innerHTML = toolbar + hero +
          section("dashboard", "Health by area", scanned.length + " of " + UI.AREAS.length + " assessed") + tiles +
          section("performance", "Live system", '<a href="#/performance">Open Performance</a>') + live +
          section("gauge", "Key figures") + kpis +
          section("sparkle", "Insights") +
          '<div class="grid grid-2-1">' + UI.card("Top recommended improvements", UI.recommendations(d.recommendations.slice(0, 6), { showArea: true }),
            '<a class="btn btn-sm" href="#/recommendations">View all ' + d.open_issues + "</a>") + UI.card("Scores by area", areaScores) + "</div>" +
          '<div class="grid grid-2-1">' + UI.card("Score trend · key areas", trend) + UI.card("Activity · last 22 weeks", heat) + "</div>" +
          section("cpu", "System & operations") +
          '<div class="grid grid-3">' + UI.card("Security & stability", health) + UI.card("Storage", storage) + UI.card("Network latency", network) + "</div>" +
          '<div class="grid grid-3">' + UI.card("System", info) + UI.card("Up next", upcoming, '<a class="btn btn-sm" href="#/activity">Activity</a>') +
          UI.card("Recent activity", UI.runsTable(d.runs.slice(0, 6), title), '<a class="btn btn-sm" href="#/history">History</a>', "card-flush") + "</div>";

        el.querySelectorAll("[data-quick]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var id = btn.getAttribute("data-quick");
            if (id.indexOf("playbook:") === 0) {
              API.get("/playbooks").then(function (p) {
                var book = p.playbooks.filter(function (b) { return b.id === id.slice(9); })[0];
                if (book) App.runActions(book.actions);
              });
            } else {
              App.runActions([id]);
            }
          });
        });
        el.querySelector("#dash-auto").addEventListener("change", function (e) { Components.store("dashAuto", e.target.checked); });
        startLive(el, App);
        // App.render stops this page's timers and live loop before drawing it again.
        var timer = setTimeout(function () {
          if (App.isCurrent("dashboard") && Components.store("dashAuto") !== false) App.render();
        }, REFRESH_MS);
        App.onLeave(function () { clearTimeout(timer); });
      });
    }
  };

  function startLive(el, App) {
    var samples = [], since = 0, stopped = false, timer = null;
    function set(id, html) { var x = el.querySelector("#" + id); if (x) x.innerHTML = html; }
    function rate(b) { return UI.formatBytes(b) + "/s"; }
    function tick() {
      if (stopped) return;
      API.get("/live?since=" + since).then(function (r) {
        if (stopped || !r.samples.length) return;
        samples = samples.concat(r.samples).slice(-45);
        since = samples[samples.length - 1].t;
        var s = samples[samples.length - 1];
        set("dl-cpu", s.cpu.toFixed(0) + "<small>%</small>");
        set("dl-cpu-sub", "Top: " + esc(((s.processes.cpu || [])[0] || {}).name || "—"));
        set("dl-cpu-chart", Charts.live(samples.map(function (x) { return x.cpu; }), { max: 100, color: "#2563EB" }));
        set("dl-mem", s.memory_pct + "<small>%</small>");
        set("dl-mem-sub", s.memory_used_gb + " of " + s.memory_total_gb + " GB in use");
        set("dl-mem-chart", Charts.live(samples.map(function (x) { return x.memory_pct; }), { max: 100, color: "#7C3AED" }));
        set("dl-disk", (s.disk_busy == null ? "–" : s.disk_busy.toFixed(0)) + "<small>% busy</small>");
        set("dl-disk-sub", "R " + rate(s.disk_read) + " · W " + rate(s.disk_write));
        set("dl-disk-chart", Charts.live(samples.map(function (x) { return x.disk_read + x.disk_write; }), { color: "#D97706" }));
        set("dl-net", esc(rate(s.net_in + s.net_out)));
        set("dl-net-sub", "In " + rate(s.net_in) + " · Out " + rate(s.net_out));
        set("dl-net-chart", Charts.live(samples.map(function (x) { return x.net_in + x.net_out; }), { color: "#0E9F6E" }));
      }).catch(function () { /* try again next tick */ }).then(function () { if (!stopped) timer = setTimeout(tick, 2000); });
    }
    App.onLeave(function () { stopped = true; clearTimeout(timer); });
    tick();
  }
})();
