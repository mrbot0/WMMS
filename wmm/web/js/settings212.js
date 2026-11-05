/* Settings 2.12: the Overview that opens first (the state of what matters, each line with a link to its section),
   Automation (rules "when this happens, run a tool", goals with an alert, programs winget must not update) and the
   Backup of your files to another disk or a NAS. Added to Settings like settings29.js and settings210.js. */
(function () {
  "use strict";
  var esc = UI.esc;
  var SECTIONS = [
    ["overview", "Overview", "dashboard", "The state of everything at a glance"],
    ["automation", "Automation", "bolt", "Rules, goals, program updates"],
    ["filebackup", "Backup of your files", "storage", "Copy to another disk or a NAS"]
  ];
  var FOLDERS = [["Documents", "Documents"], ["Desktop", "Desktop"], ["Pictures", "Pictures"], ["Videos", "Videos"], ["Music", "Music"], ["Downloads", "Downloads"]];
  function fail(e) { if (e && e.message !== "cancelled") UI.toast(e.message, "error"); }
  function metricLabel(m) {
    var base = { overall: "Overall health", c_free_pct: "Free space on C: (%)", c_free_gb: "Free space on C: (GB)", open_issues: "Open recommendations" };
    return base[m] || (m.indexOf("area:") === 0 ? "Score of " + (UI.AREA_LABEL[m.slice(5)] || m.slice(5)) : m);
  }
  function goTo(id) {
    var b = document.querySelector('.settings-nav [data-sect="' + id + '"]');
    if (b) b.click(); else UI.toast("That section is not available to your role.", "info");
  }

  /* ---------- Overview ---------- */
  function overview(box) {
    Promise.all([API.get("/app-settings").catch(function () { return null; }), API.get("/notifications").catch(function () { return null; }),
      API.get("/schedules").catch(function () { return { installation: {} }; }), API.get("/plus/automation").catch(function () { return null; })]).then(function (r) {
      var app = r[0] ? r[0].values : null, alerts = r[1], inst = r[2].installation || {}, auto = r[3];
      var righe = [];
      righe.push(Auth.enabled() ? ["ok", "Accounts are on", "Everyone signs in with their own account and role.", "security"]
        : ["warning", "Accounts are off", "Whoever opens the console on this PC can use it. Turn accounts on for a shared or company PC.", "security"]);
      if (alerts) righe.push(alerts.channels && alerts.channels.length ? ["ok", "Alerts go out by " + alerts.channels.join(", "), "Problems reach you also when the console is closed.", "channels"]
        : ["warning", "No alert channel", "Problems are seen only in the console. Set up e-mail, Telegram or a webhook.", "channels"]);
      righe.push(inst.protected ? ["ok", "Protected installation", "Schedules run from Program Files, where only administrators can write.", "agent"]
        : ["warning", "Installation not protected", "Schedules need the protected installation in Program Files.", "agent"]);
      if (app) {
        righe.push(app.block_high_risk || (app.approval_levels || []).length ? ["ok", "Risky tools are controlled", (app.block_high_risk ? "High-risk tools are blocked. " : "") +
          ((app.approval_levels || []).length ? "Approval needed for " + app.approval_levels.join(" and ") + " risk." : ""), "runs"]
          : ["info", "Risky tools ask only for a confirmation", "Block them or ask a second person to approve them (useful in a company).", "runs"]);
        righe.push(app.encrypt_data ? ["ok", "Data files are encrypted", "Readable only on this PC (DPAPI).", "protection"]
          : ["info", "Data files are not encrypted", "Network devices, Wi-Fi history and alerts can be encrypted for this PC.", "protection"]);
        righe.push(app.update_check_on_start ? ["ok", "New versions are checked at start", "", "app"] : ["info", "New versions are not checked at start", "Check by hand in This agent, or turn it on.", "app"]);
      }
      if (auto) {
        var fb = auto.file_backup || {}, st = auto.backup_status || {};
        righe.push(!fb.target ? ["warning", "Your files are not copied anywhere", "A copy on another disk or a NAS saves them from a broken disk or ransomware.", "filebackup"]
          : st.ok ? ["ok", "Your files are copied to " + fb.target, "Last copy " + UI.relative(st.at) + ".", "filebackup"]
            : ["warning", "The copy of your files did not run yet or failed", st.detail || "Run it once from Backup of your files.", "filebackup"]);
        righe.push([(auto.rules.length || auto.goals.length) ? "ok" : "info", auto.rules.length + " rules and " + auto.goals.length + " goals",
          "Rules run a tool when something happens; goals send an alert when this PC drifts away from them.", "automation"]);
      }
      var buone = righe.filter(function (x) { return x[0] === "ok"; }).length;
      box.innerHTML = UI.card("Settings at a glance", '<p class="muted" style="margin-top:0">' + buone + " of " + righe.length +
        " in good shape. Each line opens its section.</p>" + '<ul class="overview-list">' + righe.map(function (x) {
          return '<li class="overview-item">' + UI.statusIcon(x[0] === "info" ? "warning" : x[0]) + '<div class="grow"><strong>' + esc(x[1]) + "</strong>" +
            (x[2] ? '<div class="cell-sub">' + esc(x[2]) + "</div>" : "") + '</div><button type="button" class="btn btn-sm" data-goto="' + x[3] + '">Open</button></li>';
        }).join("") + "</ul>");
      box.onclick = function (e) { var b = e.target.closest("[data-goto]"); if (b) goTo(b.getAttribute("data-goto")); };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  /* ---------- Automation ---------- */
  function automation(box, App) {
    Promise.all([API.get("/plus/automation"), API.get("/plus/goals").catch(function () { return { goals: [] }; })]).then(function (r) {
      var d = r[0], stato = {};
      r[1].goals.forEach(function (g) { stato[g.id] = g; });
      var ro = !Auth.can("settings.edit");
      var sicuri = Object.keys(App.state.actions).map(function (k) { return App.state.actions[k]; })
        .filter(function (a) { return a.risk === "safe" && a.id.indexOf("custom.") !== 0; }).sort(function (a, b) { return a.title.localeCompare(b.title); });
      var rules = d.rules.slice(), goals = d.goals.slice();
      function ruleRow(x, i) {
        return '<tr data-r="' + i + '"><td><select data-k="event">' + d.events.map(function (e) {
          return '<option value="' + esc(e.id) + '"' + (e.id === x.event ? " selected" : "") + ">" + esc(e.title) + "</option>"; }).join("") + "</select></td>" +
          '<td><select data-k="action_id">' + sicuri.map(function (a) { return '<option value="' + esc(a.id) + '"' + (a.id === x.action_id ? " selected" : "") + ">" + esc(a.title) + "</option>"; }).join("") +
          '</select></td><td><input type="checkbox" data-k="enabled"' + (x.enabled ? " checked" : "") + ' aria-label="On"></td>' +
          '<td><button type="button" class="btn btn-sm btn-ghost" data-del-rule="' + i + '" aria-label="Delete">' + UI.icon("x") + "</button></td></tr>";
      }
      function goalRow(x, i) {
        var s = stato[x.id];
        var badge = !s || s.ok == null ? '<span class="badge">No data yet</span>' : s.ok ? '<span class="badge badge-status-ok">Met · ' + esc(s.current) + "</span>"
          : '<span class="badge badge-status-error">Not met · ' + esc(s.current) + "</span>";
        return '<tr data-g="' + i + '"><td><select data-k="metric">' + d.metrics.map(function (m) {
          return '<option value="' + esc(m) + '"' + (m === x.metric ? " selected" : "") + ">" + esc(metricLabel(m)) + "</option>"; }).join("") + "</select></td>" +
          '<td><select data-k="op"><option value=">="' + (x.op === ">=" ? " selected" : "") + '>at least</option><option value="<="' + (x.op === "<=" ? " selected" : "") + ">at most</option></select></td>" +
          '<td><input type="number" data-k="value" value="' + esc(x.value) + '" style="max-width:110px"></td><td><input type="checkbox" data-k="enabled"' + (x.enabled ? " checked" : "") + ' aria-label="On"></td>' +
          "<td>" + badge + '</td><td><button type="button" class="btn btn-sm btn-ghost" data-del-goal="' + i + '" aria-label="Delete">' + UI.icon("x") + "</button></td></tr>";
      }
      function read() {
        box.querySelectorAll("[data-r]").forEach(function (tr) {
          var i = Number(tr.getAttribute("data-r"));
          rules[i] = { id: rules[i].id, event: tr.querySelector('[data-k="event"]').value, action_id: tr.querySelector('[data-k="action_id"]').value, enabled: tr.querySelector('[data-k="enabled"]').checked };
        });
        box.querySelectorAll("[data-g]").forEach(function (tr) {
          var i = Number(tr.getAttribute("data-g"));
          goals[i] = { id: goals[i].id, metric: tr.querySelector('[data-k="metric"]').value, op: tr.querySelector('[data-k="op"]').value,
            value: Number(tr.querySelector('[data-k="value"]').value), enabled: tr.querySelector('[data-k="enabled"]').checked };
        });
      }
      function draw() {
        box.innerHTML = UI.card("Rules: when this happens, run a tool",
          '<p class="muted" style="margin-top:0">For example: when the disk is almost full, run the cleanup of temporary files. Rules run only safe tools, at most once every 30 minutes, ' +
          "also when no alert channel is set.</p>" +
          (rules.length ? '<div class="table-wrap"><table class="table"><thead><tr><th>When</th><th>Run</th><th>On</th><th></th></tr></thead><tbody>' + rules.map(ruleRow).join("") + "</tbody></table></div>"
            : '<p class="empty">No rule yet.</p>') +
          (ro ? "" : '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Add a rule", "data-add-rule", "btn-sm", "check") + UI.button("Save rules", "data-save-rules", "btn-sm btn-primary", "check") + "</div>")) +
          UI.card("Goals of this PC", '<p class="muted" style="margin-top:0">An alert (Goal not met) goes out once a day when the PC is outside a goal, e.g. free space on C: at least 20%. ' +
            "Checked every hour with the latest scans.</p>" +
            (goals.length ? '<div class="table-wrap"><table class="table"><thead><tr><th>Measure</th><th></th><th>Value</th><th>On</th><th>Now</th><th></th></tr></thead><tbody>' +
              goals.map(goalRow).join("") + "</tbody></table></div>" : '<p class="empty">No goal yet.</p>') +
            (ro ? "" : '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Add a goal", "data-add-goal", "btn-sm", "check") + UI.button("Save goals", "data-save-goals", "btn-sm btn-primary", "check") + "</div>")) +
          UI.card("Program updates with winget", '<p class="muted" style="margin-top:0">The tool Update programs with winget (with exceptions) updates every program winget knows except these. ' +
            "One winget ID per line, e.g. a program whose new version breaks something you use.</p>" +
            '<form class="form" onsubmit="return false"><textarea name="ex" rows="4" data-no-i18n placeholder="Zoom.Zoom">' + esc(d.winget_exclusions.join("\n")) + "</textarea></form>" +
            (ro ? "" : '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Save exceptions", "data-save-ex", "btn-sm btn-primary", "check") +
              UI.button("Schedule every night", "data-sched-winget", "btn-sm", "clock") + UI.button("Update now", "data-run-winget", "btn-sm", "play") + "</div>"));
      }
      function save(campi, msg) {
        return API.put("/plus/automation", campi).then(function (n) { d = n; rules = n.rules.slice(); goals = n.goals.slice(); UI.toast(msg, "ok"); return API.get("/plus/goals"); })
          .then(function (g) { stato = {}; g.goals.forEach(function (x) { stato[x.id] = x; }); draw(); }, fail);
      }
      draw();
      box.onclick = function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        if (b.hasAttribute("data-add-rule")) { read(); rules.push({ event: d.events[0].id, action_id: sicuri[0] ? sicuri[0].id : "", enabled: true }); draw(); }
        if (b.hasAttribute("data-add-goal")) { read(); goals.push({ metric: "c_free_pct", op: ">=", value: 15, enabled: true }); draw(); }
        if (b.getAttribute("data-del-rule")) { read(); rules.splice(Number(b.getAttribute("data-del-rule")), 1); draw(); }
        if (b.getAttribute("data-del-goal")) { read(); goals.splice(Number(b.getAttribute("data-del-goal")), 1); draw(); }
        if (b.hasAttribute("data-save-rules")) { read(); save({ automation_rules: rules }, "Rules saved."); }
        if (b.hasAttribute("data-save-goals")) { read(); save({ goals: goals }, "Goals saved."); }
        if (b.hasAttribute("data-save-ex")) save({ winget_exclusions: box.querySelector("[name=ex]").value.split(/\s+/).filter(Boolean) }, "Exceptions saved.");
        if (b.hasAttribute("data-sched-winget")) App.schedule("updates.winget_nightly");
        if (b.hasAttribute("data-run-winget")) App.runActions(["updates.winget_nightly"]);
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  /* ---------- Backup of your files ---------- */
  function filebackup(box, App) {
    API.get("/plus/automation").then(function (d) {
      var fb = d.file_backup || {}, st = d.backup_status || {}, ro = !Auth.can("settings.edit");
      box.innerHTML = UI.card("Copy of your files", '<p class="muted" style="margin-top:0">Copies your folders to another disk or to a NAS. Only new and changed files are copied ' +
        "and nothing is deleted at the destination, so a file deleted by mistake stays in the copy. Keep the disk disconnected when not in use: ransomware cannot reach it.</p>" +
        '<form class="form" data-fb onsubmit="return false"><label>Destination<input name="target" data-no-i18n value="' + esc(fb.target || "") + '" placeholder="E:\\Backup or \\\\nas\\share\\backup"></label>' +
        '<div class="check-list">' + FOLDERS.map(function (f) {
          return '<label class="check"><input type="checkbox" value="' + f[0] + '"' + ((fb.folders || []).indexOf(f[0]) >= 0 ? " checked" : "") + "> " + esc(f[1]) + "</label>"; }).join("") + "</div></form>" +
        (st.at ? '<p class="small">' + UI.statusIcon(st.ok ? "ok" : "warning") + " Last copy " + esc(UI.formatDate(st.at)) + " · " + esc(st.detail || "") + "</p>" : '<p class="muted small">No copy made yet.</p>') +
        (ro ? "" : '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Save", "data-fb-save", "btn-sm btn-primary", "check") +
          UI.button("Copy now", "data-fb-run", "btn-sm", "play") + UI.button("Schedule every day", "data-fb-sched", "btn-sm", "clock") + "</div>"));
      box.onclick = function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        var f = box.querySelector("[data-fb]");
        if (b.hasAttribute("data-fb-save")) API.put("/plus/automation", { file_backup: { target: f.target.value.trim(),
          folders: Array.prototype.filter.call(f.querySelectorAll("input[type=checkbox]"), function (x) { return x.checked; }).map(function (x) { return x.value; }) } })
          .then(function () { UI.toast("Saved.", "ok"); filebackup(box, App); }, fail);
        if (b.hasAttribute("data-fb-run")) App.runActions(["storage.user_backup"]);
        if (b.hasAttribute("data-fb-sched")) App.schedule("storage.user_backup");
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  var MOUNT = { overview: overview, automation: automation, filebackup: filebackup };
  window.Settings212 = {
    sections: function () {
      return SECTIONS.filter(function (s) { return s[0] === "overview" || Auth.can("view.settings"); });
    },
    body: function (id) { return '<div class="stack" data-s212="' + id + '"></div>'; },
    mount: function (el, App) { el.querySelectorAll("[data-s212]").forEach(function (box) { MOUNT[box.getAttribute("data-s212")](box, App); }); }
  };
})();
