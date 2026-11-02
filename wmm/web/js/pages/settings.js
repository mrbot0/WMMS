/* Settings: report branding, appearance, installation status and shortcuts. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  window.Pages.settings = {
    title: "Settings",
    render: function (el, App) {
      return Promise.all([API.get("/settings"), API.get("/schedules"), API.get("/health"), API.get("/agent/autostart")]).then(function (r) {
        var s = r[0], inst = r[1].installation || {}, info = App.state.info, hc = r[2], auto = r[3];
        // Start with Windows runs the console as administrator without a prompt: only from the protected copy.
        var autoBlocked = info.preview ? "Not available in preview mode." : !info.admin ? "Restart the console as administrator to change it." :
          !auto.protected ? "Needs the protected installation in Program Files (see This agent)." : "";
        var startCard = UI.card("Start-up", '<div class="form">' +
          '<label class="check"><input type="checkbox" id="restore-on-start"' + (s.restore_on_start === "1" ? " checked" : "") + "> " +
          "Create a restore point every time the console starts</label>" +
          '<span class="hint">Runs as an automatic action when the console starts as administrator; it shows in Activity and History. ' +
          "Windows deletes the oldest restore points when their storage is full.</span>" +
          '<label class="check"><input type="checkbox" id="autostart"' + (auto.enabled ? " checked" : "") + (autoBlocked ? " disabled" : "") + "> " +
          "Start Windows Maintenance Manager when I sign in to Windows</label>" +
          '<span class="hint">' + esc(autoBlocked || "The console starts as administrator 30 seconds after sign-in, without a prompt. Open it from the link in its window.") + "</span></div>");
        var healthCard = UI.card("Health check", '<p class="muted" style="margin-top:0">Dependencies and environment verified at start-up · ' + esc(UI.formatDate(hc.checked)) + "</p>" +
          UI.checklist(hc.checks.map(function (c) { return [c.name, c.status === "ok" ? "ok" : c.status === "warning" ? "warning" : "error", c.status === "ok" ? "OK" : c.status === "warning" ? "Warning" : "Failed", c.detail]; })),
          '<span class="badge badge-status-' + (hc.summary.error ? "error" : hc.summary.warning ? "warning" : "ok") + '">' + hc.summary.ok + " OK · " + hc.summary.warning + " warnings · " + hc.summary.error + " failed</span>" +
          '<button class="btn btn-sm" type="button" id="health-again">' + UI.icon("refresh") + "Run again</button>");
        App.setSubtitle("Report branding, appearance and installation");
        var theme = Components.theme.get(), dashHidden = Components.store("dashHidden") || [];
        var field = function (key, label, hint, area) {
          return "<label>" + esc(label) + (area ? '<textarea name="' + key + '" maxlength="500" rows="3">' + esc(s[key]) + "</textarea>"
            : '<input name="' + key + '" maxlength="200" value="' + esc(s[key]) + '">') + '<span class="hint">' + esc(hint) + "</span></label>";
        };
        el.innerHTML = UI.pageHeader("Settings", "Stored on this device in dati\\wmm.db", "") + '<div class="grid">' + healthCard + "</div>" +
          '<div class="grid grid-2"><div class="stack">' + startCard +
          UI.card("Report branding", '<form class="form" id="settings-form" onsubmit="return false">' +
            field("company", "Company", "Shown on the report cover, e.g. your IT service company.") +
            field("technician", "Default technician", "Pre-filled in the Reports page.") +
            field("report_header", "Cover note", "Short text under the report title, e.g. contract or ticket number.", true) +
            field("report_footer", "Footer", "Contact details printed at the end of every report.", true) +
            '<div class="page-actions"><button class="btn btn-primary" type="submit">' + UI.icon("check") + "Save</button></div></form>") +
          UI.card("Appearance", '<div class="form"><label>Theme<span class="btn-group" role="group">' + ["system", "light", "dark"].map(function (t) {
            return '<button type="button" class="btn btn-sm' + (theme === t ? " active" : "") + '" data-theme="' + t + '">' + t.charAt(0).toUpperCase() + t.slice(1) + "</button>";
          }).join("") + '</span></label><label>Animations<span class="btn-group" role="group">' + [["fun", "Fun"], ["subtle", "Subtle"], ["off", "Off"]].map(function (f) {
            return '<button type="button" class="btn btn-sm' + (FX.level() === f[0] ? " active" : "") + '" data-fx-level="' + f[0] + '">' + f[1] + "</button>";
          }).join("") + '</span><span class="hint">Fun: page entrances, hover effects and confetti when work completes. Subtle: short fades only. ' +
            "Off: nothing moves except spinners and progress bars.</span></label>" +
          '<label>Accent color<span style="display:flex;gap:8px">' + [["blue", "#0F6CBD"], ["teal", "#0E8A7B"], ["violet", "#6D4AD6"], ["orange", "#C2570C"], ["graphite", "#3E4C5E"]].map(function (c) {
            return '<button type="button" class="swatch-pick' + ((Components.store("accent") || "blue") === c[0] ? " active" : "") + '" data-accent="' + c[0] + '" title="' + c[0] + '" style="background:' + c[1] + '"></button>';
          }).join("") + '</span></label><label>Text size<span class="btn-group" role="group">' + [["small", "Small"], ["normal", "Normal"], ["large", "Large"]].map(function (f) {
            return '<button type="button" class="btn btn-sm' + ((Components.store("fontSize") || "normal") === f[0] ? " active" : "") + '" data-font="' + f[0] + '">' + f[1] + "</button>";
          }).join("") + '</span></label><label class="check"><input type="checkbox" id="desktop-notify"' + (Components.store("desktopNotify") ? " checked" : "") +
            '> Desktop notification when a run finishes in the background</label><label>Density<span class="btn-group" role="group">' + ["comfortable", "compact"].map(function (t) {
            return '<button type="button" class="btn btn-sm' + (Components.density.get() === t ? " active" : "") + '" data-density="' + t + '">' + t.charAt(0).toUpperCase() + t.slice(1) + "</button>";
          }).join("") + '</span></label><label class="check"><input type="checkbox" id="compact"' + (document.body.classList.contains("sidebar-collapsed") ? " checked" : "") +
            '> Compact sidebar</label><button class="btn btn-sm" type="button" id="expand-cards" style="align-self:flex-start">' + UI.icon("refresh") + "Expand all collapsed cards</button></div>") + "</div>" +
          '<div class="stack">' +
          UI.card("This agent", UI.definition([
            ["Device", esc(info.hostname)], ["Machine ID", '<span class="cell-mono">' + esc(info.machine_id) + "</span>"], ["Version", esc(info.version)],
            ["Mode", info.preview ? "Preview" : info.admin ? "Administrator" : "Read-only"], ["API", '<span class="cell-mono">http://127.0.0.1/api/v1</span>'],
            ["Installation", inst.protected ? '<span class="badge badge-status-ok">Protected</span>' : '<span class="badge badge-status-warning">Not protected</span>']
          ]) + UI.installCallout(inst)) +
          UI.card("Keyboard shortcuts", '<p class="muted" style="margin-top:0">Press <span class="kbd">?</span> anywhere to see all shortcuts, or <span class="kbd">Ctrl K</span> to search pages and actions.</p>' +
            UI.button("Show shortcuts", 'id="show-keys"', "", "keyboard")) +
          UI.card("Guides and help", '<div class="form"><label class="check"><input type="checkbox" id="guides-tips"' + (Guides.enabled() ? " checked" : "") + "> " +
            "Show a short “How this page works” tip the first time each page opens</label>" +
            '<span class="hint">The full guide of any page opens with the ? button in the top bar or with F1.</span></div>' +
            '<div class="page-actions" style="justify-content:flex-start;margin-top:10px">' + UI.button("Show all tips again", 'id="guides-reset"', "", "refresh") +
            UI.button("Take the guided tour", 'id="guides-tour"', "btn-primary", "sparkle") + UI.button("Guide for Settings", 'data-guide-open="settings"', "btn-ghost", "support") + "</div>") +
          UI.card("Dashboard sections", '<p class="muted" style="margin-top:0">Choose what the dashboard shows. The overall health and quick actions are always visible.</p><div class="form">' +
            window.Pages.dashboard.sections.map(function (sct) {
              return '<label class="check"><input type="checkbox" data-section="' + sct[0] + '"' + (dashHidden.indexOf(sct[0]) >= 0 ? "" : " checked") + "> " + esc(sct[1]) + "</label>";
            }).join("") + "</div>") +
          UI.card("Console preferences", '<p class="muted" style="margin-top:0">Theme, favorites, dashboard layout, dismissed improvements and the other choices of this browser. ' +
            "Export them to use the same console setup on another PC.</p>" +
            '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Export", 'id="prefs-export"', "", "download") +
            UI.button("Import", 'id="prefs-import"', "", "upload") + UI.button("Reset", 'id="prefs-reset"', "btn-danger", "x") +
            '<input type="file" id="prefs-file" accept="application/json,.json" hidden></div>') + "</div></div>";

        el.querySelector("#settings-form").addEventListener("submit", function (e) {
          var form = e.target, body = {};
          ["company", "technician", "report_header", "report_footer"].forEach(function (k) { body[k] = form[k].value; });
          API.put("/settings", body).then(function () { UI.toast("Settings saved.", "ok"); }, function (err) { UI.toast(err.message, "error"); });
        });
        el.querySelectorAll("[data-theme]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            Components.theme.set(btn.getAttribute("data-theme"));
            el.querySelectorAll("[data-theme]").forEach(function (b) { b.classList.toggle("active", b === btn); });
          });
        });
        el.querySelector("#compact").addEventListener("change", function (e) {
          document.body.classList.toggle("sidebar-collapsed", e.target.checked);
          Components.store("sidebar", e.target.checked);
        });
        el.querySelector("#show-keys").addEventListener("click", Components.shortcutsHelp);
        el.querySelector("#guides-tips").addEventListener("change", function (e) {
          Components.store("guidesOff", !e.target.checked);
          UI.toast(e.target.checked ? "Page tips on." : "Page tips off. The ? button still opens every guide.", "info");
        });
        el.querySelector("#guides-reset").addEventListener("click", function () {
          Guides.reset();
          UI.toast("Every page shows its tip again the next time it opens.", "ok");
          App.render();
        });
        el.querySelector("#guides-tour").addEventListener("click", function () { Guides.tour(0); });
        el.querySelector("#health-again").addEventListener("click", function (e) {
          e.currentTarget.disabled = true;
          e.currentTarget.classList.add("busy");
          API.get("/health?refresh=1").then(function (h) { App.state.health = h; App.render(); }, function (err) { UI.toast(err.message, "error"); });
        });
        el.querySelectorAll("[data-fx-level]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var value = btn.getAttribute("data-fx-level");
            FX.set(value);
            el.querySelectorAll("[data-fx-level]").forEach(function (b) { b.classList.toggle("active", b === btn); });
            UI.toast(value === "fun" ? "Animations: fun. Enjoy!" : value === "subtle" ? "Animations: subtle." : "Animations are off.", "ok");
          });
        });
        el.querySelectorAll("[data-density]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            Components.density.set(btn.getAttribute("data-density"));
            el.querySelectorAll("[data-density]").forEach(function (b) { b.classList.toggle("active", b === btn); });
          });
        });
        el.querySelectorAll("[data-accent]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var c = btn.getAttribute("data-accent");
            Components.store("accent", c);
            if (c === "blue") document.documentElement.removeAttribute("data-accent"); else document.documentElement.setAttribute("data-accent", c);
            el.querySelectorAll("[data-accent]").forEach(function (b) { b.classList.toggle("active", b === btn); });
          });
        });
        el.querySelectorAll("[data-font]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var f = btn.getAttribute("data-font");
            Components.store("fontSize", f);
            document.body.classList.remove("font-small", "font-large");
            if (f !== "normal") document.body.classList.add("font-" + f);
            el.querySelectorAll("[data-font]").forEach(function (b) { b.classList.toggle("active", b === btn); });
          });
        });
        el.querySelector("#desktop-notify").addEventListener("change", function (e) {
          Components.store("desktopNotify", e.target.checked);
          if (e.target.checked && "Notification" in window && Notification.permission === "default") Notification.requestPermission();
        });
        el.querySelector("#restore-on-start").addEventListener("change", function (e) {
          var box = e.target;
          API.put("/settings", { restore_on_start: box.checked ? "1" : "0" }).then(function () {
            UI.toast(box.checked ? "A restore point is created at every start." : "No restore point at start.", "ok");
          }, function (err) { box.checked = !box.checked; UI.toast(err.message, "error"); });
        });
        el.querySelector("#autostart").addEventListener("change", function (e) {
          var box = e.target;
          box.disabled = true;
          API.put("/agent/autostart", { enabled: box.checked }).then(function (a) {
            box.checked = a.enabled;
            UI.toast(a.enabled ? "The console starts when you sign in to Windows." : "The console no longer starts with Windows.", "ok");
          }, function (err) { box.checked = !box.checked; UI.toast(err.message, "error"); }).then(function () { box.disabled = false; });
        });
        el.querySelectorAll("[data-section]").forEach(function (box) {
          box.addEventListener("change", function () {
            var key = box.getAttribute("data-section"), list = (Components.store("dashHidden") || []).filter(function (k) { return k !== key; });
            if (!box.checked) list.push(key);
            Components.store("dashHidden", list);
            UI.toast("Dashboard updated.", "ok");
          });
        });
        el.querySelector("#prefs-export").addEventListener("click", function () {
          var prefs = {};
          try {
            for (var i = 0; i < localStorage.length; i++) {
              var k = localStorage.key(i);
              if (k.indexOf("wmm.") === 0) prefs[k] = localStorage.getItem(k);
            }
          } catch (e) { /* storage unavailable */ }
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
            } catch (e) { /* storage unavailable */ }
            location.reload();
          });
        });
        el.querySelector("#expand-cards").addEventListener("click", function () {
          try { localStorage.removeItem("wmm.collapsed"); } catch (e) { /* storage unavailable */ }
          UI.toast("All cards are expanded again.", "ok");
        });
      });
    }
  };
})();
