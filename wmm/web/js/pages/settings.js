/* Settings: a side menu of sections (one shown at a time, remembered) with branding, appearance, behaviour, dashboard,
   start-up, data and security, guides and the agent. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var SECTIONS = [
    ["general", "General", "settings", "Report branding"],
    ["appearance", "Appearance", "sun", "Theme, colors, text, animations"],
    ["behaviour", "Behaviour", "bolt", "Start page, refresh, tables, messages, sounds"],
    ["dashboard", "Dashboard", "dashboard", "Sections shown on the dashboard"],
    ["startup", "Start-up", "power", "Restore point and start with Windows"],
    ["data", "Data and security", "shield", "Inactivity, history, preferences"],
    ["guides", "Guides and shortcuts", "support", "Tips, tour, keyboard"],
    ["agent", "This agent", "cpu", "Installation and health check"]
  ];

  function store(k, v) { return Components.store(k, v); }
  function group(name, options, current) {
    return '<span class="btn-group" role="group">' + options.map(function (o) {
      return '<button type="button" class="btn btn-sm' + (String(current) === String(o[0]) ? " active" : "") + '" data-pref="' + name + '" data-value="' + esc(o[0]) + '">' + esc(o[1]) + "</button>";
    }).join("") + "</span>";
  }
  function check(id, on, label, hint) {
    return '<label class="check"><input type="checkbox" id="' + id + '"' + (on ? " checked" : "") + "> " + label + "</label>" + (hint ? '<span class="hint">' + hint + "</span>" : "");
  }

  window.Pages.settings = {
    title: "Settings",
    render: function (el, App) {
      return Promise.all([API.get("/settings"), API.get("/schedules"), API.get("/health"), API.get("/agent/autostart")]).then(function (r) {
        var s = r[0], inst = r[1].installation || {}, info = App.state.info, hc = r[2], auto = r[3];
        var active = (/[?&]s=(\w+)/.exec(location.hash) || [])[1] || store("settingsSection") || "general";
        if (!SECTIONS.some(function (x) { return x[0] === active; })) active = "general";
        App.setSubtitle("Preferences of this console and of this PC");
        var theme = Components.theme.get(), dashHidden = store("dashHidden") || [];
        var autoBlocked = info.preview ? "Not available in preview mode." : !info.admin ? "Restart the console as administrator to change it." :
          !auto.protected ? "Needs the protected installation in Program Files (see This agent)." : "";
        var field = function (key, label, hint, area) {
          return "<label>" + esc(label) + (area ? '<textarea name="' + key + '" maxlength="500" rows="3">' + esc(s[key]) + "</textarea>"
            : '<input name="' + key + '" maxlength="200" value="' + esc(s[key]) + '">') + '<span class="hint">' + esc(hint) + "</span></label>";
        };
        var pages = Hubs.CATEGORIES.map(function (c) { return [c.title, c.pages]; });

        var body = {
          general: UI.card("Report branding", '<form class="form" id="settings-form" onsubmit="return false">' +
            field("company", "Company", "Shown on the report cover, e.g. your IT service company.") +
            field("technician", "Default technician", "Pre-filled in the Reports page.") +
            field("report_header", "Cover note", "Short text under the report title, e.g. contract or ticket number.", true) +
            field("report_footer", "Footer", "Contact details printed at the end of every report.", true) +
            '<div class="page-actions"><button class="btn btn-primary" type="submit">' + UI.icon("check") + "Save</button></div></form>"),

          appearance: UI.card("Appearance", '<div class="form">' +
            "<label>Theme" + group("theme", [["system", "System"], ["light", "Light"], ["dark", "Dark"]], theme) + "</label>" +
            "<label>Animations" + group("fx", [["fun", "Fun"], ["subtle", "Subtle"], ["off", "Off"]], FX.level()) +
            '<button type="button" class="btn btn-sm btn-ghost" id="fx-try" style="align-self:flex-start">' + UI.icon("sparkle") + "Try them</button>" +
            '<span class="hint">Fun: entrances, scroll reveal, pointer glow, tilting tiles, charts that draw themselves and confetti. Subtle: short fades only. ' +
            "Off: nothing moves except spinners and progress bars.</span></label>" +
            '<label>Accent color<span style="display:flex;gap:8px">' + [["blue", "#0F6CBD"], ["teal", "#0E8A7B"], ["violet", "#6D4AD6"], ["orange", "#C2570C"], ["graphite", "#3E4C5E"]].map(function (c) {
              return '<button type="button" class="swatch-pick' + ((store("accent") || "blue") === c[0] ? " active" : "") + '" data-accent="' + c[0] + '" title="' + c[0] + '" style="background:' + c[1] + '"></button>';
            }).join("") + "</span></label>" +
            "<label>Text size" + group("fontSize", [["small", "Small"], ["normal", "Normal"], ["large", "Large"]], store("fontSize") || "normal") + "</label>" +
            "<label>Density" + group("density", [["comfortable", "Comfortable"], ["compact", "Compact"]], Components.density.get()) + "</label>" +
            check("contrast", store("contrast"), "High contrast", "Stronger borders and text for bright rooms and low vision.") +
            check("live-mini", !store("hideLiveMini"), "Show live CPU and memory in the top bar") +
            check("compact", document.body.classList.contains("sidebar-collapsed"), "Compact sidebar (icons only)") +
            '<button class="btn btn-sm" type="button" id="expand-cards" style="align-self:flex-start">' + UI.icon("refresh") + "Expand all collapsed cards</button></div>"),

          behaviour: UI.card("Behaviour", '<div class="form">' +
            '<label>Start page<select id="start-page"><option value="last">The page used last</option>' + pages.map(function (g) {
              return '<optgroup label="' + esc(g[0]) + '">' + g[1].map(function (p) {
                return '<option value="' + p[0] + '"' + (store("startPage") === p[0] ? " selected" : "") + ">" + esc(p[1]) + "</option>";
              }).join("") + "</optgroup>";
            }).join("") + '</select><span class="hint">The page the console opens on.</span></label>' +
            "<label>Dashboard refresh" + group("dashInterval", [[30, "30 s"], [60, "1 min"], [300, "5 min"], [900, "15 min"]], store("dashInterval") || 60) +
            '<span class="hint">How often the dashboard reloads by itself (when its auto-refresh switch is on).</span></label>' +
            "<label>Rows per table" + group("pageSize", [[10, "10"], [25, "25"], [50, "50"], [100, "100"]], store("pageSize") || 10) + "</label>" +
            "<label>Message duration" + group("toastSpeed", [["short", "Short"], ["normal", "Normal"], ["long", "Long"]], store("toastSpeed") || "normal") +
            '<span class="hint">How long notifications stay on screen. Hovering one always pauses it.</span></label>' +
            check("confirm-safe", store("confirmSafe"), "Ask before running safe actions too", "Every run shows its steps and asks for confirmation first.") +
            check("sound", store("sound"), "Play a sound when a run finishes", "Two short tones: rising when it succeeded, falling when something failed.") +
            check("desktop-notify", store("desktopNotify"), "Desktop notification when a run finishes in the background") + "</div>"),

          dashboard: UI.card("Dashboard sections", '<p class="muted" style="margin-top:0">Choose what the dashboard shows. The overall health and quick actions are always visible.</p><div class="form">' +
            window.Pages.dashboard.sections.map(function (sct) {
              return '<label class="check"><input type="checkbox" data-section="' + sct[0] + '"' + (dashHidden.indexOf(sct[0]) >= 0 ? "" : " checked") + "> " + esc(sct[1]) + "</label>";
            }).join("") + "</div>"),

          startup: UI.card("Start-up", '<div class="form">' +
            check("restore-on-start", s.restore_on_start === "1", "Create a restore point every time the console starts",
              "Runs as an automatic action when the console starts as administrator; it shows in Activity and History.") +
            '<label class="check"><input type="checkbox" id="autostart"' + (auto.enabled ? " checked" : "") + (autoBlocked ? " disabled" : "") + "> " +
            "Start Windows Maintenance Manager when I sign in to Windows</label>" +
            '<span class="hint">' + esc(autoBlocked || "The console starts as administrator 30 seconds after sign-in, without a prompt.") + "</span></div>"),

          data: UI.card("Inactivity", '<div class="form"><label>Disconnect this window after' +
            group("idleLock", [[0, "Never"], [15, "15 min"], [30, "30 min"], [60, "1 hour"]], store("idleLock") || 0) +
            '<span class="hint">After that time without use, this window can no longer run actions until access is requested again on this PC.</span></label></div>') +
            UI.card("History", '<div class="form"><label>Delete runs older than<select id="prune-days">' + [[30, "30 days"], [90, "90 days"], [180, "6 months"], [365, "1 year"]].map(function (d) {
              return '<option value="' + d[0] + '"' + (d[0] === 180 ? " selected" : "") + ">" + d[1] + "</option>";
            }).join("") + '</select><span class="hint">Removes old results and logs from History to keep the database small. Scores and schedules are kept.</span></label>' +
              UI.button("Delete old history", 'id="prune-go"', "btn-danger btn-sm", "trash") + "</div>") +
            UI.card("Console preferences", '<p class="muted" style="margin-top:0">Theme, favorites, dashboard layout, dismissed improvements and the other choices of this browser. ' +
              "Export them to use the same console setup on another PC.</p>" +
              '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Export", 'id="prefs-export"', "", "download") +
              UI.button("Import", 'id="prefs-import"', "", "upload") + UI.button("Reset", 'id="prefs-reset"', "btn-danger", "x") +
              '<input type="file" id="prefs-file" accept="application/json,.json" hidden></div>'),

          guides: UI.card("Guides and help", '<div class="form">' + check("guides-tips", Guides.enabled(), "Show a short “How this page works” tip the first time each page opens",
            "The full guide of any page opens with the ? button in the top bar or with F1.") + "</div>" +
            '<div class="page-actions" style="justify-content:flex-start;margin-top:10px">' + UI.button("Show all tips again", 'id="guides-reset"', "", "refresh") +
            UI.button("Take the guided tour", 'id="guides-tour"', "btn-primary", "sparkle") + "</div>") +
            UI.card("Keyboard shortcuts", '<p class="muted" style="margin-top:0">Press <span class="kbd">?</span> anywhere to see all shortcuts, or <span class="kbd">Ctrl K</span> to search pages and actions.</p>' +
              UI.button("Show shortcuts", 'id="show-keys"', "", "keyboard")),

          agent: UI.card("This agent", UI.definition([
            ["Device", esc(info.hostname)], ["Machine ID", '<span class="cell-mono">' + esc(info.machine_id) + "</span>"], ["Version", esc(info.version)],
            ["Mode", info.preview ? "Preview" : info.admin ? "Administrator" : "Read-only"], ["Data", '<span class="cell-mono">dati\\wmm.db</span>'],
            ["Installation", inst.protected ? '<span class="badge badge-status-ok">Protected</span>' : '<span class="badge badge-status-warning">Not protected</span>']
          ]) + UI.installCallout(inst)) +
            UI.card("Health check", '<p class="muted" style="margin-top:0">Dependencies and environment verified at start-up · ' + esc(UI.formatDate(hc.checked)) + "</p>" +
              UI.checklist(hc.checks.map(function (c) { return [c.name, c.status === "ok" ? "ok" : c.status === "warning" ? "warning" : "error", c.status === "ok" ? "OK" : c.status === "warning" ? "Warning" : "Failed", c.detail]; })),
              '<span class="badge badge-status-' + (hc.summary.error ? "error" : hc.summary.warning ? "warning" : "ok") + '">' + hc.summary.ok + " OK · " + hc.summary.warning + " warnings · " + hc.summary.error + " failed</span>" +
              '<button class="btn btn-sm" type="button" id="health-again">' + UI.icon("refresh") + "Run again</button>")
        };

        el.innerHTML = UI.pageHeader("Settings", "Pick a section on the left; every change is saved at once", "") +
          '<div class="settings-layout"><nav class="settings-nav" aria-label="Settings sections">' + SECTIONS.map(function (x) {
            return '<button type="button" class="settings-link' + (x[0] === active ? " active" : "") + '" data-sect="' + x[0] + '"' + (x[0] === active ? ' aria-current="true"' : "") + ">" +
              UI.icon(x[2]) + '<span><strong>' + esc(x[1]) + '</strong><span class="cell-sub">' + esc(x[3]) + "</span></span></button>";
          }).join("") + "</nav>" + '<div class="settings-panels">' + SECTIONS.map(function (x) {
            return '<section class="settings-panel stack" data-panel="' + x[0] + '"' + (x[0] === active ? "" : " hidden") + ">" + body[x[0]] + "</section>";
          }).join("") + "</div></div>";

        /* ---------- side menu ---------- */
        el.querySelector(".settings-nav").addEventListener("click", function (e) {
          var b = e.target.closest("[data-sect]");
          if (!b) return;
          var id = b.getAttribute("data-sect");
          store("settingsSection", id);
          el.querySelectorAll("[data-sect]").forEach(function (x) { var on = x === b; x.classList.toggle("active", on); if (on) x.setAttribute("aria-current", "true"); else x.removeAttribute("aria-current"); });
          el.querySelectorAll("[data-panel]").forEach(function (p) { p.hidden = p.getAttribute("data-panel") !== id; });
          var shown = el.querySelector('[data-panel="' + id + '"]');
          FX.pageEnter(shown);
          shown.scrollIntoView({ block: "nearest" });
        });

        /* ---------- button groups ---------- */
        var applyPref = {
          theme: function (v) { Components.theme.set(v); },
          fx: function (v) { FX.set(v); UI.toast(v === "fun" ? "Animations: fun. Enjoy!" : v === "subtle" ? "Animations: subtle." : "Animations are off.", "ok"); },
          fontSize: function (v) { store("fontSize", v); document.body.classList.remove("font-small", "font-large"); if (v !== "normal") document.body.classList.add("font-" + v); },
          density: function (v) { Components.density.set(v); },
          dashInterval: function (v) { store("dashInterval", Number(v)); UI.toast("The dashboard refreshes every " + (v < 60 ? v + " seconds." : v / 60 + " minute(s)."), "ok"); },
          pageSize: function (v) { store("pageSize", Number(v)); UI.toast("Tables show " + v + " rows per page.", "ok"); },
          toastSpeed: function (v) { store("toastSpeed", v); UI.toast("Messages: " + v + ".", "ok"); },
          idleLock: function (v) { store("idleLock", Number(v)); UI.toast(Number(v) ? "This window disconnects after " + v + " minutes without use." : "This window stays connected.", "ok"); }
        };
        el.querySelector(".settings-panels").addEventListener("click", function (e) {  // not on #content: it is shared by every page
          var b = e.target.closest("[data-pref]");
          if (!b) return;
          applyPref[b.getAttribute("data-pref")](b.getAttribute("data-value"));
          b.parentElement.querySelectorAll("[data-pref]").forEach(function (x) { x.classList.toggle("active", x === b); });
        });
        el.querySelectorAll("[data-accent]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var c = btn.getAttribute("data-accent");
            store("accent", c);
            if (c === "blue") document.documentElement.removeAttribute("data-accent"); else document.documentElement.setAttribute("data-accent", c);
            el.querySelectorAll("[data-accent]").forEach(function (b) { b.classList.toggle("active", b === btn); });
          });
        });

        /* ---------- switches ---------- */
        var on = function (id, fn) { el.querySelector("#" + id).addEventListener("change", function (e) { fn(e.target.checked, e.target); }); };
        on("contrast", function (v) { store("contrast", v); document.body.classList.toggle("high-contrast", v); });
        on("live-mini", function (v) { store("hideLiveMini", !v); document.getElementById("live-mini").hidden = !v; });
        on("compact", function (v) { document.body.classList.toggle("sidebar-collapsed", v); store("sidebar", v); });
        on("confirm-safe", function (v) { store("confirmSafe", v); UI.toast(v ? "Every run asks for confirmation." : "Safe actions run at once again.", "ok"); });
        on("sound", function (v) { store("sound", v); UI.toast(v ? "A sound plays when a run finishes." : "No sound.", "ok"); });
        on("desktop-notify", function (v) { store("desktopNotify", v); if (v && "Notification" in window && Notification.permission === "default") Notification.requestPermission(); });
        on("guides-tips", function (v) { store("guidesOff", !v); UI.toast(v ? "Page tips on." : "Page tips off. The ? button still opens every guide.", "info"); });
        el.querySelector("#start-page").addEventListener("change", function (e) {
          store("startPage", e.target.value);
          UI.toast("The console opens on " + e.target.selectedOptions[0].textContent.toLowerCase() + ".", "ok");
        });
        on("restore-on-start", function (v, box) {
          API.put("/settings", { restore_on_start: v ? "1" : "0" }).then(function () {
            UI.toast(v ? "A restore point is created at every start." : "No restore point at start.", "ok");
          }, function (err) { box.checked = !v; UI.toast(err.message, "error"); });
        });
        on("autostart", function (v, box) {
          box.disabled = true;
          API.put("/agent/autostart", { enabled: v }).then(function (a) {
            box.checked = a.enabled;
            UI.toast(a.enabled ? "The console starts when you sign in to Windows." : "The console no longer starts with Windows.", "ok");
          }, function (err) { box.checked = !v; UI.toast(err.message, "error"); }).then(function () { box.disabled = false; });
        });
        el.querySelectorAll("[data-section]").forEach(function (box) {
          box.addEventListener("change", function () {
            var key = box.getAttribute("data-section"), list = (store("dashHidden") || []).filter(function (k) { return k !== key; });
            if (!box.checked) list.push(key);
            store("dashHidden", list);
            UI.toast("Dashboard updated.", "ok");
          });
        });

        /* ---------- buttons ---------- */
        el.querySelector("#settings-form").addEventListener("submit", function (e) {
          var form = e.target, data = {};
          ["company", "technician", "report_header", "report_footer"].forEach(function (k) { data[k] = form[k].value; });
          API.put("/settings", data).then(function () { UI.toast("Settings saved.", "ok"); }, function (err) { UI.toast(err.message, "error"); });
        });
        el.querySelector("#fx-try").addEventListener("click", function (e) {
          if (!FX.moving()) { UI.toast("Animations are off: choose Fun or Subtle first.", "info"); return; }
          FX.burst(e.currentTarget);
          FX.floatText(e.currentTarget, "Wow!");
          FX.confetti({ count: 80 });
        });
        el.querySelector("#expand-cards").addEventListener("click", function () {
          try { localStorage.removeItem("wmm.collapsed"); } catch (err) { /* storage unavailable */ }
          UI.toast("All cards are expanded again.", "ok");
        });
        el.querySelector("#prune-go").addEventListener("click", function () {
          var days = Number(el.querySelector("#prune-days").value);
          UI.confirm("Delete old history?", "Runs older than " + days + " days and their logs are deleted from History. Scores and schedules are kept.",
            { ok: "Delete", danger: true }).then(function (ok) {
            if (!ok) return;
            API.post("/history/prune", { days: days }).then(function (r) {
              UI.toast(r.preview ? "Preview mode: nothing was deleted." : r.deleted + " old run(s) deleted.", r.preview ? "info" : "ok");
            }, function (err) { UI.toast(err.message, "error"); });
          });
        });
        el.querySelector("#guides-reset").addEventListener("click", function () { Guides.reset(); UI.toast("Every page shows its tip again the next time it opens.", "ok"); });
        el.querySelector("#guides-tour").addEventListener("click", function () { Guides.tour(0); });
        el.querySelector("#show-keys").addEventListener("click", Components.shortcutsHelp);
        el.querySelector("#health-again").addEventListener("click", function (e) {
          e.currentTarget.disabled = true;
          e.currentTarget.classList.add("busy");
          API.get("/health?refresh=1").then(function (h) { App.state.health = h; App.render(); }, function (err) { UI.toast(err.message, "error"); });
        });
        el.querySelector("#prefs-export").addEventListener("click", function () {
          var prefs = {};
          try {
            for (var i = 0; i < localStorage.length; i++) {
              var k = localStorage.key(i);
              if (k.indexOf("wmm.") === 0) prefs[k] = localStorage.getItem(k);
            }
          } catch (err) { /* storage unavailable */ }
          App.saveText(JSON.stringify({ kind: "wmm-preferences", version: info.version, exported: new Date().toISOString(), values: prefs }, null, 2), "wmm-preferences.json");
        });
        var file = el.querySelector("#prefs-file");
        el.querySelector("#prefs-import").addEventListener("click", function () { file.click(); });
        file.addEventListener("change", function () {
          if (!file.files.length) return;
          file.files[0].text().then(function (text) {
            var data = JSON.parse(text);
            if (!data || data.kind !== "wmm-preferences" || typeof data.values !== "object") throw new Error("This file is not a preferences export of Windows Maintenance Manager.");
            Object.keys(data.values).forEach(function (k) {
              // Only console preferences: anything else in the file is ignored.
              if (k.indexOf("wmm.") === 0 && typeof data.values[k] === "string") localStorage.setItem(k, data.values[k]);
            });
            UI.toast("Preferences imported. Reloading…", "ok");
            setTimeout(function () { location.reload(); }, 800);
          }).catch(function (err) { UI.toast(err instanceof SyntaxError ? "The file is not valid JSON." : err.message, "error"); });
        });
        el.querySelector("#prefs-reset").addEventListener("click", function () {
          UI.confirm("Reset console preferences", "Theme, favorites, dashboard layout, dismissed improvements and the visit checklist go back to their defaults. Data on this PC is not touched.",
            { ok: "Reset", danger: true }).then(function (ok) {
            if (!ok) return;
            try {
              Object.keys(localStorage).filter(function (k) { return k.indexOf("wmm.") === 0; }).forEach(function (k) { localStorage.removeItem(k); });
            } catch (err) { /* storage unavailable */ }
            location.reload();
          });
        });
      });
    }
  };
})();
