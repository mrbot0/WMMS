/* Performance: live monitor (CPU, memory, disk, network, processes) and tuning settings. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var WINDOW = 90;  // samples kept on screen (3 minutes at 2 s)
  var PLAN = { balanced: "Balanced", high: "High performance", saver: "Power saver", ultimate: "Ultimate performance", custom: "Custom", unknown: "Unknown" };
  var VISUAL = { 0: "Let Windows choose", 1: "Best appearance", 2: "Best performance", 3: "Custom" };

  function rate(bytes) { return UI.formatBytes(bytes) + "/s"; }

  window.Pages.performance = {
    title: "Performance",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/performance").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "performance"), m = d.memory || {}, cpu = d.cpu || {}, pf = d.pagefile || {}, power = d.power || {};
        App.setSubtitle("Live resource usage, power and responsiveness settings");

        var live = '<div class="grid grid-4">' + [
          ["cpu", "Processor", "cpu"], ["mem", "Memory", "memory"], ["disk", "Disk", "storage"], ["net", "Network", "network"]
        ].map(function (k) {
          return '<section class="card live-card"><div class="live-head"><span class="kpi-title">' + UI.icon(k[2]) + esc(k[1]) +
            '</span><span class="badge badge-status-info">Live</span></div><div class="live-value" id="live-' + k[0] + '">–</div>' +
            '<div class="live-sub" id="live-' + k[0] + '-sub">Waiting for the first sample…</div><div class="live-chart" id="live-' + k[0] + '-chart"></div></section>';
        }).join("") + "</div>";

        var procs = '<div class="grid grid-2">' + UI.card("Top processes by CPU · live", '<div id="live-proc-cpu"><p class="empty">Waiting for the first sample…</p></div>', "", "card-flush") +
          UI.card("Top processes by memory · live", '<div id="live-proc-mem"><p class="empty">Waiting for the first sample…</p></div>', "", "card-flush") + "</div>";

        var history = UI.card("CPU and memory · last 3 minutes", '<div id="live-history">' + Charts.empty("Collecting samples…", 200) + "</div>" +
          '<div class="series-key"><span><span class="swatch" style="background:#0F6CBD"></span>CPU %</span><span><span class="swatch" style="background:#8764B8"></span>Memory %</span>' +
          '<span><span class="swatch" style="background:#C27C0E"></span>Disk busy %</span></div>');

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Performance score", Components.num(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Power plan", esc(PLAN[power.plan] || power.name || "Unknown"), d.battery ? "Battery present" : "Desktop / no battery", power.plan === "saver" ? "warning" : "info") +
          UI.kpi("Commit charge", Components.num(m.commit_used_gb) + " <small>/ " + esc(m.commit_limit_gb) + " GB</small>", m.commit_pct + "% of the limit", UI.toneOf(m.commit_pct, 80, 90, true)) +
          UI.kpi("Uptime", d.uptime_hours != null ? (d.uptime_hours >= 48 ? Components.num(Math.round(d.uptime_hours / 24)) + " <small>days</small>" : Components.num(d.uptime_hours) + " <small>h</small>") : "—",
            "Since the last restart", d.uptime_hours >= 168 ? "warning" : "info") + "</div>";

        var hardware = UI.definition([
          ["Processor", esc(cpu.name)], ["Cores / threads", cpu.cores != null ? esc(cpu.cores) + " / " + esc(cpu.logical) : null],
          ["Max clock", cpu.clock_mhz ? esc((cpu.clock_mhz / 1000).toFixed(2)) + " GHz" : null], ["Memory", esc(m.total_gb) + " GB"],
          ["Memory modules", String((m.modules || []).length)], ["Page file", pf.automatic ? "Managed by Windows" : (pf.files || []).length ? "Custom size" : "Disabled"]
        ]);
        var modules = UI.table([{ title: "Slot" }, { title: "Size", cls: "num" }, { title: "Speed", cls: "num" }, { title: "Manufacturer" }],
          (m.modules || []).map(function (x) { return [esc(x.slot || "—"), esc(x.capacity_gb) + " GB", x.speed ? esc(x.speed) + " MT/s" : "—", esc(x.manufacturer || "—")]; }),
          "Module details are not available.");
        var pagefiles = UI.table([{ title: "Page file" }, { title: "Allocated", cls: "num" }, { title: "In use", cls: "num" }, { title: "Peak", cls: "num" }],
          (pf.files || []).map(function (x) { return [esc(x.name), esc(x.allocated_mb) + " MB", esc(x.current_mb) + " MB", esc(x.peak_mb) + " MB"]; }), "No page file is configured.");

        var settings = UI.checklist([
          ["Power plan", power.plan === "saver" ? "warning" : "ok", PLAN[power.plan] || power.name || "Unknown", power.name],
          ["Visual effects", d.visual_effects === 2 ? "ok" : "skipped", VISUAL[d.visual_effects] || "Windows default"],
          ["Fast Startup", d.fast_startup ? "warning" : "ok", d.fast_startup == null ? "Unknown" : d.fast_startup ? "On" : "Off"],
          ["Background game recording", d.game_dvr ? "warning" : "ok", d.game_dvr == null ? "Unknown" : d.game_dvr ? "On" : "Off"]
        ]) + '<div class="page-actions" style="margin-top:12px">' +
          '<button class="btn btn-sm" data-run="performance.power_high">' + UI.icon("bolt") + "High performance</button>" +
          '<button class="btn btn-sm" data-run="performance.power_balanced">Balanced</button>' +
          '<button class="btn btn-sm" data-run="performance.visual_best">Best performance visuals</button>' +
          '<button class="btn btn-sm" data-run="performance.free_memory">' + UI.icon("memory") + "Free standby memory</button>" +
          '<button class="btn btn-sm" data-run="performance.restart_explorer">' + UI.icon("explorer") + "Restart Explorer</button></div>";

        var bi = d.battery_info || {};
        var battery = Charts.gauge(bi.health_pct == null ? 0 : bi.health_pct, { label: "Battery health" }) + UI.definition([
          ["Health", bi.health_pct != null ? esc(bi.health_pct) + "% of design capacity" : "Not reported"], ["Charge", bi.charge_pct != null ? esc(bi.charge_pct) + "%" : null],
          ["Design capacity", bi.designed_mwh ? esc(bi.designed_mwh) + " mWh" : null], ["Full charge capacity", bi.full_mwh ? esc(bi.full_mwh) + " mWh" : null]
        ]);
        var byMem = Charts.hbars(((d.processes || {}).memory || []).map(function (p) { return { label: p.name + (p.count > 1 ? " ×" + p.count : ""), value: p.mb, color: "#8764B8" }; }),
          { format: function (x) { return x >= 1024 ? (x / 1024).toFixed(1) + " GB" : x + " MB"; } });

        el.innerHTML = parts.header + parts.errors + live + '<div class="grid grid-2-1">' + history + UI.card("Score", parts.score) + "</div>" + procs + kpis +
          '<div class="grid grid-3">' + UI.card("Hardware", hardware) + UI.card("Responsiveness settings", settings) + UI.card("Memory at scan time", byMem) + "</div>" +
          (d.battery_info ? '<div class="grid grid-3">' + UI.card("Battery", battery) + "</div>" : "") +
          '<div class="grid grid-2">' + UI.card("Memory modules", modules, "", "card-flush") + UI.card("Page files", pagefiles, "", "card-flush") + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" + '<div class="grid">' + parts.actions + "</div>" +
          '<div class="grid grid-2">' + parts.trend + parts.runs + "</div>";
        UI.bindArea(el, "performance", function () { self.render(el, App); });
        startLive(el, App);
      });
    }
  };

  function startLive(el, App) {
    var samples = [], since = 0, stopped = false, timer = null;
    function set(id, html) { var x = el.querySelector("#" + id); if (x) x.innerHTML = html; }
    function tick() {
      if (stopped) return;
      API.get("/live?since=" + since).then(function (r) {
        if (stopped) return;
        if (r.samples.length) {
          samples = samples.concat(r.samples).slice(-WINDOW);
          since = samples[samples.length - 1].t;
          draw(r);
        } else if (r.error && !samples.length) {
          set("live-cpu-sub", "Performance counters unavailable: " + esc(r.error));
        }
      }).catch(function () { /* agent busy or gone: try again next tick */ }).then(function () {
        if (!stopped) timer = setTimeout(tick, 2000);
      });
    }
    function draw() {
      var s = samples[samples.length - 1];
      set("live-cpu", s.cpu.toFixed(0) + "<small>%</small>");
      set("live-cpu-sub", "Peak in view " + Math.max.apply(null, samples.map(function (x) { return x.cpu; })).toFixed(0) + "%");
      set("live-cpu-chart", Charts.live(samples.map(function (x) { return x.cpu; }), { max: 100, color: "#0F6CBD" }));
      set("live-mem", s.memory_pct + "<small>%</small>");
      set("live-mem-sub", s.memory_used_gb + " of " + s.memory_total_gb + " GB · commit " + s.commit_pct + "%");
      set("live-mem-chart", Charts.live(samples.map(function (x) { return x.memory_pct; }), { max: 100, color: "#8764B8" }));
      set("live-disk", (s.disk_busy == null ? "–" : s.disk_busy.toFixed(0)) + "<small>% busy</small>");
      set("live-disk-sub", "Read " + rate(s.disk_read) + " · Write " + rate(s.disk_write));
      set("live-disk-chart", Charts.live(samples.map(function (x) { return x.disk_read + x.disk_write; }), { color: "#C27C0E" }));
      set("live-net", esc(rate(s.net_in + s.net_out)));
      set("live-net-sub", "In " + rate(s.net_in) + " · Out " + rate(s.net_out));
      set("live-net-chart", Charts.live(samples.map(function (x) { return x.net_in + x.net_out; }), { color: "#2E9D8F" }));
      var pt = function (key) { return samples.map(function (x) { return { x: x.t * 1000, y: x[key] == null ? 0 : x[key] }; }); };
      set("live-history", Charts.line([{ name: "CPU %", color: "#0F6CBD", points: pt("cpu") }, { name: "Memory %", color: "#8764B8", points: pt("memory_pct") },
        { name: "Disk busy %", color: "#C27C0E", points: pt("disk_busy") }], { min: 0, max: 100, height: 200, dots: false, area: true }));
      set("live-proc-cpu", UI.table([{ title: "Process" }, { title: "CPU", cls: "num" }, { title: "" }], (s.processes.cpu || []).map(function (p) {
        return ['<span class="cell-title">' + esc(p.name) + "</span>", p.cpu.toFixed(1) + "%",
          '<div class="bar-inline"><div style="width:' + Math.min(100, p.cpu) + '%;background:#0F6CBD"></div></div>'];
      }), "No process is using the CPU."));
      var maxMem = Math.max.apply(null, (s.processes.memory || []).map(function (p) { return p.mb; }).concat([1]));
      set("live-proc-mem", UI.table([{ title: "Process" }, { title: "Private memory", cls: "num" }, { title: "" }], (s.processes.memory || []).map(function (p) {
        return ['<span class="cell-title">' + esc(p.name) + "</span>", p.mb >= 1024 ? (p.mb / 1024).toFixed(1) + " GB" : p.mb + " MB",
          '<div class="bar-inline"><div style="width:' + (100 * p.mb / maxMem) + '%;background:#8764B8"></div></div>'];
      })));
    }
    App.onLeave(function () { stopped = true; clearTimeout(timer); });
    tick();
  }
})();
