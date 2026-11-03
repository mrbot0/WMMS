/* Console upgrade (2.0): notes for this PC, "On this page", page auto-refresh, the log of page errors, keyboard helpers
   (Shift F, Shift J, Shift N, Shift + arrows for tabs), scroll progress, refresh after a long absence, offline notice, installed programs
   in the command palette and the unsafe-programs counter in the menu. */
(function () {
  "use strict";
  var esc = UI.esc, store = Components.store;
  var errors = [], apps = null, pendingApp = null, autoTimer = null, hiddenAt = 0;
  var AWAY_MS = 5 * 60 * 1000;
  try { errors = JSON.parse(sessionStorage.getItem("wmm.pageErrors") || "[]"); } catch (e) { errors = []; }

  function machine() { return (App.state.info && App.state.info.machine_id) || "this-pc"; }
  function modalEl() { var all = document.querySelectorAll(".modal-backdrop"); return all[all.length - 1]; }
  function closeModal() { var m = modalEl(), b = m && m.querySelector(".modal-foot .btn"); if (b) b.click(); }
  function visible(n) { return !!(n.offsetWidth || n.offsetHeight || n.getClientRects().length); }
  function copy(text, what) {
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () { UI.toast(what + " copied.", "ok"); },
      function () { UI.toast("The clipboard is not available in this browser.", "warning"); });
  }

  /* ---------- notes for this PC (Shift N) ---------- */
  function notes() {
    var all = store("notes") || {}, mine = all[machine()] || { text: "", at: null };
    UI.modal("Notes for this PC", '<p class="cell-sub">What you did, what to check next time, who to call. Kept in this browser for this PC only: ' +
      "never write passwords here.</p>" + '<textarea class="notes-area" rows="12" maxlength="20000" aria-label="Notes">' + esc(mine.text) + "</textarea>" +
      (mine.at ? '<p class="cell-sub">Last saved ' + esc(UI.formatDate(mine.at, true)) + "</p>" : ""),
      [{ label: "Cancel", cls: "btn-ghost" },
        { label: "Copy", value: function (w) { return { text: w.querySelector("textarea").value, copy: true }; } },
        { label: "Save", cls: "btn-primary", value: function (w) { return { text: w.querySelector("textarea").value }; } }]).then(function (v) {
      if (!v) return;
      all = store("notes") || {};
      if (v.text.trim()) all[machine()] = { text: v.text, at: new Date().toISOString() }; else delete all[machine()];
      store("notes", all);
      if (v.copy) copy(v.text, "Notes"); else UI.toast(v.text.trim() ? "Notes saved." : "Notes cleared.", "ok");
    });
  }

  /* ---------- on this page (Shift J) ---------- */
  function jump() {
    var cards = Array.prototype.filter.call(document.querySelectorAll("#content .card[data-card]"), visible);
    if (!cards.length) { UI.toast("This page has no cards to jump to.", "info"); return; }
    UI.modal("On this page", '<div class="pick-list">' + cards.map(function (c, i) {
      var title = c.querySelector(".card-head h2");
      return '<button type="button" class="pick-item" data-jump="' + i + '"><span class="grow"><span class="cell-title">' + esc(title ? title.textContent : "Card " + (i + 1)) +
        "</span></span></button>";
    }).join("") + "</div>", [{ label: "Close", cls: "btn-ghost" }]);
    var m = modalEl();
    m.querySelector(".pick-list").addEventListener("click", function (e) {
      var b = e.target.closest("[data-jump]");
      if (!b) return;
      var card = cards[Number(b.getAttribute("data-jump"))];
      closeModal();
      card.classList.remove("collapsed");
      card.scrollIntoView({ behavior: "smooth", block: "start" });
      card.classList.add("card-flash");
      setTimeout(function () { card.classList.remove("card-flash"); }, 1600);
    });
    var first = m.querySelector("[data-jump]");
    if (first) first.focus();
  }

  /* ---------- page tabs (Shift + arrows), links ---------- */
  function tabBar() { var bars = Array.prototype.filter.call(document.querySelectorAll("#content .page-tabs"), visible); return bars[0] || null; }
  function stepTab(delta) {
    var bar = tabBar();
    if (!bar) return;
    var tabs = Array.prototype.slice.call(bar.querySelectorAll("[data-page-tab]"));
    var i = tabs.findIndex(function (t) { return t.getAttribute("aria-selected") === "true"; });
    var next = tabs[(i + delta + tabs.length) % tabs.length];
    next.click();
    next.focus();
  }
  function tabLink() {
    var bar = tabBar(), on = bar && bar.querySelector('[aria-selected="true"]');
    var base = location.origin + location.pathname + "#/" + App.current();
    copy(on ? base + "?tab=" + on.getAttribute("data-page-tab") : base, "Link to this tab");
  }

  /* ---------- table search (Shift F) ---------- */
  function findInTable() {
    var input = Array.prototype.filter.call(document.querySelectorAll('#content .dt-search input[type="search"]'), visible)[0];
    if (!input) { UI.toast("This page has no table to search.", "info"); return; }
    input.scrollIntoView({ block: "center" });
    input.focus();
    input.select();
  }

  /* ---------- auto-refresh of a page (command palette) ---------- */
  function typing() { var a = document.activeElement; return a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName); }
  function applyAuto() {
    clearInterval(autoTimer);
    var page = App.current(), on = page !== "dashboard" && (store("autoRefresh") || []).indexOf(page) >= 0;
    App.state.autoRefresh = on;
    App.renderStatus();
    if (on) autoTimer = setInterval(function () {
      if (document.hidden || document.querySelector(".modal-backdrop") || typing()) return;
      App.render();
    }, 60000);
  }
  function toggleAuto(page) {
    var list = (store("autoRefresh") || []).filter(function (p) { return p !== page; });
    var on = !App.state.autoRefresh;
    if (on) list.push(page);
    store("autoRefresh", list);
    applyAuto();
    UI.toast(on ? App.pageTitle(page) + " refreshes every minute." : "Auto-refresh off for " + App.pageTitle(page) + ".", "info");
  }
  window.addEventListener("hashchange", function () { setTimeout(applyAuto, 0); });

  /* ---------- page errors (kept for this session, for support) ---------- */
  function logError(text, page) {
    errors.unshift({ at: new Date().toISOString(), page: page || "", text: String(text).slice(0, 500) });
    errors = errors.slice(0, 30);
    try { sessionStorage.setItem("wmm.pageErrors", JSON.stringify(errors)); } catch (e) { /* storage unavailable */ }
  }
  function errorText() {
    var info = App.state.info || {};
    return ["Windows Maintenance Manager " + (info.version || "") + " · " + navigator.userAgent, ""].concat(errors.map(function (x) {
      return x.at + "  [" + x.page + "]  " + x.text;
    })).join("\n");
  }
  function showErrors() {
    var body = errors.length ? '<div class="table-wrap"><table class="table"><thead><tr><th>When</th><th>Page</th><th>Error</th></tr></thead><tbody>' +
      errors.map(function (x) { return "<tr><td>" + esc(UI.formatDate(x.at, true)) + "</td><td>" + esc(x.page) + '</td><td class="cell-mono">' + esc(x.text) + "</td></tr>"; }).join("") +
      "</tbody></table></div>" : '<p class="empty">No page error in this session.</p>';
    UI.modal("Page errors", body, [{ label: "Close", cls: "btn-ghost" }].concat(errors.length ? [{ label: "Copy for support", cls: "btn-primary", value: function () { return "copy"; } }] : []))
      .then(function (v) { if (v === "copy") copy(errorText(), "Error list"); });
  }

  /* ---------- installed programs in the palette, unsafe counter in the menu ---------- */
  function setApps(d) {
    apps = d && d.apps ? d.apps : apps;
    App.state.appsRisk = apps ? apps.filter(function (a) { return a.status === "risk"; }).length : 0;
    App.renderNav();
  }
  function openApp(id) { pendingApp = id; if (App.current() === "apps") App.render(); else location.hash = "#/apps"; }
  function takePendingApp() { var id = pendingApp; pendingApp = null; return id; }
  // Read once the console is idle: the first read scans the programs (a few seconds) without slowing the start.
  setTimeout(function () {
    if (!apps) API.get("/apps").then(setApps, function () { /* shown on the page itself */ });
  }, 15000);

  /* ---------- scroll progress, offline, coming back ---------- */
  var scroller = document.getElementById("scroller"), progress = document.createElement("div");
  progress.className = "scroll-progress";
  progress.setAttribute("aria-hidden", "true");
  document.body.appendChild(progress);
  function onScroll() {
    var max = scroller.scrollHeight - scroller.clientHeight;
    progress.style.transform = "scaleX(" + (max > 80 ? Math.min(1, scroller.scrollTop / max) : 0) + ")";
  }
  scroller.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("hashchange", function () { setTimeout(onScroll, 50); });

  window.addEventListener("offline", function () {
    UI.toast("This PC went offline: the console keeps working, but app updates, winget and online checks fail until the connection returns.", "warning");
  });
  window.addEventListener("online", function () { UI.toast("Back online.", "ok"); });

  // Data older than five minutes is stale: coming back to the tab redraws the page (unless a dialog is open or a run is going).
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { hiddenAt = Date.now(); return; }
    if (!hiddenAt || Date.now() - hiddenAt < AWAY_MS || store("noReturnRefresh") || document.querySelector(".modal-backdrop") || typing()) return;
    hiddenAt = 0;
    if (App.current() !== "activity" && App.current() !== "processes") { App.render(); UI.toast("Page refreshed: you were away for a while.", "info"); }
  });

  /* ---------- keyboard ---------- */
  document.addEventListener("keydown", function (e) {
    var t = e.target;
    // AltGr (Ctrl+Alt on Windows) types { and } on many layouts, Italian included: it is not a shortcut modifier here.
    var altGr = e.getModifierState && e.getModifierState("AltGraph");
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable || ((e.ctrlKey || e.metaKey || e.altKey) && !altGr)) return;
    if (document.querySelector(".modal-backdrop") || store("noKeyShortcuts")) return;
    if (e.shiftKey && e.key === "F") { e.preventDefault(); findInTable(); }
    else if (e.shiftKey && e.key === "J") { e.preventDefault(); jump(); }
    else if (e.shiftKey && e.key === "N") { e.preventDefault(); notes(); }
    // Tabs of the page: Shift + arrows, or { and } ([ and ] already change page).
    else if (e.shiftKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) { e.preventDefault(); stepTab(e.key === "ArrowRight" ? 1 : -1); }
    else if (e.key === "{" || e.key === "}") { e.preventDefault(); stepTab(e.key === "}" ? 1 : -1); }
  });

  /* ---------- command palette entries ---------- */
  function commands(page) {
    var list = [
      { group: "Commands", title: "Notes for this PC", icon: "history", keywords: "notes memo technician log Shift N", run: notes },
      { group: "Commands", title: "On this page: jump to a card", icon: "dashboard", keywords: "table of contents sections cards Shift J", run: jump },
      { group: "Commands", title: "Search the table of this page", icon: "search", keywords: "find filter Shift F", run: findInTable },
      { group: "Commands", title: "Show page errors", sub: errors.length ? errors.length + " this session" : "none", icon: "alert", keywords: "bugs console diagnostics support", run: showErrors }
    ];
    if (page !== "dashboard") {
      list.push({ group: "Preferences", title: (App.state.autoRefresh ? "Stop auto-refresh of " : "Auto-refresh every minute: ") + App.pageTitle(page), icon: "refresh",
        keywords: "reload live update timer", run: function () { toggleAuto(page); } });
    }
    list.push({ group: "Preferences", title: (store("noReturnRefresh") ? "Refresh the page when I come back" : "Do not refresh the page when I come back"), icon: "refresh",
      keywords: "stale away visibility", run: function () {
        var off = !store("noReturnRefresh");
        store("noReturnRefresh", off);
        UI.toast(off ? "Pages are no longer refreshed when you come back." : "Pages refresh when you come back after five minutes.", "info");
      } });
    if (tabBar()) list.push({ group: "Commands", title: "Copy a link to this tab", icon: "copy", keywords: "url share deep link", run: tabLink });
    (apps || []).forEach(function (a) {
      list.push({ group: "Programs", title: a.name, sub: ({ risk: "unsafe", review: "to review" }[a.status] || "safe") + (a.version ? " · " + a.version : ""),
        icon: "apps", keywords: "program application installed " + (a.publisher || ""), run: function () { openApp(a.id); } });
    });
    return list;
  }

  window.Upgrade = { commands: commands, logError: logError, setApps: setApps, takePendingApp: takePendingApp, notes: notes, jump: jump };
  applyAuto();
})();
