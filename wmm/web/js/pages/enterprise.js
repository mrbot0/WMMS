/* Company centre (2.10): the central server and its PCs, groups and assets, inventory, software deployment, Windows
   Update rings, compliance baselines, approvals, incidents, the executive report and this PC as an agent. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  function fail(e) { if (e && e.message !== "cancelled") UI.toast(e.message, "error"); }
  function when(iso) { return iso ? UI.formatDate(iso) : "—"; }
  function can(p) { return Auth.can(p); }
  function score(v) { return v == null ? "—" : '<span class="badge badge-status-' + UI.tone(v) + '">' + Math.round(v) + "</span>"; }
  function pickTools(App, filtro) {
    return Object.keys(App.state.actions).map(function (k) { return App.state.actions[k]; }).filter(filtro || function () { return true; })
      .sort(function (a, b) { return a.title.localeCompare(b.title); });
  }
  function targetPicker(c) {
    return '<label>Send to<select class="tg-kind"><option value="group">A group</option><option value="pcs">Chosen PCs</option></select></label>' +
      '<select class="tg-group">' + c.groups.map(function (g) { return '<option value="' + esc(g.name) + '">' + esc(g.name + " (" + g.members + ")") + "</option>"; }).join("") + "</select>" +
      '<select multiple size="6" class="tg-pcs" style="width:100%">' + c.agents.map(function (a) { return '<option value="' + esc(a.id) + '">' + esc(a.hostname) + "</option>"; }).join("") + "</select>";
  }
  function readTarget(w) {
    if (w.querySelector(".tg-kind").value === "group") return { group: w.querySelector(".tg-group").value };
    return { agents: Array.prototype.map.call(w.querySelector(".tg-pcs").selectedOptions, function (o) { return o.value; }) };
  }
  function watchBatch(App, lotto) {
    var host = document.createElement("div");
    UI.modal("Results", '<div class="batch-host"></div>', [{ label: "Close", cls: "btn-ghost" }]);
    var slot = document.querySelectorAll("#modal-root .batch-host");
    slot[slot.length - 1].appendChild(host);
    (function giro(n) {
      API.get("/central/batches/" + lotto).then(function (d) {
        host.innerHTML = UI.table([{ title: "PC" }, { title: "State" }, { title: "Result" }], d.jobs.map(function (j) {
          var r = j.result || {};
          var testo = r.error || (r.results ? r.results.map(function (x) { return x.action_id + ": " + x.status; }).join(", ") : r.output || (r.percent != null ? r.percent + "%" : ""));
          return [esc(j.hostname), UI.statusBadge(j.status === "done" ? "ok" : j.status === "error" ? "error" : "running") + ' <span class="cell-sub">' + esc(j.status) + "</span>",
            '<span class="cell-sub">' + esc(String(testo).slice(0, 300)) + "</span>"];
        }));
        if (d.jobs.some(function (j) { return j.status === "queued" || j.status === "sent"; }) && n < 400 && document.body.contains(host)) setTimeout(function () { giro(n + 1); }, 5000);
      }, fail);
    })(0);
  }

  // ---------- central PCs ----------
  function pcs(box, App, c) {
    var srv = c.server;
    box.innerHTML = (srv.enabled ? "" : '<div class="callout callout-info">' + UI.icon("network") + "<div>This PC is not a central server. Turn it on to manage PCs " +
      "everywhere: every PC contacts it over HTTPS, also from other offices and outside the office.</div></div>") +
      '<div class="toolbar"><label class="check"><input type="checkbox" data-srv-on' + (srv.enabled ? " checked" : "") + (can("central.manage") ? "" : " disabled") + "> Central server on</label>" +
      '<label>Port <input type="number" data-srv-port value="' + srv.port + '" style="max-width:100px"></label>' +
      (c.fingerprint ? '<span class="cell-sub cell-mono" title="Certificate fingerprint">' + esc(c.fingerprint.slice(0, 29)) + "…</span>" : "") + '<span class="grow"></span>' +
      (srv.enabled && can("central.manage") ? UI.button("Enrollment code", "data-code", "btn-sm btn-primary", "shield") + UI.button("Send a job", "data-job", "btn-sm", "play") : "") + "</div>" +
      '<div class="grid grid-4">' + UI.kpi("PCs", Components.num(c.overview.agents), c.overview.online + " online", "info") +
      UI.kpi("Need attention", Components.num(c.overview.weak), "health under 60", c.overview.weak ? "warning" : "ok") +
      UI.kpi("Compliance", c.overview.compliance == null ? "—" : c.overview.compliance + "%", "average of the baselines", "info") +
      UI.kpi("Warranty expired", Components.num(c.overview.warranty_expired), c.overview.queued + " jobs waiting", c.overview.warranty_expired ? "warning" : "ok") + "</div>" +
      (c.tenants.length ? '<div class="toolbar"><label>Client <select data-tenant-filter><option value="">All clients</option>' + c.tenants.map(function (t) {
        return '<option value="' + esc(t.id) + '"' + (t.id === c.tenantFilter ? " selected" : "") + ">" + esc(t.name + " (" + t.agents + ")") + "</option>"; }).join("") + "</select></label></div>" : "") +
      UI.table([{ title: "PC" }, { title: "Groups" }, { title: "Health" }, { title: "Compliance" }, { title: "Last contact" }, { title: "Asset" }, { title: "" }], c.agents.map(function (a) {
        return ["<strong>" + esc(a.hostname) + '</strong><div class="cell-sub cell-mono">' + esc(a.ip + " · " + (a.version || "?")) + "</div>" +
          (a.tenant_name ? '<div class="cell-sub">' + esc(a.tenant_name) + "</div>" : ""),
          a.tags.map(function (t) { return '<span class="badge">' + esc(t) + "</span>"; }).join(" ") || "—", score(a.overall),
          a.compliance == null ? "—" : esc(a.compliance + "%"), (a.online ? UI.statusIcon("ok") : UI.statusIcon("warning")) + " " + esc(when(a.last_seen)),
          esc([a.asset_tag, a.owner, a.location].filter(Boolean).join(" · ") || "—"),
          '<button class="btn btn-sm" data-agent="' + esc(a.id) + '">Details</button>'];
      }), "No PC enrolled yet: create an enrollment code and paste it on each PC (Company centre › This PC).");
    box.onclick = function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-code")) {
        UI.modal("Enrollment code", '<form class="form" onsubmit="return false"><label>Address the PCs use to reach this server<input name="host" value="' + esc(App.state.info.hostname) + '"></label>' +
          '<label>Groups for the new PCs (comma separated)<input name="tags"></label>' +
          (c.tenants.length ? '<label>Client of the new PCs<select name="tenant">' + (c.limited ? "" : '<option value="">No client</option>') + c.tenants.map(function (t) {
            return '<option value="' + esc(t.id) + '">' + esc(t.name) + "</option>"; }).join("") + "</select></label>" : "") +
          "</form>", [{ label: "Cancel", cls: "btn-ghost" }, { label: "Create", cls: "btn-primary", value: function (w) {
          var f = w.querySelector("form"); return { host: f.host.value.trim(), tags: f.tags.value.split(",").map(function (x) { return x.trim(); }).filter(Boolean),
            tenant: f.tenant ? f.tenant.value : "" }; } }])
          .then(function (d) {
            if (!d) return null;
            return API.post("/central/enroll-code", d).then(function (r) {
              UI.modal("Enrollment code", '<p class="modal-text">On each PC open Company centre › This PC and paste it. It works once, until ' + esc(when(r.expires)) + ".</p>" +
                '<pre class="code-block" data-no-i18n style="white-space:pre-wrap;word-break:break-all">' + esc(r.code) + "</pre>",
              [{ label: "Copy and close", cls: "btn-primary", value: function () { return true; } }]).then(function () { App.copyText(r.code, "Code"); });
            });
          }).catch(fail);
      }
      if (b.hasAttribute("data-job")) sendJob(App, c);
      if (b.getAttribute("data-agent")) agentDetails(App, b.getAttribute("data-agent"), c);
    };
    box.onchange = function (e) {
      if (e.target.hasAttribute("data-srv-on")) API.put("/central/server", { enabled: e.target.checked, port: Number(box.querySelector("[data-srv-port]").value) })
        .then(function () { App.render(); }, fail);
      if (e.target.hasAttribute("data-tenant-filter")) {
        var scelto = e.target.value;
        API.get("/central" + (scelto ? "?tenant=" + encodeURIComponent(scelto) : "")).then(function (d) { d.tenantFilter = scelto; pcs(box, App, d); }, fail);
      }
    };
  }

  // 2.11: the clients of a provider that manages the PCs of several companies
  function clients(box, App, c) {
    var gestisce = can("central.manage") && !c.limited;
    box.innerHTML = '<p class="muted" style="margin-top:0">For a provider that looks after several companies: every PC belongs to one client, and a technician can be ' +
      "limited to the clients they look after (they see and manage only those PCs). People with no client see every client.</p>" +
      (gestisce ? '<form class="toolbar tn-form" onsubmit="return false"><label>New client<input name="name" maxlength="60" placeholder="Rossi S.r.l."></label>' +
        UI.button("Add", "data-tn-add", "btn-sm btn-primary", "check") + "</form>" : "") +
      UI.table([{ title: "Client" }, { title: "PCs" }, { title: "People limited to it" }, { title: "" }], c.tenants.map(function (t) {
        return ["<strong>" + esc(t.name) + "</strong>" + (t.notes ? '<div class="cell-sub">' + esc(t.notes) + "</div>" : ""), Components.num(t.agents),
          esc(t.users.join(", ") || "—"),
          gestisce ? '<button class="btn btn-sm" data-tn-move="' + esc(t.id) + '">Add PCs</button> <button class="btn btn-sm btn-ghost" data-tn-del="' + esc(t.id) + '">Delete</button>' : ""];
      }), "No client yet: every PC belongs to this company.") +
      (gestisce && c.tenants.length ? "<h3>Who sees which clients</h3>" +
        '<form class="form tn-access" onsubmit="return false"><label>User name<input name="username" maxlength="64"></label><div class="check-list">' +
        c.tenants.map(function (t) { return '<label class="check"><input type="checkbox" value="' + esc(t.id) + '"> ' + esc(t.name) + "</label>"; }).join("") + "</div>" +
        UI.button("Save access", "data-tn-access", "btn-sm btn-primary", "check") + "</form>" : "");
    box.onclick = function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-tn-add")) API.post("/central/tenants", { name: box.querySelector(".tn-form").name.value.trim() }).then(function () { App.render(); }, fail);
      if (b.getAttribute("data-tn-del")) UI.confirm("Delete the client", "Only a client without PCs can be deleted.", { ok: "Delete" })
        .then(function (ok) { if (ok) return API.del("/central/tenants/" + b.getAttribute("data-tn-del")).then(function () { App.render(); }); }).catch(fail);
      if (b.getAttribute("data-tn-move")) {
        var id = b.getAttribute("data-tn-move");
        UI.modal("Add PCs to the client", '<select multiple size="10" class="tn-pcs" style="width:100%">' + c.agents.map(function (a) {
          return '<option value="' + esc(a.id) + '">' + esc(a.hostname + (a.tenant_name ? " (" + a.tenant_name + ")" : "")) + "</option>"; }).join("") + "</select>",
        [{ label: "Cancel", cls: "btn-ghost" }, { label: "Move", cls: "btn-primary", value: function (w) {
          return Array.prototype.map.call(w.querySelector(".tn-pcs").selectedOptions, function (o) { return o.value; }); } }])
          .then(function (ids) { if (ids && ids.length) return API.post("/central/tenants/move", { agents: ids, tenant: id }).then(function (r) { UI.toast(r.moved + " PCs moved.", "ok"); App.render(); }); })
          .catch(fail);
      }
      if (b.hasAttribute("data-tn-access")) {
        var f = box.querySelector(".tn-access");
        var scelti = Array.prototype.filter.call(f.querySelectorAll("input[type=checkbox]"), function (x) { return x.checked; }).map(function (x) { return x.value; });
        API.put("/central/tenants/access", { username: f.username.value.trim(), tenants: scelti }).then(function (r) {
          UI.toast(r.tenants.length ? r.username + " now sees " + r.tenants.length + " clients." : r.username + " sees every client.", "ok"); App.render(); }, fail);
      }
    };
  }

  // 2.11: back up the central server, restore it on another PC, and move the PCs to the new address
  function move(box, App, c) {
    if (c.limited || !can("central.manage")) { box.innerHTML = '<div class="callout callout-info">' + UI.icon("shield") + "<div>Only the provider's staff: backups and moving the server concern every client.</div></div>"; return; }
    box.innerHTML = '<p class="muted" style="margin-top:0">The backup holds the PCs, jobs, groups, assets, catalog, rings, clients and the certificate of the server: ' +
      "restored on another PC, the PCs keep trusting it and do not need to enroll again. It is encrypted with the password: without it nobody can read it, not even you.</p>" +
      "<h3>1. Tell the PCs the new address</h3>" +
      '<p class="muted">Before switching off this server: the PCs will call the new PC from their next contact (only a server with this certificate is accepted there).</p>' +
      '<form class="toolbar mv-reloc" onsubmit="return false"><label>New address (name or IP)<input name="host" maxlength="253"></label>' +
      '<label>Port<input name="port" type="number" min="1024" max="65535" value="' + c.server.port + '" style="max-width:110px"></label>' +
      UI.button("Send to every PC", "data-mv-reloc", "btn-sm", "play") + "</form>" +
      "<h3>2. Back up</h3>" +
      '<form class="toolbar mv-bk" onsubmit="return false"><label>Password (at least 12 characters)<input name="p1" type="password" autocomplete="new-password"></label>' +
      '<label>Repeat it<input name="p2" type="password" autocomplete="new-password"></label>' + UI.button("Download the backup", "data-mv-bk", "btn-sm btn-primary", "download") + "</form>" +
      "<h3>3. Restore on this PC</h3>" +
      '<p class="muted">Replaces the central server of this PC. What it replaces is kept in dati\\db-backups and dati\\tls.</p>' +
      '<form class="toolbar mv-rs" onsubmit="return false"><label>Backup file<input name="file" type="file" accept=".wmmcentral"></label>' +
      '<label>Password<input name="p" type="password" autocomplete="off"></label>' + UI.button("Check and restore", "data-mv-rs", "btn-sm", "refresh") + "</form>";
    function leggi(file) {
      return new Promise(function (ok, ko) {
        var r = new FileReader();
        r.onload = function () { ok(String(r.result).split(",")[1] || ""); };
        r.onerror = function () { ko(new Error("The file cannot be read.")); };
        r.readAsDataURL(file);
      });
    }
    box.onclick = function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-mv-reloc")) {
        var f = box.querySelector(".mv-reloc");
        var dati = { kind: "relocate", payload: { host: f.host.value.trim(), port: Number(f.port.value) }, agents: c.agents.map(function (a) { return a.id; }) };
        UI.confirm("Move the PCs", "Every PC will call " + dati.payload.host + ":" + dati.payload.port + " from its next contact. Restore the backup there before switching this server off.", { ok: "Send" })
          .then(function (ok) { if (ok) return API.post("/central/jobs", dati).then(function (r) { UI.toast(r.queued + " PCs will move at their next contact.", "ok"); watchBatch(App, r.batch); }); })
          .catch(fail);
      }
      if (b.hasAttribute("data-mv-bk")) {
        var k = box.querySelector(".mv-bk");
        if (k.p1.value !== k.p2.value) { UI.toast("The two passwords are different.", "error"); return; }
        b.disabled = true;
        API.download("/central/backup", "wmm-central.wmmcentral", { password: k.p1.value }).then(function () { b.disabled = false; UI.toast("Backup downloaded: keep it with the password in a safe place.", "ok"); },
          function (er) { b.disabled = false; fail(er); });
      }
      if (b.hasAttribute("data-mv-rs")) {
        var r = box.querySelector(".mv-rs");
        if (!r.file.files[0]) { UI.toast("Choose the backup file.", "error"); return; }
        b.disabled = true;
        leggi(r.file.files[0]).then(function (bundle) {
          return API.post("/central/backup/inspect", { bundle: bundle, password: r.p.value }).then(function (info) {
            return UI.confirm("Restore the central server", "Backup of " + info.source + " (" + when(info.created) + "): " + info.agents + " PCs, " + info.tenants +
              " clients, certificate " + info.fingerprint.slice(0, 23) + "…. The central server of this PC is replaced.", { ok: "Restore" }).then(function (ok) {
              if (ok) return API.post("/central/restore", { bundle: bundle, password: r.p.value, confirm: true }).then(function (x) { UI.toast("Restored: " + x.agents + " PCs.", "ok"); App.render(); });
            });
          });
        }).then(function () { b.disabled = false; }, function (er) { b.disabled = false; fail(er); });
      }
    };
  }
  function sendJob(App, c) {
    var strumenti = pickTools(App, function (a) { return a.allowed !== false && a.id.indexOf("custom.") !== 0; });
    var body = '<form class="form" onsubmit="return false"><label>What<select class="job-kind"><option value="actions">Run tools</option><option value="winget">Install or update software</option>' +
      '<option value="baseline">Check a baseline</option><option value="inventory">Read the inventory now</option></select></label>' +
      '<div class="jk jk-actions"><select multiple size="8" class="job-tools" style="width:100%">' + strumenti.map(function (a) {
        return '<option value="' + esc(a.id) + '">' + esc(a.title) + (a.kind === "report" ? " (report)" : " (fix)") + "</option>"; }).join("") + "</select></div>" +
      '<div class="jk jk-winget" hidden><select class="job-op"><option value="install">Install</option><option value="upgrade">Update</option><option value="uninstall">Remove</option></select>' +
      '<select class="job-app">' + c.catalog.map(function (s) { return '<option value="' + esc(s.winget_id) + '">' + esc(s.name) + "</option>"; }).join("") + "</select></div>" +
      '<div class="jk jk-baseline" hidden><select class="job-base"></select><label class="check"><input type="checkbox" class="job-fix"> Also fix what fails</label></div>' + targetPicker(c) + "</form>";
    var shown = UI.modal("Send a job", body, [{ label: "Cancel", cls: "btn-ghost" }, { label: "Send", cls: "btn-primary", value: function (w) {
      var tipo = w.querySelector(".job-kind").value, carico = {};
      if (tipo === "actions") carico.actions = Array.prototype.map.call(w.querySelector(".job-tools").selectedOptions, function (o) { return o.value; }).slice(0, 20);
      if (tipo === "winget") carico = { op: w.querySelector(".job-op").value, id: w.querySelector(".job-app").value };
      if (tipo === "baseline") { var b = w._baselines.filter(function (x) { return x.id === w.querySelector(".job-base").value; })[0]; carico = { checks: b ? b.checks : [], fix: w.querySelector(".job-fix").checked }; }
      return Object.assign({ kind: tipo, payload: carico }, readTarget(w));
    } }]);
    var all = document.querySelectorAll("#modal-root .modal"), w = all[all.length - 1];
    API.get("/baselines").then(function (d) { w._baselines = d.baselines; w.querySelector(".job-base").innerHTML = d.baselines.map(function (b) { return '<option value="' + esc(b.id) + '">' + esc(b.name) + "</option>"; }).join(""); });
    w.querySelector(".job-kind").addEventListener("change", function (e) { w.querySelectorAll(".jk").forEach(function (x) { x.hidden = !x.classList.contains("jk-" + e.target.value); }); });
    shown.then(function (d) { if (d) return API.post("/central/jobs", d).then(function (r) { UI.toast(r.queued + " PCs will run it at their next contact.", "ok"); watchBatch(App, r.batch); }); }).catch(fail);
  }
  function agentDetails(App, id, c) {
    API.get("/central/agents/" + id).then(function (a) {
      var hw = (a.inventory || {}).hardware || {}, s = a.asset || {};
      var corpo = UI.definition([["Model", esc([hw.manufacturer, hw.model].filter(Boolean).join(" ") || "—")], ["Serial", '<span class="cell-mono">' + esc(hw.serial || "—") + "</span>"],
        ["Processor", esc(hw.cpu || "—")], ["Memory", esc(hw.ram_gb ? hw.ram_gb + " GB" : "—")], ["Windows", esc((hw.os || "—") + " " + (hw.build || ""))],
        ["Disks", esc((hw.disks || []).map(function (d) { return d.model + " " + d.size_gb + " GB (" + d.health + ")"; }).join(", ") || "—")],
        ["Programs", esc(String(((a.inventory || {}).software || []).length))], ["Inventory read", esc(when(a.inventory_at))]]) +
        '<h3>Asset</h3><form class="form asset-form" onsubmit="return false"><div class="form-row"><label>Asset tag<input name="asset_tag" value="' + esc(s.asset_tag || "") + '"></label>' +
        '<label>Assigned to<input name="owner" value="' + esc(s.owner || "") + '"></label><label>Location<input name="location" value="' + esc(s.location || "") + '"></label></div>' +
        '<div class="form-row"><label>Purchased<input type="date" name="purchased" value="' + esc(s.purchased || "") + '"></label><label>Warranty until<input type="date" name="warranty_until" value="' + esc(s.warranty_until || "") + '"></label></div>' +
        '<label>Licenses<textarea name="licenses" rows="2">' + esc(s.licenses || "") + '</textarea></label><label>Groups (comma separated)<input name="tags" value="' + esc(a.tags.join(", ")) + '"></label></form>' +
        "<h3>Latest jobs</h3>" + UI.table([{ title: "When" }, { title: "Kind" }, { title: "State" }, { title: "By" }], a.jobs.slice(0, 15).map(function (j) {
          return [esc(when(j.created)), esc(j.kind), esc(j.status), esc(j.created_by)]; }), "No job yet.");
      var bottoni = [{ label: "Close", cls: "btn-ghost" }];
      if (can("central.manage")) {
        bottoni.push({ label: "Remove from the server", cls: "btn-ghost", value: function () { return "remove"; } });
        bottoni.push({ label: "Save", cls: "btn-primary", value: function (w) { var f = w.querySelector(".asset-form"); var v = {};
          ["asset_tag", "owner", "location", "purchased", "warranty_until", "licenses"].forEach(function (k) { v[k] = f[k].value; });
          return { asset: v, tags: f.tags.value.split(",").map(function (x) { return x.trim(); }).filter(Boolean) }; } });
      }
      UI.modal(a.hostname, corpo, bottoni).then(function (v) {
        if (v === "remove") return UI.confirm("Remove " + a.hostname, "The PC leaves the central server with its jobs; it can enroll again with a new code.", { ok: "Remove" })
          .then(function (ok) { if (ok) return API.del("/central/agents/" + id).then(function () { App.render(); }); });
        if (v && v.asset) return Promise.all([API.put("/central/agents/" + id + "/asset", v.asset), API.put("/central/agents/" + id + "/tags", { tags: v.tags })])
          .then(function () { UI.toast("Saved.", "ok"); App.render(); });
      }).catch(fail);
      var all = document.querySelectorAll("#modal-root .modal"); if (all.length) all[all.length - 1].classList.add("modal-wide");
    }, fail);
  }

  // ---------- inventory, software, updates ----------
  function inventory(box) {
    box.innerHTML = '<div class="toolbar"><label class="dt-search">' + UI.icon("search") + '<input type="search" class="sw-q" placeholder="Program or publisher…"></label>' +
      '<span class="grow"></span>' + UI.button("Inventory CSV", "data-inv-csv", "btn-sm", "download") + '</div><div class="sw-out"></div>';
    function cerca() {
      API.get("/central/software?q=" + encodeURIComponent(box.querySelector(".sw-q").value)).then(function (d) {
        box.querySelector(".sw-out").innerHTML = '<p class="cell-sub">' + esc(d.software.length + " installations") + "</p>" +
          UI.table([{ title: "PC" }, { title: "Program" }, { title: "Version" }, { title: "Publisher" }], d.software.slice(0, 500).map(function (s) {
            return [esc(s.hostname), esc(s.name), '<span class="cell-mono">' + esc(s.version || "") + "</span>", esc(s.publisher || "")]; }), "Nothing found.");
      }, fail);
    }
    box.querySelector(".sw-q").addEventListener("change", cerca);
    box.onclick = function (e) { if (e.target.closest("[data-inv-csv]")) API.download("/central/inventory.csv", "wmm-inventory.csv").catch(fail); };
    cerca();
  }
  function software(box, App, c) {
    box.innerHTML = '<p class="muted" style="margin-top:0">The company catalog: programs that can be installed or updated on the PCs with winget (IDs like Mozilla.Firefox).</p>' +
      (can("deploy.manage") ? '<form class="form-row cat-form" onsubmit="return false"><input name="winget_id" placeholder="winget ID (e.g. 7zip.7zip)"><input name="name" placeholder="Name">' +
        '<label class="check"><input type="checkbox" name="required"> Required on every PC</label>' + UI.button("Add", "data-cat-add", "btn-sm btn-primary", "check") + "</form>" : "") +
      UI.table([{ title: "Program" }, { title: "winget ID" }, { title: "" }], c.catalog.map(function (s) {
        return ["<strong>" + esc(s.name) + "</strong>" + (s.required ? ' <span class="badge">Required</span>' : ""), '<span class="cell-mono">' + esc(s.winget_id) + "</span>",
          (can("deploy.manage") ? '<button class="btn btn-sm" data-local="' + esc(s.winget_id) + '">Install here</button> <button class="btn btn-sm btn-ghost" data-cat-del="' + esc(s.id) + '">' + UI.icon("trash") + "</button>" : "")];
      }), "The catalog is empty.");
    box.onclick = function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-cat-add")) { var f = box.querySelector(".cat-form"); API.post("/central/catalog", { winget_id: f.winget_id.value.trim(), name: f.name.value, required: f.required.checked }).then(function () { App.render(); }, fail); }
      if (b.getAttribute("data-cat-del")) API.del("/central/catalog/" + b.getAttribute("data-cat-del")).then(function () { App.render(); }, fail);
      if (b.getAttribute("data-local")) { b.disabled = true; UI.toast("Installing with winget: it can take a few minutes.", "info");
        API.post("/software/winget", { op: "install", id: b.getAttribute("data-local") }).then(function (r) { UI.toast(r.ok ? "Done." : "winget: " + r.output.slice(-200), r.ok ? "ok" : "warning"); b.disabled = false; }, function (er) { fail(er); b.disabled = false; }); }
    };
  }
  function updates(box, App, c) {
    box.innerHTML = '<p class="muted" style="margin-top:0">A ring delays quality and feature updates, can keep a Windows version, pause updates and set active hours. ' +
      "PCs get the ring of their group at their next contact.</p>" + (can("updates.policy") ? '<form class="form-row ring-form" onsubmit="return false"><input name="name" placeholder="Ring name (e.g. Pilot)">' +
        '<input type="number" name="quality_days" min="0" max="30" value="0" title="Quality updates: days"><input type="number" name="feature_days" min="0" max="365" value="0" title="Feature updates: days">' +
        '<input name="target_version" placeholder="24H2" style="max-width:80px"><input name="active_hours" value="8-18" style="max-width:80px">' + UI.button("Add", "data-ring-add", "btn-sm btn-primary", "check") + "</form>" : "") +
      UI.table([{ title: "Ring" }, { title: "Quality" }, { title: "Feature" }, { title: "Version" }, { title: "Active hours" }, { title: "PCs" }, { title: "" }], c.rings.map(function (r) {
        return ["<strong>" + esc(r.name) + "</strong>", esc(r.quality_days + " d"), esc(r.feature_days + " d"), esc(r.target_version || "latest"), esc(r.active_hours), esc(String(r.members)),
          can("updates.policy") ? '<button class="btn btn-sm" data-assign="' + esc(r.id) + '">Assign</button> <button class="btn btn-sm btn-ghost" data-ring-del="' + esc(r.id) + '">' + UI.icon("trash") + "</button>" : ""];
      }), "No ring yet.") + '<h3>This PC</h3><div class="upd-local">' + UI.button("Read the update compliance", "data-upd", "btn-sm", "refresh") + "</div>";
    box.onclick = function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-ring-add")) { var f = box.querySelector(".ring-form");
        API.post("/central/rings", { name: f.name.value, quality_days: Number(f.quality_days.value), feature_days: Number(f.feature_days.value), target_version: f.target_version.value, active_hours: f.active_hours.value })
          .then(function () { App.render(); }, fail); }
      if (b.getAttribute("data-ring-del")) API.del("/central/rings/" + b.getAttribute("data-ring-del")).then(function () { App.render(); }, fail);
      if (b.getAttribute("data-assign")) { var ring = b.getAttribute("data-assign");
        UI.modal("Assign the ring", '<form class="form" onsubmit="return false">' + targetPicker(c) + "</form>", [{ label: "Cancel", cls: "btn-ghost" }, { label: "Assign", cls: "btn-primary", value: readTarget }])
          .then(function (t) { if (t) return API.post("/central/rings/assign", Object.assign({ ring: ring }, t)).then(function (r) { UI.toast(r.assigned + " PCs.", "ok"); App.render(); }); }).catch(fail); }
      if (b.hasAttribute("data-upd")) { b.disabled = true; API.get("/updates/compliance").then(function (u) {
        box.querySelector(".upd-local").innerHTML = '<p>' + (u.compliant ? UI.statusIcon("ok") : UI.statusIcon("warning")) + " " + esc(u.pending.length + " pending, " + u.critical + " critical or important · last installed " +
          (u.days_since_last == null ? "?" : u.days_since_last) + " days ago") + "</p>" + UI.table([{ title: "Update" }, { title: "Severity" }], u.pending.slice(0, 30).map(function (x) { return [esc(x.title), esc(x.severity || "—")]; }), "Nothing pending.");
      }, function (er) { fail(er); b.disabled = false; }); }
    };
  }

  // ---------- compliance ----------
  function compliance(box, App) {
    API.get("/baselines").then(function (d) {
      box.innerHTML = '<div class="toolbar"><span class="grow muted small">A baseline is a list of checks: the result is the percentage of this PC that complies, and the fixes for what does not.</span>' +
        (can("compliance.manage") ? UI.button("New baseline", "data-base-new", "btn-sm btn-primary", "shield") : "") + "</div>" +
        UI.table([{ title: "Baseline" }, { title: "Checks" }, { title: "Last result" }, { title: "" }], d.baselines.map(function (b) {
          return ["<strong>" + esc(b.name) + '</strong><div class="cell-sub">' + esc(b.description || "") + "</div>", esc(String(b.checks.length)),
            b.last ? score(b.last.percent) + ' <span class="cell-sub">' + esc(when(b.last.checked)) + "</span>" : "—",
            '<button class="btn btn-sm" data-base-run="' + esc(b.id) + '">Check</button>' + (can("compliance.manage") ? ' <button class="btn btn-sm" data-base-fix="' + esc(b.id) + '">Fix</button>' +
              (b.builtin ? "" : ' <button class="btn btn-sm btn-ghost" data-base-del="' + esc(b.id) + '">' + UI.icon("trash") + "</button>") : "")];
        })) + '<div class="base-out"></div>';
      box.onclick = function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        if (b.getAttribute("data-base-run")) { b.disabled = true; API.post("/baselines/" + b.getAttribute("data-base-run") + "/run").then(function (r) {
          box.querySelector(".base-out").innerHTML = "<h3>" + esc(r.baseline + " · " + r.percent + "%") + "</h3>" + UI.table([{ title: "Check" }, { title: "Value" }, { title: "" }], r.checks.map(function (x) {
            return [esc(x.label), '<span class="cell-mono">' + esc(x.value == null ? "—" : x.value) + "</span>", x.ok == null ? "—" : x.ok ? UI.statusIcon("ok") : UI.statusIcon("error")]; }));
          b.disabled = false; }, function (er) { fail(er); b.disabled = false; }); }
        if (b.getAttribute("data-base-fix")) API.post("/baselines/" + b.getAttribute("data-base-fix") + "/fix", {}).then(function (r) {
          if (r.nothing) UI.toast("Everything complies.", "ok"); else if (r.approval) UI.toast("Sent for approval.", "info"); else { UI.toast("Fixing " + r.actions.length + " checks.", "info"); App.render(); } }, fail);
        if (b.getAttribute("data-base-del")) API.del("/baselines/" + b.getAttribute("data-base-del")).then(function () { compliance(box, App); }, fail);
        if (b.hasAttribute("data-base-new")) UI.modal("New baseline", '<form class="form" onsubmit="return false"><label>Name<input name="name"></label><label>Description<input name="description"></label>' +
          '<div class="perm-grid" style="max-height:320px;overflow:auto">' + d.checks.map(function (c) { return '<label class="check"><input type="checkbox" data-chk="' + esc(c.id) + '"> ' + esc(c.title) + "</label>"; }).join("") + "</div></form>",
        [{ label: "Cancel", cls: "btn-ghost" }, { label: "Create", cls: "btn-primary", value: function (w) { var f = w.querySelector("form");
          return { name: f.name.value, description: f.description.value, checks: Array.prototype.map.call(w.querySelectorAll("[data-chk]:checked"), function (x) { return x.getAttribute("data-chk"); }) }; } }])
          .then(function (v) { if (v) return API.post("/baselines", v).then(function () { compliance(box, App); }); }).catch(fail);
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  // ---------- approvals, incidents, report, this PC ----------
  function approvals(box, App) {
    API.get("/approvals").then(function (d) {
      var me = Auth.me() || {};
      box.innerHTML = '<p class="muted" style="margin-top:0">' + (d.levels.length ? esc("Runs with " + d.levels.join(" and ") + " tools need a second person.") :
        "No approval is required now (Settings › Runs and safety).") + "</p>" + UI.table([{ title: "Requested" }, { title: "By" }, { title: "Tools" }, { title: "Reason" }, { title: "State" }, { title: "" }],
        d.approvals.map(function (a) {
          return [esc(when(a.created)), esc(a.requester), esc(a.actions.map(function (x) { return (App.state.actions[x] || { title: x }).title; }).join(", ")), esc(a.reason || "—"),
            esc(a.status) + (a.decided_by ? '<div class="cell-sub">' + esc(a.decided_by + " · " + when(a.decided_at)) + "</div>" : ""),
            a.status === "pending" && can("approvals.decide") && a.requester_id !== me.id ? '<button class="btn btn-sm btn-primary" data-ap="' + a.id + '|approve">Approve</button> <button class="btn btn-sm btn-ghost" data-ap="' + a.id + '|reject">Reject</button>' : ""];
        }), "No request.");
      box.onclick = function (e) { var b = e.target.closest("[data-ap]"); if (!b) return; var p = b.getAttribute("data-ap").split("|");
        API.post("/approvals/" + p[0] + "/" + p[1], {}).then(function () { UI.toast(p[1] === "approve" ? "Approved: the run starts." : "Rejected.", "ok"); approvals(box, App); }, fail); };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }
  function incidentsTab(box) {
    API.get("/incidents").then(function (d) {
      box.innerHTML = UI.table([{ title: "When" }, { title: "Alert" }, { title: "State" }, { title: "Ticket" }, { title: "" }], d.incidents.map(function (i) {
        return [esc(when(i.at)), "<strong>" + esc(i.title) + '</strong><div class="cell-sub">' + esc(i.text.slice(0, 160)) + "</div>",
          esc(i.status) + (i.by ? '<div class="cell-sub">' + esc(i.by) + "</div>" : "") + (i.escalated_at ? ' <span class="badge badge-status-warning">Escalated</span>' : ""),
          '<span class="cell-mono">' + esc(i.ticket || "—") + "</span>",
          can("incidents.manage") ? (i.status === "open" ? '<button class="btn btn-sm btn-primary" data-inc="' + i.id + '|ack">Take it</button> ' : "") +
            (i.status !== "closed" ? '<button class="btn btn-sm" data-inc="' + i.id + '|close">Close</button>' : '<button class="btn btn-sm btn-ghost" data-inc="' + i.id + '|reopen">Reopen</button>') : ""];
      }), "No incident: alerts appear here when they are sent.");
      box.onclick = function (e) { var b = e.target.closest("[data-inc]"); if (!b) return; var p = b.getAttribute("data-inc").split("|");
        var passo = p[1] === "close" ? UI.modal("Close the incident", '<form class="form" onsubmit="return false"><label>What was done<textarea name="n" rows="3"></textarea></label></form>',
          [{ label: "Cancel", cls: "btn-ghost" }, { label: "Close it", cls: "btn-primary", value: function (w) { return w.querySelector("[name=n]").value || " "; } }]) : Promise.resolve("");
        passo.then(function (nota) { if (nota === undefined || nota === null) return; return API.post("/incidents/" + p[0] + "/" + p[1], { note: nota }).then(function () { incidentsTab(box); }); }).catch(fail); };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }
  function report(box) {
    box.innerHTML = '<p class="muted" style="margin-top:0">A PDF for the management or the customer: health, work done, incidents, updates, compliance and what needs attention. ' +
      "With PCs on the central server it covers all of them, otherwise this PC.</p>" +
      '<div class="form-row"><label>Language<select class="rp-lang"><option value="it">Italiano</option><option value="en">English</option></select></label>' +
      '<label>Days<select class="rp-days"><option>30</option><option>90</option><option>365</option></select></label>' + UI.button("Download the PDF", "data-rp", "btn-primary", "download") + "</div>";
    box.onclick = function (e) { if (e.target.closest("[data-rp]")) API.download("/reports/executive.pdf?lang=" + box.querySelector(".rp-lang").value + "&days=" + box.querySelector(".rp-days").value,
      "wmm-executive-report.pdf").catch(fail); };
  }
  function thisPc(box) {
    API.get("/central/client").then(function (s) {
      box.innerHTML = s.enrolled ? UI.definition([["Central server", '<span class="cell-mono">' + esc(s.server + ":" + s.port) + "</span>"],
        ["Certificate", '<span class="cell-mono">' + esc(s.fingerprint.slice(0, 29)) + "…</span>"], ["Last contact", esc(when(s.last_contact))],
        ["Problem", esc(s.last_error || "—")], ["Inventory sent", esc(when(s.inventory_at))]]) +
        '<div class="form-row"><label>What the server may run here<select class="cl-level"><option value="reports">Reports only</option><option value="safe">Reports and safe fixes</option>' +
        '<option value="all">Everything it sends (software, update rings, all fixes)</option></select></label><label>Contact every (seconds)<input type="number" class="cl-int" min="60" max="86400" value="' + s.interval + '"></label></div>' +
        '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Save", "data-cl-save", "btn-sm btn-primary", "check") + UI.button("Contact now", "data-cl-now", "btn-sm", "refresh") +
        UI.button("Leave the server", "data-cl-leave", "btn-sm btn-ghost", "x") + "</div>"
        : '<p class="modal-text">Paste the enrollment code created on the central server (Company centre › Managed PCs › Enrollment code).</p><form class="form" onsubmit="return false">' +
          '<textarea class="cl-code" rows="3" data-no-i18n placeholder="wmm://server:8770/…"></textarea></form>' + UI.button("Enroll this PC", "data-cl-enroll", "btn-primary", "shield");
      var sel = box.querySelector(".cl-level"); if (sel) sel.value = s.level;
      box.onclick = function (e) { var b = e.target.closest("button"); if (!b) return;
        if (b.hasAttribute("data-cl-enroll")) API.post("/central/client/enroll", { code: box.querySelector(".cl-code").value.trim() }).then(function () { UI.toast("Enrolled.", "ok"); thisPc(box); }, fail);
        if (b.hasAttribute("data-cl-save")) API.put("/central/client", { level: box.querySelector(".cl-level").value, interval: Number(box.querySelector(".cl-int").value) }).then(function () { UI.toast("Saved.", "ok"); }, fail);
        if (b.hasAttribute("data-cl-now")) API.post("/central/client/contact").then(function () { thisPc(box); }, function (er) { fail(er); thisPc(box); });
        if (b.hasAttribute("data-cl-leave")) UI.confirm("Leave the central server", "This PC stops contacting the server. It can enroll again with a new code.", { ok: "Leave" })
          .then(function (ok) { if (ok) return API.del("/central/client").then(function () { thisPc(box); }); }).catch(fail); };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  window.Pages.enterprise = {
    title: "Company centre",
    render: function (el, App) {
      return API.get("/central").then(function (c) {
        App.setSubtitle(c.overview.agents + " managed PCs · " + c.overview.online + " online");
        var tabs = [["pcs", "Managed PCs", "network"], ["clients", "Clients", "users"], ["inventory", "Inventory", "storage"], ["software", "Software", "download"], ["updates", "Updates", "updates"],
          ["compliance", "Compliance", "shield"], ["approvals", "Approvals", "check"], ["incidents", "Incidents", "alert"], ["report", "Executive report", "reports"], ["move", "Backup and move", "storage"], ["thispc", "This PC", "cpu"]];
        var attiva = (/[?&]tab=(\w+)/.exec(location.hash) || [])[1] || Components.store("entTab") || "pcs";
        if (!tabs.some(function (t) { return t[0] === attiva; })) attiva = "pcs";
        el.innerHTML = UI.pageHeader("Company centre", "Every PC of the company from one place: central server, inventory, software, updates, compliance and incidents", "") +
          '<div class="tabs" role="tablist">' + tabs.map(function (t) { return '<button type="button" class="tab" role="tab" data-etab="' + t[0] + '" aria-selected="' + (t[0] === attiva) + '">' + UI.icon(t[2]) + "<span>" + esc(t[1]) + "</span></button>"; }).join("") +
          '</div><div class="card"><div class="card-body" id="ent-body"></div></div>';
        function show(id) {
          Components.store("entTab", id);
          el.querySelectorAll("[data-etab]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-etab") === id)); });
          var vecchio = el.querySelector("#ent-body"), nuovo = document.createElement("div");
          nuovo.id = "ent-body"; nuovo.className = "card-body";
          vecchio.parentNode.replaceChild(nuovo, vecchio);
          ({ pcs: pcs, clients: clients, move: move, inventory: inventory, software: software, updates: updates, compliance: compliance, approvals: approvals, incidents: incidentsTab, report: report, thispc: thisPc })[id](nuovo, App, c);
        }
        el.querySelector(".tabs").addEventListener("click", function (e) { var b = e.target.closest("[data-etab]"); if (b) show(b.getAttribute("data-etab")); });
        show(attiva);
      });
    }
  };
})();
