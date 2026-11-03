/* Registry editor: key tree, address bar, favorites, value editing, key management, search, .reg export and backups.
   Every change is preceded by a .reg backup of the key; essential keys cannot be deleted. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var TYPES = ["REG_SZ", "REG_EXPAND_SZ", "REG_MULTI_SZ", "REG_DWORD", "REG_QWORD", "REG_BINARY"];
  var ROOTS = [["HKCR", "HKEY_CLASSES_ROOT"], ["HKCU", "HKEY_CURRENT_USER"], ["HKLM", "HKEY_LOCAL_MACHINE"], ["HKU", "HKEY_USERS"], ["HKCC", "HKEY_CURRENT_CONFIG"]];
  var FAVORITES = [
    ["Startup (all users)", "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run"],
    ["Startup (this user)", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"],
    ["Installed programs", "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"],
    ["Policies (machine)", "HKLM\\SOFTWARE\\Policies"],
    ["Environment (this user)", "HKCU\\Environment"],
    ["Environment (system)", "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment"],
    ["Windows version", "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion"],
    ["Services", "HKLM\\SYSTEM\\CurrentControlSet\\Services"]
  ];

  function typeIcon(t) { return /SZ$/.test(t) ? "ab" : t === "REG_BINARY" ? "01" : "#"; }

  /* One value in .reg syntax, with the key header, ready to paste into a .reg file. */
  var LONG_ROOT = { HKCR: "HKEY_CLASSES_ROOT", HKCU: "HKEY_CURRENT_USER", HKLM: "HKEY_LOCAL_MACHINE", HKU: "HKEY_USERS", HKCC: "HKEY_CURRENT_CONFIG" };
  function regQuote(s) { return '"' + String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"'; }
  function regLine(path, v) {
    var root = path.split("\\")[0].toUpperCase(), key = (LONG_ROOT[root] || root) + path.slice(root.length);
    var name = v.name ? regQuote(v.name) : "@", data = null;
    if (v.type === "REG_SZ") data = regQuote(v.data);
    else if (v.type === "REG_DWORD") data = "dword:" + ("00000000" + (Number(v.data) >>> 0).toString(16)).slice(-8);
    var head = "Windows Registry Editor Version 5.00\r\n\r\n[" + key + "]\r\n";
    // The other types are byte lists: a comment with the readable data, the exact bytes come from Export .reg.
    if (data == null) return head + "; " + (v.name || "(Default)") + " (" + v.type + "): " + v.display + "\r\n; Use Export .reg for the exact bytes of this value.\r\n";
    return head + name + "=" + data + "\r\n";
  }

  window.Pages.registry = {
    title: "Registry",
    render: function (el, App) {
      var info = App.state.info || {}, canWrite = info.admin || info.preview;
      var state = { path: Components.store("regPath") || "HKLM\\SOFTWARE", expanded: {}, data: null };
      var bookmarks = function () { return Components.store("regBookmarks") || []; };
      App.setSubtitle("Browse, edit and back up the Windows registry");

      el.innerHTML = UI.pageHeader("Registry", "Every change is backed up first; essential keys cannot be deleted",
        UI.hint("Before every change the key is exported to a .reg file. Open Backups to restore it: the key gets back the values it had.") +
        UI.button("Backups", 'id="rg-backups"', "", "history") + UI.button("Export .reg", 'id="rg-export"', "", "download")) +
        (canWrite ? "" : '<div class="callout callout-warning">' + UI.icon("shield") + "<div>Read-only: restart the console as administrator to change the registry.</div></div>") +
        (info.preview ? '<div class="callout callout-info">' + UI.icon("info") + "<div>Preview mode: changes are recorded in History but not written.</div></div>" : "") +
        '<form class="rg-address" id="rg-form"><span class="rg-computer">' + UI.icon("explorer") + '</span><input id="rg-path" spellcheck="false" aria-label="Key path" value="' + esc(state.path) +
        '"><button class="btn btn-sm" type="submit">Go</button><button class="btn btn-sm" type="button" id="rg-up" title="Parent key" aria-label="Parent key">↑</button>' +
        '<button class="btn btn-sm rg-star" type="button" id="rg-star" title="Bookmark this key" aria-label="Bookmark this key">★</button>' +
        '<button class="btn btn-sm" type="button" id="rg-copy" title="Copy the path">Copy</button>' +
        '<button class="btn btn-sm" type="button" id="rg-copy-ps" title="Copy as a PowerShell path (HKLM:\\…), ready for Get-ItemProperty">PS</button>' +
        '<button class="btn btn-sm" type="button" id="rg-copy-reg" title="Copy a reg query command that lists this key">reg</button></form>' +
        '<div class="rg-layout"><aside class="card rg-side"><div class="rg-favs"><div class="log-head">Favorites</div><div id="rg-favs"></div></div>' +
        '<div class="log-head" style="padding:0 14px">Keys</div><ul class="rg-tree" id="rg-tree" role="tree"></ul></aside>' +
        '<section class="card rg-main"><div id="rg-main">' + UI.loading("Opening the key…") + "</div></section></div>";
      var tree = el.querySelector("#rg-tree"), main = el.querySelector("#rg-main"), input = el.querySelector("#rg-path");

      /* ---------- favorites ---------- */
      function drawFavs() {
        var all = FAVORITES.concat(bookmarks().map(function (b) { return [b.split("\\").pop() + " ★", b]; }));
        var recent = (Components.store("regRecent") || []).filter(function (p) { return p !== state.path; }).slice(0, 8);
        el.querySelector("#rg-favs").innerHTML = all.map(function (f) {
          return '<button type="button" class="rg-fav" data-go="' + esc(f[1]) + '" title="' + esc(f[1]) + '">' + esc(f[0]) + "</button>";
        }).join("") + (recent.length ? '<div class="log-head rg-recent">Recent</div>' + recent.map(function (p) {
          return '<button type="button" class="rg-fav" data-go="' + esc(p) + '" title="' + esc(p) + '">' + esc(p.split("\\").pop() || p) + "</button>";
        }).join("") : "");
        el.querySelector("#rg-star").classList.toggle("on", bookmarks().indexOf(state.path) >= 0);
      }

      /* ---------- tree (subkeys load when a node opens) ---------- */
      function node(path, name) {
        var open = !!state.expanded[path];
        return '<li role="treeitem" aria-expanded="' + open + '" data-node="' + esc(path) + '"><div class="rg-row' + (path === state.path ? " active" : "") + '">' +
          '<button type="button" class="rg-twist" data-twist="' + esc(path) + '" aria-label="' + (open ? "Collapse " : "Expand ") + esc(name) + '">' + (open ? "▾" : "▸") + "</button>" +
          '<button type="button" class="rg-key" data-go="' + esc(path) + '">' + UI.icon("folder") + "<span>" + esc(name) + "</span></button></div>" +
          (open ? '<ul role="group" data-children="' + esc(path) + '"><li class="muted small rg-empty">…</li></ul>' : "") + "</li>";
      }
      function fillChildren(path) {
        var ul = tree.querySelector('[data-children="' + CSS.escape(path) + '"]');
        if (!ul) return Promise.resolve();
        return API.get("/registry?path=" + encodeURIComponent(path)).then(function (r) {
          ul.innerHTML = r.subkeys.length ? r.subkeys.map(function (k) { return node(k.path, k.name); }).join("") : '<li class="muted small rg-empty">No subkeys</li>';
          return Promise.all(r.subkeys.filter(function (k) { return state.expanded[k.path]; }).map(function (k) { return fillChildren(k.path); }));
        }, function (e) { ul.innerHTML = '<li class="muted small rg-empty">' + esc(e.message) + "</li>"; });
      }
      function drawTree() {
        tree.innerHTML = ROOTS.map(function (r) { return node(r[0], r[1]); }).join("");
        return Promise.all(ROOTS.filter(function (r) { return state.expanded[r[0]]; }).map(function (r) { return fillChildren(r[0]); })).then(function () {
          var active = tree.querySelector(".rg-row.active");
          if (active) active.scrollIntoView({ block: "nearest" });
        });
      }
      function expandTo(path) {
        var acc = "";
        path.split("\\").slice(0, -1).forEach(function (p) { acc = acc ? acc + "\\" + p : p; state.expanded[acc] = true; });
      }

      /* ---------- key view ---------- */
      function open(path) {
        main.innerHTML = UI.loading("Opening the key…");
        return API.get("/registry?path=" + encodeURIComponent(path)).then(function (r) {
          state.path = r.path;
          state.data = r;
          input.value = r.path;
          Components.store("regPath", r.path);
          Components.store("regRecent", [r.path].concat((Components.store("regRecent") || []).filter(function (p) { return p !== r.path; })).slice(0, 12));
          expandTo(r.path);
          drawKey();
          drawFavs();
          return drawTree();
        }, function (e) { main.innerHTML = UI.errorBox(e); });
      }
      function crumbs(path) {
        var acc = "";
        return path.split("\\").map(function (p) {
          acc = acc ? acc + "\\" + p : p;
          return '<button type="button" class="link-btn" data-go="' + esc(acc) + '">' + esc(p) + "</button>";
        }).join('<span class="rg-sep">›</span>');
      }
      function drawKey() {
        var r = state.data;
        var tools = canWrite ? UI.button("New value", 'id="rg-newval"', "btn-sm btn-primary", "play") + UI.button("New key", 'id="rg-newkey"', "btn-sm", "folder") +
          UI.button("Delete key", 'id="rg-delkey"' + (r.protected ? ' disabled title="Essential key: it cannot be deleted"' : ""), "btn-sm btn-danger", "trash") : "";
        main.innerHTML = '<div class="rg-head"><div class="rg-crumbs">' + crumbs(r.path) + "</div>" +
          '<div class="rg-meta"><span class="badge">' + r.counts.subkeys + ' subkeys</span><span class="badge">' + r.counts.values + " values</span>" +
          (r.modified ? '<span class="badge" title="Last write time">' + UI.icon("clock") + esc(UI.formatDate(r.modified)) + "</span>" : "") +
          (r.protected ? '<span class="badge badge-status-info">' + UI.icon("shield") + "Protected key</span>" : "") +
          (r.truncated ? '<span class="badge badge-status-warning">Very large key: list truncated</span>' : "") + '</div><div class="rg-tools">' + tools + "</div></div>" +
          '<form class="rg-search" id="rg-search"><label class="dt-search">' + UI.icon("search") + '<span class="sr-only">Search under this key</span>' +
          '<input type="search" id="rg-q" placeholder="Search keys, value names and text under this key…"></label><button class="btn btn-sm" type="submit">Search</button></form>' +
          '<div id="rg-results"></div><div id="rg-values"></div>' +
          (r.subkeys.length ? '<div class="section-title" style="margin:18px 0 8px">' + UI.icon("folder") + 'Subkeys<span class="extra">' + r.subkeys.length + "</span></div>" +
            '<div class="rg-subkeys">' + r.subkeys.slice(0, 300).map(function (k) {
              return '<button type="button" class="rg-chip" data-go="' + esc(k.path) + '">' + UI.icon("folder") + esc(k.name) + "</button>";
            }).join("") + (r.subkeys.length > 300 ? '<span class="muted small">and ' + (r.subkeys.length - 300) + " more in the tree</span>" : "") + "</div>" : "");
        Components.dataTable(main.querySelector("#rg-values"), {
          rows: r.values, pageSize: 50, exportName: "wmm-registry-values", placeholder: "Filter values…", empty: "This key has no values.",
          filters: [{ key: "type", label: "All types", options: TYPES.map(function (t) { return [t, t]; }) }],
          columns: [
            { key: "name", title: "Name", render: function (v) {
              return '<span class="rg-type">' + typeIcon(v.type) + '</span><span class="cell-title">' + (v.name ? esc(v.name) : '<span class="muted">(Default)</span>') + "</span>"; } },
            { key: "type", title: "Type", render: function (v) { return '<span class="cell-mono">' + esc(v.type) + "</span>"; } },
            { key: "display", title: "Data", render: function (v) { return '<span class="cell-mono rg-data" title="' + esc(v.display) + '">' + esc(v.display) + "</span>"; } },
            { key: "_act", title: "", sortable: false, csv: false, cls: "actions", render: function (v) {
              var key = esc(JSON.stringify(v.name));
              var regLine = '<button class="btn btn-sm btn-ghost" data-regline="' + key + '" title="Copy as a .reg line, to paste into a .reg file">.reg</button>';
              return canWrite ? '<span class="tm-actions"><button class="btn btn-sm" data-edit="' + key + '"' + (v.editable ? "" : " disabled") + ">Edit</button>" +
                '<button class="btn btn-sm" data-rename="' + key + '">Rename</button>' + regLine + '<button class="btn btn-sm" data-delval="' + key + '" aria-label="Delete">' + UI.icon("trash") + "</button></span>"
                : '<span class="tm-actions"><button class="btn btn-sm" data-copyval="' + key + '">Copy</button>' + regLine + "</span>";
            } }
          ]
        });
      }

      /* ---------- changes ---------- */
      function change(op, body, okText) {
        // Deleting a key makes a restore point first (and asks when Windows cannot make one).
        var send = op === "delete-key" ? UI.withRestorePoint("/registry/" + op, body) : API.post("/registry/" + op, body);
        return send.then(function (r) {
          UI.toast(r.preview ? "Preview mode: nothing was written (recorded in History)." : okText + (r.backup ? " Backup: " + r.backup : ""), r.preview ? "info" : "ok");
          return r;
        }, function (e) { UI.toast(e.message, e.cancelled ? "info" : "error"); throw e; });
      }
      function valueByName(name) { return state.data.values.filter(function (v) { return v.name === name; })[0]; }
      function dataField(type, data) {
        if (type === "REG_MULTI_SZ") return '<label>Data (one string per line)<textarea name="data" rows="6" spellcheck="false">' + esc(Array.isArray(data) ? data.join("\n") : data) + "</textarea></label>";
        if (type === "REG_BINARY") return '<label>Data (hexadecimal bytes)<textarea name="data" rows="5" spellcheck="false" class="cell-mono">' + esc(data) + "</textarea></label>";
        if (type === "REG_DWORD" || type === "REG_QWORD") {
          return '<label>Data<input name="data" value="' + esc(data) + '" placeholder="decimal, or hexadecimal like 0x1F"></label>' +
            '<p class="muted small" style="margin:0">' + (type === "REG_DWORD" ? "32-bit" : "64-bit") + " number. Hexadecimal values start with 0x.</p>";
        }
        return '<label>Data<input name="data" value="' + esc(data) + '" spellcheck="false"></label>';
      }
      function editValue(v) {
        var isNew = !v;
        v = v || { name: "", type: "REG_SZ", data: "" };
        var body = '<form class="form" onsubmit="return false"><p class="muted small cell-mono" style="margin:0">' + esc(state.path) + "</p>" +
          '<label>Name<input name="name" value="' + esc(v.name) + '"' + (isNew ? ' placeholder="leave empty for (Default)"' : " readonly") + "></label>" +
          '<label>Type<select name="type"' + (isNew ? "" : " disabled") + ">" + TYPES.map(function (t) { return "<option" + (t === v.type ? " selected" : "") + ">" + t + "</option>"; }).join("") + "</select></label>" +
          "<div data-field>" + dataField(v.type, v.data) + "</div>" +
          '<div class="callout callout-info">' + UI.icon("shield") + "<div>The key is exported to a .reg backup before the change, so it can be restored from Backups.</div></div></form>";
        var done = UI.modal(isNew ? "New value" : "Edit " + (v.name || "(Default)"), body, [{ label: "Cancel", cls: "btn-ghost" }, { label: "Save", cls: "btn-primary", value: function (w) {
          var f = w.querySelector("form");
          return { name: f.name.value, type: f.type.value, data: f.data.value };
        } }]);
        var form = document.querySelector("#modal-root form");
        if (form && isNew) form.type.addEventListener("change", function () { form.querySelector("[data-field]").innerHTML = dataField(form.type.value, ""); });
        done.then(function (x) {
          if (!x) return;
          change("set", { path: state.path, name: x.name, type: x.type, data: x.type === "REG_MULTI_SZ" ? x.data.split("\n") : x.data }, "Value saved.")
            .then(function () { open(state.path); }, function () { /* toast shown */ });
        });
      }

      main.addEventListener("click", function (e) {
        if (e.target.closest("[data-clear-results]")) { main.querySelector("#rg-results").innerHTML = ""; return; }
        var t = e.target.closest("[data-edit],[data-rename],[data-delval],[data-copyval],[data-regline]");
        if (t) {
          var attr = ["data-edit", "data-rename", "data-delval", "data-copyval", "data-regline"].filter(function (a) { return t.hasAttribute(a); })[0];
          var v = valueByName(JSON.parse(t.getAttribute(attr)));
          if (!v) return;
          if (attr === "data-edit") editValue(v);
          if (attr === "data-copyval") App.copyText(v.display, "Value");
          if (attr === "data-regline") App.copyText(regLine(state.path, v), ".reg line");
          if (attr === "data-delval") {
            UI.confirm("Delete " + (v.name || "(Default)") + "?", "The value is removed from " + state.path + ". A .reg backup of the key is made first.", { ok: "Delete", danger: true })
              .then(function (ok) { if (ok) change("delete-value", { path: state.path, name: v.name }, "Value deleted.").then(function () { open(state.path); }, function () {}); });
          }
          if (attr === "data-rename") {
            UI.modal("Rename " + (v.name || "(Default)"), '<form class="form" onsubmit="return false"><label>New name<input name="n" value="' + esc(v.name) + '"></label></form>',
              [{ label: "Cancel", cls: "btn-ghost" }, { label: "Rename", cls: "btn-primary", value: function (w) { return w.querySelector("input").value; } }]).then(function (n) {
              if (n != null && n !== v.name) change("rename-value", { path: state.path, name: v.name, new_name: n }, "Value renamed.").then(function () { open(state.path); }, function () {});
            });
          }
          return;
        }
        if (e.target.closest("#rg-newval")) { editValue(null); return; }
        if (e.target.closest("#rg-newkey")) {
          UI.modal("New key under " + state.path, '<form class="form" onsubmit="return false"><label>Key name<input name="n" placeholder="New Key #1"></label></form>',
            [{ label: "Cancel", cls: "btn-ghost" }, { label: "Create", cls: "btn-primary", value: function (w) { return w.querySelector("input").value.trim(); } }]).then(function (n) {
            if (n) change("create-key", { path: state.path, name: n }, "Key created.").then(function (r) { open(r.path || state.path); }, function () {});
          });
          return;
        }
        if (e.target.closest("#rg-delkey")) {
          UI.confirm("Delete " + state.path + "?", "The key, its values and every subkey are deleted. A .reg backup is made first and can be restored from Backups.",
            { ok: "Delete key", danger: true }).then(function (ok) {
            if (!ok) return;
            var parent = state.path.split("\\").slice(0, -1).join("\\");
            change("delete-key", { path: state.path }, "Key deleted.").then(function () { open(parent); }, function () {});
          });
        }
      });
      main.addEventListener("submit", function (e) {
        if (e.target.id !== "rg-search") return;
        e.preventDefault();
        var q = main.querySelector("#rg-q").value.trim(), box = main.querySelector("#rg-results");
        if (q.length < 2) { UI.toast("Search for at least two characters.", "warning"); return; }
        box.innerHTML = UI.loading("Searching under " + state.path + "…");
        API.get("/registry/search?path=" + encodeURIComponent(state.path) + "&q=" + encodeURIComponent(q)).then(function (r) {
          box.innerHTML = '<div class="callout callout-info rg-results">' + UI.icon("search") + "<div><strong>" + r.results.length + " result(s)</strong> in " + r.keys_searched + " keys" +
            (r.stopped === "time" ? " (stopped after 8 seconds: search a deeper key for more)" : r.stopped === "limit" ? " (first 200)" : "") +
            ' <button type="button" class="btn btn-sm btn-ghost" data-clear-results>Close</button><ul>' + r.results.map(function (x) {
              return '<li><button type="button" class="link-btn" data-go="' + esc(x.path) + '">' + esc(x.path) + "</button>" +
                (x.kind === "value" ? " › <strong>" + esc(x.name || "(Default)") + '</strong> <span class="cell-mono muted">' + esc(x.display || "") + "</span>" : "") + "</li>";
            }).join("") + "</ul></div></div>";
        }, function (err) { box.innerHTML = UI.errorBox(err); });
      });

      /* ---------- navigation ---------- */
      el.addEventListener("click", function (e) {
        var go = e.target.closest("[data-go]");
        if (go) { open(go.getAttribute("data-go")); return; }
        var tw = e.target.closest("[data-twist]");
        if (tw) {
          var p = tw.getAttribute("data-twist"), li = tw.closest("li");
          state.expanded[p] = !state.expanded[p];
          li.outerHTML = node(p, li.querySelector(".rg-key span").textContent);
          if (state.expanded[p]) fillChildren(p);
        }
      });
      el.querySelector("#rg-form").addEventListener("submit", function (e) { e.preventDefault(); open(input.value.trim()); });
      el.querySelector("#rg-up").addEventListener("click", function () {
        var parent = state.path.split("\\").slice(0, -1).join("\\");
        if (parent) open(parent);
      });
      el.querySelector("#rg-copy").addEventListener("click", function () { App.copyText(state.data ? state.data.long_path : state.path, "Key path"); });
      // HKLM\SOFTWARE\x -> HKLM:\SOFTWARE\x for PowerShell; the long hive names have no drive, so they use the Registry:: provider.
      var DRIVES = { HKLM: "HKLM:", HKCU: "HKCU:", HKEY_LOCAL_MACHINE: "HKLM:", HKEY_CURRENT_USER: "HKCU:" };
      el.querySelector("#rg-copy-ps").addEventListener("click", function () {
        var p = state.path, hive = p.split("\\")[0].toUpperCase(), rest = p.slice(hive.length);
        App.copyText(DRIVES[hive] ? "'" + DRIVES[hive] + rest + "'" : "'Registry::" + p + "'", "PowerShell path");
      });
      el.querySelector("#rg-copy-reg").addEventListener("click", function () { App.copyText('reg query "' + state.path + '"', "reg command"); });
      el.querySelector("#rg-star").addEventListener("click", function () {
        var list = bookmarks(), i = list.indexOf(state.path);
        if (i >= 0) list.splice(i, 1); else list.push(state.path);
        Components.store("regBookmarks", list.slice(-20));
        drawFavs();
      });
      el.querySelector("#rg-export").addEventListener("click", function () {
        var a = document.createElement("a");
        a.href = API.url("/registry/export?path=" + encodeURIComponent(state.path));
        a.download = state.path.split("\\").pop() + ".reg";
        document.body.appendChild(a);
        a.click();
        a.remove();
      });
      el.querySelector("#rg-backups").addEventListener("click", function () {
        API.get("/registry/backups").then(function (r) {
          var body = r.backups.length ? '<div class="table-wrap" style="max-height:52vh"><table class="table"><thead><tr><th>Created</th><th>Key</th><th class="num">Size</th><th></th></tr></thead><tbody>' +
            r.backups.map(function (b) {
              return "<tr><td>" + esc(UI.formatDate(b.created)) + '</td><td><span class="cell-mono">' + esc(b.key) + '</span><div class="cell-sub">' + esc(b.name) + '</div></td><td class="num">' +
                esc(UI.formatBytes(b.bytes)) + "</td><td>" + (canWrite ? '<button class="btn btn-sm" data-restore="' + esc(b.name) + '">Restore</button>' : "") + "</td></tr>";
            }).join("") + "</tbody></table></div>" : '<p class="empty">No backups yet: one is made before every change.</p>';
          UI.modal("Registry backups", '<p class="modal-text muted">Restoring imports the .reg file: the key gets back the values it had. Keys added later are kept.</p>' + body,
            [{ label: "Close", cls: "btn-primary" }]);
          var root = document.querySelector("#modal-root .modal-backdrop:last-child");
          if (!root) return;
          root.querySelector(".modal").classList.add("modal-wide");
          root.addEventListener("click", function (e) {
            var b = e.target.closest("[data-restore]");
            if (!b) return;
            UI.confirm("Restore this backup?", "The key " + b.closest("tr").querySelector(".cell-mono").textContent + " gets back the values saved in " + b.getAttribute("data-restore") + ".",
              { ok: "Restore" }).then(function (ok) {
              if (ok) change("restore", { backup: b.getAttribute("data-restore") }, "Backup restored.").then(function () { open(state.path); }, function () {});
            });
          });
        }, function (e) { UI.toast(e.message, "error"); });
      });

      drawFavs();
      return open(state.path);
    }
  };
})();
