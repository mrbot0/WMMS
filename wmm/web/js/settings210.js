/* Settings 2.10: Company sign-in (Entra ID / OpenID Connect, Windows and Active Directory), Integrations (SIEM, tickets,
   escalation), Protection (HTTPS on the network, encrypted data, ransomware, background agent, approvals, automatic
   undo, audit chain) and API tokens. Added to the side menu of Settings like settings29.js. */
(function () {
  "use strict";
  var esc = UI.esc;
  var SECTIONS = [
    ["sso", "Company sign-in", "users", "Entra ID, OpenID Connect, Windows"],
    ["integrations", "Integrations", "network", "SIEM, tickets, escalation"],
    ["protection", "Protection", "shield", "HTTPS, encryption, ransomware, approvals"],
    ["tokens", "API tokens", "keyboard", "Scripts and PowerShell"]
  ];
  function fail(e) { if (e && e.message !== "cancelled") UI.toast(e.message, "error"); }
  function lines(map) { return Object.keys(map || {}).map(function (k) { return k + " = " + map[k]; }).join("\n"); }
  function parseLines(testo) {
    var m = {};
    testo.split("\n").forEach(function (r) { var p = r.split("="); if (p.length >= 2 && p[0].trim()) m[p[0].trim()] = p.slice(1).join("=").trim(); });
    return m;
  }
  function roleSelect(name, roles, current, empty) {
    return '<select name="' + name + '"><option value="">' + esc(empty) + "</option>" + roles.map(function (r) {
      return '<option value="' + esc(r.id) + '"' + (r.id === current ? " selected" : "") + ">" + esc(r.name) + "</option>"; }).join("") + "</select>";
  }

  function sso(box) {
    Promise.all([API.get("/integrations/sso"), API.get("/roles")]).then(function (r) {
      var s = r[0], roles = r[1].roles;
      box.innerHTML = UI.card("Microsoft Entra ID or OpenID Connect", '<form class="form" data-oidc onsubmit="return false">' +
          '<label class="check"><input type="checkbox" name="oidc_enabled"' + (s.oidc_enabled ? " checked" : "") + "> Sign in with the company account</label>" +
          '<label>Issuer<input name="issuer" value="' + esc(s.issuer) + '" placeholder="https://login.microsoftonline.com/<tenant>/v2.0"></label>' +
          '<div class="form-row"><label>Client ID<input name="client_id" value="' + esc(s.client_id) + '"></label><label>Client secret (optional)<input name="client_secret" type="password" placeholder="' + (s.has_secret ? "saved" : "") + '"></label></div>' +
          '<p class="cell-sub">Redirect address to register: <span class="cell-mono" data-no-i18n>' + esc(s.redirect) + "</span></p>" +
          '<div class="form-row"><label>Claim with the groups<input name="role_claim" value="' + esc(s.role_claim) + '"></label><label>Allowed domains<input name="domains" value="' + esc(s.domains) + '" placeholder="company.com"></label></div>' +
          '<label>Group → role (one per line, the first that matches wins)<textarea name="role_map" rows="4" data-no-i18n placeholder="IT-Admins = admin">' + esc(lines(s.role_map)) + "</textarea></label>" +
          '<div class="form-row"><label>Role of everyone else' + roleSelect("default_role", roles, s.default_role, "Nobody else may sign in") + "</label>" +
          '<label class="check" style="align-self:end"><input type="checkbox" name="auto_create"' + (s.auto_create ? " checked" : "") + "> Create the user at the first sign-in</label></div></form>",
          UI.button("Save", "data-save-oidc", "btn-sm btn-primary", "check")) +
        UI.card("Windows and Active Directory", '<form class="form" data-win onsubmit="return false"><label class="check"><input type="checkbox" name="windows_enabled"' + (s.windows_enabled ? " checked" : "") +
          "> Sign in with a Windows or domain account (DOMAIN\\user)</label>" +
          '<label>Windows group → role (one per line)<textarea name="windows_role_map" rows="4" data-no-i18n placeholder="Domain Admins = admin">' + esc(lines(s.windows_role_map)) + "</textarea></label>" +
          "<label>Role of everyone else" + roleSelect("windows_default_role", roles, s.windows_default_role, "Nobody else may sign in") + "</label></form>",
          UI.button("Save", "data-save-win", "btn-sm btn-primary", "check"));
      box.onclick = function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        if (b.hasAttribute("data-save-oidc")) {
          var f = box.querySelector("[data-oidc]");
          var v = { oidc_enabled: f.oidc_enabled.checked, issuer: f.issuer.value.trim(), client_id: f.client_id.value.trim(), role_claim: f.role_claim.value.trim(),
            domains: f.domains.value.trim(), role_map: parseLines(f.role_map.value), default_role: f.default_role.value, auto_create: f.auto_create.checked };
          if (f.client_secret.value) v.client_secret = f.client_secret.value;
          API.put("/integrations/sso", v).then(function () { UI.toast("Saved.", "ok"); }, fail);
        }
        if (b.hasAttribute("data-save-win")) {
          var w = box.querySelector("[data-win]");
          API.put("/integrations/sso", { windows_enabled: w.windows_enabled.checked, windows_role_map: parseLines(w.windows_role_map.value), windows_default_role: w.windows_default_role.value })
            .then(function () { UI.toast("Saved.", "ok"); }, fail);
        }
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  function integrations(box) {
    Promise.all([API.get("/integrations/siem"), API.get("/integrations/tickets"), API.get("/integrations/escalation"), API.get("/roles"), API.get("/notifications")]).then(function (r) {
      var siem = r[0], t = r[1], esc2 = r[2], roles = r[3].roles, ev = r[4].event_titles;
      box.innerHTML = UI.card("SIEM: audit log", '<form class="form" data-siem onsubmit="return false"><div class="form-row"><label>Syslog server<input name="host" value="' + esc(siem.syslog_host) + '"></label>' +
          '<label>Port<input type="number" name="port" value="' + siem.syslog_port + '" style="max-width:100px"></label><label>Protocol<select name="proto"><option value="udp"' + (siem.syslog_proto === "udp" ? " selected" : "") + '>UDP</option><option value="tcp"' + (siem.syslog_proto === "tcp" ? " selected" : "") + ">TCP</option></select></label></div>" +
          '<label class="check"><input type="checkbox" name="eventlog"' + (siem.eventlog ? " checked" : "") + "> Also write to the Windows Application log</label></form>",
          UI.button("Save", "data-save-siem", "btn-sm btn-primary", "check") + UI.button("Send a test", "data-test-siem", "btn-sm", "bell")) +
        UI.card("Tickets", '<form class="form" data-tk onsubmit="return false"><label class="check"><input type="checkbox" name="enabled"' + (t.enabled ? " checked" : "") + "> Open a ticket for the alerts ticked below</label>" +
          '<div class="form-row"><label>Service<select name="kind">' + ["jira", "servicenow", "glpi", "generic"].map(function (k) { return '<option value="' + k + '"' + (t.kind === k ? " selected" : "") + ">" + k + "</option>"; }).join("") + "</select></label>" +
          '<label>Address<input name="url" value="' + esc(t.url) + '" placeholder="https://company.atlassian.net"></label></div>' +
          '<div class="form-row"><label>User<input name="user" value="' + esc(t.user) + '"></label><label>Token or password<input name="secret" type="password" placeholder="' + (t.has_secret ? "saved" : "") + '"></label>' +
          '<label>Project (Jira) / App token (GLPI)<input name="project" value="' + esc(t.project) + '"></label></div>' +
          '<div class="perm-grid">' + Object.keys(ev).map(function (k) { return '<label class="check"><input type="checkbox" data-tev="' + k + '"' + (t.events.indexOf(k) >= 0 ? " checked" : "") + "> " + esc(ev[k]) + "</label>"; }).join("") + "</div></form>",
          UI.button("Save", "data-save-tk", "btn-sm btn-primary", "check") + UI.button("Open a test ticket", "data-test-tk", "btn-sm", "bell")) +
        UI.card("Escalation", '<form class="form" data-esc onsubmit="return false">' + '<label>If nobody takes an alert within minutes (0 = never)<input type="number" name="minutes" min="0" max="1440" value="' + esc2.minutes + '" style="max-width:120px"></label>' +
          '<div class="perm-grid">' + ["email", "telegram", "webhook"].map(function (c) { return '<label class="check"><input type="checkbox" data-ech="' + c + '"' + (esc2.channels.indexOf(c) >= 0 ? " checked" : "") + "> " + c + "</label>"; }).join("") + "</div>" +
          "<label>Also to the users of</label><div class=\"perm-grid\">" + roles.map(function (x) { return '<label class="check"><input type="checkbox" data-erole="' + esc(x.id) + '"' + (esc2.roles.indexOf(x.id) >= 0 ? " checked" : "") + "> " + esc(x.name) + "</label>"; }).join("") + "</div></form>",
          UI.button("Save", "data-save-esc", "btn-sm btn-primary", "check"));
      box.onclick = function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        if (b.hasAttribute("data-save-siem")) { var f = box.querySelector("[data-siem]");
          API.put("/integrations/siem", { syslog_host: f.host.value.trim(), syslog_port: Number(f.port.value), syslog_proto: f.proto.value, eventlog: f.eventlog.checked }).then(function () { UI.toast("Saved.", "ok"); }, fail); }
        if (b.hasAttribute("data-test-siem")) API.post("/integrations/siem/test").then(function () { UI.toast("Test sent: check the SIEM.", "ok"); }, fail);
        if (b.hasAttribute("data-save-tk")) { var k = box.querySelector("[data-tk]");
          var v = { enabled: k.enabled.checked, kind: k.kind.value, url: k.url.value.trim(), user: k.user.value, project: k.project.value,
            events: Array.prototype.map.call(box.querySelectorAll("[data-tev]:checked"), function (x) { return x.getAttribute("data-tev"); }) };
          if (k.secret.value) v.secret = k.secret.value;
          API.put("/integrations/tickets", v).then(function () { UI.toast("Saved.", "ok"); }, fail); }
        if (b.hasAttribute("data-test-tk")) API.post("/integrations/tickets/test").then(function (x) { UI.toast(x.ok ? "Ticket " + x.id + " opened." : "Not opened: " + x.error, x.ok ? "ok" : "warning"); }, fail);
        if (b.hasAttribute("data-save-esc")) API.put("/integrations/escalation", { minutes: Number(box.querySelector("[data-esc]").minutes.value),
          channels: Array.prototype.map.call(box.querySelectorAll("[data-ech]:checked"), function (x) { return x.getAttribute("data-ech"); }),
          roles: Array.prototype.map.call(box.querySelectorAll("[data-erole]:checked"), function (x) { return x.getAttribute("data-erole"); }) }).then(function () { UI.toast("Saved.", "ok"); }, fail);
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  function protection(box) {
    Promise.all([API.get("/security/tls"), API.get("/app-settings"), API.get("/security/canary"), API.get("/agent/service")]).then(function (r) {
      var tls = r[0], s = r[1].values, can = r[2], svc = r[3];
      var cfa = { on: "On", audit: "Audit only", off: "Off", unknown: "Not readable" };
      box.innerHTML = UI.card("HTTPS on the local network", '<p class="muted" style="margin-top:0">The phone console, the PC sharing and the central server answer over HTTPS with a certificate made on this PC. ' +
          "Compare the fingerprint when a phone or a PC connects the first time.</p>" + (tls.fingerprint ? '<p class="cell-mono" data-no-i18n style="word-break:break-all">' + esc(tls.fingerprint) + "</p>" : ""),
          UI.button(tls.https_lan ? "Turn off" : "Turn on", "data-tls", tls.https_lan ? "btn-sm" : "btn-sm btn-primary", "shield") + (tls.fingerprint ? UI.button("New certificate", "data-tls-new", "btn-sm btn-ghost", "refresh") : "")) +
        UI.card("Encrypted data files", '<p class="muted" style="margin-top:0">Network devices, Wi-Fi and Bluetooth, connection log, suspicious programs, alerts, paired PCs and phones are encrypted with DPAPI, ' +
          "readable only on this PC. The history databases are not: protect the disk with BitLocker.</p>", UI.button(s.encrypt_data ? "Decrypt" : "Encrypt", "data-enc", s.encrypt_data ? "btn-sm" : "btn-sm btn-primary", "shield")) +
        UI.card("Ransomware", "<p>" + esc("Controlled folder access of Defender: " + (cfa[can.cfa.mode] || can.cfa.mode)) + '</p><div class="page-actions" style="justify-content:flex-start">' +
          ["on", "audit", "off"].map(function (m) { return UI.button(cfa[m], 'data-cfa="' + m + '"', "btn-sm" + (can.cfa.mode === m ? " active" : ""), "shield"); }).join("") + "</div>" +
          (can.cfa.events.length ? UI.table([{ title: "When" }, { title: "Program" }, { title: "File" }], can.cfa.events.slice(0, 8).map(function (x) { return [esc(UI.formatDate(x.at)), esc(x.program || ""), '<span class="cell-sub">' + esc(x.path || "") + "</span>"]; })) : "") +
          "<p>" + esc(can.decoys.decoys.length ? can.decoys.decoys.length + " decoy files placed · last check " + (can.decoys.last_check ? UI.formatDate(can.decoys.last_check) : "never") : "No decoy files yet.") + "</p>",
          UI.button(can.decoys.decoys.length ? "Place them again" : "Place decoy files", "data-decoy", "btn-sm btn-primary", "shield") + (can.decoys.decoys.length ? UI.button("Remove", "data-decoy-rm", "btn-sm btn-ghost", "trash") : "") +
          UI.button("Schedule the check", 'data-schedule="security.canary_watch"', "btn-sm", "clock")) +
        UI.card("Background agent", '<p class="muted" style="margin-top:0">' + esc(svc.installed ? "Installed: the agent runs as SYSTEM from boot and restarts by itself (" + (svc.status || "") + ")." :
          "Not installed: the agent runs only while the console is open.") + "</p>", svc.installed ? UI.button("Remove", "data-svc-rm", "btn-sm btn-ghost", "x") : UI.button("Install", "data-svc", "btn-sm btn-primary", "cpu")) +
        UI.card("Approvals and automatic undo", '<div class="form"><label class="check"><input type="checkbox" data-ap="moderate"' + (s.approval_levels.indexOf("moderate") >= 0 ? " checked" : "") + "> Moderate fixes need a second person</label>" +
          '<label class="check"><input type="checkbox" data-ap="high"' + (s.approval_levels.indexOf("high") >= 0 ? " checked" : "") + "> High-risk fixes need a second person</label>" +
          '<label class="check"><input type="checkbox" data-rb' + (s.auto_rollback ? " checked" : "") + "> Undo by itself a fix whose check says it made things worse</label></div>",
          UI.button("Save", "data-save-ap", "btn-sm btn-primary", "check")) +
        UI.card("Integrity of the audit log", '<p class="muted" style="margin-top:0">Every entry is chained to the previous one: a changed or deleted entry is found here.</p><div class="chain-out"></div>',
          UI.button("Verify", "data-chain", "btn-sm", "check"));
      box.onclick = function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        if (b.hasAttribute("data-tls")) { b.disabled = true; API.put("/security/tls", { enabled: !tls.https_lan }).then(function () { protection(box); }, fail); }
        if (b.hasAttribute("data-tls-new")) API.post("/security/tls/regenerate").then(function () { UI.toast("New certificate: phones and PCs must accept the new fingerprint.", "ok"); protection(box); }, fail);
        if (b.hasAttribute("data-enc")) API.put("/security/encryption", { enabled: !s.encrypt_data }).then(function (x) { UI.toast(x.converted.length + " files converted.", "ok"); protection(box); }, fail);
        if (b.getAttribute("data-cfa")) API.put("/security/cfa", { mode: b.getAttribute("data-cfa") }).then(function () { protection(box); }, fail);
        if (b.hasAttribute("data-decoy")) API.post("/security/canary").then(function (x) { UI.toast(x.decoys.length + " decoy files placed.", "ok"); protection(box); }, fail);
        if (b.hasAttribute("data-decoy-rm")) API.del("/security/canary").then(function () { protection(box); }, fail);
        if (b.hasAttribute("data-svc")) API.post("/agent/service").then(function () { protection(box); }, fail);
        if (b.hasAttribute("data-svc-rm")) API.del("/agent/service").then(function () { protection(box); }, fail);
        if (b.hasAttribute("data-save-ap")) API.put("/app-settings", { approval_levels: Array.prototype.map.call(box.querySelectorAll("[data-ap]:checked"), function (x) { return x.getAttribute("data-ap"); }),
          auto_rollback: box.querySelector("[data-rb]").checked }).then(function () { UI.toast("Saved.", "ok"); }, fail);
        if (b.hasAttribute("data-chain")) API.get("/audit/verify").then(function (v) {
          box.querySelector(".chain-out").innerHTML = v.ok ? '<p class="callout callout-info">' + esc(v.checked + " entries verified: the chain is intact.") + "</p>"
            : '<p class="callout callout-warning">' + esc("Broken at entry " + v.broken.id + " (" + v.broken.at + "): " + v.broken.reason) + "</p>";
        }, fail);
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  function tokens(box) {
    if (!Auth.enabled()) { box.innerHTML = UI.card("API tokens", '<p class="modal-text">API tokens belong to users: turn accounts on first.</p>'); return; }
    API.get("/tokens").then(function (d) {
      box.innerHTML = UI.card("API tokens", '<p class="muted" style="margin-top:0">A token lets a script act as you, with fewer permissions if you choose, only from this PC. Use it with tools\\WMM.psm1 or any HTTP client: ' +
          '<span class="cell-mono" data-no-i18n>Authorization: Bearer wmm_…</span></p>' +
          UI.table([{ title: "Name" }, { title: "Created" }, { title: "Last used" }, { title: "Expires" }, { title: "" }], d.tokens.map(function (t) {
            return [esc(t.name) + ' <span class="cell-mono cell-sub">' + esc(t.prefix) + "…</span>" + (t.revoked ? ' <span class="badge">Revoked</span>' : ""), esc(UI.formatDate(t.created)),
              esc(t.last_used ? UI.formatDate(t.last_used) : "—"), esc(t.expires ? UI.formatDate(t.expires) : "Never"), t.revoked ? "" : '<button class="btn btn-sm btn-ghost" data-tok-del="' + esc(t.id) + '">Revoke</button>'];
          }), "No token."), UI.button("New token", "data-tok-new", "btn-sm btn-primary", "keyboard"));
      box.onclick = function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        if (b.getAttribute("data-tok-del")) API.del("/tokens/" + b.getAttribute("data-tok-del")).then(function () { tokens(box); }, fail);
        if (b.hasAttribute("data-tok-new")) UI.modal("New API token", '<form class="form" onsubmit="return false"><label>Name<input name="name" placeholder="Backup script"></label>' +
          '<label>Expires after days (0 = never)<input type="number" name="days" value="90" min="0" max="730"></label>' +
          '<label class="check"><input type="checkbox" name="ro" checked> Read-only (pages and reports, no changes)</label></form>',
          [{ label: "Cancel", cls: "btn-ghost" }, { label: "Create", cls: "btn-primary", value: function (w) { var f = w.querySelector("form");
            var me = Auth.me() || { permissions: [] };
            return { name: f.name.value, days: Number(f.days.value), scopes: f.ro.checked ? me.permissions.filter(function (p) { return /^view\.|\.report$/.test(p); }) : [] }; } }])
          .then(function (v) { if (!v) return null; return API.post("/tokens", v).then(function (t) {
            UI.modal("Your new token", '<p class="modal-text">Copy it now: it is not shown again.</p><pre class="code-block" data-no-i18n style="word-break:break-all">' + esc(t.token) + "</pre>",
              [{ label: "Copy and close", cls: "btn-primary", value: function () { return true; } }]).then(function () { App.copyText(t.token, "Token"); tokens(box); }); }); }).catch(fail);
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  var MOUNT = { sso: sso, integrations: integrations, protection: protection, tokens: tokens };
  window.Settings210 = {
    sections: function () {
      return SECTIONS.filter(function (s) {
        if (s[0] === "sso" || s[0] === "integrations") return Auth.can("integrations.manage");
        if (s[0] === "tokens") return Auth.enabled() && Auth.can("api.tokens");
        return Auth.can("view.settings");
      });
    },
    body: function (id) { return '<div class="stack" data-s210="' + id + '"></div>'; },
    mount: function (el) { el.querySelectorAll("[data-s210]").forEach(function (box) { MOUNT[box.getAttribute("data-s210")](box); }); }
  };
})();
