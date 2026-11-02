/* Guides: what each page is for and how to use it. A short tip appears the first time a page opens, the full guide opens
   from the ? button or F1, and a guided tour walks new users through a first maintenance. */
(function () {
  "use strict";
  var esc = UI.esc;

  var GUIDES = {
    dashboard: { intro: "The dashboard sums up this PC: the overall score, every category with its pages, live usage and what to do next.",
      steps: ["Press Scan all (top right) to assess every area; it changes nothing on the PC.", "Open a category or a page from All categories to work on one area.",
        "Use the quick actions or the Top recommended improvements to fix the biggest problems.", "Tick the visit checklist as you go and keep notes for next time."],
      tips: ["Customize which sections appear in Settings › Dashboard.", "Press Ctrl K anywhere to search pages, actions and commands."] },
    recommendations: { intro: "Every improvement the scans found, sorted by impact, with the action that fixes it.",
      steps: ["Start from High impact: they matter most for speed, security or stability.", "Apply runs the fix; Schedule repeats it automatically.",
        "Dismiss what does not apply to this PC; it stays hidden until it changes."],
      tips: ["Safe fixes run without a confirmation; the others create a restore point first."] },
    performance: { intro: "Memory, processor, power plan and visual effects, with live usage and 80+ speed tools.",
      steps: ["Check the live charts and the heaviest processes to find what slows the PC.", "Run the reports (Processor, Memory, Disk latency…) to measure before changing anything.",
        "Apply the fixes that match the PC: power and CPU tweaks for desktops, background and visual tweaks for slow laptops."],
      tips: ["Reports are read-only. Fixes that are not safe show a warning and create a restore point first.", "Every power tweak affects the active plan: choose Balanced to undo."] },
    cleanup: { intro: "Frees space by deleting files Windows and apps no longer need.",
      steps: ["Look at the recoverable space by category.", "Run Temporary files and caches: it is safe and keeps recent files.",
        "Use the moderate actions (components, Recycle Bin, dumps) only when you understand their warning."] },
    storage: { intro: "Where the space goes, the health of every disk and 30+ disk tools.",
      steps: ["Check Volumes and Physical disks: health, wear and temperature.", "Run all diagnostics in Disk management for a full disk report.",
        "Use the largest folders and files to find what fills the drive."], tips: ["Delete Windows.old only when the upgrade works well: going back is no longer possible."] },
    startup: { intro: "Programs that start with Windows and the applications installed on this PC.",
      steps: ["Turn off what is not needed at sign-in with the switch next to each entry.", "Optimize startup turns off everything except essential software (security, drivers, VPN…).",
        "Turn all startup programs back on restores the previous state."] },
    services: { intro: "Windows services this suite can safely disable, with a backup of the original state.",
      steps: ["Disable unnecessary services turns off telemetry, maps, fax and similar.", "Restore modified services brings back every change from the backup."],
      tips: ["Live start, stop and restart of any service is in System › Task Manager › Services."] },
    integrity: { intro: "Checks that Windows files, the disk and the component store are sound.",
      steps: ["Look at crashes and disk errors in the last weeks.", "Run DISM first, then SFC: the playbook Repair Windows does it in the right order.",
        "Use the online disk check; schedule a full repair only when errors are found."] },
    security: { intro: "Antivirus, firewall, encryption and hardening of this PC.",
      steps: ["Make sure every control is green: Defender on, firewall on, signatures fresh.", "Run the status reports (BitLocker, TPM, Secure Boot, Defender) for the details.",
        "Apply the hardening actions that fit the environment (SMBv1, LLMNR, LSA protection…)."] },
    updates: { intro: "Pending Windows updates, drivers, devices with problems and app updates.",
      steps: ["Install pending updates, especially the critical ones.", "Check devices with errors and old third-party drivers.", "Update desktop apps with winget."] },
    network: { intro: "Adapters, latency, DNS and network repairs.",
      steps: ["Check latency and packet loss to spot a bad connection.", "Run the connectivity test and the Wi-Fi reports when users complain.",
        "Use the repairs from the lightest (flush DNS) to the strongest (full network reset)."] },
    events: { intro: "Windows event logs, already filtered for what matters: critical errors, hardware, applications and services.",
      steps: ["Pick a category tab: Critical and errors is a good start.", "Narrow down with time, level, source or event ID; the search box filters instantly.",
        "Click a message for the full event; from there filter by its source or ID."],
      tips: ["Kernel-Power 41 means the PC lost power or froze; WHEA events point to hardware faults.", "Turn on Live to follow new events while you reproduce a problem."] },
    processes: { intro: "Everything running on this PC, refreshed live, and the Windows services.",
      steps: ["Sort by CPU or Memory to find what slows the PC; use the quick filters to focus.", "Click a name for every detail: path, command line, user, parent, services.",
        "End a process (Shift-click ends its children too), change its priority, or start a new program."],
      tips: ["Processes with a shield are essential to Windows and cannot be ended.", "Choose the columns you need with Columns; the choice is remembered."] },
    registry: { intro: "Browse and edit the Windows registry safely.",
      steps: ["Navigate with the tree, the favorites or by typing a path in the address bar.", "Edit, rename or delete values; create or delete keys.",
        "Every change saves a .reg backup first: restore it from Backups if something goes wrong."],
      tips: ["Keys Windows needs to boot or sign in cannot be deleted.", "Search looks at key names, value names and text under the current key."] },
    toolbox: { intro: "Every tool in one place, by area. Fixes change the PC; reports only read it.",
      steps: ["Pick an area tab and switch between Fixes and Reports.", "Run a tool, or tick several and press Run selected.", "Run diagnostics runs every report in the current view and opens their output."] },
    actions: { intro: "The full action catalog with filters, favorites and multi-select.",
      steps: ["Filter by area, risk or kind; star the actions you use often.", "Select several actions and run them as one job, in a safe order."] },
    activity: { intro: "Runs and scans in progress and the recent ones, with their live log.",
      steps: ["Follow the current step and the log while a run is in progress.", "Open History for older runs."] },
    playbooks: { intro: "Ready-made sequences for the usual jobs.",
      steps: ["Quick tune-up is safe at every visit.", "Full maintenance takes 45-60 minutes; Repair Windows fixes a damaged system."] },
    schedules: { intro: "Maintenance that runs on its own through Windows Task Scheduler, even when nobody is signed in.",
      steps: ["Create a schedule from any action or with New schedule.", "Pick once, daily or weekly and the time.", "Check the next run and the last result here."],
      tips: ["Schedules need the protected installation: use Fix automatically if a warning appears."] },
    history: { intro: "Every run with its result, freed space and full log.",
      steps: ["Filter by area, result or date.", "Open a log to see exactly what happened.", "Export the list as CSV for your records."] },
    reports: { intro: "Reports for the customer with your branding.",
      steps: ["Set the company name and contacts in Settings.", "Pick the scope and the format (PDF, HTML, CSV, JSON) and export."] },
    settings: { intro: "Report branding, appearance, guides, start-up and installation.",
      steps: ["Fill in the report branding once.", "Choose theme, accent, density and animations.", "Turn page tips on or off, or show them all again."] },
    support: { intro: "User guide, frequently asked questions and diagnostics to share with support.",
      steps: ["Look for your question in the FAQ.", "Copy the diagnostics when you contact support."] }
  };
  var HUB = { intro: "A category groups related pages. Open a page below, scan the whole category, or apply its safe fixes in one click.",
    steps: ["Read the category score and the open improvements.", "Open a page to work on that area.", "Use Apply safe fixes to run every safe improvement of the category."] };

  var TOUR = [
    ["dashboard", "Welcome", "This console keeps Windows fast, clean and safe. The dashboard shows the overall health and every category of the console."],
    ["dashboard", "1 · Scan", "Press Scan all at the top right. It assesses every area in one to three minutes and changes nothing on the PC."],
    ["recommendations", "2 · Fix", "Recommendations lists what the scans found, by impact. Apply fixes the problem; safe fixes need no confirmation."],
    ["cat-optimize", "3 · Explore by category", "Each category in the sidebar is a page with its child pages, scores and safe fixes. Click a category title to open it."],
    ["toolbox", "4 · Every tool", "The Toolbox holds all the tools: fixes that change the PC and reports that only read it."],
    ["schedules", "5 · Automate", "Schedule the maintenance you want repeated; it runs through Windows Task Scheduler."]
  ];

  function store(k, v) { return Components.store(k, v); }
  function seen() { return store("guideSeen") || []; }
  function enabled() { return store("guidesOff") !== true; }
  function guideFor(page) { return GUIDES[page] || (page.indexOf("cat-") === 0 ? HUB : null); }
  function title(page) { return (window.App && App.pageTitle(page)) || page; }
  function closeModal() { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); }

  /* The short tip shown at the top of a page the first time it opens. */
  function tip(page) {
    var g = guideFor(page);
    if (!g || !enabled() || seen().indexOf(page) >= 0) return "";
    return '<div class="guide-tip" role="note" data-guide-tip="' + esc(page) + '"><span class="guide-tip-icon">' + UI.icon("support") + '</span><div class="grow">' +
      "<strong>How this page works</strong><p>" + esc(g.intro) + "</p><ol>" + g.steps.slice(0, 3).map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ol></div>" +
      '<div class="guide-tip-actions"><button type="button" class="btn btn-sm" data-guide-open="' + esc(page) + '">Full guide</button>' +
      '<button type="button" class="btn btn-sm btn-ghost" data-guide-dismiss="' + esc(page) + '">Got it</button></div></div>';
  }
  function dismiss(page) {
    var list = seen();
    if (list.indexOf(page) < 0) list.push(page);
    store("guideSeen", list);
  }

  function open(page) {
    var g = guideFor(page);
    if (!g) { location.hash = "#/support"; return Promise.resolve(); }
    var cat = window.Hubs && Hubs.categoryOf(page);
    var body = '<p class="modal-text">' + esc(g.intro) + '</p><ol class="guide-steps">' + g.steps.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ol>" +
      (g.tips && g.tips.length ? '<div class="callout callout-info">' + UI.icon("info") + "<div>" + g.tips.map(esc).join("<br>") + "</div></div>" : "") +
      (cat && page.indexOf("cat-") !== 0 ? '<p class="muted small">Part of <a href="#/cat-' + cat.id + '" data-close-modal>' + esc(cat.title) + "</a>: " + esc(cat.text) + "</p>" : "") +
      '<label class="check" style="margin-top:8px"><input type="checkbox" id="guides-on"' + (enabled() ? " checked" : "") + "> Show a short tip the first time a page opens</label>";
    var done = UI.modal("Guide · " + title(page), body, [
      { label: "Take the tour", cls: "btn-ghost", value: function () { return "tour"; } },
      { label: "User guide", cls: "", value: function () { return "support"; } },
      { label: "Close", cls: "btn-primary" }]);
    var box = document.getElementById("guides-on");
    if (box) box.addEventListener("change", function () { store("guidesOff", !box.checked); });
    return done.then(function (v) {
      if (v === "tour") tour(0);
      if (v === "support") location.hash = "#/support";
    });
  }

  /* Guided tour: one step per dialog, opening the page it talks about. */
  function tour(i) {
    i = i || 0;
    var s = TOUR[i];
    if (!s) { store("tourDone", true); UI.toast("Tour completed. Press ? or F1 on any page for its guide.", "ok"); return; }
    if (location.hash.replace(/^#\/?/, "").split("?")[0] !== s[0]) location.hash = "#/" + s[0];
    var dots = '<div class="tour-dots" aria-label="Step ' + (i + 1) + " of " + TOUR.length + '">' + TOUR.map(function (x, k) { return '<span class="' + (k === i ? "on" : "") + '"></span>'; }).join("") + "</div>";
    UI.modal(s[1], '<p class="modal-text">' + esc(s[2]) + "</p>" + dots, [{ label: "Skip tour", cls: "btn-ghost", value: function () { return "skip"; } }]
      .concat(i ? [{ label: "Back", cls: "", value: function () { return "back"; } }] : [])
      .concat([{ label: i === TOUR.length - 1 ? "Finish" : "Next", cls: "btn-primary", value: function () { return "next"; } }])
    ).then(function (v) {
      if (v === "next") tour(i + 1);
      else if (v === "back") tour(i - 1);
      else store("tourDone", true);
    });
  }

  document.addEventListener("click", function (e) {
    var d = e.target.closest && e.target.closest("[data-guide-dismiss]");
    if (d) {
      dismiss(d.getAttribute("data-guide-dismiss"));
      var box = d.closest("[data-guide-tip]");
      if (box) { box.classList.add("leaving"); setTimeout(function () { box.remove(); }, 250); }
      return;
    }
    var o = e.target.closest && e.target.closest("[data-guide-open]");
    if (o) { open(o.getAttribute("data-guide-open")); return; }
    if (e.target.closest && e.target.closest("[data-close-modal]")) closeModal();
  });

  window.Guides = {
    GUIDES: GUIDES, tip: tip, open: open, tour: tour, dismiss: dismiss, enabled: enabled,
    reset: function () { store("guideSeen", []); store("tourDone", false); store("guidesOff", false); },
    shouldTour: function () { return !store("tourDone"); }
  };
})();
