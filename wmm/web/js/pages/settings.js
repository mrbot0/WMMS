/* Settings: a side menu of sections (one shown at a time, remembered) with branding, appearance, behaviour, dashboard,
   start-up, data and security, guides and the agent. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var SECTIONS = [
    ["general", "General", "settings", "Report branding"],
    ["appearance", "Appearance", "sun", "Theme, colors, text, animations"],
    ["behaviour", "Behaviour", "bolt", "Start page, formats, tables, keyboard"],
    ["notifications", "Notifications", "bell", "Sounds, volume, quiet hours, alerts"],
    ["maintenance", "Maintenance", "clock", "Schedule defaults, battery, reports"],
    ["dashboard", "Dashboard", "dashboard", "Sections shown on the dashboard"],
    ["startup", "Start-up", "power", "Restore point and start with Windows"],
    ["data", "Data and security", "shield", "Privacy, inactivity, history, preferences"],
    ["guides", "Guides and shortcuts", "support", "Tips, tour, keyboard"],
    ["agent", "This agent", "cpu", "Installation and health check"]
  ];

  function store(k, v) { return Components.store(k, v); }
  /* The preferences of each section, for “Reset this section”. */
  var SECTION_KEYS = {
    appearance: ["accent", "fontSize", "density", "corners", "contrast", "cbSafe", "noBlur", "wideText", "underlineLinks", "hideLiveMini", "sidebar",
      "sidebarWidth", "shadows", "typeface", "pageWidth", "hideStatusbar", "noTips"],
    behaviour: ["startPage", "dashInterval", "pageSize", "toastSpeed", "confirmSafe", "warnOnClose", "noKeyShortcuts", "paletteActions", "pageTabs", "autoScanDays",
      "liveInterval", "toastLevel", "timeFormat", "dateStyle", "sizeUnits"],
    notifications: ["sound", "soundVolume", "desktopNotify", "notifyProblemsOnly", "titleProgress", "flashTitle", "speak", "scheduleNotice", "quietHours"],
    maintenance: ["defaultTime", "defaultDelay", "batteryWarn", "autoOpenReports", "autoDrawer", "longRunMinutes", "tempAlert", "sensorInterval"],
    dashboard: ["dashHidden", "pinnedPages"],
    data: ["privacy", "hideDevice", "idleLock"]
  };
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
    sections: SECTIONS,
    render: function (el, App) {
      return Promise.all([API.get("/settings"), API.get("/schedules").catch(function () { return { installation: {} }; }),
        API.get("/health").catch(function () { return { checks: [], summary: { ok: 0, warning: 0, error: 0 } }; }), API.get("/agent/autostart").catch(function () { return {}; })]).then(function (r) {
        var s = r[0], inst = r[1].installation || {}, info = App.state.info, hc = r[2], auto = r[3];
        var active = (/[?&]s=(\w+)/.exec(location.hash) || [])[1] || store("settingsSection") || "general";
        var sezioni = SECTIONS.concat(window.Settings29 ? Settings29.sections() : [], window.Settings210 ? Settings210.sections() : []);  // 2.9: account, security, channels, app, runs, data
        if (!sezioni.some(function (x) { return x[0] === active; })) active = "general";
        App.setSubtitle("Preferences of this console and of this PC");
        var theme = Components.theme.get(), dashHidden = store("dashHidden") || [];
        var quiet = Object.assign({ on: false, from: "22:00", to: "07:00" }, store("quietHours") || {});
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
            "<label>Language" + group("lang", [["auto", "Automatic"], ["en", "English"], ["it", "Italiano"]], window.I18N ? I18N.choice() : "auto") +
            '<span class="hint">Automatic follows the browser language. Data, paths and program names stay as Windows writes them.</span></label>' +
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
            "<label>Corners" + group("corners", [["rounded", "Rounded"], ["square", "Square"]], store("corners") || "rounded") + "</label>" +
            "<label>Menu width" + group("sidebarWidth", [["narrow", "Narrow"], ["normal", "Normal"], ["wide", "Wide"]], store("sidebarWidth") || "normal") + "</label>" +
            "<label>Shadows" + group("shadows", [["none", "None"], ["soft", "Soft"], ["strong", "Strong"]], store("shadows") || "soft") + "</label>" +
            "<label>Typeface" + group("typeface", [["system", "Segoe UI"], ["readable", "Verdana (more legible)"], ["rounded", "Rounded"]], store("typeface") || "system") + "</label>" +
            "<label>Page width" + group("pageWidth", [["full", "Full screen"], ["centered", "Centered (1400 px)"]], store("pageWidth") || "full") +
            '<span class="hint">Centered keeps lines short on very wide monitors.</span></label>' +
            check("hide-statusbar", store("hideStatusbar"), "Hide the status bar at the bottom") +
            check("no-tips", store("noTips"), "Turn off hover tooltips", "Titles of buttons and values stay available to screen readers.") +
            check("contrast", store("contrast"), "High contrast", "Stronger borders and text for bright rooms and low vision.") +
            check("cb-safe", store("cbSafe"), "Color-blind friendly status colors", "Blue for good and orange for problems instead of green and red; icons stay the same.") +
            check("no-blur", store("noBlur"), "Reduce transparency", "Solid top bar, menus and dialogs: easier to read and lighter on old graphics cards.") +
            check("wide-text", store("wideText"), "Wider letter and line spacing", "Helps reading long descriptions, also with dyslexia.") +
            check("underline-links", store("underlineLinks"), "Always underline links") +
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
            check("warn-close", store("warnOnClose") !== false, "Ask before closing the tab while a run is in progress", "The run goes on in the agent anyway; this only avoids closing the view by mistake.") +
            check("no-keys", store("noKeyShortcuts"), "Turn off single-key shortcuts", "G then a letter, /, ? and Shift shortcuts stop working; Ctrl K still opens search. Useful with screen readers or speech input.") +
            check("page-tabs", store("pageTabs") !== false, "Split long pages into tabs", "Dashboard, area pages, Hardware and Schedules show one group at a time: overview first, details after.") +
            check("palette-actions", store("paletteActions") !== false, "List actions in the search (Ctrl K)", "Off: the search shows pages, commands and settings only, without the 200+ tools.") +
            "<label>Scan at start when the last scan is older than" + group("autoScanDays", [[0, "Never"], [1, "1 day"], [3, "3 days"], [7, "1 week"]], store("autoScanDays") || 0) +
            '<span class="hint">Only when the console runs as administrator; the scan changes nothing on the PC.</span></label>' +
            "<label>Live CPU and memory in the top bar" + group("liveInterval", [[3, "Every 3 s"], [10, "Every 10 s"], [30, "Every 30 s"], [0, "Off"]], store("liveInterval") != null ? store("liveInterval") : 3) + "</label>" +
            "<label>Messages shown" + group("toastLevel", [["all", "All"], ["problems", "Only warnings and errors"]], store("toastLevel") || "all") + "</label></div>") +
            UI.card("Formats", '<div class="form">' +
              "<label>Time" + group("timeFormat", [["system", "Like Windows"], ["24", "24-hour"], ["12", "12-hour"]], store("timeFormat") || "system") + "</label>" +
              "<label>Dates" + group("dateStyle", [["short", "02 Nov 2026"], ["numeric", "02/11/2026"], ["iso", "2026-11-02"]], store("dateStyle") || "short") + "</label>" +
              "<label>Sizes" + group("sizeUnits", [["binary", "Windows (1 GB = 1024 MB)"], ["decimal", "Decimal (1 GB = 1000 MB)"]], store("sizeUnits") || "binary") +
              '<span class="hint">Decimal matches the size printed on disk boxes; Windows Explorer uses the other one.</span></label></div>'),

          notifications: UI.card("Sounds and alerts", '<div class="form">' +
            check("sound", store("sound"), "Play a sound when a run finishes", "Two short tones: rising when it succeeded, falling when something failed.") +
            "<label>Volume" + group("soundVolume", [["low", "Low"], ["medium", "Medium"], ["high", "High"]], store("soundVolume") || "medium") +
            '<button type="button" class="btn btn-sm btn-ghost" id="sound-test" style="align-self:flex-start">' + UI.icon("play") + "Test</button></label>" +
            check("desktop-notify", store("desktopNotify"), "Desktop notification when a run finishes in the background") +
            check("problems-only", store("notifyProblemsOnly"), "Only for runs with warnings or errors", "Successful runs show in the console but stay silent on the desktop.") +
            check("title-progress", store("titleProgress") !== false, "Show the run percentage in the browser tab", "Title and icon of the tab show the progress, visible from other tabs.") +
            check("flash-title", store("flashTitle"), "Blink the tab title when a run finishes in the background", "Until you look at the console again.") +
            check("speak", store("speak"), "Read the result aloud", "Uses the Windows voice: “Run completed” or “Run finished with errors”.") +
            '<button type="button" class="btn btn-sm btn-ghost" id="speak-test" style="align-self:flex-start">' + UI.icon("play") + "Test the voice</button>" +
            check("schedule-notice", store("scheduleNotice") !== false, "On the dashboard, report the scheduled runs since the last visit", "How many ran and how many failed while the console was closed.") + "</div>") +
            UI.card("Email and Telegram alerts", '<div id="remote-alerts"></div>') +
            UI.card("Periodic report", '<div id="remote-digest"></div>') +
            UI.card("Quiet hours", '<div class="form">' + check("quiet-on", quiet.on, "No sounds or desktop notifications during these hours") +
              '<div class="form-row"><label>From<input type="time" id="quiet-from" value="' + esc(quiet.from) + '"></label><label>To<input type="time" id="quiet-to" value="' + esc(quiet.to) + '"></label></div>' +
              '<span class="hint">The hours may span midnight, for example 22:00 to 07:00. Runs still finish and appear in Activity and History.</span></div>'),

          maintenance: UI.card("Schedule defaults", '<div class="form">' +
            '<label>Default time of new schedules<input type="time" id="default-time" value="' + esc(store("defaultTime") || "12:00") + '">' +
            '<span class="hint">Pre-filled for daily, weekly and monthly schedules; choose a time when the PC is usually on. ' +
            "One-time schedules start an hour from now; suggested routines keep their own time.</span></label>" +
            "<label>Wait after startup or sign-in" + group("defaultDelay", [[0, "None"], [2, "2 min"], [5, "5 min"], [10, "10 min"], [15, "15 min"]], store("defaultDelay") != null ? store("defaultDelay") : 0) +
            '<span class="hint">Pre-filled for “At every startup” and “At every sign-in”, so the PC can finish starting first.</span></label></div>') +
            UI.card("Runs", '<div class="form">' +
              check("battery-warn", store("batteryWarn"), "Ask before long runs on battery", "Runs of 10 minutes or more ask first when a laptop is not plugged in.") +
              check("auto-reports", store("autoOpenReports") !== false, "Open the output of diagnostic reports when they finish", "Off: the output stays one click away in Activity and History.") +
              check("auto-drawer", store("autoDrawer") !== false, "Open the Activity panel when a run starts", "Off: progress stays in the top line and in the tab title.") +
              "<label>Ask before runs longer than" + group("longRunMinutes", [[0, "Never"], [30, "30 min"], [60, "1 hour"]], store("longRunMinutes") || 0) + "</label></div>") +
            UI.card("Hardware sensors", '<div class="form">' +
              "<label>Temperature alert for processor and graphics" + group("tempAlert", [[80, "80 °C"], [85, "85 °C"], [90, "90 °C"], [95, "95 °C"]], store("tempAlert") || 90) +
              '<span class="hint">Disks alert 20 °C lower. The Hardware page warns once every 10 minutes per sensor.</span></label>' +
              "<label>Sensor refresh" + group("sensorInterval", [[2, "2 s"], [5, "5 s"], [10, "10 s"], [30, "30 s"]], store("sensorInterval") || 5) + "</label></div>"),

          dashboard: UI.card("Dashboard sections", '<p class="muted" style="margin-top:0">Choose what the dashboard shows. The overall health and quick actions are always visible.</p><div class="form">' +
            window.Pages.dashboard.sections.map(function (sct) {
              return '<label class="check"><input type="checkbox" data-section="' + sct[0] + '"' + (dashHidden.indexOf(sct[0]) >= 0 ? "" : " checked") + "> " + esc(sct[1]) + "</label>";
            }).join("") + "</div>"),

          startup: UI.card("Start-up", '<div class="form">' +
            check("restore-on-start", s.restore_on_start === "1", "Create a restore point every time the console starts",
              "Runs as an automatic action when the console starts as administrator; it shows in Activity and History.") +
            check("restore-before-changes", s.restore_before_changes !== "0", "Create a restore point before uninstalling programs, removing Store apps and deleting registry keys",
              "A point made in the last hour is reused. History › Undo opens System Restore on the point made before a change.") +
            '<label class="check"><input type="checkbox" id="autostart"' + (auto.enabled ? " checked" : "") + (autoBlocked ? " disabled" : "") + "> " +
            "Start Windows Maintenance Manager when I sign in to Windows</label>" +
            '<span class="hint">' + esc(autoBlocked || "30 seconds after sign-in the console opens in your browser, as administrator and without a prompt. " +
              "No window stays open: stop it from the search (Ctrl K › Stop Windows Maintenance Manager). Turn it off and on again to update an existing task.") + "</span></div>"),

          data: UI.card("Privacy", '<div class="form">' +
            check("privacy", store("privacy"), "Privacy mode: hide serial numbers, MAC addresses and IDs on screen",
              "For screen sharing and remote sessions. Hover a hidden value to read it. Shortcut: Shift P.") +
            check("hide-device", store("hideDevice"), "Hide the device name in the top bar", "For screenshots and screen sharing; reports still name the PC.") +
            '<button class="btn btn-sm" type="button" id="clear-recent" style="align-self:flex-start">' + UI.icon("x") + "Clear recent commands and pages</button>" +
            '<button class="btn btn-sm" type="button" id="forget-recs" style="align-self:flex-start">' + UI.icon("refresh") + "Show hidden and snoozed improvements again</button>" +
            '<button class="btn btn-sm" type="button" id="reset-filters" style="align-self:flex-start">' + UI.icon("x") + "Reset the filters of every page</button>" +
            '<span class="hint">Forgets what the search (Ctrl K) lists under Recent pages and recent commands.</span></div>') +
            UI.card("Inactivity", '<div class="form"><label>Disconnect this window after' +
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
            ["Device", esc(info.hostname)], ["Machine ID", '<span class="cell-mono sensitive">' + esc(info.machine_id) + "</span>"], ["Version", esc(info.version)],
            ["Mode", info.preview ? "Preview" : info.admin ? "Administrator" : "Read-only"], ["Data", '<span class="cell-mono">dati\\wmm.db</span>'],
            ["Installation", inst.protected ? '<span class="badge badge-status-ok">Protected</span>' : '<span class="badge badge-status-warning">Not protected</span>']
          ]) + UI.installCallout(inst)) +
            UI.card("Program updates", '<div id="program-updates"></div>') +
            UI.card("Health check", '<p class="muted" style="margin-top:0">Dependencies and environment verified at start-up · ' + esc(UI.formatDate(hc.checked)) + "</p>" +
              UI.checklist(hc.checks.map(function (c) { return [c.name, c.status === "ok" ? "ok" : c.status === "warning" ? "warning" : "error", c.status === "ok" ? "OK" : c.status === "warning" ? "Warning" : "Failed", c.detail]; })),
              '<span class="badge badge-status-' + (hc.summary.error ? "error" : hc.summary.warning ? "warning" : "ok") + '">' + hc.summary.ok + " OK · " + hc.summary.warning + " warnings · " + hc.summary.error + " failed</span>" +
              '<button class="btn btn-sm" type="button" id="health-again">' + UI.icon("refresh") + "Run again</button>")
        };

        if (window.Settings29) Settings29.sections().forEach(function (x) { body[x[0]] = Settings29.body(x[0]); });
        if (window.Settings210) Settings210.sections().forEach(function (x) { body[x[0]] = Settings210.body(x[0]); });
        el.innerHTML = UI.pageHeader("Settings", "Pick a section on the left; every change is saved at once", "") +
          '<div class="settings-layout"><nav class="settings-nav" aria-label="Settings sections">' +
          '<label class="dt-search settings-search">' + UI.icon("search") + '<span class="sr-only">Search settings</span><input type="search" id="settings-q" placeholder="Search settings…"></label>' +
          '<p class="muted small settings-noresult" hidden>No setting matches.</p>' + sezioni.map(function (x) {
            return '<button type="button" class="settings-link' + (x[0] === active ? " active" : "") + '" data-sect="' + x[0] + '"' + (x[0] === active ? ' aria-current="true"' : "") + ">" +
              UI.icon(x[2]) + '<span><strong>' + esc(x[1]) + '</strong><span class="cell-sub">' + esc(x[3]) + "</span></span></button>";
          }).join("") + "</nav>" + '<div class="settings-panels">' + sezioni.map(function (x) {
            var reset = SECTION_KEYS[x[0]] ? '<div class="section-reset"><button type="button" class="btn btn-sm btn-ghost" data-reset-section="' + x[0] + '" data-title="' + esc(x[1]) + '">' +
              UI.icon("refresh") + "Reset this section</button></div>" : "";
            return '<section class="settings-panel stack" data-panel="' + x[0] + '"' + (x[0] === active ? "" : " hidden") + ">" + body[x[0]] + reset + "</section>";
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
          lang: function (v) { if (window.I18N) I18N.set(v); },  // reloads the console in the chosen language
          fx: function (v) { FX.set(v); UI.toast(v === "fun" ? "Animations: fun. Enjoy!" : v === "subtle" ? "Animations: subtle." : "Animations are off.", "ok"); },
          fontSize: function (v) { store("fontSize", v); document.body.classList.remove("font-small", "font-large"); if (v !== "normal") document.body.classList.add("font-" + v); },
          density: function (v) { Components.density.set(v); },
          dashInterval: function (v) { store("dashInterval", Number(v)); UI.toast("The dashboard refreshes every " + (v < 60 ? v + " seconds." : v / 60 + " minute(s)."), "ok"); },
          pageSize: function (v) { store("pageSize", Number(v)); UI.toast("Tables show " + v + " rows per page.", "ok"); },
          toastSpeed: function (v) { store("toastSpeed", v); UI.toast("Messages: " + v + ".", "ok"); },
          idleLock: function (v) { store("idleLock", Number(v)); UI.toast(Number(v) ? "This window disconnects after " + v + " minutes without use." : "This window stays connected.", "ok"); },
          corners: function (v) { store("corners", v); App.applyLook(); },
          timeFormat: function (v) { store("timeFormat", v); UI.toast("Times now look like " + UI.formatDate(new Date().toISOString()) + ".", "ok"); },
          dateStyle: function (v) { store("dateStyle", v); UI.toast("Dates now look like " + UI.formatDate(new Date().toISOString(), false) + ".", "ok"); },
          sizeUnits: function (v) { store("sizeUnits", v); UI.toast("500 GB disks now show as " + UI.formatBytes(500e9) + ".", "ok"); },
          soundVolume: function (v) { store("soundVolume", v); },
          defaultDelay: function (v) { store("defaultDelay", Number(v)); UI.toast(Number(v) ? "Startup and sign-in schedules wait " + v + " minutes by default." : "No default wait.", "ok"); },
          sidebarWidth: function (v) { store("sidebarWidth", v); App.applyLook(); },
          shadows: function (v) { store("shadows", v); App.applyLook(); },
          typeface: function (v) { store("typeface", v); App.applyLook(); },
          pageWidth: function (v) { store("pageWidth", v); App.applyLook(); },
          autoScanDays: function (v) { store("autoScanDays", Number(v)); UI.toast(Number(v) ? "The console scans at start when the last scan is older than " + v + " day(s)." : "No scan at start.", "ok"); },
          liveInterval: function (v) {
            store("liveInterval", Number(v));
            if (!Number(v)) document.getElementById("live-mini").textContent = "";
          },
          toastLevel: function (v) { store("toastLevel", v); if (v === "all") UI.toast("All messages are shown.", "ok"); },
          longRunMinutes: function (v) { store("longRunMinutes", Number(v)); },
          tempAlert: function (v) { store("tempAlert", Number(v)); UI.toast("Processor and graphics alert at " + v + " °C, disks at " + (v - 20) + " °C.", "ok"); },
          sensorInterval: function (v) { store("sensorInterval", Number(v)); }
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
        if (window.AlertsPanel) AlertsPanel.mount(el.querySelector("#remote-alerts"));
        if (window.Settings29) Settings29.mount(el);
        if (window.Settings210) Settings210.mount(el);
        if (window.Insights28) Insights28.digest(el.querySelector("#remote-digest"));
        if (window.UpdatesPanel) UpdatesPanel.mount(el.querySelector("#program-updates"));
        on("contrast", function (v) { store("contrast", v); App.applyLook(); });
        [["cb-safe", "cbSafe"], ["no-blur", "noBlur"], ["wide-text", "wideText"], ["underline-links", "underlineLinks"], ["privacy", "privacy"]].forEach(function (p) {
          on(p[0], function (v) { store(p[1], v); App.applyLook(); });
        });
        on("warn-close", function (v) { store("warnOnClose", v); });
        [["hide-statusbar", "hideStatusbar"], ["no-tips", "noTips"], ["hide-device", "hideDevice"]].forEach(function (p) {
          on(p[0], function (v) { store(p[1], v); App.applyLook(); });
        });
        on("palette-actions", function (v) { store("paletteActions", v); });
        on("page-tabs", function (v) { store("pageTabs", v); UI.toast(v ? "Long pages are split into tabs." : "Long pages show everything at once.", "ok"); });
        on("flash-title", function (v) { store("flashTitle", v); });
        on("speak", function (v) { store("speak", v); if (v && !window.speechSynthesis) UI.toast("This browser has no voice: nothing will be read.", "warning"); });
        on("schedule-notice", function (v) { store("scheduleNotice", v); });
        on("auto-drawer", function (v) { store("autoDrawer", v); });
        el.querySelector("#speak-test").addEventListener("click", function () {
          var was = store("speak");
          store("speak", true);
          App.speak("Run completed.");
          store("speak", was);
        });
        el.querySelector("#forget-recs").addEventListener("click", function () {
          store("recDismissed", null);
          store("recSnoozed", null);
          UI.toast("Every hidden or snoozed improvement shows again in Recommendations.", "ok");
        });
        el.querySelector("#reset-filters").addEventListener("click", function () {
          // Views and filters only: saved event filters, bookmarks and favorites are kept.
          ["toolbox", "events", "routineTab", "taskmgr", "scriptsView", "recView", "hwView"].forEach(function (k) { store(k, null); });
          UI.toast("Page filters reset: every page opens with its default view.", "ok");
        });
        /* ---------- reset one section ---------- */
        el.querySelector(".settings-panels").addEventListener("click", function (e) {
          var b = e.target.closest("[data-reset-section]");
          if (!b) return;
          var id = b.getAttribute("data-reset-section"), keys = SECTION_KEYS[id];
          UI.confirm("Reset " + b.getAttribute("data-title") + "?", "The options of this section go back to their defaults. Other sections and the data on this PC are not touched.",
            { ok: "Reset", danger: true }).then(function (ok) {
            if (!ok) return;
            keys.forEach(function (k) { try { localStorage.removeItem("wmm." + k); } catch (err) { /* storage unavailable */ } });
            location.reload();
          });
        });
        on("no-keys", function (v) { store("noKeyShortcuts", v); UI.toast(v ? "Single-key shortcuts are off. Ctrl K still opens search." : "Keyboard shortcuts are on.", "info"); });
        on("problems-only", function (v) { store("notifyProblemsOnly", v); });
        on("title-progress", function (v) { store("titleProgress", v); });
        on("battery-warn", function (v) { store("batteryWarn", v); if (v && !navigator.getBattery) UI.toast("This browser does not report the battery: the warning cannot appear here.", "warning"); });
        on("auto-reports", function (v) { store("autoOpenReports", v); });
        var saveQuiet = function () {
          quiet = { on: el.querySelector("#quiet-on").checked, from: el.querySelector("#quiet-from").value || "22:00", to: el.querySelector("#quiet-to").value || "07:00" };
          store("quietHours", quiet);
        };
        ["quiet-on", "quiet-from", "quiet-to"].forEach(function (id) { el.querySelector("#" + id).addEventListener("change", function () {
          saveQuiet();
          UI.toast(quiet.on ? "Quiet from " + quiet.from + " to " + quiet.to + "." : "Quiet hours off.", "ok");
        }); });
        el.querySelector("#default-time").addEventListener("change", function (e) {
          if (!e.target.value) return;
          store("defaultTime", e.target.value);
          UI.toast("New schedules start at " + e.target.value + " by default.", "ok");
        });
        el.querySelector("#sound-test").addEventListener("click", function () {
          var was = store("sound");
          store("sound", true);
          App.chime(true);
          store("sound", was);
          if (App.quiet()) UI.toast("Quiet hours are on now: sounds are muted.", "info");
        });
        el.querySelector("#clear-recent").addEventListener("click", function () {
          store("recentCommands", null);
          store("recentPages", null);
          UI.toast("Recent commands and pages cleared.", "ok");
        });

        /* ---------- search: shows the sections and the options that match ---------- */
        el.querySelector("#settings-q").addEventListener("input", function (e) {
          var q = e.target.value.toLowerCase().trim(), first = null;
          el.querySelectorAll("[data-panel]").forEach(function (panel) {
            var id = panel.getAttribute("data-panel"), link = el.querySelector('[data-sect="' + id + '"]');
            var items = panel.querySelectorAll(".form > label, .form > .check, .card");
            var match = false;
            items.forEach(function (it) {
              var hit = !q || it.textContent.toLowerCase().indexOf(q) >= 0;
              if (it.classList.contains("card")) return;
              it.classList.toggle("search-dim", !!q && !hit);
              if (hit && q) match = true;
            });
            if (!q) match = true;
            if (q && link.textContent.toLowerCase().indexOf(q) >= 0) match = true;
            link.hidden = !match;
            link.classList.toggle("search-hit", !!q && match);
            if (match && !first) first = link;
          });
          el.querySelector(".settings-noresult").hidden = !!first;
          if (q && first && first.getAttribute("aria-current") !== "true") first.click();
        });
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
        on("restore-before-changes", function (v, box) {
          API.put("/settings", { restore_before_changes: v ? "1" : "0" }).then(function () {
            UI.toast(v ? "A restore point protects uninstalls and deleted keys." : "No restore point before manual changes.", "ok");
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
