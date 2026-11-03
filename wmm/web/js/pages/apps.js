/* Applications: every installed program with a safety verdict (end of support, known holes, adware), how long since it
   was last used, uninstall, Store apps, app updates with winget, browser cache cleanup and setup files left in Downloads. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var MB = 1048576;
  var STATUS = { risk: ["Unsafe", "error"], review: ["Review", "warning"], ok: ["Safe", "ok"] };
  var USAGE = { recent: "In use", unused: "Not used", unknown: "Unknown" };
  var CATEGORY = { app: "Application", browser: "Browser", runtime: "Runtime", system: "Driver / system", antivirus: "Security",
    remote: "Remote access", optimizer: "Optimizer", unwanted: "Unwanted" };
  var VIEWS = [["all", "All"], ["risk", "Unsafe"], ["review", "To review"], ["unused", "Not used"], ["recent30", "New (30 days)"],
    ["large", "Over 1 GB"], ["startup", "Start with Windows"], ["broken", "Leftovers"]];

  function statusBadge(s) { var x = STATUS[s] || STATUS.ok; return '<span class="badge badge-status-' + x[1] + '">' + x[0] + "</span>"; }
  function size(mb) { return mb ? UI.formatBytes(mb * MB) : "—"; }
  function daysAgo(iso) { return iso ? Math.round((Date.now() - new Date(iso + "T12:00:00").getTime()) / 86400000) : null; }
  function lastUsed(a) {
    if (!a.last_used) return a.usage === "unused" ? '<span class="cell-sub">No use recorded</span>' : '<span class="cell-sub">—</span>';
    var d = daysAgo(a.last_used);
    var text = d <= 0 ? "Today" : d === 1 ? "Yesterday" : d < 60 ? d + " days ago" : Math.round(d / 30) + " months ago";
    return '<span class="' + (a.usage === "unused" ? "text-warning" : "") + '" title="' + esc(a.last_used) + '">' + esc(text) + "</span>";
  }
  function inView(view) {
    return {
      all: function () { return true; },
      risk: function (a) { return a.status === "risk"; },
      review: function (a) { return a.status === "review"; },
      unused: function (a) { return a.usage === "unused" && a.removable; },
      recent30: function (a) { var d = daysAgo(a.installed); return d != null && d <= 30; },
      large: function (a) { return (a.size_mb || 0) >= 1024; },
      startup: function (a) { return a.startup; },
      broken: function (a) { return a.broken; }
    }[view] || function () { return true; };
  }
  function done(r, what) {
    if (r && r.preview) UI.toast("Preview mode: " + what + " was simulated, nothing changed.", "info");
    return r;
  }

  window.Pages.apps = {
    title: "Applications",
    render: function (el, App) {
      var self = this;
      var refresh = self._refresh;
      self._refresh = false;
      return API.get("/apps" + (refresh ? "?refresh=1" : "")).then(function (d) { draw(el, App, d, self); });
    }
  };

  function draw(el, App, d, page) {
    var apps = d.apps || [], store = d.store || [], browsers = d.browsers || [], inst = d.installers || { files: [] };
    var count = function (f) { return apps.filter(f).length; };
    var risky = count(function (a) { return a.status === "risk"; }), review = count(function (a) { return a.status === "review"; });
    var unused = apps.filter(function (a) { return a.usage === "unused" && a.removable; });
    var unusedMb = unused.reduce(function (s, a) { return s + (a.size_mb || 0); }, 0);
    var cacheMb = browsers.reduce(function (s, b) { return s + (b.cache_mb || 0); }, 0);
    var totalMb = apps.reduce(function (s, a) { return s + (a.size_mb || 0); }, 0);
    App.setSubtitle(apps.length + " programs and " + store.length + " Store apps · scanned " + UI.formatDate(d.scanned, true));

    var root = document.createElement("div");
    root.className = "apps-page";
    root.innerHTML = UI.pageHeader("Applications", "What is installed, what is unsafe and what you no longer use",
      UI.button("Scan again", "data-apps-rescan", "", "refresh") + UI.button("Check app updates", "data-apps-updates", "btn-primary", "updates")) +
      (d.errors && d.errors.length ? '<div class="callout callout-warning">' + UI.icon("alert") + "<div>" + d.errors.map(esc).join("<br>") + "</div></div>" : "") +
      '<div class="grid grid-5">' +
      UI.kpi("Installed", Components.num(apps.length), store.length + " Store apps · " + size(totalMb) + " reported", "info") +
      UI.kpi("Unsafe", Components.num(risky), risky ? "update or remove them" : "nothing unsafe found", risky ? "error" : "ok") +
      UI.kpi("To review", Components.num(review), "remote access, optimizers, unknown publishers", review ? "warning" : "ok") +
      UI.kpi("Not used for months", Components.num(unused.length), unusedMb ? size(unusedMb) + " to free" : "", unused.length ? "warning" : "ok") +
      UI.kpi("Browser caches", size(cacheMb), browsers.length + " browsers", cacheMb > 1024 ? "warning" : "info") + "</div>" +
      overview(apps, d) + programs() + security(apps, d) + updates(d) + storeCard(store) + browserCards(browsers, inst);
    el.innerHTML = "";
    el.appendChild(root);

    // The tabs show how much is inside: programs, problems, Store apps, cache size.
    UI.pageTabs(root, "apps", [
      { id: "overview", label: "Overview", icon: "dashboard" },
      { id: "programs", label: "Programs (" + apps.length + ")", icon: "apps" },
      { id: "security", label: "Security" + (risky + review ? " (" + (risky + review) + ")" : ""), icon: "security" },
      { id: "updates", label: "Updates", icon: "updates" },
      { id: "store", label: "Store apps (" + store.length + ")", icon: "explorer" },
      { id: "browsers", label: "Browsers & leftovers" + (cacheMb >= 100 ? " (" + size(cacheMb) + ")" : ""), icon: "cleanup" }
    ], { sharedHead: true });
    if (window.Upgrade) {
      Upgrade.setApps(d);
      var pending = Upgrade.takePendingApp();  // a program chosen in the command palette
      if (pending) setTimeout(function () { var a = byId(pending); if (a) detail(a); }, 0);
    }
    var tabs = root.querySelector(".page-tabs");
    function showTab(id) { var b = tabs && tabs.querySelector('[data-page-tab="' + id + '"]'); if (b) b.click(); }

    // ---------- programs table, with quick views ----------
    var view = Components.store("appsView") || "all";
    function drawPrograms() {
      root.querySelectorAll("[data-apps-view]").forEach(function (b) { b.setAttribute("aria-checked", String(b.getAttribute("data-apps-view") === view)); });
      var host = root.querySelector("#apps-table"), fresh = host.cloneNode(false);
      host.parentNode.replaceChild(fresh, host);  // a new table: the listeners of the old one go with it
      Components.dataTable(fresh, {
        rows: apps.filter(inView(view)), exportName: "wmm-applications", placeholder: "Search programs, publishers, versions…", sort: "name", pageSize: 25,
        empty: "No program in this view.",
        filters: [{ key: "category", label: "All kinds", options: Object.keys(CATEGORY).map(function (k) { return [k, CATEGORY[k]]; }) },
          { key: "usage", label: "Any use", options: Object.keys(USAGE).map(function (k) { return [k, USAGE[k]]; }) }],
        columns: [
          { key: "status", title: "Safety", value: function (a) { return (STATUS[a.status] || STATUS.ok)[0]; }, render: function (a) { return statusBadge(a.status); } },
          { key: "name", title: "Program", render: function (a) {
            return '<button type="button" class="link-btn cell-title" data-app-detail="' + esc(a.id) + '">' + esc(a.name) + "</button>" +
              (a.startup ? ' <span class="badge" title="Starts with Windows">Startup</span>' : "") +
              (a.issues.length ? '<div class="cell-sub">' + esc(a.issues[0].text) + "</div>" : ""); } },
          { key: "publisher", title: "Publisher", render: function (a) { return esc(a.publisher || "—"); } },
          { key: "version", title: "Version", render: function (a) { return '<span class="cell-mono">' + esc(a.version || "—") + "</span>"; } },
          { key: "last_used", title: "Last used", value: function (a) { return a.last_used || ""; }, render: lastUsed },
          { key: "installed", title: "Installed", render: function (a) { return a.installed ? esc(UI.formatDate(a.installed, false)) : "—"; } },
          { key: "size_mb", title: "Size", cls: "num", render: function (a) { return size(a.size_mb); } },
          { key: "id", title: "", sortable: false, csv: false, render: rowActions }
        ]
      });
    }
    function rowActions(a) {
      if (a.broken) return '<button class="btn btn-sm" type="button" data-app-entry="' + esc(a.id) + '">Remove entry</button>';
      return '<span class="row-actions">' + (a.uninstall ? '<button class="btn btn-sm" type="button" data-app-uninstall="' + esc(a.id) + '">' + UI.icon("trash") + "Uninstall</button>" : "") +
        (a.folder ? '<button class="btn btn-sm btn-ghost" type="button" data-app-folder="' + esc(a.id) + '" title="Open the install folder" aria-label="Open the install folder">' +
          UI.icon("folder") + "</button>" : "") + "</span>";
    }
    drawPrograms();

    // ---------- actions ----------
    function byId(id) { return apps.filter(function (a) { return a.id === id; })[0]; }
    function busy(btn, on) { if (btn) { btn.disabled = on; btn.classList.toggle("busy", on); } }
    function uninstall(a, btn) {
      var body = '<p class="modal-text">The uninstaller of <strong>' + esc(a.name) + "</strong> starts now" +
        (a.quiet ? " and removes it without questions." : ": follow its window to finish.") + "</p>" +
        (a.category === "runtime" || a.category === "system" ? '<div class="callout callout-warning">' + UI.icon("alert") +
          "<div>Other programs or devices may need it. Remove it only if you know they do not.</div></div>" : "") +
        '<p class="cell-sub">Command (read from Windows):</p><pre class="code-block">' + esc(a.uninstall) + "</pre>";
      UI.modal("Uninstall " + a.name, body, [{ label: "Cancel", cls: "btn-ghost" }, { label: "Uninstall", cls: "btn-danger", value: function () { return true; } }])
        .then(function (ok) {
          if (!ok) return;
          busy(btn, true);
          UI.withRestorePoint("/apps/" + a.id + "/uninstall").then(function (r) {
            done(r, "the uninstall");
            if (!r.preview) {
              UI.toast("Uninstaller of " + a.name + " started: follow its window. This page waits for it and then looks for leftovers.", "ok");
              Components.notifications.add("Uninstall started", a.name, "ok");
              follow(a);
            }
            busy(btn, false);
          }, function (e) { UI.toast(e.message, e.cancelled ? "info" : "error"); busy(btn, false); });
        });
    }
    /* Waits for the uninstaller (checking every 3 seconds, up to 30 minutes), then offers what it left behind. */
    function follow(a) {
      var limit = Date.now() + 1000 * 60 * 30;
      (function check() {
        API.get("/apps/" + a.id + "/uninstall-status").then(function (st) {
          // Some uninstallers hand over to a copy of themselves and end at once: the registry entry says when the program is gone.
          if (!st.removed) {
            if (Date.now() < limit) setTimeout(check, st.running ? 3000 : 5000);
            else UI.toast(a.name + " is still installed: the uninstall was cancelled or needs a restart.", "warning");
            return;
          }
          if (st.running) { setTimeout(check, 3000); return; }
          var left = st.leftovers || [];
          Components.notifications.add("Program removed", a.name + (left.length ? ", " + left.length + " leftover(s) found" : ""), "ok");
          if (!left.length) { UI.toast(a.name + " removed, nothing left behind.", "ok"); rescan(); return; }
          offerLeftovers(a, left);
        }, function () { if (Date.now() < limit) setTimeout(check, 5000); });
      })();
    }
    function offerLeftovers(a, left) {
      var body = '<p class="modal-text"><strong>' + esc(a.name) + "</strong> is removed. Its uninstaller left these behind:</p>" +
        '<div class="leftover-list">' + left.map(function (l) {
          // Settings in AppData are kept by default: they matter if the program comes back.
          var keep = l.kind === "folder" && /\\AppData\\/i.test(l.path);
          return '<label class="check"><input type="checkbox" data-leftover="' + esc(l.id) + '"' + (keep ? "" : " checked") + "> " +
            '<span><span class="badge">' + (l.kind === "folder" ? "Folder" : "Registry key") + '</span> <span class="cell-mono">' + esc(l.path) + "</span>" +
            (l.size_mb ? ' <span class="cell-sub">' + size(l.size_mb) + "</span>" : "") + (keep ? ' <span class="cell-sub">(settings)</span>' : "") + "</span></label>";
        }).join("") + "</div>" +
        '<p class="cell-sub">Folders go to the Recycle Bin; registry keys are deleted with a backup (Registry › Backups).</p>';
      UI.modal("Leftovers of " + a.name, body, [{ label: "Keep everything", cls: "btn-ghost" }, { label: "Remove selected", cls: "btn-primary", value: function (w) {
        return Array.prototype.filter.call(w.querySelectorAll("[data-leftover]"), function (c) { return c.checked; }).map(function (c) { return c.getAttribute("data-leftover"); });
      } }]).then(function (ids) {
        if (!ids || !ids.length) { rescan(); return; }
        API.post("/apps/" + a.id + "/leftovers", { ids: ids }).then(function (r) {
          done(r, "the cleanup");
          if (!r.preview) UI.toast((r.removed || []).length + " leftover(s) removed" + ((r.errors || []).length ? ", " + r.errors.length + " could not be removed (in use?)" : "") + ".",
            (r.errors || []).length ? "warning" : "ok");
          rescan();
        }, function (e) { UI.toast(e.message, "error"); });
      });
    }
    function rescan() { if (App.isCurrent("apps")) { page._refresh = true; App.render(); } }
    function removeEntry(a, btn) {
      UI.confirm("Remove the leftover entry", a.name + " is no longer on this PC but is still listed in Settings › Apps. The entry is removed from the registry; " +
        "a backup is kept in Registry › Backups.", { ok: "Remove entry" }).then(function (ok) {
        if (!ok) return;
        busy(btn, true);
        API.post("/apps/" + a.id + "/remove-entry").then(function (r) {
          done(r, "the removal");
          if (r.preview) { busy(btn, false); return; }
          apps.splice(apps.indexOf(a), 1);
          UI.toast("Entry removed. Backup: " + (r.backup || "saved"), "ok");
          drawPrograms();
        }, function (e) { UI.toast(e.message, "error"); busy(btn, false); });
      });
    }
    function detail(a) {
      var rows = [["Publisher", esc(a.publisher || "—")], ["Version", esc(a.version || "—")], ["Kind", esc(CATEGORY[a.category] || a.category)],
        ["Installed", a.installed ? esc(UI.formatDate(a.installed, false)) : "—"], ["Last used", lastUsed(a)],
        ["Size", "<span data-size-cell>" + size(a.size_mb) + "</span>" + (a.folder ? ' <button class="btn btn-sm btn-ghost" type="button" data-measure>Measure</button>' : "")],
        ["For", a.scope === "user" ? "This account only" : "Every account"], ["Folder", a.folder ? '<span class="cell-mono">' + esc(a.folder) + "</span>" : "—"],
        ["Uninstall", a.uninstall ? '<span class="cell-mono">' + esc(a.uninstall) + "</span>" : "—"]];
      if (/^https?:\/\//i.test(a.url || "")) rows.push(["Website", '<a href="' + esc(a.url) + '" target="_blank" rel="noopener noreferrer">' + esc(a.url) + "</a>"]);
      var issues = a.issues.length ? '<ul class="issue-list">' + a.issues.map(function (i) {
        return '<li class="issue-' + esc(i.level) + '">' + UI.icon(i.level === "info" ? "info" : "alert") + "<span>" + esc(i.text) + "</span></li>";
      }).join("") + "</ul>" : '<div class="callout callout-info">' + UI.icon("check") + "<div>No problem found: supported version and known publisher.</div></div>";
      var search = "https://www.bing.com/search?q=" + encodeURIComponent(a.name + " " + (a.version || "") + " latest version");
      var body = "<p>" + statusBadge(a.status) + "</p>" + issues + UI.definition(rows) +
        '<p class="small"><a href="' + search + '" target="_blank" rel="noopener noreferrer">Search the web for the latest version</a></p>';
      var p = UI.modal(a.name, body, [{ label: "Close", cls: "btn-ghost" }].concat(a.uninstall && !a.broken ? [{ label: "Uninstall…", cls: "btn-danger", value: function () { return "uninstall"; } }] : []));
      var backdrops = document.querySelectorAll(".modal-backdrop"), modalEl = backdrops[backdrops.length - 1];
      var measure = modalEl && modalEl.querySelector("[data-measure]");
      if (measure) measure.addEventListener("click", function () {
        busy(measure, true);
        API.post("/apps/" + a.id + "/size").then(function (r) {
          a.size_mb = r.size_mb;
          modalEl.querySelector("[data-size-cell]").textContent = size(r.size_mb);
          measure.remove();
        }, function (e) { UI.toast(e.message, "error"); busy(measure, false); });
      });
      p.then(function (v) { if (v === "uninstall") uninstall(a); });
    }

    root.addEventListener("click", function (e) {
      var t = e.target.closest("button, a");
      if (!t || !root.contains(t)) return;
      var id;
      if (t.hasAttribute("data-apps-view")) { view = t.getAttribute("data-apps-view"); Components.store("appsView", view); drawPrograms(); return; }
      if ((id = t.getAttribute("data-app-detail"))) { detail(byId(id)); return; }
      if ((id = t.getAttribute("data-app-uninstall"))) { uninstall(byId(id), t); return; }
      if ((id = t.getAttribute("data-app-entry"))) { removeEntry(byId(id), t); return; }
      if ((id = t.getAttribute("data-app-folder"))) {
        API.post("/apps/" + id + "/open-folder").then(function () { UI.toast("Folder opened in File Explorer.", "ok"); }, function (e2) { UI.toast(e2.message, "error"); });
        return;
      }
      if ((id = t.getAttribute("data-suggest"))) {
        var parts = id.split(":");
        if (parts[0] === "filter") { view = parts[1]; Components.store("appsView", view); drawPrograms(); showTab("programs"); } else showTab(parts[1]);
        return;
      }
      if (t.hasAttribute("data-apps-rescan")) { busy(t, true); page._refresh = true; App.render(); return; }
      if (t.hasAttribute("data-apps-updates")) { showTab("updates"); checkUpdates(); return; }
      if (t.hasAttribute("data-updates-check")) { checkUpdates(); return; }
      if ((id = t.getAttribute("data-update"))) { updateOne(id, t); return; }
      if ((id = t.getAttribute("data-store-remove"))) { removeStore(id, t); return; }
      if ((id = t.getAttribute("data-browser-clean"))) { cleanBrowsers([id], t); return; }
      if (t.hasAttribute("data-browser-all")) { cleanBrowsers(browsers.filter(function (b) { return b.cache_mb > 0; }).map(function (b) { return b.id; }), t); return; }
      if (t.hasAttribute("data-copy-apps")) { App.copyText(summary(apps, store, d), "Applications summary"); return; }
      if (t.hasAttribute("data-rules-update")) {
        busy(t, true);
        API.post("/apps/rules/update").then(function (r) {
          if (!r.updated) { UI.toast("The rules are already the latest (" + UI.formatDate(r.version, false) + ").", "info"); busy(t, false); return; }
          UI.toast("New rules of " + UI.formatDate(r.version, false) + ": scanning again with them.", "ok");
          page._refresh = true;
          App.render();
        }, function (e) { UI.toast(e.message, "error"); busy(t, false); });
      }
    });

    // ---------- updates (winget) ----------
    function checkUpdates() {
      var box = root.querySelector("#apps-updates");
      if (!box) return;
      box.innerHTML = UI.loading("Asking winget which apps have a newer version (up to a minute)…");
      API.get("/apps/updates").then(function (r) {
        var list = r.updates || [];
        if (!list.length) { box.innerHTML = '<div class="callout callout-info">' + UI.icon("check") + "<div>Every app winget knows is up to date.</div></div>"; return; }
        var fresh = box.cloneNode(false);
        box.parentNode.replaceChild(fresh, box);
        Components.dataTable(fresh, {
          rows: list, exportName: "wmm-app-updates", placeholder: "Search updates…", sort: "name", pageSize: 25,
          columns: [
            { key: "name", title: "App", render: function (u) { return '<span class="cell-title">' + esc(u.name) + '</span><div class="cell-sub cell-mono">' + esc(u.id) + "</div>"; } },
            { key: "version", title: "Installed", render: function (u) { return '<span class="cell-mono">' + esc(u.version) + "</span>"; } },
            { key: "available", title: "Available", render: function (u) { return '<span class="cell-mono text-ok">' + esc(u.available) + "</span>"; } },
            { key: "id", title: "", sortable: false, csv: false, render: function (u) {
              return '<button class="btn btn-sm btn-primary" type="button" data-update="' + esc(u.id) + '">' + UI.icon("download") + "<span>Update</span></button>"; } }
          ]
        });
        UI.toast(list.length + " app update(s) available.", "info");
      }, function (e) { box.innerHTML = UI.errorBox(e); });
    }
    function updateOne(id, btn) {
      busy(btn, true);
      btn.lastChild.textContent = "Updating…";
      API.post("/apps/update", { id: id }).then(function (r) {
        done(r, "the update");
        btn.classList.remove("busy");
        btn.innerHTML = UI.icon("check") + "<span>" + (r.preview ? "Simulated" : "Updated") + "</span>";
        if (!r.preview) UI.toast(id + " updated.", "ok");
      }, function (e) { UI.toast(e.message, "error"); busy(btn, false); btn.lastChild.textContent = "Retry"; });
    }

    // ---------- Store apps ----------
    function removeStore(id, btn) {
      var s = store.filter(function (x) { return x.id === id; })[0];
      UI.confirm("Remove " + s.name, "The app is removed for this account. You can install it again from the Microsoft Store.", { ok: "Remove", danger: true }).then(function (ok) {
        if (!ok) return;
        busy(btn, true);
        UI.withRestorePoint("/apps/store/" + id + "/remove").then(function (r) {
          done(r, "the removal");
          if (r.preview) { busy(btn, false); return; }
          UI.toast(s.name + " removed.", "ok");
          var row = btn.closest("tr");
          if (row) row.remove();
          store.splice(store.indexOf(s), 1);
        }, function (e) { UI.toast(e.message, e.cancelled ? "info" : "error"); busy(btn, false); });
      });
    }
    Components.dataTable(root.querySelector("#store-table"), {
      rows: store, exportName: "wmm-store-apps", placeholder: "Search Store apps…", sort: "name", pageSize: 25,
      filters: [{ key: "bloat", label: "All Store apps", options: [["true", "Preinstalled extras"], ["false", "Others"]] }],
      columns: [
        { key: "name", title: "App", render: function (s) { return '<span class="cell-title">' + esc(s.name) + "</span>" + (s.bloat ? ' <span class="badge badge-status-info">Preinstalled extra</span>' : ""); } },
        { key: "publisher", title: "Publisher", render: function (s) { return esc(s.publisher || "—"); } },
        { key: "version", title: "Version", render: function (s) { return '<span class="cell-mono">' + esc(s.version) + "</span>"; } },
        { key: "last_used", title: "Last used", value: function (s) { return s.last_used || ""; }, render: lastUsed },
        { key: "installed", title: "Installed", render: function (s) { return s.installed ? esc(UI.formatDate(s.installed, false)) : "—"; } },
        { key: "id", title: "", sortable: false, csv: false, render: function (s) {
          return '<button class="btn btn-sm" type="button" data-store-remove="' + esc(s.id) + '">' + UI.icon("trash") + "Remove</button>"; } }
      ]
    });

    // ---------- browsers ----------
    function cleanBrowsers(ids, btn) {
      if (!ids.length) { UI.toast("The browser caches are already empty.", "info"); return; }
      var running = browsers.filter(function (b) { return ids.indexOf(b.id) >= 0 && b.running; }).map(function (b) { return b.name; });
      var text = "Only cached pages, images and scripts are deleted: logins, passwords, history, bookmarks and open tabs stay." +
        (running.length ? " " + running.join(", ") + (running.length > 1 ? " are" : " is") + " open: close it first, or the files in use are skipped." : "");
      UI.confirm(ids.length > 1 ? "Clear every browser cache" : "Clear the cache", text, { ok: "Clear cache" }).then(function (ok) {
        if (!ok) return;
        busy(btn, true);
        var freed = 0, skipped = 0, preview = false;
        ids.reduce(function (p, id) {
          return p.then(function () {
            return API.post("/apps/browsers/" + id + "/clean").then(function (r) { preview = preview || !!r.preview; freed += r.freed_mb || 0; skipped += r.skipped || 0; });
          });
        }, Promise.resolve()).then(function () {
          if (preview) { done({ preview: true }, "the cleanup"); return; }
          UI.toast(size(freed) + " freed" + (skipped ? ", " + skipped + " files in use were skipped" : "") + ".", "ok");
          Components.notifications.add("Browser cache cleared", size(freed) + " freed", "ok");
          return API.get("/apps").then(function (fresh) { browsers = d.browsers = fresh.browsers || []; root.querySelector("#browser-list").innerHTML = browserList(browsers); });
        }).catch(function (e) { UI.toast(e.message, "error"); }).then(function () { busy(btn, false); });
      });
    }
  }

  // ---------- sections ----------

  function overview(apps, d) {
    var suggestions = d.suggestions || [];
    var list = suggestions.length ? '<ul class="suggest-list">' + suggestions.map(function (s) {
      var tone = s.level === "risk" ? "error" : s.level === "review" ? "warning" : "info";
      return '<li class="suggest suggest-' + tone + '"><span class="suggest-icon">' + UI.icon(s.level === "info" ? "recommendations" : "alert") + "</span><div><strong>" +
        esc(s.title) + "</strong><p>" + esc(s.text) + "</p></div>" +
        (s.action ? '<button class="btn btn-sm" type="button" data-suggest="' + esc(s.action) + '">Show</button>' : "") + "</li>";
    }).join("") + "</ul>" : '<div class="callout callout-info">' + UI.icon("check") + "<div>Nothing to suggest: the installed applications look in order.</div></div>";

    var byStatus = ["risk", "review", "ok"].map(function (k, i) {
      return { label: STATUS[k][0], value: apps.filter(function (a) { return a.status === k; }).length, color: ["#D13438", "#C27C0E", "#2E9D8F"][i] };
    });
    var cats = {};
    apps.forEach(function (a) { cats[a.category] = (cats[a.category] || 0) + 1; });
    var catSeries = Object.keys(cats).sort(function (a, b) { return cats[b] - cats[a]; }).map(function (k, i) {
      return { label: CATEGORY[k] || k, value: cats[k], color: Charts.PALETTE[i % Charts.PALETTE.length] };
    });
    var use = ["recent", "unused", "unknown"].map(function (k, i) {
      return { label: USAGE[k], value: apps.filter(function (a) { return a.usage === k; }).length, color: ["#2E9D8F", "#C27C0E", "#B4BCC6"][i] };
    });
    var biggest = Charts.hbars(apps.filter(function (a) { return a.size_mb; }).sort(function (a, b) { return b.size_mb - a.size_mb; }).slice(0, 8).map(function (a, i) {
      return { label: a.name, value: a.size_mb * MB, color: Charts.PALETTE[i % Charts.PALETTE.length] };
    }), { format: UI.formatBytes, empty: "No size information" });
    var recent = apps.filter(function (a) { var x = daysAgo(a.installed); return x != null && x <= 30; })
      .sort(function (a, b) { return a.installed < b.installed ? 1 : -1; });
    var recentList = recent.length ? UI.table([{ title: "Program" }, { title: "Publisher" }, { title: "Installed" }], recent.slice(0, 10).map(function (a) {
      return ['<button type="button" class="link-btn cell-title" data-app-detail="' + esc(a.id) + '">' + esc(a.name) + "</button>", esc(a.publisher || "—"),
        esc(UI.formatDate(a.installed, false))];
    })) : '<p class="empty">Nothing installed in the last 30 days.</p>';

    return '<div data-tab-group="overview"><div class="grid grid-2">' +
      UI.card("Suggestions", list, '<button class="btn btn-sm btn-ghost" type="button" data-copy-apps>Copy summary</button>') +
      UI.card("Safety", '<div class="chart-row">' + Charts.donut(byStatus, { center: apps.length, sub: "programs" }) + Charts.legend(byStatus) + "</div>" +
        '<p class="cell-sub">' + esc("Last use read from " + (d.usage_source || "Windows")) + ".</p>") + "</div>" +
      '<div class="grid grid-3">' +
      UI.card("Kinds of program", '<div class="chart-row">' + Charts.donut(catSeries, { center: apps.length, sub: "programs" }) + Charts.legend(catSeries) + "</div>") +
      UI.card("Use", '<div class="chart-row">' + Charts.donut(use, { center: apps.length, sub: "programs" }) + Charts.legend(use) + "</div>") +
      UI.card("Largest programs", biggest) + "</div>" +
      '<div class="grid">' + UI.card("Installed in the last 30 days", recentList, '<span class="muted small">Something you do not remember installing? Check it.</span>') + "</div></div>";
  }

  function programs() {
    return '<div data-tab-group="programs"><div class="grid">' + UI.card("Installed programs",
      '<div class="apps-views"><div class="segmented" role="radiogroup" aria-label="View">' + VIEWS.map(function (v) {
        return '<button type="button" role="radio" data-apps-view="' + v[0] + '" aria-checked="false">' + esc(v[1]) + "</button>";
      }).join("") + '</div></div><div id="apps-table"></div>', "", "card-flush") + "</div></div>";
  }

  function security(apps, d) {
    var groups = [["eol", "End of support", "No more security fixes: replace them with a supported version or remove them."],
      ["vulnerable", "Versions with known holes", "A newer version fixes them: update."],
      ["unwanted", "Adware and unwanted programs", "Remove them, then check the home page and search engine of every browser."],
      ["remote", "Remote access", "Keep only the tools you use, with a strong password."],
      ["optimizer", "Optimizers and driver updaters", "Windows Update and the hardware maker's site are the safe sources for drivers."],
      ["publisher", "Unknown publisher", "Make sure you know where they come from."],
      ["eol_soon", "Support ending soon", "Plan the move to a newer version."]];
    var blocks = groups.map(function (g) {
      var hit = apps.filter(function (a) { return a.issues.some(function (i) { return i.kind === g[0]; }); });
      if (!hit.length) return "";
      return UI.card(g[1] + " (" + hit.length + ")", '<p class="cell-sub card-note">' + esc(g[2]) + "</p>" +
        UI.table([{ title: "Program" }, { title: "Version" }, { title: "Why" }, { title: "" }], hit.map(function (a) {
          var why = a.issues.filter(function (i) { return i.kind === g[0]; })[0].text;
          return ['<button type="button" class="link-btn cell-title" data-app-detail="' + esc(a.id) + '">' + esc(a.name) + "</button>",
            '<span class="cell-mono">' + esc(a.version || "—") + "</span>", '<span class="cell-sub">' + esc(why) + "</span>",
            a.uninstall && !a.broken ? '<button class="btn btn-sm" type="button" data-app-uninstall="' + esc(a.id) + '">Uninstall</button>' : ""];
        })), "", "card-flush");
    }).join("");
    var safe = apps.filter(function (a) { return a.status === "ok"; }).length;
    return '<div data-tab-group="security"><div class="grid">' + (blocks || UI.card("Security", '<div class="callout callout-info">' + UI.icon("check") +
      "<div>No unsafe program found among " + apps.length + " installed.</div></div>")) +
      UI.card("How the verdict works", '<ul class="plain-list"><li><strong>Unsafe</strong>: end of support (Office 2016, 2019 and 2021, .NET 6, Python 3.10 and older, Flash, ' +
        "Skype…), versions with holes used in real attacks (WinRAR, 7-Zip, VLC, PuTTY) or known adware.</li><li><strong>Review</strong>: remote access tools, " +
        "\"optimizers\", programs without a publisher, support ending within three months.</li><li><strong>Safe</strong>: " + safe +
        " programs with none of these problems. Keep them updated from the Updates tab.</li></ul>" + rulesLine(d.rules),
        '<button class="btn btn-sm" type="button" data-rules-update title="Download the latest rules from the project repository">' + UI.icon("download") + "Update the rules</button>") +
      "</div></div>";
  }

  function rulesLine(r) {
    if (!r || !r.version) return "";
    return '<p class="cell-sub" data-rules-line>Rules of ' + esc(UI.formatDate(r.version, false)) + " (" + (r.source === "downloaded" ? "downloaded" : "built in") + "): " +
      esc(r.end_of_life + " end-of-support products and " + r.min_versions + " minimum safe versions") + ".</p>";
  }

  function updates(d) {
    return '<div data-tab-group="updates"><div class="grid">' + UI.card("App updates (winget)",
      d.winget ? '<div id="apps-updates"><p class="empty card-note">Press Check to ask winget which installed apps have a newer version.</p></div>'
        : '<div class="callout callout-warning">' + UI.icon("alert") + "<div>winget is not available: install <strong>App Installer</strong> from the Microsoft Store.</div></div>",
      d.winget ? UI.button("Check", "data-updates-check", "btn-sm", "refresh") + '<button class="btn btn-sm btn-primary" type="button" data-run="updates.winget_upgrade">' +
        UI.icon("bolt") + "Update all</button>" : "", "card-flush") + "</div></div>";
  }

  function storeCard(store) {
    var extra = store.filter(function (s) { return s.bloat; }).length;
    return '<div data-tab-group="store"><div class="grid">' + UI.card("Microsoft Store apps", '<div id="store-table"></div>',
      '<span class="muted small">' + extra + " preinstalled extras you can remove safely</span>", "card-flush") + "</div></div>";
  }

  function browserList(browsers) {
    if (!browsers.length) return '<p class="empty">No browser profile found.</p>';
    return '<div class="browser-grid">' + browsers.map(function (b) {
      return '<div class="browser-tile"><div class="browser-name">' + esc(b.name) + (b.running ? ' <span class="badge badge-status-warning" title="Close it to clear every file">Open</span>' : "") +
        '</div><div class="browser-size">' + size(b.cache_mb) + '</div><div class="cell-sub">' + Components.num(b.files) + " cached files</div>" +
        '<button class="btn btn-sm" type="button" data-browser-clean="' + esc(b.id) + '"' + (b.cache_mb ? "" : " disabled") + ">" + UI.icon("trash") + "Clear cache</button></div>";
    }).join("") + "</div>";
  }

  function browserCards(browsers, inst) {
    var files = inst.files || [];
    var setup = files.length ? '<p class="cell-sub">' + esc(inst.count + " setup files older than 30 days in " + inst.folder + ": " + size(inst.mb) +
      ". The programs are installed: you can delete the files from File Explorer.") + "</p>" +
      UI.table([{ title: "File" }, { title: "Downloaded" }, { title: "Size", cls: "num" }], files.slice(0, 15).map(function (f) {
        return ['<span class="cell-mono">' + esc(f.name) + "</span>", esc(UI.formatDate(f.date, false)), size(f.mb)];
      })) : '<p class="empty">No old setup file in Downloads.</p>';
    return '<div data-tab-group="browsers"><div class="grid grid-2">' +
      UI.card("Browser caches", '<p class="cell-sub">Clearing the cache frees space and fixes pages that load wrong or look old. ' +
        "Logins, passwords, history, bookmarks and open tabs stay.</p>" + '<div id="browser-list">' + browserList(browsers) + "</div>",
        '<button class="btn btn-sm btn-primary" type="button" data-browser-all>' + UI.icon("bolt") + "Clear all caches</button>") +
      UI.card("Setup files left in Downloads", setup) + "</div></div>";
  }

  function summary(apps, store, d) {
    var lines = ["Applications on this PC (" + new Date().toLocaleString() + ")", apps.length + " programs, " + store.length + " Store apps", ""];
    (d.suggestions || []).forEach(function (s) { lines.push("- " + s.title + ": " + s.text); });
    var risky = apps.filter(function (a) { return a.status !== "ok"; });
    if (risky.length) {
      lines.push("", "Programs to act on:");
      risky.forEach(function (a) { lines.push("- " + a.name + " " + (a.version || "") + " [" + STATUS[a.status][0] + "] " + a.issues[0].text); });
    }
    return lines.join("\n");
  }
})();
