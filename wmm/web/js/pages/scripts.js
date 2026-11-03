/* Scripts: the automatic shutdown timer, the user's .bat / .cmd scripts (upload, edit, run, schedule) and ready-made scripts. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var PRESETS = [5, 15, 30, 60, 90, 120, 240];
  /* Building blocks for the editor: the usual lines of a maintenance .bat. */
  var SNIPPETS = [
    ["Quiet start (@echo off, UTF-8)", "@echo off\nchcp 65001 >nul\nsetlocal"],
    ["Stop unless run as administrator", "net session >nul 2>&1 || (echo Run this script as administrator. & exit /b 1)"],
    ["Write a log next to the script", "set LOG=%~dp0%~n0.log\necho [%date% %time%] Started>>\"%LOG%\""],
    ["Wait N seconds", "timeout /t 30 /nobreak >nul"],
    ["Only if a file exists", "if exist \"C:\\path\\file.txt\" (\n    echo Found\n) else (\n    echo Missing\n)"],
    ["Loop over the files of a folder", "for %%F in (\"C:\\folder\\*.log\") do (\n    echo %%~nxF\n)"],
    ["Stop on error", "if errorlevel 1 (\n    echo Failed with code %errorlevel%\n    exit /b %errorlevel%\n)"],
    ["Close a program", "taskkill /im notepad.exe /f >nul 2>&1"],
    ["Start a program and wait", "start \"\" /wait \"C:\\Program Files\\App\\app.exe\""],
    ["Copy a folder (robocopy)", "robocopy \"C:\\source\" \"D:\\backup\" /e /r:1 /w:1 /np"],
    ["Run PowerShell", "powershell -NoProfile -ExecutionPolicy Bypass -Command \"Get-Date\""],
    ["Flush DNS", "ipconfig /flushdns"],
    ["Exit with success", "exit /b 0"]
  ];
  /* Commands that can destroy data or stop Windows from starting: the editor warns, it never blocks. */
  var DANGER = [
    [/\bformat\s+[a-z]:/i, "format erases a drive"],
    [/\b(del|erase)\b[^\r\n]*\/s[^\r\n]*\b[a-z]:\\(\s|\*|"|$)/i, "del /s on the root of a drive"],
    [/\b(rd|rmdir)\b[^\r\n]*\/s/i, "rd /s deletes whole folders"],
    [/\bdiskpart\b/i, "diskpart changes partitions"],
    [/\bbcdedit\b/i, "bcdedit changes how Windows starts"],
    [/\breg\s+delete\s+HK(LM|EY_LOCAL_MACHINE)/i, "reg delete on HKLM"],
    [/\bcipher\s+\/w/i, "cipher /w wipes free space and takes hours"],
    [/\bvssadmin\s+delete\b/i, "vssadmin delete removes restore points"],
    [/\bshutdown\b[^\r\n]*\/(s|r)\b/i, "shutdown turns the PC off or restarts it"]
  ];

  function clock(seconds) {
    var h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    return (h ? h + ":" + ("0" + m).slice(-2) : m) + ":" + ("0" + s).slice(-2);
  }
  var scheduleText = UI.scheduleText;
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
        var sv = Components.store("scriptsView") || { sort: "name" };
        var lastOf = function (s) { return (s.last_run && (s.last_run.finished || s.last_run.started)) || ""; };
        var SORT = {
          name: function (a, b) { return a.name.localeCompare(b.name); },
          recent: function (a, b) { return lastOf(b) < lastOf(a) ? -1 : lastOf(b) > lastOf(a) ? 1 : 0; },
          scheduled: function (a, b) { return (!!b.schedule - !!a.schedule) || a.name.localeCompare(b.name); },
          newest: function (a, b) { return (b.created || "") < (a.created || "") ? -1 : 1; }
        };
        var rows = data.scripts.slice().sort(SORT[sv.sort] || SORT.name);
        var tools = rows.length > 1 ? '<div class="script-tools"><label class="dt-search">' + UI.icon("search") + '<span class="sr-only">Search scripts</span>' +
          '<input type="search" data-script-q placeholder="Search scripts by name or file…"></label><label class="tb-sort">Sort<select data-script-sort>' +
          [["name", "Name"], ["recent", "Last run"], ["scheduled", "Scheduled first"], ["newest", "Newest"]].map(function (o) {
            return '<option value="' + o[0] + '"' + (sv.sort === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
          }).join("") + "</select></label></div>" : "";
        var body = rows.length ? tools + '<div class="script-list">' + rows.map(function (s) {
          var last = s.last_run, running = last && last.status === "running";
          return '<div class="script-row" data-id="' + s.id + '"><span class="script-icon">' + UI.icon("scripts") + "</span>" +
            '<div class="grow"><button type="button" class="link-btn cell-title" data-edit>' + esc(s.name) + '</button><div class="cell-sub">' +
            '<span class="cell-mono">' + esc(s.file) + "</span> · " + esc(UI.formatBytes(s.size)) + " · " + esc(scheduleText(s.schedule)) + "</div>" +
            '<div class="script-meta">' + (running ? '<span class="badge badge-status-running"><span class="spinner" style="width:10px;height:10px"></span>Running</span>'
              : last ? UI.statusBadge(last.status) + '<span class="cell-sub">' + esc(UI.relative(last.finished)) + " · exit " + esc(last.exit) + "</span>" : '<span class="cell-sub">Never run</span>') +
            (s.schedule ? '<span class="badge badge-status-info">' + UI.icon("clock") + "Scheduled</span>" : "") + "</div></div>" +
            '<div class="tm-actions">' + UI.button("Run", "data-run-script" + (running || !data.can_change ? " disabled" : ""), "btn-sm btn-primary", "play") +
            UI.button("Edit", 'data-edit title="Open the editor"', "btn-sm", "scripts") +
            UI.button(s.schedule ? "Unschedule" : "Schedule", s.schedule ? "data-unschedule" : "data-schedule-script", "btn-sm", "clock") +
            (last && last.output ? UI.button("Output", "data-output-script", "btn-sm btn-ghost", "reports") : "") +
            UI.button("", 'data-copy-script title="Copy the content" aria-label="Copy the content of ' + esc(s.name) + '"', "btn-sm btn-ghost", "copy") +
            UI.button("", 'data-duplicate title="Duplicate: a copy to change without touching this one" aria-label="Duplicate ' + esc(s.name) + '"', "btn-sm btn-ghost", "plus") +
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
              }).join("") + '<div class="action-foot"><span class="grow"></span>' + UI.button("Add and edit", 'data-add-template data-then-edit title="Add it to My scripts and open it in the editor to adapt it"', "btn-sm btn-ghost", "scripts") +
                UI.button("Add to my scripts", "data-add-template", "btn-sm", "play") + "</div></div>";
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
          var original = full.content;
          var done = UI.modal(s ? "Edit " + s.name : "New script", '<form class="form" onsubmit="return false"><label>Name<input name="name" maxlength="80" value="' + esc(full.name) +
            '"></label><div class="editor-bar"><label class="tb-sort">Insert<select data-snippet><option value="">Snippet…</option>' + SNIPPETS.map(function (sn, i) {
              return '<option value="' + i + '">' + esc(sn[0]) + "</option>";
            }).join("") + '</select></label><span class="grow"></span><span class="muted small" data-pos>Line 1, column 1</span></div>' +
            '<label class="sr-only" for="script-content">Commands (.bat)</label><textarea id="script-content" name="content" rows="16" spellcheck="false" class="cell-mono script-editor">' + esc(full.content) + "</textarea>" +
            '<div class="callout callout-warning" data-danger hidden>' + UI.icon("alert") + "<div></div></div>" +
            '<p class="muted small" style="margin:0">Runs with cmd.exe as administrator (SYSTEM when scheduled). Ctrl S saves. Test it with Run before scheduling it.</p></form>',
            [{ label: "Cancel", cls: "btn-ghost" },
              { label: "Save and run", cls: "", value: function (w) { var f = w.querySelector("form"); return { name: f.name.value.trim(), content: f.content.value, run: true }; } },
              { label: "Save", cls: "btn-primary", value: function (w) { var f = w.querySelector("form"); return { name: f.name.value.trim(), content: f.content.value }; } }]);
          done.then(function (v) {
            if (!v) return;
            var body = { name: v.name, content: v.content };
            (s ? API.post("/scripts/" + s.id + "/save", body) : API.post("/scripts", { name: v.name || "New script", content: v.content, filename: "script.bat" }))
              .then(function (r) {
                UI.toast(v.content === original && s ? "Saved (no changes to the commands)." : "Script saved.", "ok");
                load();
                var saved = s || r;
                if (v.run && saved && saved.id) {
                  API.post("/scripts/" + saved.id + "/run").then(function (x) {
                    if (x.preview) { UI.toast("Preview mode: the script did not run (recorded in History).", "info"); return; }
                    UI.toast((saved.name || v.name) + " is running…", "info");
                    waitForRun(saved);
                  }, function (er) { UI.toast(er.message, "error"); });
                }
              }, function (e) { UI.toast(e.message, "error"); });
          });
          var area = document.querySelector("#modal-root .script-editor");
          if (!area) return;
          var form = area.closest("form"), pos = form.querySelector("[data-pos]"), danger = form.querySelector("[data-danger]");
          area.closest(".modal").classList.add("modal-wide");
          var status = function () {
            var before = area.value.slice(0, area.selectionStart), line = before.split("\n").length, col = before.length - before.lastIndexOf("\n");
            pos.textContent = "Line " + line + ", column " + col + " · " + area.value.split("\n").length + " lines";
            var hits = DANGER.filter(function (d) { return d[0].test(area.value); }).map(function (d) { return d[1]; });
            danger.hidden = !hits.length;
            danger.querySelector("div").textContent = hits.length ? "Careful: " + hits.join("; ") + ". Check the paths before running it." : "";
          };
          ["input", "click", "keyup"].forEach(function (ev) { area.addEventListener(ev, status); });
          status();
          area.addEventListener("keydown", function (e) {
            if (e.key === "Tab") {  // Tab inserts spaces instead of leaving the editor
              e.preventDefault();
              area.setRangeText("    ", area.selectionStart, area.selectionEnd, "end");
            }
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
              e.preventDefault();
              var save = Array.prototype.filter.call(document.querySelectorAll("#modal-root .modal-actions button, #modal-root footer button"), function (b) { return b.textContent.trim() === "Save"; })[0];
              if (save) save.click();
            }
          });
          form.querySelector("[data-snippet]").addEventListener("change", function (e) {
            var sn = SNIPPETS[Number(e.target.value)];
            e.target.value = "";
            if (!sn) return;
            var at = area.selectionStart, before = area.value.slice(0, at), lead = before && !/\n$/.test(before) ? "\r\n" : "";
            area.setRangeText(lead + sn[1].replace(/\n/g, "\r\n") + "\r\n", at, area.selectionEnd, "end");
            area.focus();
            status();
          });
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
            if (b.hasAttribute("data-then-edit")) editor(r);
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
        if (b.hasAttribute("data-copy-script")) {
          API.get("/scripts/" + s.id).then(function (full) { App.copyText(full.content, "Script"); }, function (er) { UI.toast(er.message, "error"); });
        }
        if (b.hasAttribute("data-duplicate")) {
          API.get("/scripts/" + s.id).then(function (full) {
            return API.post("/scripts", { name: (s.name + " (copy)").slice(0, 80), content: full.content, filename: "copy" + s.file.slice(-4) });
          }).then(function (r) { UI.toast("Duplicated as " + r.name + ". The copy is not scheduled.", "ok"); load(); }, function (er) { UI.toast(er.message, "error"); });
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
      host.addEventListener("input", function (e) {
        if (!e.target.hasAttribute("data-script-q")) return;
        var q = e.target.value.toLowerCase().trim();
        host.querySelectorAll(".script-row").forEach(function (row) { row.hidden = !!q && row.textContent.toLowerCase().indexOf(q) < 0; });
      });
      host.addEventListener("change", function (e) {
        if (e.target.hasAttribute("data-script-sort")) { Components.store("scriptsView", { sort: e.target.value }); load(); return; }
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
