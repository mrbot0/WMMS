/* Settings 2.9: six sections added to Settings. My account (profile, password, two-step, sessions); Accounts and
   security (turn accounts on, password, lockout and session policies, two-step for administrators, audit retention);
   E-mail, Telegram and webhook (SMTP presets, bot check, chat detection, test per channel, webhook, routing per event,
   repeat interval, quiet hours, language, subject prefix, alerts to roles, alert history); App and connections
   (organization, PC label, port, language of new users, update check, proxy, offline mode, allowed networks); Runs and
   safety (maintenance window, high-risk lock, reason for changes, confirmation with the PC name); Data and backup
   (retention, database checks, backup and restore, reset, diagnostics, history of settings changes). */
(function () {
  "use strict";
  var esc = UI.esc;
  var SECTIONS = [
    ["account", "My account", "users", "Profile, password, two-step, sessions"],
    ["security", "Accounts and security", "shield", "Sign-in, passwords, lockout, sessions"],
    ["channels", "E-mail, Telegram, webhook", "bell", "Presets, tests, routing, history"],
    ["app", "App and connections", "network", "Organization, port, proxy, offline"],
    ["runs", "Runs and safety", "play", "Maintenance window, approvals"],
    ["datamgmt", "Data and backup", "storage", "Retention, database, backup, reset"]
  ];
  var DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  function fail(e) { if (e && e.message !== "cancelled") UI.toast(e.message, "error"); }
  function check(name, on, label, hint, disabled) {
    return '<label class="check"><input type="checkbox" data-k="' + name + '"' + (on ? " checked" : "") + (disabled ? " disabled" : "") + "> " + esc(label) + "</label>" +
      (hint ? '<span class="hint">' + esc(hint) + "</span>" : "");
  }
  function num(name, value, label, min, max, hint) {
    return "<label>" + esc(label) + '<input type="number" data-n="' + name + '" min="' + min + '" max="' + max + '" value="' + esc(String(value)) + '" style="max-width:120px">' +
      (hint ? '<span class="hint">' + esc(hint) + "</span>" : "") + "</label>";
  }
  function saveApp(valori, msg) {
    return API.put("/app-settings", valori).then(function (r) { UI.toast(msg || "Saved.", "ok"); return r; }, function (e) { fail(e); throw e; });
  }
  function readOnly() { return !Auth.can("settings.edit"); }

  // ---------- my account ----------
  function account(box) {
    if (!Auth.enabled()) {
      box.innerHTML = UI.card("My account", '<p class="modal-text">Accounts are off: everyone who opens the console on this PC uses it with full rights. ' +
        "Turn them on in Accounts and security to give each person a user name and a role.</p>");
      return;
    }
    Promise.all([API.get("/auth/me"), API.get("/auth/sessions")]).then(function (r) {
      var u = r[0], s = r[1].sessions;
      box.innerHTML = UI.card("Profile", '<form class="form" data-profile onsubmit="return false">' +
          '<div class="form-row"><label>Full name<input name="display" maxlength="80" value="' + esc(u.display || "") + '"></label>' +
          '<label>Language<select name="lang"><option value="">Of the console</option><option value="it"' + (u.lang === "it" ? " selected" : "") + '>Italiano</option><option value="en"' + (u.lang === "en" ? " selected" : "") + ">English</option></select></label></div>" +
          '<div class="form-row"><label>E-mail for alerts<input name="email" type="email" value="' + esc(u.email || "") + '"></label>' +
          '<label>Telegram chat ID<input name="telegram" value="' + esc(u.telegram || "") + '"></label></div>' +
          '<p class="muted small">' + esc("User name " + u.username + " · role " + u.role + " · " + u.permissions.length + " permissions") + "</p></form>",
          UI.button("Save", "data-save-profile", "btn-sm btn-primary", "check")) +
        UI.card("Password", '<p class="muted" style="margin-top:0">' + esc("Changed " + (u.password_changed ? UI.formatDate(u.password_changed) : "never") +
          (u.password_expires ? " · expires " + UI.formatDate(u.password_expires) : "")) + "</p>", UI.button("Change password", "data-change-pw", "btn-sm", "shield")) +
        UI.card("Two-step verification", '<p class="muted" style="margin-top:0">' + (u.totp_on ? "On: signing in also needs the 6-digit code of your authenticator app." :
          "Off: add a 6-digit code from an authenticator app to the password.") + "</p>",
          u.totp_on ? UI.button("Turn off", "data-2fa-off", "btn-sm btn-ghost", "x") : UI.button("Set up", "data-2fa-on", "btn-sm btn-primary", "shield")) +
        UI.card("My sessions", UI.table([{ title: "Since" }, { title: "Last activity" }, { title: "Browser" }], s.map(function (x) {
          return [esc(UI.formatDate(x.created)) + (x.current ? ' <span class="badge badge-status-ok">This window</span>' : ""), esc(UI.formatDate(x.last_seen)), '<span class="cell-sub">' + esc(x.agent.slice(0, 70)) + "</span>"];
        })), s.length > 1 ? UI.button("Sign out the others", "data-signout-others", "btn-sm", "x") : "") +
        UI.card("Sign out", '<p class="muted" style="margin-top:0">Ends this session on this window.</p>', UI.button("Sign out", "data-sign-out", "btn-sm btn-ghost", "x"));
    }, function (e) { box.innerHTML = UI.errorBox(e); });
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-save-profile")) {
        var f = box.querySelector("[data-profile]");
        API.put("/auth/profile", { display: f.display.value, email: f.email.value, telegram: f.telegram.value, lang: f.lang.value }).then(function () { UI.toast("Profile saved.", "ok"); }, fail);
      }
      if (b.hasAttribute("data-change-pw")) API.get("/auth/state").then(function (st) { return Auth.changePassword(st, false); }).then(function () { account(box); }).catch(fail);
      if (b.hasAttribute("data-2fa-on")) API.get("/auth/state").then(function (st) { return Auth.enroll(st, false); }).then(function () { account(box); }).catch(fail);
      if (b.hasAttribute("data-2fa-off")) UI.modal("Turn off two-step verification", '<form class="form" onsubmit="return false"><label>Your password<input name="p" type="password" autocomplete="current-password"></label></form>',
        [{ label: "Cancel", cls: "btn-ghost" }, { label: "Turn off", cls: "btn-danger", value: function (w) { return w.querySelector("[name=p]").value; } }]).then(function (p) {
        if (p) return API.post("/auth/2fa/disable", { password: p }).then(function () { UI.toast("Two-step verification is off.", "ok"); account(box); });
      }).catch(fail);
      if (b.hasAttribute("data-signout-others")) API.post("/auth/sessions/signout-others").then(function (r) { UI.toast(r.signed_out + " other sessions signed out.", "ok"); account(box); }, fail);
      if (b.hasAttribute("data-sign-out")) Auth.signOut();
    });
  }

  // ---------- accounts and security ----------
  function security(box) {
    API.get("/auth/state").then(function (st) {
      if (!st.enabled) {
        box.innerHTML = UI.card("Turn accounts on", '<p class="modal-text">Create the first administrator. From then on everyone signs in with their own user name and password, ' +
          "sees only what their role allows, and every sign-in and change is recorded in the audit log.</p>" +
          '<form class="form" data-setup onsubmit="return false"><div class="form-row"><label>User name<input name="username" maxlength="32" autocapitalize="off" required></label>' +
          '<label>Full name<input name="display" maxlength="80"></label></div>' +
          '<div class="form-row"><label>Password<input name="password" type="password" autocomplete="new-password" required></label>' +
          '<label>Password again<input name="again" type="password" autocomplete="new-password" required></label></div>' +
          '<p class="muted small">' + esc("At least " + st.min_length + " characters and " + st.classes + " of: lowercase, uppercase, digits, symbols.") + "</p></form>",
          UI.button("Create the administrator and turn accounts on", "data-setup-go", "btn-sm btn-primary", "shield"));
        return;
      }
      return API.get("/auth/policy").then(function (p) {
        var ro = !Auth.can("settings.security");
        box.innerHTML = UI.card("Passwords", '<div class="form">' + num("min_length", p.min_length, "Minimum length", 8, 64) + num("classes", p.classes, "Kinds of characters required (of 4)", 1, 4, "Lowercase, uppercase, digits, symbols.") +
            num("history", p.history, "Last passwords that cannot be used again", 0, 24) + num("expiry_days", p.expiry_days, "Expire after days (0 = never)", 0, 365) + "</div>") +
          UI.card("Wrong passwords", '<div class="form">' + num("lockout_attempts", p.lockout_attempts, "Lock the account after", 3, 20, "wrong passwords in a row") +
            num("lockout_minutes", p.lockout_minutes, "For minutes", 1, 1440) + "</div>") +
          UI.card("Sessions", '<div class="form">' + num("idle_minutes", p.idle_minutes, "Sign out after minutes without activity", 5, 480) +
            num("max_hours", p.max_hours, "Sign in again after hours in any case", 1, 168) +
            '<label class="check"><input type="checkbox" data-pb="single_session"' + (p.single_session ? " checked" : "") + "> One session per user: signing in elsewhere ends the previous one</label></div>") +
          UI.card("Two-step and audit", '<div class="form"><label class="check"><input type="checkbox" data-pb="require_2fa_admins"' + (p.require_2fa_admins ? " checked" : "") +
            "> Two-step verification required for everyone who can manage users</label>" + num("audit_days", p.audit_days, "Keep the audit log for days", 30, 3650) + "</div>" +
            '<p class="muted small">Each role can also require two-step verification (Users and roles › Roles).</p>') +
          '<div class="page-actions" style="justify-content:flex-start">' + (ro ? "" : UI.button("Save the policies", "data-policy-save", "btn-primary", "check")) +
          (Auth.can("users.manage") && Auth.can("roles.manage") ? UI.button("Turn accounts off", "data-accounts-off", "btn-ghost", "x") : "") +
          '<a class="btn" href="#/users">' + UI.icon("users") + "Users and roles</a></div>";
        if (ro) box.querySelectorAll("input").forEach(function (i) { i.disabled = true; });
      });
    }).catch(function (e) { box.innerHTML = UI.errorBox(e); });
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-setup-go")) {
        var f = box.querySelector("[data-setup]");
        if (f.password.value !== f.again.value) { UI.toast("The two passwords are different.", "warning"); return; }
        API.post("/auth/setup", { username: f.username.value, display: f.display.value, password: f.password.value }).then(function (r) {
          API.setSession(r.token);
          UI.toast("Accounts are on: you are signed in as " + r.user.username + ".", "ok");
          setTimeout(function () { location.reload(); }, 800);
        }, fail);
      }
      if (b.hasAttribute("data-policy-save")) {
        var v = {};
        box.querySelectorAll("[data-n]").forEach(function (i) { v[i.getAttribute("data-n")] = Number(i.value); });
        box.querySelectorAll("[data-pb]").forEach(function (i) { v[i.getAttribute("data-pb")] = i.checked; });
        API.put("/auth/policy", v).then(function () { UI.toast("Policies saved.", "ok"); }, fail);
      }
      if (b.hasAttribute("data-accounts-off")) UI.modal("Turn accounts off", '<p class="modal-text">Everyone who opens the console will have full rights again and every session ends. Users and roles are kept for when you turn accounts on again.</p>' +
        '<form class="form" onsubmit="return false"><label>Your password<input name="p" type="password"></label></form>',
        [{ label: "Cancel", cls: "btn-ghost" }, { label: "Turn off", cls: "btn-danger", value: function (w) { return w.querySelector("[name=p]").value; } }]).then(function (p) {
        if (p) return API.post("/auth/disable", { password: p }).then(function () { API.setSession(""); location.reload(); });
      }).catch(fail);
    });
  }

  // ---------- e-mail, telegram, webhook ----------
  function channels(box) {
    Promise.all([API.get("/app-settings"), API.get("/notifications"), API.get("/notifications/log")]).then(function (r) {
      var s = r[0].values, meta = r[0], n = r[1], log = r[2].entries, ro = !Auth.can("notifications.manage");
      var eventi = Object.keys(meta.events);
      var rotte = eventi.map(function (ev) {
        var scelti = s.alert_routes[ev];
        return ["<strong>" + esc(meta.events[ev]) + "</strong>"].concat(meta.channels.map(function (c) {
          return '<input type="checkbox" data-route="' + ev + "|" + c + '"' + (!scelti || scelti.indexOf(c) >= 0 ? " checked" : "") + (ro ? " disabled" : "") + ' aria-label="' + esc(c) + '">';
        }));
      });
      box.innerHTML =
        UI.card("E-mail: provider presets", '<p class="muted" style="margin-top:0">Fills the server and port of the e-mail settings above for your provider.</p>' +
          '<div class="form-row"><select data-preset style="max-width:320px"><option value="">Choose a provider…</option>' + meta.presets.map(function (p) { return '<option value="' + p.id + '">' + esc(p.name) + "</option>"; }).join("") + "</select>" +
          UI.button("Apply", "data-preset-apply", "btn-sm", "check") + '</div><p class="muted small preset-note"></p>') +
        UI.card("Telegram", '<p class="muted" style="margin-top:0">Check the bot of the token saved above, or find the chat ID: send any message to the bot from Telegram, then press Find my chat.</p>' +
          '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Check the bot", "data-tg-bot", "btn-sm", "check") + UI.button("Find my chat", "data-tg-chats", "btn-sm", "search") + "</div><div class=\"tg-out\"></div>") +
        UI.card("Test each channel", '<p class="muted" style="margin-top:0">' + esc("Channels set up: " + (n.channels.length ? n.channels.join(", ") : "none")) + "</p>" +
          '<div class="page-actions" style="justify-content:flex-start">' + ["email", "telegram", "webhook"].map(function (c) {
            return UI.button("Test " + c, 'data-test-ch="' + c + '"' + (n.channels.indexOf(c) < 0 ? " disabled" : ""), "btn-sm", "bell"); }).join("") + "</div>") +
        UI.card("Webhook (Teams, Slack, Discord or your own)", '<div class="form"><div class="form-row"><label>Address (https)<input data-s="webhook_url" value="' + esc(s.webhook_url) + '" placeholder="https://…"></label>' +
          '<label>Kind<select data-s="webhook_kind">' + meta.webhook_kinds.map(function (k) { return '<option value="' + k + '"' + (s.webhook_kind === k ? " selected" : "") + ">" + esc(k) + "</option>"; }).join("") + "</select></label></div></div>",
          UI.button("Save", "data-save-webhook", "btn-sm btn-primary", "check") + UI.button("Test", "data-webhook-test", "btn-sm", "bell")) +
        UI.card("Which channel for each alert", UI.table([{ title: "Alert" }].concat(meta.channels.map(function (c) { return { title: c }; })), rotte) +
          '<p class="muted small">An alert goes only to the ticked channels that are set up.</p>', UI.button("Save", "data-save-routes", "btn-sm btn-primary", "check")) +
        UI.card("Alert rules", '<div class="form">' +
          '<div class="form-row"><label>Language of the alerts<select data-s="alert_lang"><option value="it"' + (s.alert_lang === "it" ? " selected" : "") + '>Italiano</option><option value="en"' + (s.alert_lang === "en" ? " selected" : "") + ">English</option></select></label>" +
          '<label>Subject prefix<input data-s="alert_prefix" maxlength="60" value="' + esc(s.alert_prefix) + '" placeholder="e.g. ACME"></label></div>' +
          num("alert_repeat_hours", s.alert_repeat_hours, "Repeat the same alert after hours", 1, 168) +
          '<label class="check"><input type="checkbox" data-q="enabled"' + (s.alert_quiet.enabled ? " checked" : "") + "> Quiet hours: no alerts between</label>" +
          '<div class="form-row"><label>From<input type="time" data-q="from" value="' + esc(s.alert_quiet.from) + '"></label><label>To<input type="time" data-q="to" value="' + esc(s.alert_quiet.to) + '"></label></div>' +
          "<label>Also alert the users of these roles (at their own e-mail and Telegram)</label><div class=\"perm-grid\">" + meta.roles.map(function (rr) {
            return '<label class="check"><input type="checkbox" data-role-alert="' + esc(rr.id) + '"' + (s.alert_roles.indexOf(rr.id) >= 0 ? " checked" : "") + "> " + esc(rr.name) + "</label>"; }).join("") + "</div></div>",
          UI.button("Save", "data-save-rules", "btn-sm btn-primary", "check")) +
        UI.card("Alert history", UI.table([{ title: "When" }, { title: "Alert" }, { title: "Result" }], log.slice(0, 40).map(function (x) {
          var esiti = Object.keys(x.results || {}).map(function (k) { return k + ": " + x.results[k]; }).join(" · ");
          return [esc(UI.formatDate(x.at)), "<strong>" + esc(x.title) + '</strong><div class="cell-sub cell-mono">' + esc(x.event) + "</div>", esc(x.skipped ? "Not sent: " + x.skipped : esiti || "—")];
        }), "No alert sent yet."), log.length ? UI.button("Clear", "data-log-clear", "btn-sm btn-ghost", "trash") : "");
      if (ro) box.querySelectorAll("input, select, [data-save-webhook], [data-save-routes], [data-save-rules], [data-preset-apply]").forEach(function (i) { i.disabled = true; });
      box.addEventListener("change", function (e) {
        if (e.target.hasAttribute("data-preset")) {
          var p = meta.presets.filter(function (x) { return x.id === e.target.value; })[0];
          box.querySelector(".preset-note").textContent = p ? p.host + ":" + p.port + (p.note ? " · " + p.note : "") : "";
        }
      });
      box.onclick = function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        var out = box.querySelector(".tg-out");
        if (b.hasAttribute("data-preset-apply")) {
          var p = meta.presets.filter(function (x) { return x.id === box.querySelector("[data-preset]").value; })[0];
          if (p) API.put("/notifications", { smtp_host: p.host, smtp_port: p.port }).then(function () { UI.toast("Server and port set: write the user name and password in the e-mail settings above.", "ok"); App.render(); }, fail);
        }
        if (b.hasAttribute("data-tg-bot")) API.post("/notifications/telegram/bot", {}).then(function (bot) { out.innerHTML = '<p class="callout callout-info">' + esc("Bot: " + bot.name + " (@" + bot.username + ")") + "</p>"; }, fail);
        if (b.hasAttribute("data-tg-chats")) API.post("/notifications/telegram/chats", {}).then(function (d) {
          out.innerHTML = d.chats.length ? UI.table([{ title: "Chat" }, { title: "ID" }, { title: "" }], d.chats.map(function (c) {
            return [esc(c.name + " (" + c.type + ")"), '<span class="cell-mono">' + esc(c.id) + "</span>", '<button class="btn btn-sm" data-use-chat="' + esc(c.id) + '">Use it</button>'];
          })) : '<p class="callout callout-warning">No message found: write to the bot from Telegram, then try again.</p>';
        }, fail);
        if (b.getAttribute("data-use-chat")) API.put("/notifications", { telegram_chat: b.getAttribute("data-use-chat") }).then(function () { UI.toast("Chat saved.", "ok"); }, fail);
        if (b.getAttribute("data-test-ch")) API.post("/notifications/test/" + b.getAttribute("data-test-ch")).then(function (r) {
          UI.toast(r.ok ? "Test sent." : "Not delivered: " + Object.keys(r.results).map(function (k) { return k + " " + r.results[k]; }).join(" · "), r.ok ? "ok" : "warning");
        }, fail);
        if (b.hasAttribute("data-save-webhook")) saveApp({ webhook_url: box.querySelector('[data-s="webhook_url"]').value, webhook_kind: box.querySelector('[data-s="webhook_kind"]').value }).catch(function () {});
        if (b.hasAttribute("data-webhook-test")) API.post("/notifications/webhook/test", { url: box.querySelector('[data-s="webhook_url"]').value, kind: box.querySelector('[data-s="webhook_kind"]').value })
          .then(function (r) { UI.toast(r.ok ? "Webhook works." : "Webhook answered: " + r.result, r.ok ? "ok" : "warning"); }, fail);
        if (b.hasAttribute("data-save-routes")) {
          var rotte = {};
          eventi.forEach(function (ev) { rotte[ev] = []; });
          box.querySelectorAll("[data-route]:checked").forEach(function (c) { var p = c.getAttribute("data-route").split("|"); rotte[p[0]].push(p[1]); });
          saveApp({ alert_routes: rotte }).catch(function () {});
        }
        if (b.hasAttribute("data-save-rules")) {
          var q = {};
          box.querySelectorAll("[data-q]").forEach(function (i) { q[i.getAttribute("data-q")] = i.type === "checkbox" ? i.checked : i.value; });
          saveApp({ alert_lang: box.querySelector('[data-s="alert_lang"]').value, alert_prefix: box.querySelector('[data-s="alert_prefix"]').value,
            alert_repeat_hours: Number(box.querySelector('[data-n="alert_repeat_hours"]').value), alert_quiet: q,
            alert_roles: Array.prototype.map.call(box.querySelectorAll("[data-role-alert]:checked"), function (c) { return c.getAttribute("data-role-alert"); }) }).catch(function () {});
        }
        if (b.hasAttribute("data-log-clear")) API.del("/notifications/log").then(function () { channels(box); }, fail);
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  // ---------- app and connections ----------
  var SERVICES = [["update_check", "Program updates (GitHub)"], ["kev", "CISA catalog of exploited vulnerabilities"], ["virustotal", "VirusTotal lookups"],
    ["assistant", "Assistant (Anthropic)"], ["telegram", "Telegram alerts"], ["webhook", "Webhook alerts"]];
  function app(box) {
    API.get("/app-settings").then(function (r) {
      var s = r.values, ro = readOnly();
      box.innerHTML = UI.card("Organization", '<div class="form"><div class="form-row"><label>Organization name<input data-s="org_name" maxlength="60" value="' + esc(s.org_name) + '"><span class="hint">On the sign-in screen and in alerts.</span></label>' +
          '<label>Name of this PC in alerts<input data-s="pc_label" maxlength="60" value="' + esc(s.pc_label) + '" placeholder="' + esc(r.hostname) + '"></label></div>' +
          '<label>Language of new users<select data-s="default_user_lang"><option value="it"' + (s.default_user_lang === "it" ? " selected" : "") + '>Italiano</option><option value="en"' + (s.default_user_lang === "en" ? " selected" : "") + ">English</option></select></label></div>") +
        UI.card("Console", '<div class="form">' + num("console_port", s.console_port, "Port of the console (0 = 8765)", 0, 65535, "Used at the next start, unless --port is given.") +
          check("update_check_on_start", s.update_check_on_start, "Check for a new version when the console opens") + "</div>") +
        UI.card("Proxy", '<div class="form"><label>Proxy for internet connections<input data-s="proxy_url" value="' + esc(s.proxy_url) + '" placeholder="http://proxy.company.local:8080"><span class="hint">Updates, catalogs, Telegram, webhooks, VirusTotal and the assistant use it. E-mail connects directly.</span></label>' +
          '<label>Exceptions<input data-s="proxy_bypass" value="' + esc(s.proxy_bypass) + '" placeholder="intranet.local, *.company.local"></label></div>') +
        UI.card("Connections to the internet", '<div class="form">' + check("offline", s.offline, "Offline mode: no connection to the internet at all", "E-mail alerts still go out.") +
          '<div class="perm-grid">' + SERVICES.map(function (x) { return check("allow_" + x[0], s["allow_" + x[0]], x[1], "", s.offline); }).join("") + "</div></div>") +
        UI.card("Allowed networks", '<div class="form"><label>Phone console and PC sharing answer only these networks<input data-s="lan_allow" value="' + esc(s.lan_allow) + '" placeholder="192.168.1.0/24, 10.0.5.0/24">' +
          '<span class="hint">Empty: every private network.</span></label></div>') +
        (ro ? "" : '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Save", "data-save-app", "btn-primary", "check") + "</div>");
      if (ro) box.querySelectorAll("input, select").forEach(function (i) { i.disabled = true; });
      box.onclick = function (e) {
        if (!e.target.closest("[data-save-app]")) return;
        var v = {};
        box.querySelectorAll("[data-s]").forEach(function (i) { v[i.getAttribute("data-s")] = i.value; });
        box.querySelectorAll("[data-k]").forEach(function (i) { v[i.getAttribute("data-k")] = i.checked; });
        v.console_port = Number(box.querySelector('[data-n="console_port"]').value) || 0;
        saveApp(v).then(function () { app(box); }, function () {});
      };
      box.onchange = function (e) { if (e.target.getAttribute("data-k") === "offline") box.querySelectorAll('[data-k^="allow_"]').forEach(function (i) { i.disabled = e.target.checked; }); };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  // ---------- runs and safety ----------
  function runs(box) {
    API.get("/app-settings").then(function (r) {
      var s = r.values, w = s.maint_window, ro = readOnly();
      box.innerHTML = UI.card("Maintenance window", '<div class="form"><label class="check"><input type="checkbox" data-w="enabled"' + (w.enabled ? " checked" : "") + "> Scheduled fixes run only in this window</label>" +
          '<div class="day-pick">' + DAYS.map(function (d, i) { return '<label class="check"><input type="checkbox" data-wd="' + i + '"' + (w.days.indexOf(i) >= 0 ? " checked" : "") + "> " + d + "</label>"; }).join("") + "</div>" +
          '<div class="form-row"><label>From<input type="time" data-w="from" value="' + esc(w.from) + '"></label><label>To<input type="time" data-w="to" value="' + esc(w.to) + '"></label></div>' +
          '<span class="hint">Read-only reports always run. A window can cross midnight (22:00–06:00).</span></div>') +
        UI.card("Safety rules for every run", '<div class="form">' +
          check("block_high_risk", s.block_high_risk, "Block high-risk tools on this PC", "No one can run them, from the console, a schedule or another PC, until this is off.") +
          check("require_reason", s.require_reason, "Ask the reason or ticket number before every change", "Recorded in the audit log with the user and the tools.") +
          check("confirm_high_with_name", s.confirm_high_with_name, "Confirm high-risk tools by typing the name of this PC", "(" + r.hostname + ")") + "</div>") +
        (ro ? "" : '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Save", "data-save-runs", "btn-primary", "check") + "</div>");
      if (ro) box.querySelectorAll("input").forEach(function (i) { i.disabled = true; });
      box.onclick = function (e) {
        if (!e.target.closest("[data-save-runs]")) return;
        var finestra = { enabled: box.querySelector('[data-w="enabled"]').checked, from: box.querySelector('[data-w="from"]').value, to: box.querySelector('[data-w="to"]').value,
          days: Array.prototype.map.call(box.querySelectorAll("[data-wd]:checked"), function (c) { return Number(c.getAttribute("data-wd")); }) };
        var v = { maint_window: finestra };
        box.querySelectorAll("[data-k]").forEach(function (i) { v[i.getAttribute("data-k")] = i.checked; });
        saveApp(v).then(function () { App.state.info.run_rules = { block_high_risk: v.block_high_risk, require_reason: v.require_reason, confirm_high_with_name: v.confirm_high_with_name }; }, function () {});
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  // ---------- data and backup ----------
  function datamgmt(box) {
    Promise.all([API.get("/app-settings"), API.get("/data/info")]).then(function (r) {
      var s = r[0].values, info = r[1], ro = readOnly(), ret = s.retention;
      box.innerHTML = UI.card("How long data is kept", '<div class="form">' + num("history_days", ret.history_days, "History of runs (days, 0 = always)", 0, 3650) +
          num("connection_days", ret.connection_days, "Connection log (days)", 0, 3650) + num("snapshots_days", ret.snapshots_days, "Copies of the configuration (days)", 0, 3650) +
          num("notify_log_days", ret.notify_log_days, "Alert history (days)", 0, 3650) + "</div>",
          (ro ? "" : UI.button("Save", "data-save-ret", "btn-sm btn-primary", "check") + UI.button("Delete old data now", "data-ret-run", "btn-sm", "trash"))) +
        UI.card("Data of this PC", '<p class="muted" style="margin-top:0">' + esc(info.folder + " · " + UI.formatBytes(info.total_bytes)) + "</p>" +
          UI.table([{ title: "File" }, { title: "Size" }, { title: "Changed" }], info.files.map(function (f) {
            return ['<span class="cell-mono">' + esc(f.name) + "</span>" + (f.files ? ' <span class="cell-sub">' + f.files + " files</span>" : ""), esc(UI.formatBytes(f.bytes)), esc(f.modified ? UI.formatDate(f.modified) : "—")];
          })), ro ? "" : UI.button("Check the databases", 'data-db="integrity"', "btn-sm", "check") + UI.button("Compact", 'data-db="compact"', "btn-sm", "storage")) +
        UI.card("Backup and restore", '<p class="muted" style="margin-top:0">The backup holds the settings of the app, alerts (without passwords or tokens), report branding, roles, account policies and your own tools. ' +
          "No history, users or secrets.</p>", (Auth.can("data.backup") ? UI.button("Download a backup", "data-backup", "btn-sm", "download") +
          UI.button("Restore from a backup", "data-restore", "btn-sm", "refresh") : "")) +
        UI.card("Reset", '<p class="muted" style="margin-top:0">Puts a group of app settings back to the defaults.</p><div class="form-row"><select data-reset-sect>' +
          [["app", "Organization and console"], ["connections", "Proxy, offline, networks"], ["runs", "Runs and safety"], ["data", "Retention"], ["alerts", "Alert rules and webhook"], ["all", "All of them"]]
            .map(function (x) { return '<option value="' + x[0] + '">' + esc(x[1]) + "</option>"; }).join("") + "</select>" + (ro ? "" : UI.button("Reset", "data-reset-go", "btn-sm btn-ghost", "refresh")) + "</div>") +
        UI.card("For support", '<p class="muted" style="margin-top:0">A file with versions, health check, data sizes and settings, without secrets or personal data.</p>',
          UI.button("Download diagnostics", "data-diag", "btn-sm", "download")) +
        (Auth.can("audit.view") ? UI.card("Who changed the settings", '<div class="settings-history">' + UI.loading("Reading the audit log…") + "</div>") : "");
      if (ro) box.querySelectorAll("input").forEach(function (i) { i.disabled = true; });
      if (Auth.can("audit.view") && Auth.enabled()) {
        Promise.all(["api.app_settings", "api.put_settings", "policy.", "api.notification_put"].map(function (a) { return API.get("/audit?limit=20&action=" + encodeURIComponent(a)); })).then(function (rr) {
          var tutte = [].concat.apply([], rr.map(function (x) { return x.entries; })).sort(function (a, b) { return b.at < a.at ? -1 : 1; }).slice(0, 30);
          box.querySelector(".settings-history").innerHTML = UI.table([{ title: "When" }, { title: "User" }, { title: "What" }], tutte.map(function (e) {
            return [esc(UI.formatDate(e.at)), esc(e.user), '<span class="cell-mono">' + esc(e.action) + "</span>"];
          }), "No settings change recorded.");
        }, function () {});
      } else if (box.querySelector(".settings-history")) {
        box.querySelector(".settings-history").innerHTML = '<p class="muted">The history of changes is recorded when accounts are on.</p>';
      }
      box.onclick = function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        if (b.hasAttribute("data-save-ret")) {
          var v = {};
          box.querySelectorAll("[data-n]").forEach(function (i) { v[i.getAttribute("data-n")] = Number(i.value); });
          saveApp({ retention: v }).catch(function () {});
        }
        if (b.hasAttribute("data-ret-run")) UI.confirm("Delete old data", "Everything older than the days set here is deleted now.", { ok: "Delete" }).then(function (ok) {
          if (ok) return API.post("/data/retention").then(function (x) { UI.toast("Deleted: " + Object.keys(x.deleted).map(function (k) { return k + " " + x.deleted[k]; }).join(", ") + ".", "ok"); datamgmt(box); });
        }).catch(fail);
        if (b.getAttribute("data-db")) API.post("/data/maintenance", { action: b.getAttribute("data-db") }).then(function (x) {
          UI.toast(x.results.map(function (y) { return y.name + ": " + y.result + (y.before !== y.after ? " (" + UI.formatBytes(y.before) + " → " + UI.formatBytes(y.after) + ")" : ""); }).join(" · "), "ok");
          datamgmt(box);
        }, fail);
        if (b.hasAttribute("data-restore")) restore();
        if (b.hasAttribute("data-backup")) API.download("/config/export", "wmm-config.json").catch(fail);
        if (b.hasAttribute("data-diag")) API.download("/diagnostics", "wmm-diagnostics.json").catch(fail);
        if (b.hasAttribute("data-reset-go")) {
          var sez = box.querySelector("[data-reset-sect]").value;
          UI.confirm("Reset", "These app settings go back to the defaults.", { ok: "Reset" }).then(function (ok) {
            if (ok) return API.post("/app-settings/reset", { section: sez }).then(function () { UI.toast("Reset.", "ok"); });
          }).catch(fail);
        }
      };
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }
  function restore() {
    UI.modal("Restore from a backup", '<input type="file" accept=".json,application/json" class="bk-file"><p class="muted small bk-info"></p>',
      [{ label: "Cancel", cls: "btn-ghost" }, { label: "Restore", cls: "btn-primary", value: function (w) { return w.querySelector(".bk-file")._data || null; } }]).then(function (dati) {
      if (!dati) return null;
      return API.post("/config/import", { data: dati }).then(function (r) { UI.toast("Restored: " + r.restored.join(", ") + ".", "ok"); });
    }).catch(fail);
    setTimeout(function () {
      var all = document.querySelectorAll("#modal-root .bk-file"), f = all[all.length - 1];
      if (f) f.addEventListener("change", function () {
        if (!f.files[0]) return;
        f.files[0].text().then(function (t) {
          try {
            f._data = JSON.parse(t);
            f.parentNode.querySelector(".bk-info").textContent = "Backup of version " + f._data.version + ", " + f._data.created + ".";
          } catch (e) { f.parentNode.querySelector(".bk-info").textContent = "Not a valid backup file."; }
        });
      });
    }, 50);
  }

  var MOUNT = { account: account, security: security, channels: channels, app: app, runs: runs, datamgmt: datamgmt };
  function visible(id) {
    if (id === "account") return Auth.enabled();
    if (id === "security") return !Auth.enabled() || Auth.can("users.view") || Auth.can("settings.security");
    return true;
  }
  window.Settings29 = {
    sections: function () { return SECTIONS.filter(function (s) { return visible(s[0]); }); },
    body: function (id) { return '<div class="stack" data-s29="' + id + '"></div>'; },
    mount: function (el) { el.querySelectorAll("[data-s29]").forEach(function (box) { MOUNT[box.getAttribute("data-s29")](box); }); }
  };
})();
