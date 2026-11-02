/* Scripts: the automatic shutdown timer, the user's .bat / .cmd scripts (upload, edit, run, schedule) and ready-made scripts. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var PRESETS = [5, 15, 30, 60, 90, 120, 240];
  var DAY = { MON: "Mon", TUE: "Tue", WED: "Wed", THU: "Thu", FRI: "Fri", SAT: "Sat", SUN: "Sun" };

  function clock(seconds) {
    var h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    return (h ? h + ":" + ("0" + m).slice(-2) : m) + ":" + ("0" + s).slice(-2);
  }
  function scheduleText(s) {
    if (!s) return "Not scheduled";
    var at = s.at.replace("T", " ");
    return s.kind === "once" ? "Once on " + at : s.kind === "daily" ? "Every day at " + at.slice(11) + " (from " + at.slice(0, 10) + ")"
      : "Every " + s.days.split(",").map(function (d) { return DAY[d] || d; }).join(", ") + " at " + at.slice(11);
  }
  /* Uploaded .bat files are usually ANSI (Windows-1252); newer ones UTF-8. Both become text here. */
  function decode(buffer) {
    try { return new TextDecoder("utf-8", { fatal: true }).decode(buffer).replace(/^\uFEFF/, ""); }
    catch (e) { return new TextDecoder("windows-1252").decode(buffer); }
  }

  window.Pages.scripts = {
    title: "Scripts",
    render: function (el, App) {
      var data = null, ticker = null;
      // Listeners live on this page's own container: #content is shared by every page.
      el.innerHTML = '<div class="scripts-page"></div>';
      var host = el.firstChild;
      App.setSubtitle("Batch scripts, schedules and the shutdown timer");

      function load() { return API.get("/scripts").then(function (r) { data = r; draw(); }); }

      /* ---------- shutdown timer ---------- */
      function timerForm(t, can) {
        var presets = '<div class="timer-presets">' + PRESETS.map(function (m) {
          return '<button type="button" class="chip-btn" data-preset="' + m + '">' + (m < 60 ? m + " min" : m / 60 + " h") + "</button>";
        }).join("") + "</div>";
        return '<div class="timer-form"><div class="segmented" role="radiogroup" aria-label="What to do"><button type="button" role="radio" data-timer-action="shutdown" aria-checked="' +
          (!t.active || t.action === "shutdown") + '">Shut down</button><button type="button" role="radio" data-timer-action="restart" aria-checked="' + (t.active && t.action === "restart") +
          '">Restart</button></div><label class="timer-minutes">In<input type="number" data-timer-min min="1" max="10080" value="' + (t.active ? t.minutes : 30) +
          '">minutes</label>' + presets + UI.button(t.active ? "Change time" : "Start timer", "data-timer-go" + (can ? "" : " disabled"), "btn-primary", "clock") + "</div>";
      }
      function timerCard() {
        var t = data.timer, can = data.can_change;
        if (!t.active) {
          return '<section class="card timer-card"><div class="timer-head"><span class="timer-icon">' + UI.icon("power") + "</span><div><h2>Automatic shutdown</h2>" +
            '<p class="muted">Shut down or restart this PC after the minutes you choose. Windows keeps the countdown even if you close this console.</p></div></div>' +
            timerForm(t, can) + "</section>";
        }
        var due = new Date(t.due * 1000);
        return '<section class="card timer-card active"><div class="timer-head"><div class="timer-ring" style="--p:0%"><span data-timer-left>' + clock(t.remaining) + "</span></div><div>" +
          "<h2>" + (t.action === "restart" ? "Restart" : "Shutdown") + ' planned</h2><p class="muted">At ' + esc(due.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })) +
          " (" + esc(due.toLocaleDateString()) + ") · set for " + t.minutes + " minutes. Save your work before then.</p>" +
          '<div class="timer-quick">' + UI.button("+15 min", 'data-add="15"' + (can ? "" : " disabled"), "btn-sm", "clock") + UI.button("+1 h", 'data-add="60"' + (can ? "" : " disabled"), "btn-sm", "clock") +
          UI.button("Cancel", "data-timer-cancel" + (can ? "" : " disabled"), "btn-sm btn-danger", "x") + "</div></div></div>" +
          '<details class="timer-change"><summary>Change the time or the action</summary>' + timerForm(t, can) + "</details></section>";
      }
      function tick() {
        clearInterval(ticker);
        if (!data.timer.active) return;
        var total = data.timer.minutes * 60;
        ticker = setInterval(function () {
          var left = Math.max(0, Math.round(data.timer.due - Date.now() / 1000)), box = host.querySelector("[data-timer-left]");
          if (!box) { clearInterval(ticker); return; }
          box.textContent = clock(left);
          box.parentElement.style.setProperty("--p", Math.round(100 * (1 - left / total)) + "%");
          if (!left) { clearInterval(ticker); load(); }
        }, 1000);
      }
      function startTimer(minutes, action) {
        API.post("/shutdown-timer", { minutes: minutes, action: action }).then(function (r) {
          if (r.preview) { UI.toast("Preview mode: no timer was set (recorded in History).", "info"); return; }
          UI.toast((action === "restart" ? "Restart" : "Shutdown") + " in " + minutes + " minute(s).", "ok");
          load();
        }, function (e) { UI.toast(e.message, "error"); });
      }

      /* ---------- my scripts ---------- */
      function scriptsCard() {
        var rows = data.scripts;
        var body = rows.length ? '<div class="script-list">' + rows.map(function (s) {
          var last = s.last_run, running = last && last.status === "running";
          return '<div class="script-row" data-id="' + s.id + '"><span class="script-icon">' + UI.icon("scripts") + "</span>" +
            '<div class="grow"><button type="button" class="link-btn cell-title" data-edit>' + esc(s.name) + '</button><div class="cell-sub">' +
            '<span class="cell-mono">' + esc(s.file) + "</span> · " + esc(UI.formatBytes(s.size)) + " · " + esc(scheduleText(s.schedule)) + "</div>" +
            '<div class="script-meta">' + (running ? '<span class="badge badge-status-running"><span class="spinner" style="width:10px;height:10px"></span>Running</span>'
              : last ? UI.statusBadge(last.status) + '<span class="cell-sub">' + esc(UI.relative(last.finished)) + " · exit " + esc(last.exit) + "</span>" : '<span class="cell-sub">Never run</span>') +
            (s.schedule ? '<span class="badge badge-status-info">' + UI.icon("clock") + "Scheduled</span>" : "") + "</div></div>" +
            '<div class="tm-actions">' + UI.button("Run", "data-run-script" + (running || !data.can_change ? " disabled" : ""), "btn-sm btn-primary", "play") +
            UI.button(s.schedule ? "Unschedule" : "Schedule", s.schedule ? "data-unschedule" : "data-schedule-script", "btn-sm", "clock") +
            (last && last.output ? UI.button("Output", "data-output-script", "btn-sm btn-ghost", "reports") : "") +
            UI.button("", 'data-download title="Download" aria-label="Download ' + esc(s.name) + '"', "btn-sm btn-ghost", "download") +
            UI.button("", 'data-delete title="Delete" aria-label="Delete ' + esc(s.name) + '"', "btn-sm btn-ghost", "trash") + "</div></div>";
        }).join("") + "</div>"
          : '<div class="empty-state" style="padding:28px">' + UI.icon("scripts") + "<h2>No scripts yet</h2><p>Upload a .bat or .cmd file, write a new one, or add a ready-made script below.</p></div>";
        return UI.card("My scripts", body, '<input type="file" data-script-file accept=".bat,.cmd" multiple hidden>' +
          UI.button("Upload .bat / .cmd", "data-script-upload", "btn-sm", "upload") + UI.button("New script", "data-script-new", "btn-sm btn-primary", "play"));
      }

      /* ---------- ready-made scripts ---------- */
      function templatesCard() {
        var groups = {};
        data.templates.forEach(function (t) { (groups[t.group] = groups[t.group] || []).push(t); });
        return UI.card("Ready-made scripts", Object.keys(groups).map(function (g) {
          return '<div class="section-title">' + esc(g) + '</div><div class="action-grid">' + groups[g].map(function (t) {
            return '<div class="action-card template-card" data-template="' + t.id + '"><div class="action-top"><span class="tool-icon">' + UI.icon(t.icon) + '</span><span class="cell-title grow">' +
              esc(t.title) + '</span></div><div class="cell-sub">' + esc(t.description) + "</div>" + t.params.map(function (p) {
                return '<label class="template-param">' + esc(p.label) + '<input name="' + esc(p.name) + '" type="' + esc(p.type) + '" value="' + esc(p.default) + '"' +
                  (p.min ? ' min="' + p.min + '" max="' + p.max + '"' : "") + "></label>";
              }).join("") + '<div class="action-foot"><span class="grow"></span>' + UI.button("Add to my scripts", "data-add-template", "btn-sm", "play") + "</div></div>";
          }).join("") + "</div>";
        }).join(""), '<span class="muted small">Add one, then run it or schedule it</span>');
      }

      function draw() {
        host.innerHTML = UI.pageHeader("Scripts", "Your batch scripts, run now or at a set time",
          UI.hint("Scripts run with administrator rights. Scheduled scripts run as SYSTEM through Windows Task Scheduler, even when nobody is signed in, " +
            "so they need the protected installation. Every run is recorded in History.")) +
          (data.can_change ? "" : '<div class="callout callout-warning">' + UI.icon("shield") + "<div>Read-only: restart the console as administrator to run scripts or set the timer.</div></div>") +
          (data.preview ? '<div class="callout callout-info">' + UI.icon("info") + "<div>Preview mode: runs, schedules and the timer are recorded in History but nothing happens.</div></div>" : "") +
          (data.can_schedule ? "" : '<div class="callout callout-warning">' + UI.icon("clock") + "<div>Scheduling scripts needs the protected installation. " +
            '<a href="#/settings">Settings › This agent › Fix automatically</a> sets it up; running a script now works anyway.</div></div>') +
          timerCard() + '<div class="grid">' + scriptsCard() + "</div>" + '<div class="grid">' + templatesCard() + "</div>";
        tick();
      }

      function byId(node) { var row = node.closest("[data-id]"); return row && data.scripts.filter(function (s) { return s.id === row.getAttribute("data-id"); })[0]; }
      function editor(s) {
        var get = s ? API.get("/scripts/" + s.id) : Promise.resolve({ name: "", content: "@echo off\r\nrem Your commands here\r\n" });
        get.then(function (full) {
          UI.modal(s ? "Edit " + s.name : "New script", '<form class="form" onsubmit="return false"><label>Name<input name="name" maxlength="80" value="' + esc(full.name) +
            '"></label><label>Commands (.bat)<textarea name="content" rows="14" spellcheck="false" class="cell-mono script-editor">' + esc(full.content) + "</textarea></label>" +
            '<p class="muted small" style="margin:0">Runs with cmd.exe as administrator (SYSTEM when scheduled). Test it with Run before scheduling it.</p></form>',
            [{ label: "Cancel", cls: "btn-ghost" }, { label: "Save", cls: "btn-primary", value: function (w) {
              var f = w.querySelector("form");
              return { name: f.name.value.trim(), content: f.content.value };
            } }]).then(function (v) {
            if (!v) return;
            (s ? API.post("/scripts/" + s.id + "/save", v) : API.post("/scripts", { name: v.name || "New script", content: v.content, filename: "script.bat" }))
              .then(function () { UI.toast("Script saved.", "ok"); load(); }, function (e) { UI.toast(e.message, "error"); });
          });
          var area = document.querySelector("#modal-root .script-editor");
          if (area) {
            area.closest(".modal").classList.add("modal-wide");
            area.addEventListener("keydown", function (e) {  // Tab inserts spaces instead of leaving the editor
              if (e.key !== "Tab") return;
              e.preventDefault();
              area.setRangeText("    ", area.selectionStart, area.selectionEnd, "end");
            });
          }
        }, function (e) { UI.toast(e.message, "error"); });
      }
      function waitForRun(s) {
        var tries = 0;
        (function poll() {
          API.get("/scripts/" + s.id).then(function (full) {
            var last = full.last_run || {};
            if (last.status === "running" && tries++ < 1800) { setTimeout(poll, 2000); return; }
            if (App.isCurrent("scripts")) load();
            UI.toast(s.name + ": " + (last.status === "ok" ? "completed" : "finished with exit code " + last.exit) + ".", last.status === "ok" ? "ok" : "error");
            Components.reportViewer(s.name, last.output || "(no output)", "Exit code " + last.exit + " · " + last.seconds + " s");
          });
        })();
      }

      host.addEventListener("click", function (e) {
        var b = e.target.closest("button");
        if (!b || b.disabled) return;
        var s = byId(b);
        if (b.hasAttribute("data-preset")) { b.closest(".timer-form").querySelector("[data-timer-min]").value = b.getAttribute("data-preset"); return; }
        if (b.hasAttribute("data-timer-action")) {
          b.parentElement.querySelectorAll("[data-timer-action]").forEach(function (x) { x.setAttribute("aria-checked", String(x === b)); });
          return;
        }
        if (b.hasAttribute("data-timer-go")) {
          var form = b.closest(".timer-form");
          startTimer(Number(form.querySelector("[data-timer-min]").value), form.querySelector('[data-timer-action][aria-checked="true"]').getAttribute("data-timer-action"));
          return;
        }
        if (b.hasAttribute("data-add")) {
          var left = Math.max(1, Math.round((data.timer.due - Date.now() / 1000) / 60));
          startTimer(left + Number(b.getAttribute("data-add")), data.timer.action);
          return;
        }
        if (b.hasAttribute("data-timer-cancel")) {
          API.post("/shutdown-timer/cancel").then(function (r) { UI.toast(r.preview ? "Preview mode: nothing was cancelled." : "Planned shutdown cancelled.", "ok"); load(); },
            function (er) { UI.toast(er.message, "error"); });
          return;
        }
        if (b.hasAttribute("data-script-upload")) { host.querySelector("[data-script-file]").click(); return; }
        if (b.hasAttribute("data-script-new")) { editor(null); return; }
        if (b.hasAttribute("data-add-template")) {
          var card = b.closest("[data-template]"), params = {};
          card.querySelectorAll("input[name]").forEach(function (i) { params[i.name] = i.type === "number" ? Number(i.value) : i.value; });
          API.post("/scripts", { template: card.getAttribute("data-template"), params: params }).then(function (r) {
            UI.toast("Added to My scripts: " + r.name + ".", "ok");
            FX.burst(b);
            load();
          }, function (er) { UI.toast(er.message, "error"); });
          return;
        }
        if (!s) return;
        if (b.hasAttribute("data-edit")) editor(s);
        if (b.hasAttribute("data-run-script")) {
          UI.confirm("Run " + s.name + "?", "The script runs now with administrator rights. Its output opens when it finishes.", { ok: "Run now" }).then(function (ok) {
            if (!ok) return;
            API.post("/scripts/" + s.id + "/run").then(function (r) {
              if (r.preview) { UI.toast("Preview mode: the script did not run (recorded in History).", "info"); return; }
              UI.toast(s.name + " is running…", "info");
              load();
              waitForRun(s);
            }, function (er) { UI.toast(er.message, "error"); });
          });
        }
        if (b.hasAttribute("data-schedule-script")) {
          UI.scheduleDialog({ title: s.name, description: "Batch script " + s.file, risk: "moderate",
            warning: "The script runs as SYSTEM with full rights, even when nobody is signed in." }).then(function (v) {
            if (!v) return;
            if (!v.confirmed) { UI.toast("Tick the confirmation box to schedule a script.", "warning"); return; }
            if (v.kind === "weekly" && !v.days) { UI.toast("Choose at least one day.", "warning"); return; }
            API.post("/scripts/" + s.id + "/schedule", v).then(function (r) {
              UI.toast(r.preview ? "Preview mode: not scheduled (recorded in History)." : s.name + " scheduled.", r.preview ? "info" : "ok");
              load();
            }, function (er) { UI.toast(er.message, "error"); });
          });
        }
        if (b.hasAttribute("data-unschedule")) {
          API.post("/scripts/" + s.id + "/unschedule").then(function () { UI.toast("Schedule removed.", "ok"); load(); }, function (er) { UI.toast(er.message, "error"); });
        }
        if (b.hasAttribute("data-output-script")) {
          Components.reportViewer(s.name, s.last_run.output, "Exit code " + s.last_run.exit + " · " + UI.formatDate(s.last_run.finished));
        }
        if (b.hasAttribute("data-download")) {
          API.get("/scripts/" + s.id).then(function (full) { Components.downloadText(s.name.replace(/[^\w.-]+/g, "_") + s.file.slice(-4), full.content, "text/plain;charset=utf-8"); });
        }
        if (b.hasAttribute("data-delete")) {
          UI.confirm("Delete " + s.name + "?", "The script" + (s.schedule ? " and its schedule are" : " is") + " removed.", { ok: "Delete", danger: true }).then(function (ok) {
            if (ok) API.post("/scripts/" + s.id + "/delete").then(function () { UI.toast("Script deleted.", "ok"); load(); }, function (er) { UI.toast(er.message, "error"); });
          });
        }
      });
      host.addEventListener("change", function (e) {
        if (!e.target.hasAttribute("data-script-file")) return;
        var files = Array.prototype.slice.call(e.target.files);
        Promise.all(files.map(function (f) {
          if (!/\.(bat|cmd)$/i.test(f.name)) { UI.toast(f.name + ": only .bat and .cmd files.", "warning"); return null; }
          return f.arrayBuffer().then(function (buf) {
            return API.post("/scripts", { name: f.name.replace(/\.(bat|cmd)$/i, ""), filename: f.name, content: decode(buf) });
          }).catch(function (er) { UI.toast(f.name + ": " + er.message, "error"); return null; });
        })).then(function (r) {
          var n = r.filter(Boolean).length;
          if (n) UI.toast(n + " script(s) uploaded.", "ok");
          load();
        });
      });
      App.onLeave(function () { clearInterval(ticker); });
      return load();
    }
  };
})();
