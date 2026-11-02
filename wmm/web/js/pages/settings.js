/* Settings: report branding, appearance, installation status and shortcuts. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  window.Pages.settings = {
    title: "Settings",
    render: function (el, App) {
      return Promise.all([API.get("/settings"), API.get("/schedules"), API.get("/health")]).then(function (r) {
        var s = r[0], inst = r[1].installation || {}, info = App.state.info, hc = r[2];
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
          '<div class="grid grid-2"><div class="stack">' +
          UI.card("Report branding", '<form class="form" id="settings-form" onsubmit="return false">' +
            field("company", "Company", "Shown on the report cover, e.g. your IT service company.") +
            field("technician", "Default technician", "Pre-filled in the Reports page.") +
            field("report_header", "Cover note", "Short text under the report title, e.g. contract or ticket number.", true) +
            field("report_footer", "Footer", "Contact details printed at the end of every report.", true) +
            '<div class="page-actions"><button class="btn btn-primary" type="submit">' + UI.icon("check") + "Save</button></div></form>") +
          UI.card("Appearance", '<div class="form"><label>Theme<span class="btn-group" role="group">' + ["system", "light", "dark"].map(function (t) {
            return '<button type="button" class="btn btn-sm' + (theme === t ? " active" : "") + '" data-theme="' + t + '">' + t.charAt(0).toUpperCase() + t.slice(1) + "</button>";
          }).join("") + '</span></label><label>Accent color<span style="display:flex;gap:8px">' + [["blue", "#0F6CBD"], ["teal", "#0E8A7B"], ["violet", "#6D4AD6"], ["orange", "#C2570C"], ["graphite", "#3E4C5E"]].map(function (c) {
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
          ]) + (inst.protected ? "" : '<div class="callout callout-warning">' + UI.icon("shield") + "<div>Schedules need a protected installation. Run once as administrator:" +
            '<pre class="log" style="min-height:0;margin-top:8px">' + esc(inst.command || "") + "</pre></div></div>")) +
          UI.card("Keyboard shortcuts", '<p class="muted" style="margin-top:0">Press <span class="kbd">?</span> anywhere to see all shortcuts, or <span class="kbd">Ctrl K</span> to search pages and actions.</p>' +
            UI.button("Show shortcuts", 'id="show-keys"', "", "keyboard")) +
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
        el.querySelector("#health-again").addEventListener("click", function (e) {
          e.currentTarget.disabled = true;
          e.currentTarget.classList.add("busy");
          API.get("/health?refresh=1").then(function (h) { App.state.health = h; App.render(); }, function (err) { UI.toast(err.message, "error"); });
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
