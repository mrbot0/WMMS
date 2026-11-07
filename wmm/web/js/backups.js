/* 2.13: the Backup tab of Storage. Backup profiles (copy, mirror, dated archives with optional encryption), run now or on
   a schedule, versions to browse, check and restore (all files or the chosen ones), the history of every run. */
(function () {
  "use strict";
  var esc = UI.esc;
  var KIND = {
    copy: ["Copy", "New and changed files are copied; nothing is deleted at the destination."],
    mirror: ["Mirror", "The destination becomes an exact copy: files deleted here are deleted there too."],
    archive: ["Dated archives", "Every run makes a zip you can go back to; the oldest are removed. Can be encrypted."]
  };
  var FREQ = { manual: ["Manual"], daily: ["Every day"], weekly: ["Every week"] };
  var timer = null, suggested = [];

  function fail(e) { UI.toast(e.message, "error"); }
  function badge(text, cls) { return '<span class="badge ' + (cls || "") + '">' + esc(text) + "</span>"; }
  function closeModal(node) { var m = node && node.closest(".modal-backdrop"); if (m) m.querySelector(".modal-foot .btn").click(); }
  function lastLine(p) {
    if (p.running) return badge("Running", "badge-status-running") + (p.running.total ? ' <span class="cell-sub">' + p.running.done + " / " + p.running.total + " files</span>" : "");
    if (!p.last) return '<span class="cell-sub">Never run</span>';
    return UI.statusBadge(p.last.ok ? "ok" : "error") + ' <span class="cell-sub">' + esc(UI.relative(p.last.finished)) + '</span> <span class="cell-sub">· ' +
      p.last.files + " files, " + esc(UI.formatBytes(p.last.bytes || 0)) + "</span>";
  }

  /* ---------- the tab ---------- */
  function render(host, App) {
    if (timer) { clearTimeout(timer); timer = null; }
    if (!host.innerHTML) host.innerHTML = UI.loading();
    return API.get("/backups").then(function (d) { draw(host, App, d); }, function (e) { host.innerHTML = UI.errorBox(e); });
  }

  function draw(host, App, d) {
    var ps = d.profiles || [];
    suggested = d.suggested || [];
    var ultimo = ps.map(function (p) { return p.last_ok && p.last_ok.finished; }).filter(Boolean).sort().pop();
    var spazio = ps.reduce(function (s, p) { return s + (p.versions_bytes || 0); }, 0);
    var versioni = ps.reduce(function (s, p) { return s + (p.versions || 0); }, 0);
    var kpis = '<div class="grid grid-4">' +
      UI.kpi("Backups", Components.num(ps.length), ps.filter(function (p) { return p.enabled && p.frequency !== "manual"; }).length + " on a schedule", "info") +
      UI.kpi("Last good backup", ultimo ? esc(UI.relative(ultimo)) : "Never", ultimo ? esc(UI.formatDate(ultimo)) : "Run one to be safe", ultimo ? "ok" : "warning") +
      UI.kpi("Problems", Components.num(d.failed || 0), (d.due || []).length + " due now", d.failed ? "error" : "ok") +
      UI.kpi("Saved versions", Components.num(versioni), esc(UI.formatBytes(spazio)) + " at the destinations", "info") + "</div>";
    var tools = UI.button("New backup", "data-bk-new", "btn-primary btn-sm", "download") +
      UI.button("Run the ones due", 'data-run="storage.backup_profiles"', "btn-sm", "play") +
      UI.button("Schedule automatic runs", 'data-schedule="storage.backup_profiles"', "btn-sm", "clock") +
      UI.button("Refresh", "data-bk-refresh", "btn-sm btn-ghost", "refresh");
    var cards = ps.length ? '<div class="backup-grid">' + ps.map(profileCard).join("") + "</div>" :
      '<div class="empty-state">' + UI.icon("storage") + "<h3>No backup yet</h3><p>Choose the folders to save and a disk or a NAS to save them to. " +
      "Three kinds: a copy, a mirror, or dated archives you can go back to.</p>" + UI.button("New backup", "data-bk-new", "btn-primary", "download") + "</div>";
    var auto = ps.some(function (p) { return p.frequency !== "manual"; }) ?
      '<p class="muted small">Daily and weekly backups run when the tool Run the backups that are due runs: schedule it every hour or when the PC is idle.</p>' : "";
    host.innerHTML = kpis + UI.card("Backups", auto + cards, tools) + UI.card("Backup history", '<div data-bk-history></div>', "", "card-flush");
    Components.dataTable(host.querySelector("[data-bk-history]"), {
      rows: d.history || [], exportName: "wmm-backup-history", placeholder: "Search the history…", pageSize: 10, sort: "finished", desc: true,
      columns: [
        { key: "finished", title: "When", render: function (r) { return esc(UI.formatDate(r.finished)); } },
        { key: "name", title: "Backup", render: function (r) { return '<span class="cell-title" data-no-i18n>' + esc(r.name) + "</span>"; } },
        { key: "kind", title: "Kind", value: function (r) { return (KIND[r.kind] || [r.kind])[0]; } },
        { key: "ok", title: "Result", value: function (r) { return r.ok ? "ok" : "error"; }, render: function (r) { return UI.statusBadge(r.ok ? "ok" : "error"); } },
        { key: "files", title: "Files", cls: "num" },
        { key: "bytes", title: "Size", cls: "num", render: function (r) { return esc(UI.formatBytes(r.bytes || 0)); } },
        { key: "errors", title: "Problems", value: function (r) { return (r.errors || []).join(" "); },
          render: function (r) { return (r.errors || []).length ? '<span class="cell-sub" data-no-i18n title="' + esc(r.errors.join("\n")) + '">' + esc(r.errors[0]) + "</span>" : "—"; } }
      ]
    });
    host.onclick = function (e) {
      var b = e.target.closest("[data-bk-new],[data-bk-refresh],[data-bk]");
      if (!b) return;
      if (b.hasAttribute("data-bk-new")) return editor(host, App, null);
      if (b.hasAttribute("data-bk-refresh")) return render(host, App);
      var p = ps.filter(function (x) { return x.id === b.getAttribute("data-id"); })[0];
      if (p) act(host, App, b.getAttribute("data-bk"), p);
    };
    if (ps.some(function (p) { return p.running; })) timer = setTimeout(function () { if (document.body.contains(host)) render(host, App); }, 2500);
  }

  function profileCard(p) {
    var k = KIND[p.kind] || [p.kind, ""];
    var btn = function (label, what, iconName, cls) { return UI.button(label, 'data-bk="' + what + '" data-id="' + esc(p.id) + '"', "btn-sm " + (cls || ""), iconName); };
    return '<div class="backup-card' + (p.enabled ? "" : " off") + '">' +
      '<div class="backup-top"><span class="cell-title grow" data-no-i18n>' + esc(p.name) + "</span>" + badge(k[0]) + (p.encrypted ? badge("Encrypted", "badge-status-ok") : "") +
      (p.enabled ? "" : badge("Paused")) + badge((FREQ[p.frequency] || [p.frequency])[0]) + "</div>" +
      '<dl class="backup-facts"><dt>Saves</dt><dd data-no-i18n>' + p.sources.map(esc).join("<br>") + "</dd>" +
      "<dt>To</dt><dd data-no-i18n>" + esc(p.folder) + "</dd>" +
      (p.exclude && p.exclude.length ? "<dt>Skips</dt><dd data-no-i18n>" + esc(p.exclude.join(", ")) + "</dd>" : "") +
      "<dt>Last run</dt><dd>" + lastLine(p) + "</dd>" +
      (p.kind === "archive" ? "<dt>Versions</dt><dd>" + p.versions + " of " + p.keep + " kept · " + esc(UI.formatBytes(p.versions_bytes || 0)) + "</dd>" : "") +
      (p.last && !p.last.ok && p.last.errors && p.last.errors.length ? '<dt>Problem</dt><dd class="text-error" data-no-i18n>' + esc(p.last.errors[0]) + "</dd>" : "") +
      "</dl>" +
      '<div class="backup-actions">' + btn("Run now", "run", "play", "btn-primary") + btn("Try it", "preview", "search") +
      (p.kind === "archive" ? btn("Versions", "versions", "history") : btn("Restore", "restore", "download")) +
      btn("Check", "verify", "check") + btn("Size", "estimate", "gauge") + '<span class="grow"></span>' + btn("Edit", "edit", "settings", "btn-ghost") +
      btn("Delete", "delete", "trash", "btn-ghost") + "</div></div>";
  }

  /* ---------- what a button does ---------- */
  function act(host, App, what, p) {
    if (what === "run" || what === "preview") {
      return API.post("/backups/" + p.id + "/run", { preview: what === "preview" }).then(function (r) {
        UI.toast(what === "preview" ? "Trying the backup: nothing is written." : r.preview ? "Preview mode: the backup is only simulated, nothing is written." : "Backup started.", "ok");
        setTimeout(function () { render(host, App); }, 700);
      }, fail);
    }
    if (what === "edit") return editor(host, App, p);
    if (what === "delete") {
      return UI.confirm("Delete the backup", "The profile is removed. The backups already made stay at the destination: delete them there if you do not need them.",
        { ok: "Delete", danger: true }).then(function (ok) {
        if (ok) API.del("/backups/" + p.id).then(function () { UI.toast("Backup deleted.", "ok"); render(host, App); }, fail);
      });
    }
    if (what === "estimate") {
      UI.toast("Measuring the folders…", "info");
      return API.get("/backups/" + p.id + "/estimate").then(function (e) {
        UI.modal("Size of the backup", UI.definition([
          ["Files", Components.num(e.files) + (e.truncated ? " (at least)" : "")], ["Size", esc(UI.formatBytes(e.bytes))],
          ["Free at the destination", e.target_ok ? esc(UI.formatBytes(e.target_free)) : "Not reachable now"],
          ["Room enough", e.fits == null ? "—" : e.fits ? "Yes" : "No"]]), [{ label: "Close", cls: "btn-primary" }]);
      }, fail);
    }
    if (what === "verify") return passwordFor(p).then(function (pw) { if (pw !== false) verify(p, null, pw); });
    if (what === "versions") return versions(host, App, p);
    if (what === "restore") return restoreDialog(host, App, p, null, null, null);
  }

  /* An encrypted archive opens with the saved password; another one can be typed if it was changed since. */
  function passwordFor(p) {
    if (!p.encrypted) return Promise.resolve(null);
    return UI.modal("Password of the archive", '<div class="form"><label>Password<input type="password" id="bk-pw" autocomplete="off" placeholder="Saved password"></label>' +
      '<span class="hint">Leave it empty to use the saved password. Type another only if the archive was made with an older one.</span></div>',
    [{ label: "Cancel", cls: "btn-ghost" }, { label: "Continue", cls: "btn-primary", value: function (w) { return { pw: w.querySelector("#bk-pw").value }; } }])
      .then(function (v) { return v ? v.pw || null : false; });
  }

  function verify(p, version, password) {
    UI.toast("Checking the backup…", "info");
    return API.post("/backups/" + p.id + "/verify", { version: version, password: password || undefined }).then(function (r) {
      UI.modal(r.ok ? "The backup is good" : "The backup has problems", '<p class="modal-text">' + esc(r.detail) + "</p>" +
        (r.missing && r.missing.length ? '<pre class="code-block" data-no-i18n>' + esc(r.missing.slice(0, 20).join("\n")) + "</pre>" : ""),
      [{ label: "Close", cls: "btn-primary" }]);
    }, fail);
  }

  /* ---------- versions of an archive backup ---------- */
  function versions(host, App, p) {
    return API.get("/backups/" + p.id + "/versions").then(function (d) {
      var vv = d.versions || [];
      var body = vv.length ? '<table class="table"><thead><tr><th>Version</th><th class="num">Size</th><th></th></tr></thead><tbody>' + vv.map(function (v) {
        var b = function (label, what, iconName, cls) { return UI.button(label, 'data-v="' + what + '" data-name="' + esc(v.name) + '"', "btn-sm " + (cls || ""), iconName); };
        return '<tr><td><span class="cell-title">' + esc(UI.formatDate(v.created)) + "</span> " + (v.encrypted ? badge("Encrypted", "badge-status-ok") : "") +
          '<div class="cell-sub" data-no-i18n>' + esc(v.name) + '</div></td><td class="num">' + esc(UI.formatBytes(v.size)) + '</td><td class="row-actions">' +
          b("Files", "files", "folder") + b("Restore all", "restore", "download") + b("Check", "verify", "check") + b("Delete", "delete", "trash", "btn-ghost") + "</td></tr>";
      }).join("") + "</tbody></table>" : '<p class="modal-text">No version yet: run the backup once.</p>';
      var aperto = UI.modal("Versions", '<div class="backup-versions">' + body + "</div>", [{ label: "Close", cls: "btn-primary" }]);
      var box = document.querySelector(".modal .backup-versions");
      if (box) box.addEventListener("click", function (e) {
        var b = e.target.closest("[data-v]");
        if (!b) return;
        var nome = b.getAttribute("data-name"), cosa = b.getAttribute("data-v");
        closeModal(b);
        if (cosa === "delete") {
          return UI.confirm("Delete this version", "This archive is deleted from the destination for good.", { ok: "Delete", danger: true }).then(function (ok) {
            if (ok) API.del("/backups/" + p.id + "/versions?version=" + encodeURIComponent(nome)).then(function () { UI.toast("Version deleted.", "ok"); render(host, App); }, fail);
          });
        }
        passwordFor(p).then(function (pw) {
          if (pw === false) return;
          if (cosa === "files") fileBrowser(host, App, p, nome, pw);
          else if (cosa === "restore") restoreDialog(host, App, p, nome, null, pw);
          else verify(p, nome, pw);
        });
      });
      return aperto;
    }, fail);
  }

  function fileBrowser(host, App, p, nome, pw) {
    UI.toast("Opening the archive…", "info");
    return API.post("/backups/" + p.id + "/files", { version: nome, password: pw || undefined }).then(function (d) {
      UI.modal("Files in the archive", '<p class="muted small">' + Components.num(d.count) + " files, " + esc(UI.formatBytes(d.bytes)) +
        ". Select the files to bring back, then choose where.</p><div data-bk-files></div>", [{ label: "Close", cls: "btn-ghost" }]);
      var el = document.querySelector(".modal [data-bk-files]");
      Components.dataTable(el, {
        rows: (d.files || []).map(function (f) { return Object.assign({ id: f.path }, f); }), placeholder: "Search files…", pageSize: 10, sort: "path",
        columns: [
          { key: "path", title: "File", render: function (r) { return '<span class="cell-mono" data-no-i18n>' + esc(r.path) + "</span>"; } },
          { key: "size", title: "Size", cls: "num", render: function (r) { return esc(UI.formatBytes(r.size || 0)); } },
          { key: "mtime", title: "Changed", render: function (r) { return r.mtime ? esc(UI.formatDate(r.mtime)) : "—"; } }
        ],
        select: { key: "id", actions: [{ label: "Restore the selected", icon: "download", cls: "btn-primary", run: function (sel) {
          closeModal(el);
          return restoreDialog(host, App, p, nome, sel.map(function (r) { return r.path; }), pw);
        } }] }
      });
    }, fail);
  }

  function restoreDialog(host, App, p, nome, files, pw) {
    var quanti = files ? files.length + " chosen files" : "every file";
    var body = '<div class="form"><p class="modal-text">Restores ' + esc(quanti) + ".</p>" +
      '<label class="check"><input type="radio" name="bk-where" value="new" checked><span class="check-text">Into a new folder (safest)</span></label>' +
      '<label>Folder<input type="text" id="bk-dest" data-no-i18n value="' + esc("C:\\Restored\\" + p.name.replace(/[^\w\- ]/g, "_")) + '"></label>' +
      '<label class="check"><input type="radio" name="bk-where" value="place"><span class="check-text">Back to where they were</span></label>' +
      '<label class="check"><input type="checkbox" id="bk-over"><span class="check-text">Replace the files that are already there</span>' +
      '<span class="hint">Off: a file that exists is kept and only the missing ones come back.</span></label></div>';
    function opts(w, preview) {
      var place = w.querySelector('input[name="bk-where"]:checked').value === "place";
      return { place: place, dest: w.querySelector("#bk-dest").value.trim(), over: w.querySelector("#bk-over").checked, preview: preview };
    }
    return UI.modal("Restore files", body, [{ label: "Cancel", cls: "btn-ghost" },
      { label: "Try it", cls: "", value: function (w) { return opts(w, true); } },
      { label: "Restore", cls: "btn-primary", value: function (w) { return opts(w, false); } }]).then(function (o) {
      if (!o) return;
      var corpo = { version: nome, files: files || undefined, dest: o.place ? undefined : o.dest, overwrite: o.over, password: pw || undefined, preview: o.preview };
      UI.toast(o.preview ? "Counting what would come back…" : "Restoring…", "info");
      return API.post("/backups/" + p.id + "/restore", corpo).then(function (r) {
        var problemi = (r.errors || []).length;
        UI.modal(r.preview ? "What would come back" : "Restore finished", UI.definition([
          [r.preview ? "Files that would come back" : "Files restored", Components.num(r.restored)],
          ["Kept because they already exist", Components.num(r.skipped || 0)],
          ["Where", '<span data-no-i18n>' + esc(r.dest) + "</span>"],
          ["Problems", problemi ? '<span data-no-i18n>' + esc(r.errors.slice(0, 5).join("; ")) + "</span>" : "None"]]),
        r.preview ? [{ label: "Close", cls: "btn-ghost" }, { label: "Restore now", cls: "btn-primary", value: function () { return true; } }] : [{ label: "Close", cls: "btn-primary" }])
          .then(function (again) { if (again) restoreDialog(host, App, p, nome, files, pw); });
      }, fail);
    });
  }

  /* ---------- new backup and edit ---------- */
  function editor(host, App, p, draft) {
    var v = draft || p || { name: "", sources: [], exclude: ["*.tmp", "~$*", "Thumbs.db", "node_modules"], target: "", kind: "archive", keep: 10, frequency: "daily", enabled: true };
    var opt = function (map, cur) { return Object.keys(map).map(function (k) { return '<option value="' + k + '"' + (k === cur ? " selected" : "") + ">" + esc(map[k][0]) + "</option>"; }).join(""); };
    var body = '<div class="form backup-form">' +
      '<label>Name<input type="text" id="bk-name" maxlength="60" data-no-i18n value="' + esc(v.name) + '" placeholder="Documents every day"></label>' +
      '<label>Folders to save<textarea id="bk-src" rows="3" data-no-i18n>' + esc((v.sources || []).join("\n")) + "</textarea></label>" +
      '<span class="hint">One folder per line, such as C:\\Users\\name\\Documents. ' + (suggested.length ? UI.button("Add my folders", "data-bk-mine", "btn-sm btn-ghost", "folder") : "") + "</span>" +
      '<label>Destination<input type="text" id="bk-target" data-no-i18n value="' + esc(v.target) + '" placeholder="E:\\Backup  ·  \\\\nas\\backup"></label>' +
      '<span class="hint">Another disk or a NAS share. A folder with the name of this PC is made inside it.</span>' +
      '<label>Kind<select id="bk-kind">' + opt(KIND, v.kind) + '</select></label><span class="hint" id="bk-kind-hint">' + esc(KIND[v.kind][1]) + "</span>" +
      '<label>When<select id="bk-freq">' + opt(FREQ, v.frequency) + "</select></label>" +
      '<label data-arch>Versions to keep<input type="number" id="bk-keep" min="1" max="365" value="' + esc(v.keep) + '"></label>' +
      '<label data-arch>Password to encrypt the archives<input type="password" id="bk-pw" autocomplete="new-password" placeholder="' +
      esc(p && p.has_password ? "Saved: leave empty to keep it" : "Empty: not encrypted") + '"></label>' +
      (p && p.has_password ? '<label class="check" data-arch><input type="checkbox" id="bk-pw-clear"><span class="check-text">Stop encrypting the next archives</span></label>' : "") +
      '<span class="hint" data-arch>Keep the password somewhere safe: without it an encrypted archive cannot be opened, not even by this app.</span>' +
      '<label>Skip these names<textarea id="bk-ex" rows="2" data-no-i18n>' + esc((v.exclude || []).join("\n")) + "</textarea></label>" +
      '<span class="hint">One per line, * is any text: *.tmp, node_modules, ~$*.</span>' +
      '<label class="check"><input type="checkbox" id="bk-on"' + (v.enabled ? " checked" : "") + '><span class="check-text">Active</span>' +
      '<span class="hint">A paused backup is skipped by the scheduled runs; you can still run it by hand.</span></label></div>';
    var prom = UI.modal(p ? "Edit the backup" : "New backup", body, [{ label: "Cancel", cls: "btn-ghost" }, { label: p ? "Save" : "Create", cls: "btn-primary", value: function (w) {
      var lines = function (id) { return w.querySelector(id).value.split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean); };
      var out = { name: w.querySelector("#bk-name").value.trim(), sources: lines("#bk-src"), target: w.querySelector("#bk-target").value.trim(),
        kind: w.querySelector("#bk-kind").value, frequency: w.querySelector("#bk-freq").value, keep: parseInt(w.querySelector("#bk-keep").value, 10) || 10,
        exclude: lines("#bk-ex"), enabled: w.querySelector("#bk-on").checked };
      var pw = w.querySelector("#bk-pw").value;
      if (pw) out.password = pw;
      var clr = w.querySelector("#bk-pw-clear");
      if (clr && clr.checked) out.clear_password = true;
      return out;
    } }]);
    var w = document.querySelector(".modal .backup-form");
    if (w) {
      var kind = w.querySelector("#bk-kind");
      var sync = function () {
        w.querySelector("#bk-kind-hint").textContent = KIND[kind.value][1];
        w.querySelectorAll("[data-arch]").forEach(function (n) { n.hidden = kind.value !== "archive"; });
      };
      kind.addEventListener("change", sync);
      sync();
      var mine = w.querySelector("[data-bk-mine]");
      if (mine) mine.addEventListener("click", function () {
        var ta = w.querySelector("#bk-src");
        var cur = ta.value.split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean);
        suggested.forEach(function (f) { if (cur.indexOf(f) < 0) cur.push(f); });
        ta.value = cur.join("\n");
      });
    }
    return prom.then(function (out) {
      if (!out) return;
      var req = p ? API.put("/backups/" + p.id, out) : API.post("/backups", out);
      return req.then(function () { UI.toast(p ? "Backup saved." : "Backup created: run it once to check it.", "ok"); render(host, App); },
        function (e) { fail(e); editor(host, App, p, Object.assign({}, out, { password: undefined })); });
    });
  }

  window.BackupTab = { render: render };
})();
