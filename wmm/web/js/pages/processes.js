/* Task Manager: every running process with live CPU, memory and I/O, filters, column choice, end / priority / start,
   and the live list of services with start, stop and restart. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var COLUMNS = [
    ["name", "Name", true], ["pid", "PID", true], ["ppid", "Parent", false], ["cpu", "CPU", true], ["memory_mb", "Memory", true],
    ["io_bps", "Disk / net I/O", true], ["threads", "Threads", true], ["handles", "Handles", false], ["uptime_s", "Running for", true],
    ["user", "User", true], ["priority", "Priority", false], ["session", "Session", false], ["company", "Company", false],
    ["description", "Description", true], ["version", "Version", false], ["services", "Services", false], ["path", "Path", false], ["command", "Command line", false]
  ];
  var QUICK = [["all", "All"], ["apps", "Apps"], ["background", "Background"], ["windows", "Windows"], ["services", "Service hosts"],
    ["cpu", "CPU > 5%"], ["memory", "Memory > 500 MB"], ["mine", "My processes"]];
  var PRIORITIES = [["idle", "Low"], ["below_normal", "Below normal"], ["normal", "Normal"], ["above_normal", "Above normal"], ["high", "High"]];
  var SUGGESTED = ["notepad", "cmd", "powershell", "explorer", "regedit", "taskmgr", "control", "msconfig", "services.msc", "devmgmt.msc", "eventvwr.msc",
    "diskmgmt.msc", "compmgmt.msc", "perfmon", "resmon", "mstsc", "winver"];

  function saved() {
    return Components.store("taskmgr") || { tab: "processes", quick: "all", interval: 2000, paused: false,
      columns: COLUMNS.filter(function (c) { return c[2]; }).map(function (c) { return c[0]; }) };
  }
  function duration(s) {
    if (!s && s !== 0) return "—";
    return s < 60 ? s + " s" : s < 3600 ? Math.floor(s / 60) + " min" : s < 86400 ? Math.floor(s / 3600) + " h " + Math.floor(s % 3600 / 60) + " min"
      : Math.floor(s / 86400) + " d " + Math.floor(s % 86400 / 3600) + " h";
  }
  function windowsPath(p) { return /^[a-z]:\\windows\\/i.test(p.path || "") || p.critical || p.pid === 4; }
  function quickFilter(name, me) {
    return {
      all: function () { return true; },
      apps: function (p) { return p.session > 0 && !windowsPath(p) && !p.services.length; },
      background: function (p) { return !p.session || p.services.length > 0; },
      windows: windowsPath,
      services: function (p) { return p.services.length > 0; },
      cpu: function (p) { return p.cpu > 5; },
      memory: function (p) { return p.memory_mb > 500; },
      mine: function (p) { return !!me && (p.user || "").toLowerCase() === me; }
    }[name] || function () { return true; };
  }

  function processDetail(App, p, ops) {
    var rows = [["Name", esc(p.name)], ["PID / parent", esc(p.pid) + " / " + esc(p.ppid != null ? p.ppid : "—")], ["CPU", esc(p.cpu) + " %"],
      ["Memory (private)", esc(p.memory_mb) + " MB"], ["Disk / net I/O", esc(UI.formatBytes(p.io_bps)) + "/s"], ["Threads / handles", esc(p.threads) + " / " + esc(p.handles)],
      ["Running for", esc(duration(p.uptime_s))], ["Started", esc(p.started ? UI.formatDate(p.started) : "—")], ["User", esc(p.user || "—")],
      ["Session", esc(p.session != null ? p.session : "—")], ["Priority", esc(p.priority || "—")], ["Company", esc(p.company || "—")],
      ["Description", esc(p.description || "—")], ["Version", esc(p.version || "—")], ["Services", esc(p.services.join(", ") || "—")],
      ["Path", '<span class="cell-mono">' + esc(p.path || "—") + "</span>"]];
    var body = (p.critical ? '<div class="callout callout-warning">' + UI.icon("shield") + "<div>Essential to Windows: it cannot be ended or reprioritized from here.</div></div>" : "") +
      UI.definition(rows) + '<div class="log-head" style="margin-top:12px">Command line</div><pre class="log" style="min-height:0;max-height:22vh">' + esc(p.command || "(not available)") + "</pre>";
    UI.modal(p.name + " · PID " + p.pid, body, [
      { label: "Search online", cls: "btn-ghost", value: function () { return "web"; } },
      { label: "Copy path", cls: "btn-ghost", value: function () { return "path"; } },
      { label: "Copy", cls: "btn-ghost", value: function () { return "copy"; } },
      { label: "Open location", cls: "", value: function () { return "reveal"; } },
      { label: "End process", cls: p.critical ? "" : "btn-danger", value: function () { return "end"; } },
      { label: "Close", cls: "btn-primary" }
    ]).then(function (v) {
      if (v === "copy") App.copyText(COLUMNS.map(function (c) { var x = p[c[0]]; return c[1] + ": " + (Array.isArray(x) ? x.join(", ") : x == null ? "" : x); }).join("\n"), "Process details");
      // "What is this process?": the file name and its company, never the command line (it may hold paths or tokens).
      if (v === "web") window.open("https://www.google.com/search?q=" + encodeURIComponent(p.name + (p.company ? " " + p.company : "") + " what is this process"), "_blank", "noopener,noreferrer");
      if (v === "path") { if (p.path) App.copyText(p.path, "Path"); else UI.toast("Windows does not report the path of this process.", "info"); }
      if (v === "reveal") ops.reveal(p);
      if (v === "end") ops.end([p], false);
    });
  }

  function startDialog() {
    var body = '<form class="form" onsubmit="return false"><label>Program<input name="program" list="start-suggest" placeholder="notepad, cmd, C:\\Tools\\app.exe…" required></label>' +
      '<datalist id="start-suggest">' + SUGGESTED.map(function (s) { return '<option value="' + s + '">'; }).join("") + "</datalist>" +
      '<label>Arguments<input name="arguments" placeholder="optional"></label><label>Working folder<input name="folder" placeholder="the program folder"></label>' +
      '<label class="check"><input type="checkbox" name="elevated"> Run as administrator</label>' +
      '<p class="muted small" style="margin:0">Unticked, the program runs with standard user rights even though this console is elevated. ' +
      "Programs, .bat/.cmd scripts and management consoles (.msc, .cpl) can be started; every start is recorded in History.</p></form>";
    UI.modal("Start a new process", body, [{ label: "Cancel", cls: "btn-ghost" }, { label: "Start", cls: "btn-primary", value: function (w) {
      var f = w.querySelector("form");
      return { program: f.program.value.trim(), arguments: f.arguments.value.trim(), folder: f.folder.value.trim(), elevated: f.elevated.checked };
    } }]).then(function (v) {
      if (!v || !v.program) return;
      API.post("/processes/start", v).then(function (r) {
        UI.toast(r.preview ? "Preview mode: nothing was started." : "Started " + v.program + (r.pid ? " (PID " + r.pid + ")" : "") + ".", r.preview ? "info" : "ok");
      }, function (e) { UI.toast(e.message, "error"); });
    });
  }

  window.Pages.processes = {
    title: "Task Manager",
    render: function (el, App) {
      var view = saved(), timer = null, table = null, picked = {}, rows = [], me = "";
      App.setSubtitle("Live processes and services · end, prioritize, start");

      function save() { Components.store("taskmgr", view); }
      var ops = {
        end: function (list, tree) {
          var blocked = list.filter(function (p) { return p.critical; });
          if (blocked.length) {
            UI.toast(blocked.map(function (p) { return p.name; }).join(", ") + " cannot be ended: essential to Windows.", "warning");
            list = list.filter(function (p) { return !p.critical; });
          }
          if (!list.length) return;
          UI.confirm(list.length === 1 ? "End " + list[0].name + "?" : "End " + list.length + " processes?",
            "Unsaved work in " + (list.length === 1 ? "this program" : "these programs") + " is lost" + (tree ? ", and every process they started ends too" : "") + ".",
            { ok: tree ? "End process tree" : "End process", danger: true }).then(function (ok) {
            if (!ok) return;
            Promise.all(list.map(function (p) {
              return API.post("/processes/" + p.pid + "/end", { name: p.name, tree: !!tree }).then(function (r) { return r.preview ? "preview" : "ok"; },
                function (e) { UI.toast(p.name + ": " + e.message, "error"); return "error"; });
            })).then(function (res) {
              var done = res.filter(function (x) { return x === "ok"; }).length;
              if (done) UI.toast(done + " process(es) ended.", "ok");
              if (res.indexOf("preview") >= 0) UI.toast("Preview mode: nothing was ended.", "info");
              picked = {};
              refresh();
            });
          });
        },
        priority: function (p, value) {
          API.post("/processes/" + p.pid + "/priority", { name: p.name, priority: value }).then(function (r) {
            UI.toast(r.preview ? "Preview mode: priority not changed." : "Priority of " + p.name + " changed.", r.preview ? "info" : "ok");
            refresh();
          }, function (e) { UI.toast(e.message, "error"); });
        },
        reveal: function (p) { API.post("/processes/" + p.pid + "/reveal", { name: p.name }).catch(function (e) { UI.toast(e.message, "error"); }); }
      };

      el.innerHTML = UI.pageHeader("Task Manager", "Everything running on this PC, refreshed live",
        '<span class="muted small" id="tm-time"></span>' +
        '<label class="tb-sort">Refresh<select id="tm-interval">' + [[1000, "1 s"], [2000, "2 s"], [5000, "5 s"], [10000, "10 s"]].map(function (o) {
          return '<option value="' + o[0] + '"' + (view.interval === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
        }).join("") + "</select></label>" + UI.button(view.paused ? "Resume" : "Pause", 'id="tm-pause"', "", view.paused ? "play" : "clock") +
        UI.button("Copy top 10", 'id="tm-top" title="The 10 processes using the most CPU and memory, as text for a ticket"', "", "copy") +
        UI.button("Start new process", 'id="tm-start"', "btn-primary", "play")) +
        '<div class="tabs" role="tablist"><button type="button" role="tab" class="tab" data-tab="processes" aria-selected="' + (view.tab === "processes") + '">' + UI.icon("cpu") +
        '<span>Processes</span><span class="tab-count" id="tm-pcount">…</span></button><button type="button" role="tab" class="tab" data-tab="services" aria-selected="' +
        (view.tab === "services") + '">' + UI.icon("services") + '<span>Services</span><span class="tab-count" id="tm-scount">…</span></button></div>' +
        '<div id="tm-body">' + UI.loading("Reading processes…") + "</div>";
      var bodyEl = el.querySelector("#tm-body");

      /* ---------- processes ---------- */
      function columns() {
        return COLUMNS.filter(function (c) { return c[0] === "name" || view.columns.indexOf(c[0]) >= 0; }).map(function (c) {
          var key = c[0], col = { key: key, title: c[1] };
          if (key === "name") col.render = function (p) {
            return '<span class="tm-name"><input type="checkbox" data-pick="' + p.pid + '"' + (picked[p.pid] ? " checked" : "") + ' aria-label="Select ' + esc(p.name) + '">' +
              (p.critical ? '<span class="tm-shield" title="Essential to Windows">' + UI.icon("shield") + "</span>" : "") +
              '<button type="button" class="link-btn cell-title" data-detail="' + p.pid + '">' + esc(p.name) + "</button></span>";
          };
          if (key === "cpu") { col.cls = "num"; col.render = function (p) { return '<span class="tm-meter" style="--v:' + Math.min(100, p.cpu) + '%">' + p.cpu.toFixed(1) + " %</span>"; }; }
          if (key === "memory_mb") {
            col.cls = "num";
            col.render = function (p) {
              return '<span class="tm-meter mem" style="--v:' + Math.min(100, p.memory_mb / 20) + '%">' +
                (p.memory_mb >= 1024 ? (p.memory_mb / 1024).toFixed(2) + " GB" : p.memory_mb.toFixed(1) + " MB") + "</span>";
            };
          }
          if (key === "io_bps") { col.cls = "num"; col.render = function (p) { return p.io_bps ? esc(UI.formatBytes(p.io_bps)) + "/s" : '<span class="muted">0</span>'; }; }
          if (key === "uptime_s") col.render = function (p) { return esc(duration(p.uptime_s)); };
          if (key === "services") { col.value = function (p) { return p.services.join(", "); }; col.render = function (p) { return '<span class="cell-sub">' + esc(p.services.join(", ")) + "</span>"; }; }
          if (key === "path" || key === "command") col.render = function (p) { return '<span class="cell-mono tm-clip" title="' + esc(p[key] || "") + '">' + esc(p[key] || "") + "</span>"; };
          if (["pid", "ppid", "threads", "handles", "session"].indexOf(key) >= 0) col.cls = "num";
          return col;
        }).concat([{ key: "_act", title: "", sortable: false, csv: false, cls: "actions", render: function (p) {
          return '<span class="tm-actions"><select data-prio="' + p.pid + '" aria-label="Priority of ' + esc(p.name) + '"' + (p.critical ? " disabled" : "") + '><option value="">Priority…</option>' +
            PRIORITIES.map(function (o) { return '<option value="' + o[0] + '">' + o[1] + "</option>"; }).join("") + "</select>" +
            '<button type="button" class="btn btn-sm" data-end="' + p.pid + '"' + (p.critical ? " disabled" : "") + ' title="End process (Shift-click: with child processes)">' + UI.icon("x") + "End</button></span>";
        } }]);
      }
      function filtered() {
        var f = quickFilter(view.quick, me);
        return rows.filter(function (p) { return f(p) && (!view.user || (p.user || "") === view.user) && (!view.prio || (p.priority || "") === view.prio); });
      }
      function drawProcesses() {
        var users = {}, prios = {};
        rows.forEach(function (p) { if (p.user) users[p.user] = 1; if (p.priority) prios[p.priority] = 1; });
        bodyEl.innerHTML = '<div class="grid grid-5" id="tm-kpis"></div>' +
          '<section class="card"><div class="card-body"><div class="tb-bar">' +
          '<div class="segmented" role="radiogroup" aria-label="Quick filter">' + QUICK.map(function (q) {
            return '<button type="button" role="radio" data-quick="' + q[0] + '" aria-checked="' + (view.quick === q[0]) + '">' + esc(q[1]) + "</button>";
          }).join("") + "</div>" +
          '<label class="tb-sort">User<select id="tm-user"><option value="">All users</option>' + Object.keys(users).sort().map(function (u) {
            return "<option" + (view.user === u ? " selected" : "") + ">" + esc(u) + "</option>"; }).join("") + "</select></label>" +
          '<label class="tb-sort">Priority<select id="tm-prio"><option value="">Any</option>' + Object.keys(prios).sort().map(function (u) {
            return "<option" + (view.prio === u ? " selected" : "") + ">" + esc(u) + "</option>"; }).join("") + "</select></label>" +
          UI.hint("Shield: essential to Windows, cannot be ended. End stops one process; Shift-click or End with child processes stops what it started too. " +
            "Priority decides who gets the CPU first: High can starve other programs, use it only for a while.") +
          '<details class="tm-cols"><summary class="btn btn-sm">' + UI.icon("settings") + "Columns</summary><div>" + COLUMNS.filter(function (c) { return c[0] !== "name"; }).map(function (c) {
            return '<label class="check"><input type="checkbox" data-col="' + c[0] + '"' + (view.columns.indexOf(c[0]) >= 0 ? " checked" : "") + "> " + esc(c[1]) + "</label>";
          }).join("") + "</div></details></div>" +
          '<div class="tm-selbar" id="tm-selbar" hidden><span id="tm-selinfo"></span>' + UI.button("End selected", 'id="tm-endsel"', "btn-danger btn-sm", "x") +
          UI.button("End with child processes", 'id="tm-endtree"', "btn-sm", "x") + UI.button("Clear", 'id="tm-clearsel"', "btn-ghost btn-sm", "") + "</div>" +
          '<div id="tm-table"></div></div></section>';
        table = Components.dataTable(bodyEl.querySelector("#tm-table"), {
          rows: filtered(), columns: columns(), pageSize: 50, sort: view.sort || "cpu", desc: view.sort ? !!view.desc : true, exportName: "wmm-processes",
          placeholder: "Search name, PID, path, command line, user, company…", alwaysFoot: true
        });
        kpis();
        selection();
      }
      function kpis() {
        var box = bodyEl.querySelector("#tm-kpis");
        if (!box) return;
        var cpu = rows.reduce(function (s, p) { return s + p.cpu; }, 0), mem = rows.reduce(function (s, p) { return s + p.memory_mb; }, 0);
        var io = rows.reduce(function (s, p) { return s + p.io_bps; }, 0), top = rows.slice().sort(function (a, b) { return b.memory_mb - a.memory_mb; })[0];
        box.innerHTML = UI.kpi("Processes", String(rows.length), filtered().length + " shown", "info") +
          UI.kpi("CPU in use", Math.min(100, cpu).toFixed(1) + " <small>%</small>", "Sum of all processes", UI.toneOf(cpu, 60, 85, true)) +
          UI.kpi("Private memory", (mem / 1024).toFixed(1) + " <small>GB</small>", top ? "Largest: " + esc(top.name) : "", "info") +
          UI.kpi("Disk / net I/O", esc(UI.formatBytes(io)) + "<small>/s</small>", "All processes", "info") +
          UI.kpi("Threads", String(rows.reduce(function (s, p) { return s + p.threads; }, 0)), rows.reduce(function (s, p) { return s + p.handles; }, 0) + " handles", "info");
        el.querySelector("#tm-pcount").textContent = rows.length;
      }
      function selection() {
        var bar = bodyEl.querySelector("#tm-selbar"), n = Object.keys(picked).length;
        if (!bar) return;
        bar.hidden = !n;
        bodyEl.querySelector("#tm-selinfo").textContent = n + " selected";
      }
      function byPid(pid) { return rows.filter(function (p) { return p.pid === Number(pid); })[0]; }

      bodyEl.addEventListener("click", function (e) {
        var q = e.target.closest("[data-quick]");
        if (q) { view.quick = q.getAttribute("data-quick"); save(); drawProcesses(); return; }
        var d = e.target.closest("[data-detail]");
        if (d) { var p = byPid(d.getAttribute("data-detail")); if (p) processDetail(App, p, ops); return; }
        var end = e.target.closest("[data-end]");
        if (end) { var pe = byPid(end.getAttribute("data-end")); if (pe) ops.end([pe], e.shiftKey); return; }
        if (e.target.closest("#tm-endsel") || e.target.closest("#tm-endtree")) {
          ops.end(Object.keys(picked).map(byPid).filter(Boolean), !!e.target.closest("#tm-endtree"));
          return;
        }
        if (e.target.closest("#tm-clearsel")) { picked = {}; table.redraw(); selection(); return; }
        if (e.target.closest("[data-sort]")) {
          // The table has already redrawn: remember the column and direction it now shows.
          var th = bodyEl.querySelector("#tm-table th.sorted");
          if (th) { view.sort = th.getAttribute("data-sort"); view.desc = th.getAttribute("aria-sort") === "descending"; save(); }
          return;
        }
        var sid = e.target.closest("[data-svc]");
        if (sid) { serviceOp(sid.getAttribute("data-svc"), sid.getAttribute("data-op")); return; }
        var sd = e.target.closest("[data-svc-detail]");
        if (sd) serviceDetail(sd.getAttribute("data-svc-detail"));
      });
      bodyEl.addEventListener("change", function (e) {
        var attr = function (n) { return e.target.getAttribute ? e.target.getAttribute(n) : null; };
        if (attr("data-pick")) { if (e.target.checked) picked[attr("data-pick")] = 1; else delete picked[attr("data-pick")]; selection(); return; }
        if (attr("data-prio") && e.target.value) { var p = byPid(attr("data-prio")); if (p) ops.priority(p, e.target.value); e.target.value = ""; return; }
        if (attr("data-col")) {
          view.columns = Array.prototype.map.call(bodyEl.querySelectorAll("[data-col]:checked"), function (i) { return i.getAttribute("data-col"); });
          save();
          drawProcesses();
          bodyEl.querySelector(".tm-cols").open = true;
          return;
        }
        if (e.target.id === "tm-user") { view.user = e.target.value; save(); table.setRows(filtered()); kpis(); }
        if (e.target.id === "tm-prio") { view.prio = e.target.value; save(); table.setRows(filtered()); kpis(); }
      });

      /* ---------- services ---------- */
      var services = [], stable = null;
      function serviceDetail(name) {
        var s = services.filter(function (x) { return x.name === name; })[0];
        if (!s) return;
        UI.modal(s.display || s.name, '<p class="modal-text">' + esc(s.description || "No description.") + "</p>" + UI.definition([["Name", '<span class="cell-mono">' + esc(s.name) + "</span>"],
          ["State", esc(s.state)], ["Start type", esc(s.start)], ["Process ID", esc(s.pid || "—")], ["Essential", s.critical ? "Yes: cannot be stopped from here" : "No"],
          ["Command", '<span class="cell-mono">' + esc(s.path) + "</span>"]]), [{ label: "Close", cls: "btn-primary" }]);
      }
      function serviceOp(name, op) {
        var s = services.filter(function (x) { return x.name === name; })[0];
        if (!s) return;
        var ask = op === "start" ? Promise.resolve(true) : UI.confirm((op === "stop" ? "Stop " : "Restart ") + (s.display || s.name) + "?",
          "Programs that depend on this service may stop working until it runs again.", { ok: op === "stop" ? "Stop" : "Restart", danger: op === "stop" });
        ask.then(function (ok) {
          if (!ok) return;
          UI.toast((op === "start" ? "Starting " : op === "stop" ? "Stopping " : "Restarting ") + (s.display || s.name) + "…", "info");
          API.post("/services/" + encodeURIComponent(s.name) + "/" + op).then(function (r) {
            UI.toast(r.preview ? "Preview mode: the service was not changed." : (s.display || s.name) + ": " + (r.state || "done") + ".", r.preview ? "info" : "ok");
            loadServices(true);
          }, function (e) { UI.toast(e.message, "error"); });
        });
      }
      function drawServices() {
        var running = services.filter(function (s) { return s.state === "Running"; }).length;
        bodyEl.innerHTML = '<div class="grid grid-4">' + UI.kpi("Services", String(services.length), running + " running", "info") +
          UI.kpi("Running", String(running), "Started now", "ok") +
          UI.kpi("Stopped automatic", String(services.filter(function (s) { return s.start === "auto" && s.state !== "Running"; }).length), "Set to start with Windows", "warning") +
          UI.kpi("Essential", String(services.filter(function (s) { return s.critical; }).length), "Never stopped from here", "info") + "</div>" +
          '<section class="card"><div class="card-body"><div id="tm-stable"></div></div></section>';
        stable = Components.dataTable(bodyEl.querySelector("#tm-stable"), {
          rows: services, pageSize: 50, sort: "display", exportName: "wmm-services", placeholder: "Search services…", alwaysFoot: true,
          filters: [{ key: "state", label: "Any state", options: [["Running", "Running"], ["Stopped", "Stopped"], ["Paused", "Paused"]] },
            { key: "start", label: "Any start type", options: [["auto", "Automatic"], ["manual", "Manual"], ["disabled", "Disabled"]] }],
          columns: [
            { key: "display", title: "Service", render: function (s) {
              return (s.critical ? '<span class="tm-shield" title="Essential">' + UI.icon("shield") + "</span>" : "") + '<button type="button" class="link-btn cell-title" data-svc-detail="' +
                esc(s.name) + '">' + esc(s.display || s.name) + '</button><div class="cell-sub">' + esc(s.name) + "</div>"; } },
            { key: "state", title: "State", render: function (s) {
              return UI.statusBadge(s.state === "Running" ? "ok" : s.state === "Stopped" ? "skipped" : "warning").replace(/>[^<]*</, ">" + esc(s.state) + "<"); } },
            { key: "start", title: "Start type" },
            { key: "pid", title: "PID", cls: "num", render: function (s) { return s.pid || "—"; } },
            { key: "description", title: "Description", render: function (s) { return '<span class="cell-sub tm-clip" title="' + esc(s.description) + '">' + esc(s.description) + "</span>"; } },
            { key: "_act", title: "", sortable: false, csv: false, cls: "actions", render: function (s) {
              var run = s.state === "Running", n = esc(s.name);
              return '<span class="tm-actions">' + (run ? "" : '<button class="btn btn-sm" data-svc="' + n + '" data-op="start"' + (s.start === "disabled" ? " disabled" : "") + ">" +
                UI.icon("play") + "Start</button>") + (run ? '<button class="btn btn-sm" data-svc="' + n + '" data-op="restart"' + (s.critical ? " disabled" : "") + ">" + UI.icon("refresh") +
                "Restart</button>" + '<button class="btn btn-sm" data-svc="' + n + '" data-op="stop"' + (s.critical ? " disabled" : "") + ">" + UI.icon("x") + "Stop</button>" : "") + "</span>";
            } }
          ]
        });
        el.querySelector("#tm-scount").textContent = services.length;
      }
      function loadServices(fresh) {
        return API.get("/services/live" + (fresh ? "?fresh=1" : "")).then(function (r) {
          services = r.services;
          el.querySelector("#tm-scount").textContent = services.length;
          if (view.tab !== "services" || !App.isCurrent("processes")) return;
          if (stable) stable.setRows(services); else drawServices();
        });
      }

      /* ---------- refresh loop ---------- */
      function refresh() {
        if (view.tab === "services") return loadServices(false).catch(function (e) { bodyEl.innerHTML = UI.errorBox(e); });
        return API.get("/processes?full=1").then(function (r) {
          if (!App.isCurrent("processes") || view.tab !== "processes") return;
          rows = r.processes;
          if (!me) {
            var shell = rows.filter(function (p) { return p.name.toLowerCase() === "explorer.exe" && p.user; })[0];
            me = shell ? shell.user.toLowerCase() : "";
          }
          el.querySelector("#tm-time").textContent = "Updated " + new Date().toLocaleTimeString();
          if (table && bodyEl.querySelector("#tm-table")) {
            // An open priority menu would close on redraw: wait for the next tick.
            var busy = document.activeElement && bodyEl.contains(document.activeElement) && document.activeElement.tagName === "SELECT";
            if (!busy) { table.setRows(filtered()); kpis(); }
          } else drawProcesses();
        }, function (e) { bodyEl.innerHTML = UI.errorBox(e); });
      }
      function loop() {
        clearInterval(timer);
        if (!view.paused) timer = setInterval(function () { if (!document.hidden) refresh(); }, view.tab === "services" ? Math.max(5000, view.interval) : view.interval);
      }

      el.querySelector(".tabs").addEventListener("click", function (e) {
        var t = e.target.closest("[data-tab]");
        if (!t) return;
        view.tab = t.getAttribute("data-tab");
        save();
        el.querySelectorAll("[data-tab]").forEach(function (x) { x.setAttribute("aria-selected", String(x === t)); });
        table = stable = null;
        bodyEl.innerHTML = UI.loading(view.tab === "services" ? "Reading services…" : "Reading processes…");
        refresh();
        loop();
      });
      el.querySelector("#tm-interval").addEventListener("change", function (e) { view.interval = Number(e.target.value); save(); loop(); });
      el.querySelector("#tm-pause").addEventListener("click", function () { view.paused = !view.paused; save(); App.render(); });
      el.querySelector("#tm-start").addEventListener("click", startDialog);
      el.querySelector("#tm-top").addEventListener("click", function () {
        if (!rows.length) { UI.toast("Open the Processes tab first.", "info"); return; }
        var line = function (p) { return "- " + p.name + " (PID " + p.pid + "): CPU " + p.cpu + "%, memory " + p.memory_mb + " MB" + (p.company ? " · " + p.company : ""); };
        var byCpu = rows.slice().sort(function (a, b) { return b.cpu - a.cpu; }).slice(0, 10);
        var byMem = rows.slice().sort(function (a, b) { return b.memory_mb - a.memory_mb; }).slice(0, 10);
        App.copyText(["Top 10 by CPU (" + new Date().toLocaleTimeString() + "):"].concat(byCpu.map(line), ["", "Top 10 by memory:"], byMem.map(line)).join("\n"), "Top processes");
      });
      App.onLeave(function () { clearInterval(timer); });
      loop();
      if (view.tab === "processes") loadServices(false).catch(function () { /* only the tab count */ });
      return refresh();
    }
  };
})();
