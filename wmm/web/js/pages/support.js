/* Support: user guide, FAQ with search, troubleshooting, glossary, risk levels, shortcuts and diagnostics. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  var STEPS = [
    ["Start the console", "Double-click start_wmm.bat. It installs or updates the protected copy in Program Files, runs the health check and opens the console."],
    ["Scan all areas", "Click Scan all (top right). In about a minute every area gets a score from 0 to 100 and a list of improvements."],
    ["Review the improvements", "Open Recommendations: high impact first. Safe fixes run without confirmation; the others ask once and create a restore point."],
    ["Run a playbook", "For a standard visit use Quick tune-up; for a slow or unstable PC use Full maintenance or Repair Windows."],
    ["Follow the progress", "Activity shows every step with its real percentage and the live output."],
    ["Schedule maintenance", "Every action can be scheduled once, daily or weekly in Windows Task Scheduler (needs the protected installation)."],
    ["Deliver the report", "Reports › Full Maintenance: add your notes, then download HTML or print to PDF for the customer."]
  ];
  var FAQ = [
    ["This window is not connected / access denied", "The browser window has no valid session. Click Request access and answer Yes on the desktop of the PC, or open the link printed in the Windows Maintenance Manager window."],
    ["Actions fail with administrator rights required", "The agent runs without elevation. Click Restart as administrator in the banner and approve UAC: the console reopens with full rights."],
    ["Why can't I create schedules?", "Scheduled tasks run as SYSTEM, so the program must run from Program Files and Python must be installed for all users. Settings › Health check shows what is missing."],
    ["Is it safe to apply all safe actions?", "Yes: safe actions never delete personal data or change persistent settings. They clean caches, temporary files and run read-only checks."],
    ["What happens before a risky action?", "A System Restore point is created first. If it cannot be created, the action does not run."],
    ["Can I undo a change?", "Services changed by the suite can be restored from Services › Restore. Startup entries can be turned back on. For anything else use the restore point created before the run."],
    ["Why is a percentage marked estimated?", "Some commands print no progress. The estimate uses how long the same action took on this PC before."],
    ["Why is a scan marked incomplete?", "Some data needs administrator rights or a PowerShell module was unavailable. Scan again as administrator; incomplete scans are capped at 50."],
    ["Where is my data stored?", "In the dati folder next to the program: history database, service backup and change log. Nothing is sent over the network except the latency test and Windows Update."],
    ["The console does not open", "Check that Python 3.9+ is installed, then run start_wmm.bat again. If port 8765 is busy another console is open; use python wmm.py --port 9000."]
  ];
  var GLOSSARY = {
    performance: "Live CPU, memory, disk and network, power plan, page file and responsiveness settings.",
    cleanup: "Recoverable space in temporary folders, caches, crash dumps and the Recycle Bin.",
    storage: "Drives, largest folders and files, browser caches, Windows.old and restore point storage.",
    startup: "Programs that start with Windows, installed applications and third-party scheduled tasks.",
    services: "All Windows services, non-essential ones that can be disabled and the restore backup.",
    integrity: "Disk health, stability events, event log errors and Windows image and file repairs.",
    security: "Defender, firewall, UAC, SmartScreen, BitLocker, SMB, LSA, privacy and restore points.",
    updates: "Pending Windows updates, devices with errors, driver age, Office and app updates.",
    network: "Adapters, latency, jitter, packet loss, DNS, proxy and hosts file."
  };

  window.Pages.support = {
    title: "Support",
    render: function (el, App) {
      return API.get("/health").then(function (hc) {
        var info = App.state.info;
        App.setSubtitle("User guide, frequently asked questions and troubleshooting");
        var steps = '<ol class="playbook-steps">' + STEPS.map(function (s) {
          return '<li><span class="grow"><span class="cell-title">' + esc(s[0]) + '</span><br><span class="cell-sub">' + esc(s[1]) + "</span></span></li>";
        }).join("") + "</ol>";
        var faq = '<label class="dt-search" style="max-width:none;margin-bottom:12px">' + UI.icon("search") + '<input type="search" id="faq-search" placeholder="Search the guide…"></label>' +
          '<div id="faq-list">' + FAQ.map(function (f, i) {
            return '<details class="faq" data-text="' + esc((f[0] + " " + f[1]).toLowerCase()) + '"' + (i === 0 ? " open" : "") + "><summary>" + esc(f[0]) + "</summary><p>" + esc(f[1]) + "</p></details>";
          }).join("") + '</div><p class="empty" id="faq-empty" hidden>No answer matches. Try other words.</p>';
        var glossary = '<ul class="check-list">' + UI.AREAS.map(function (a) {
          return '<li data-area="' + a + '"><span class="tile-icon" style="width:30px;height:30px">' + UI.icon(a) + '</span><span class="grow"><a class="cell-title" href="#/' + a + '">' +
            esc(UI.AREA_LABEL[a]) + '</a><br><span class="cell-sub">' + esc(GLOSSARY[a]) + "</span></span></li>";
        }).join("") + "</ul>";
        var risks = UI.checklist([
          ["Safe", "ok", "No confirmation", "No personal data deleted, no persistent setting changed. Can run unattended and on schedules."],
          ["Moderate", "warning", "Confirmation", "Changes a setting or deletes cache data. A restore point is created first."],
          ["High risk", "error", "Confirmation", "Can affect connectivity, sign-in or require a restart. A restore point is created first."]
        ]);
        var keys = '<div class="shortcuts">' + [["Ctrl K or /", "Command palette"], ["?", "All shortcuts"], ["G then a letter", "Go to a page (G D dashboard, G Z actions…)"],
          ["Shift R", "Refresh the page"], ["Shift S", "Scan all areas"], ["Shift T", "Light / dark theme"], ["Esc", "Close dialogs and panels"]].map(function (k) {
          return "<div><span>" + esc(k[1]) + '</span><span class="kbd">' + esc(k[0]) + "</span></div>";
        }).join("") + "</div>";
        var diag = UI.definition([["Version", esc(info.version)], ["Device", esc(info.hostname)], ["Machine ID", '<span class="cell-mono">' + esc(info.machine_id) + "</span>"],
          ["Mode", info.preview ? "Preview" : info.admin ? "Administrator" : "Read-only"],
          ["Health", hc.summary.ok + " OK · " + hc.summary.warning + " warnings · " + hc.summary.error + " failed"], ["Actions", String(Object.keys(App.state.actions).length)]]);

        el.innerHTML = UI.pageHeader("Support", "Everything a technician needs to use Windows Maintenance Manager",
          UI.button("Copy diagnostic info", 'id="copy-diag"', "", "download") + UI.button("Health check", 'id="go-health"', "", "shield")) +
          '<div class="grid grid-2-1"><div class="stack">' + UI.card("Getting started", steps) + UI.card("Frequently asked questions", faq) + "</div>" +
          '<div class="stack">' + UI.card("Risk levels", risks) + UI.card("Keyboard shortcuts", keys) + UI.card("Diagnostics", diag) + "</div></div>" +
          '<div class="grid">' + UI.card("Areas at a glance", glossary) + "</div>";

        el.querySelector("#faq-search").addEventListener("input", function (e) {
          var q = e.target.value.toLowerCase().trim(), shown = 0;
          el.querySelectorAll(".faq").forEach(function (d) {
            var ok = !q || d.getAttribute("data-text").indexOf(q) >= 0;
            d.hidden = !ok;
            if (ok) { shown++; if (q) d.open = true; }
          });
          el.querySelector("#faq-empty").hidden = shown > 0;
        });
        el.querySelector("#go-health").addEventListener("click", function () { location.hash = "#/settings"; });
        el.querySelector("#copy-diag").addEventListener("click", function () {
          var text = ["Windows Maintenance Manager " + info.version, "Device: " + info.hostname + " (" + info.machine_id + ")",
            "Mode: " + (info.preview ? "preview" : info.admin ? "administrator" : "read-only")].concat(hc.checks.map(function (c) {
            return "[" + c.status.toUpperCase() + "] " + c.name + ": " + c.detail;
          })).join("\n");
          (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () { UI.toast("Diagnostic information copied.", "ok"); },
            function () { UI.toast("The clipboard is not available in this browser.", "warning"); });
        });
      });
    }
  };
})();
