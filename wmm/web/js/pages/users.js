/* Users and roles (2.9): a page of its own. Users: list with search and filters, details (sessions, sign-ins, activity),
   create, edit, copy, delete, temporary password, unlock, two-step reset, sign out, access hours and expiry, bulk actions,
   CSV import and export. Roles: create from a template, edit the permission matrix (pages, tools per area and risk,
   capabilities), copy, compare, export, import, reset the built-in ones, delete with reassignment, members.
   Sessions of every user and the audit log with filters and CSV export. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var STATUS = { active: ["badge-status-ok", "Active"], disabled: ["", "Disabled"], locked: ["badge-status-error", "Locked"], expired: ["badge-status-warning", "Expired"] };
  var DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  var catalog = null;

  function badge(s) { var x = STATUS[s] || ["", s]; return '<span class="badge ' + x[0] + '">' + esc(x[1]) + "</span>"; }
  function roleBadge(r) { return '<span class="role-badge role-' + esc(r.color || "gray") + '">' + esc(r.name) + "</span>"; }
  function when(iso) { return iso ? UI.formatDate(iso) : "—"; }
  function wide() { var all = document.querySelectorAll("#modal-root .modal"); if (all.length) all[all.length - 1].classList.add("modal-wide"); }
  function fail(e) { if (e && e.message !== "cancelled") UI.toast(e.message, "error"); }
  function showSecret(title, text, password) {
    return UI.modal(title, '<p class="modal-text">' + esc(text) + '</p><pre class="code-block" data-no-i18n style="font-size:18px;text-align:center">' + esc(password) + "</pre>",
      [{ label: "Copy and close", cls: "btn-primary", value: function () { return true; } }]).then(function () { App.copyText(password, "Password"); });
  }
  function loadCatalog() { return catalog ? Promise.resolve(catalog) : API.get("/permissions").then(function (c) { catalog = c; return c; }); }

  // ---------- user editor ----------
  function userForm(u, roles, isNew) {
    u = u || { role_id: "viewer", active: true, lang: "", hours: null, expires: "" };
    var ore = u.hours || { days: [0, 1, 2, 3, 4], from: "08:00", to: "18:00" };
    return '<form class="form" data-user-form onsubmit="return false">' +
      '<div class="form-row"><label>User name<input name="username" maxlength="32" required value="' + esc(u.username || "") + '" autocapitalize="off" spellcheck="false"></label>' +
      '<label>Full name<input name="display" maxlength="80" value="' + esc(u.display || "") + '"></label></div>' +
      '<div class="form-row"><label>Role<select name="role_id">' + roles.map(function (r) {
        return '<option value="' + esc(r.id) + '"' + (r.id === u.role_id ? " selected" : "") + ">" + esc(r.name) + "</option>"; }).join("") + "</select></label>" +
      '<label>Language<select name="lang"><option value="">Of the console</option><option value="it"' + (u.lang === "it" ? " selected" : "") + '>Italiano</option>' +
      '<option value="en"' + (u.lang === "en" ? " selected" : "") + ">English</option></select></label></div>" +
      '<div class="form-row"><label>E-mail for alerts<input name="email" type="email" maxlength="200" value="' + esc(u.email || "") + '"></label>' +
      '<label>Telegram chat ID<input name="telegram" maxlength="40" value="' + esc(u.telegram || "") + '"></label></div>' +
      '<div class="form-row"><label>Account expires on<input name="expires" type="date" value="' + esc(u.expires || "") + '"></label>' +
      '<label class="check" style="align-self:end"><input type="checkbox" name="active"' + (u.active ? " checked" : "") + "> Active</label></div>" +
      '<fieldset><legend><label class="check"><input type="checkbox" name="hours_on"' + (u.hours ? " checked" : "") + "> Sign-in allowed only at these times</label></legend>" +
      '<div class="day-pick">' + DAYS.map(function (d, i) { return '<label class="check"><input type="checkbox" name="day" value="' + i + '"' + (ore.days.indexOf(i) >= 0 ? " checked" : "") + "> " + d + "</label>"; }).join("") + "</div>" +
      '<div class="form-row"><label>From<input type="time" name="from" value="' + esc(ore.from) + '"></label><label>To<input type="time" name="to" value="' + esc(ore.to) + '"></label></div></fieldset>' +
      (isNew ? '<label>Password<input name="password" type="password" autocomplete="new-password" placeholder="Leave empty for a temporary password"></label>' : "") +
      '<label class="check"><input type="checkbox" name="must_change"' + (u.must_change ? " checked" : "") + "> Change the password at the next sign-in</label>" +
      '<label>Notes<textarea name="notes" rows="2" maxlength="500">' + esc(u.notes || "") + "</textarea></label></form>";
  }
  function readUser(w, isNew) {
    var f = w.querySelector("[data-user-form]");
    var giorni = Array.prototype.map.call(f.querySelectorAll("[name=day]:checked"), function (c) { return Number(c.value); });
    var dati = { username: f.username.value.trim(), display: f.display.value, role_id: f.role_id.value, lang: f.lang.value, email: f.email.value,
      telegram: f.telegram.value, expires: f.expires.value, active: f.active.checked, must_change: f.must_change.checked, notes: f.notes.value,
      hours: f.hours_on.checked ? { days: giorni, from: f.from.value, to: f.to.value } : null };
    if (isNew && f.password.value) dati.password = f.password.value;
    return dati;
  }
  function editUser(u, roles, reload) {
    var nuovo = !u;
    return UI.modal(nuovo ? "New user" : "Edit " + u.username, userForm(u, roles, nuovo), [{ label: "Cancel", cls: "btn-ghost" },
      { label: nuovo ? "Create" : "Save", cls: "btn-primary", value: function (w) { return readUser(w, nuovo); } }]).then(function (dati) {
      if (!dati) return null;
      var richiesta = nuovo ? API.post("/users", dati) : API.put("/users/" + u.id, dati);
      return richiesta.then(function (r) {
        UI.toast(nuovo ? "User created." : "Saved.", "ok");
        reload();
        if (r.temporary_password) return showSecret("Temporary password of " + r.username, "Give it to the user: it works once and must be changed at the first sign-in. It is not shown again.", r.temporary_password);
      });
    }).catch(fail);
  }

  // ---------- user details ----------
  function details(id, roles, reload) {
    Promise.all([API.get("/users/" + id), Auth.can("audit.view") ? API.get("/users/" + id + "/activity") : Promise.resolve({ entries: [] })]).then(function (r) {
      var u = r[0], att = r[1].entries;
      var ore = u.hours ? u.hours.days.map(function (d) { return DAYS[d]; }).join(" ") + " " + u.hours.from + "–" + u.hours.to : "Any time";
      var corpo = UI.definition([["User name", '<span class="cell-mono">' + esc(u.username) + "</span>"], ["Full name", esc(u.display || "—")], ["Role", esc(u.role)],
        ["State", badge(u.status) + (u.locked_until ? ' <span class="cell-sub">until ' + esc(UI.formatDate(u.locked_until)) + "</span>" : "")],
        ["Two-step verification", u.totp_on ? "On" : "Off"], ["Access hours", esc(ore)], ["Expires", esc(u.expires || "Never")],
        ["E-mail · Telegram", esc((u.email || "—") + " · " + (u.telegram || "—"))], ["Created", esc(when(u.created))], ["Last sign-in", esc(when(u.last_login))],
        ["Password changed", esc(when(u.password_changed))], ["Notes", esc(u.notes || "—")]]) +
        "<h3>Open sessions</h3>" + UI.table([{ title: "Since" }, { title: "Last activity" }, { title: "Browser" }, { title: "" }], u.sessions.map(function (s) {
          return [esc(when(s.created)), esc(when(s.last_seen)), '<span class="cell-sub">' + esc(s.agent.slice(0, 60)) + "</span>",
            Auth.can("sessions.manage") ? '<button class="btn btn-sm btn-ghost" data-revoke="' + esc(s.id) + '">Sign out</button>' : ""];
        }), "No open session.") +
        "<h3>Latest sign-ins</h3>" + UI.table([{ title: "When" }, { title: "Result" }, { title: "Detail" }], u.logins.map(function (l) {
          return [esc(when(l.at)), l.ok ? UI.statusBadge("ok") : UI.statusBadge("error"), '<span class="cell-sub">' + esc(l.detail) + "</span>"];
        }), "Never signed in.") +
        (att.length ? "<h3>Activity</h3>" + UI.table([{ title: "When" }, { title: "Action" }, { title: "On" }], att.slice(0, 30).map(function (e) {
          return [esc(when(e.at)), '<span class="cell-mono">' + esc(e.action) + "</span>", '<span class="cell-sub">' + esc(e.target) + "</span>"];
        })) : "");
      UI.modal(u.display || u.username, corpo, [{ label: "Close", cls: "btn-ghost" }]);
      wide();
      var m = document.querySelectorAll("#modal-root .modal"), box = m[m.length - 1];
      box.addEventListener("click", function (e) {
        var b = e.target.closest("[data-revoke]");
        if (!b) return;
        API.del("/sessions/" + b.getAttribute("data-revoke")).then(function () { b.closest("tr").remove(); UI.toast("Signed out.", "ok"); }, fail);
      });
    }, fail);
  }

  // ---------- one user: the actions menu ----------
  function userAction(azione, u, roles, reload) {
    var me = Auth.me() || {};
    if (azione === "edit") return editUser(u, roles, reload);
    if (azione === "details") return details(u.id, roles, reload);
    if (azione === "copy") {
      return UI.modal("Copy " + u.username, '<p class="modal-text">The new user gets the same role, access hours, expiry and language, and a temporary password.</p>' +
        '<form class="form" onsubmit="return false"><label>New user name<input name="username" maxlength="32" required></label><label>Full name<input name="display" maxlength="80"></label></form>',
      [{ label: "Cancel", cls: "btn-ghost" }, { label: "Copy", cls: "btn-primary", value: function (w) { var f = w.querySelector("form"); return { username: f.username.value, display: f.display.value }; } }])
        .then(function (d) {
          if (!d) return null;
          return API.post("/users/" + u.id + "/copy", d).then(function (n) { reload(); return showSecret("Temporary password of " + n.username, "Give it to the user: it must be changed at the first sign-in.", n.temporary_password); });
        }).catch(fail);
    }
    if (azione === "password") {
      return UI.confirm("Temporary password", "A new temporary password replaces the current one and " + u.username + " is signed out everywhere.", { ok: "Create it" }).then(function (ok) {
        if (!ok) return null;
        return API.post("/users/" + u.id + "/password").then(function (r) { reload(); return showSecret("Temporary password of " + u.username, "It works once and must be changed at the next sign-in.", r.temporary_password); });
      }).catch(fail);
    }
    var semplici = { unlock: ["/unlock", "Unlocked."], twostep: ["/2fa-reset", "Two-step verification reset: it is set up again at the next sign-in if the role requires it."],
      signout: ["/signout", "Signed out of every session."] };
    if (semplici[azione]) return API.post("/users/" + u.id + semplici[azione][0]).then(function () { UI.toast(semplici[azione][1], "ok"); reload(); }, fail);
    if (azione === "toggle") return API.put("/users/" + u.id, { active: !u.active }).then(function () { UI.toast(u.active ? "Disabled." : "Enabled.", "ok"); reload(); }, fail);
    if (azione === "delete") {
      if (u.id === me.id) { UI.toast("You cannot delete yourself.", "warning"); return null; }
      return UI.confirm("Delete " + u.username, "The account and its sessions are deleted. Its actions stay in the audit log.", { ok: "Delete", danger: true }).then(function (ok) {
        if (ok) return API.del("/users/" + u.id).then(function () { UI.toast("Deleted.", "ok"); reload(); });
      }).catch(fail);
    }
    return null;
  }
  function menuFor(u) {
    var gestisci = Auth.can("users.manage");
    var voci = [["details", "Details"]];
    if (gestisci) voci = voci.concat([["edit", "Edit"], ["copy", "Copy"], ["password", "Temporary password"], ["toggle", u.active ? "Disable" : "Enable"]]);
    if (gestisci && u.locked) voci.push(["unlock", "Unlock"]);
    if (gestisci && u.totp_on) voci.push(["twostep", "Reset two-step"]);
    if (Auth.can("sessions.manage") && u.sessions) voci.push(["signout", "Sign out"]);
    if (gestisci) voci.push(["delete", "Delete"]);
    return '<select class="user-act" data-user="' + esc(u.id) + '" aria-label="Actions"><option value="">Actions…</option>' +
      voci.map(function (v) { return '<option value="' + v[0] + '">' + esc(v[1]) + "</option>"; }).join("") + "</select>";
  }

  // ---------- users tab ----------
  function usersTab(box, App) {
    var filtro = { q: "", role: "", status: "" }, dati = null, scelti = {};
    function reload() {
      var qs = Object.keys(filtro).filter(function (k) { return filtro[k]; }).map(function (k) { return k + "=" + encodeURIComponent(filtro[k]); }).join("&");
      return API.get("/users" + (qs ? "?" + qs : "")).then(function (d) { dati = d; draw(); }, function (e) { box.innerHTML = UI.errorBox(e); });
    }
    function draw() {
      var gestisci = Auth.can("users.manage");
      var righe = dati.users.map(function (u) {
        var r = dati.roles.filter(function (x) { return x.id === u.role_id; })[0] || { name: u.role_id };
        return [(gestisci ? '<input type="checkbox" data-pick="' + esc(u.id) + '"' + (scelti[u.id] ? " checked" : "") + ' aria-label="Select">' : ""),
          '<button class="link-btn" data-open="' + esc(u.id) + '"><strong>' + esc(u.display || u.username) + '</strong></button><div class="cell-sub cell-mono">' + esc(u.username) +
            (u.email ? " · " + esc(u.email) : "") + "</div>",
          roleBadge(r), badge(u.status) + (u.must_change ? ' <span class="badge">New password</span>' : ""), u.totp_on ? UI.statusIcon("ok") : "—",
          esc(when(u.last_login)), esc(String(u.sessions)), menuFor(u)];
      });
      var nScelti = Object.keys(scelti).filter(function (k) { return scelti[k]; }).length;
      box.innerHTML = '<div class="toolbar users-filters"><label class="dt-search">' + UI.icon("search") + '<input type="search" data-f="q" placeholder="Search name, user name, e-mail…" value="' + esc(filtro.q) + '"></label>' +
        '<select data-f="role"><option value="">Every role</option>' + dati.roles.map(function (r) { return '<option value="' + esc(r.id) + '"' + (filtro.role === r.id ? " selected" : "") + ">" + esc(r.name) + "</option>"; }).join("") + "</select>" +
        '<select data-f="status"><option value="">Every state</option>' + Object.keys(STATUS).map(function (s) { return '<option value="' + s + '"' + (filtro.status === s ? " selected" : "") + ">" + esc(STATUS[s][1]) + "</option>"; }).join("") + "</select>" +
        '<span class="grow"></span>' + (gestisci ? UI.button("Select all", "data-pick-all", "btn-sm btn-ghost", "check") + UI.button("New user", "data-new-user", "btn-primary btn-sm", "users") + UI.button("Import CSV", "data-import", "btn-sm", "download") : "") +
        (Auth.can("export.data") ? UI.button("Export CSV", "data-export", "btn-sm", "download") : "") + "</div>" +
        (nScelti ? '<div class="bulk-bar"><strong>' + nScelti + ' selected</strong> <select data-bulk><option value="">Apply to the selected…</option>' +
          [["enable", "Enable"], ["disable", "Disable"], ["role", "Change role"], ["unlock", "Unlock"], ["must_change", "New password at next sign-in"], ["expires", "Set expiry"],
            ["signout", "Sign out"], ["delete", "Delete"]].map(function (b) { return '<option value="' + b[0] + '">' + esc(b[1]) + "</option>"; }).join("") +
          '</select> <button class="btn btn-sm btn-ghost" data-clear>Clear the selection</button></div>' : "") +
        UI.table([{ title: "" }, { title: "User" }, { title: "Role" }, { title: "State" },
          { title: "Two-step" }, { title: "Last sign-in" }, { title: "Sessions" }, { title: "" }], righe, "No user matches.");
    }
    function bulk(azione) {
      var ids = Object.keys(scelti).filter(function (k) { return scelti[k]; });
      var passo = Promise.resolve(null);
      if (azione === "role") {
        passo = UI.modal("Change role", '<select class="bulk-role" style="width:100%">' + dati.roles.map(function (r) { return '<option value="' + esc(r.id) + '">' + esc(r.name) + "</option>"; }).join("") + "</select>",
          [{ label: "Cancel", cls: "btn-ghost" }, { label: "Apply", cls: "btn-primary", value: function (w) { return w.querySelector(".bulk-role").value; } }]);
      } else if (azione === "expires") {
        passo = UI.modal("Account expiry", '<input type="date" class="bulk-date"><p class="muted small">Empty: never expires.</p>',
          [{ label: "Cancel", cls: "btn-ghost" }, { label: "Apply", cls: "btn-primary", value: function (w) { return w.querySelector(".bulk-date").value || ""; } }]);
      } else if (azione === "delete") {
        passo = UI.confirm("Delete " + ids.length + " users", "Their accounts and sessions are deleted. Their actions stay in the audit log.", { ok: "Delete", danger: true }).then(function (ok) { return ok ? true : undefined; });
      } else {
        passo = Promise.resolve(true);
      }
      passo.then(function (v) {
        if (v === undefined || v === null && azione !== "expires") return;
        return API.post("/users/bulk", { ids: ids, action: azione, value: v === true ? null : v }).then(function (r) {
          UI.toast(r.done + " done" + (r.errors.length ? ", " + r.errors.length + " not changed: " + r.errors[0].error : "."), r.errors.length ? "warning" : "ok");
          scelti = {};
          reload();
        });
      }).catch(fail);
    }
    box.addEventListener("input", function (e) {
      var f = e.target.getAttribute("data-f");
      if (f === "q") { clearTimeout(box._t); box._t = setTimeout(function () { filtro.q = e.target.value; reload().then(function () { var i = box.querySelector("[data-f=q]"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 250); }
    });
    box.addEventListener("change", function (e) {
      var t = e.target, f = t.getAttribute("data-f");
      if (f && f !== "q") { filtro[f] = t.value; reload(); return; }
      if (t.hasAttribute("data-pick")) { scelti[t.getAttribute("data-pick")] = t.checked; draw(); return; }
      if (t.hasAttribute("data-bulk") && t.value) { bulk(t.value); return; }
      if (t.classList.contains("user-act") && t.value) {
        var u = dati.users.filter(function (x) { return x.id === t.getAttribute("data-user"); })[0], azione = t.value;
        t.value = "";
        userAction(azione, u, dati.roles, reload);
      }
    });
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-new-user")) editUser(null, dati.roles, reload);
      if (b.getAttribute("data-open")) details(b.getAttribute("data-open"), dati.roles, reload);
      if (b.hasAttribute("data-clear")) { scelti = {}; draw(); }
      if (b.hasAttribute("data-pick-all")) { dati.users.forEach(function (u) { scelti[u.id] = true; }); draw(); }
      if (b.hasAttribute("data-export")) API.download("/users/export.csv", "wmm-users.csv").catch(fail);
      if (b.hasAttribute("data-import")) importUsers(reload);
    });
    reload();
  }
  function importUsers(reload) {
    UI.modal("Import users", '<p class="modal-text">A CSV file with a header row: <span class="cell-mono">username, display, email, telegram, role, active</span>. ' +
      "The role is its name or id. Every new user gets a temporary password.</p>" +
      '<input type="file" accept=".csv,text/csv" class="imp-file"><textarea class="imp-text" rows="6" style="width:100%" placeholder="username,display,email,role&#10;mario.rossi,Mario Rossi,mario@example.com,Operator" data-no-i18n></textarea>',
    [{ label: "Cancel", cls: "btn-ghost" }, { label: "Import", cls: "btn-primary", value: function (w) { return w.querySelector(".imp-text").value; } }]).then(function (testo) {
      if (!testo) return null;
      return API.post("/users/import", { csv: testo }).then(function (r) {
        reload();
        UI.modal("Imported", '<p class="modal-text">' + esc(r.created.length + " created, " + r.skipped.length + " skipped.") + " Copy the temporary passwords now: they are not shown again.</p>" +
          UI.table([{ title: "User" }, { title: "Temporary password" }], r.created.map(function (c) { return [esc(c.username), '<span class="cell-mono" data-no-i18n>' + esc(c.temporary_password) + "</span>"]; })) +
          (r.skipped.length ? "<h3>Skipped</h3>" + UI.table([{ title: "User" }, { title: "Why" }], r.skipped.map(function (s) { return [esc(s.username), esc(s.error)]; })) : ""),
        [{ label: "Close", cls: "btn-ghost" }]);
      });
    }).catch(fail);
    setTimeout(function () {
      var all = document.querySelectorAll("#modal-root .imp-file"), input = all[all.length - 1];
      if (input) input.addEventListener("change", function () {
        var f = input.files[0];
        if (f) f.text().then(function (t) { input.parentNode.querySelector(".imp-text").value = t; });
      });
    }, 50);
  }

  // ---------- role editor ----------
  function roleEditor(r, cat) {
    var have = {};
    (r.permissions || []).forEach(function (p) { have[p] = true; });
    var gruppi = {};
    cat.permissions.forEach(function (p) { if (p.group !== "Pages" && p.group !== "Tools") (gruppi[p.group] = gruppi[p.group] || []).push(p); });
    var cb = function (id, label) { return '<label class="check"><input type="checkbox" data-perm="' + esc(id) + '"' + (have[id] ? " checked" : "") + (r.locked ? " disabled" : "") + "> " + esc(label) + "</label>"; };
    var pagine = cat.permissions.filter(function (p) { return p.group === "Pages"; });
    return '<form class="form role-form" onsubmit="return false">' +
      '<div class="form-row"><label>Name<input name="name" maxlength="40" required value="' + esc(r.name || "") + '"' + (r.locked ? " disabled" : "") + '></label>' +
      '<label>Color<select name="color"' + (r.locked ? " disabled" : "") + ">" + cat.colors.map(function (c) { return '<option value="' + c + '"' + (c === (r.color || "gray") ? " selected" : "") + ">" + esc(c) + "</option>"; }).join("") + "</select></label></div>" +
      '<label>Description<input name="description" maxlength="200" value="' + esc(r.description || "") + '"' + (r.locked ? " disabled" : "") + "></label>" +
      '<label class="check"><input type="checkbox" name="require_2fa"' + (r.require_2fa ? " checked" : "") + (r.locked ? " disabled" : "") + "> Two-step verification required for this role</label>" +
      '<div class="perm-count muted small"></div>' +
      '<fieldset><legend>What the role sees <button type="button" class="link-btn" data-all="view.">all</button> · <button type="button" class="link-btn" data-none="view.">none</button></legend>' +
      '<div class="perm-grid">' + pagine.map(function (p) { return cb(p.id, p.label); }).join("") + "</div></fieldset>" +
      '<fieldset><legend>Tools it may run, by area and risk <button type="button" class="link-btn" data-all="run.">all</button> · <button type="button" class="link-btn" data-none="run.">none</button></legend>' +
      '<table class="table perm-matrix"><thead><tr><th>Area</th>' + cat.levels.map(function (l) { return '<th><button type="button" class="link-btn" data-col="' + l.id + '">' + esc(l.title) + "</button></th>"; }).join("") + "</tr></thead><tbody>" +
      cat.areas.map(function (a) {
        return '<tr><th><button type="button" class="link-btn" data-row="' + a.id + '">' + esc(a.title) + "</button></th>" + cat.levels.map(function (l) {
          var id = "run." + a.id + "." + l.id;
          return '<td><input type="checkbox" data-perm="' + id + '"' + (have[id] ? " checked" : "") + (r.locked ? " disabled" : "") + ' aria-label="' + esc(a.title + " " + l.title) + '"></td>';
        }).join("") + "</tr>";
      }).join("") + "</tbody></table></fieldset>" +
      Object.keys(gruppi).map(function (g) {
        return "<fieldset><legend>" + esc(g) + "</legend><div class=\"perm-grid\">" + gruppi[g].map(function (p) { return cb(p.id, p.label); }).join("") + "</div></fieldset>";
      }).join("") + "</form>";
  }
  function bindEditor(w) {
    var form = w.querySelector(".role-form");
    var conta = function () { form.querySelector(".perm-count").textContent = form.querySelectorAll("[data-perm]:checked").length + " permissions of " + form.querySelectorAll("[data-perm]").length; };
    form.addEventListener("change", conta);
    form.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      var sel = function (fn, on) { form.querySelectorAll("[data-perm]").forEach(function (c) { if (!c.disabled && fn(c.getAttribute("data-perm"))) c.checked = on; }); conta(); };
      if (b.dataset.all) sel(function (p) { return p.indexOf(b.dataset.all) === 0; }, true);
      if (b.dataset.none) sel(function (p) { return p.indexOf(b.dataset.none) === 0; }, false);
      if (b.dataset.row) {
        var riga = form.querySelectorAll('[data-perm^="run.' + b.dataset.row + '."]'), tutti = Array.prototype.every.call(riga, function (c) { return c.checked; });
        riga.forEach(function (c) { c.checked = !tutti; }); conta();
      }
      if (b.dataset.col) {
        var col = Array.prototype.filter.call(form.querySelectorAll('[data-perm^="run."]'), function (c) { return c.getAttribute("data-perm").split(".")[2] === b.dataset.col; });
        var pieni = col.every(function (c) { return c.checked; });
        col.forEach(function (c) { c.checked = !pieni; }); conta();
      }
    });
    conta();
  }
  function readRole(w) {
    var f = w.querySelector(".role-form");
    return { name: f.name.value, description: f.description.value, color: f.color.value, require_2fa: f.require_2fa.checked,
      permissions: Array.prototype.map.call(f.querySelectorAll("[data-perm]:checked"), function (c) { return c.getAttribute("data-perm"); }) };
  }
  function editRole(r, reload) {
    return loadCatalog().then(function (cat) {
      var nuovo = !r.id;
      var shown = UI.modal(nuovo ? "New role" : r.locked ? r.name + " (cannot be changed)" : "Edit " + r.name, roleEditor(r, cat),
        r.locked ? [{ label: "Close", cls: "btn-ghost" }] : [{ label: "Cancel", cls: "btn-ghost" }, { label: nuovo ? "Create" : "Save", cls: "btn-primary", value: readRole }]);
      wide();
      var all = document.querySelectorAll("#modal-root .modal");
      bindEditor(all[all.length - 1]);
      return shown.then(function (dati) {
        if (!dati) return null;
        return (nuovo ? API.post("/roles", dati) : API.put("/roles/" + r.id, dati)).then(function () { UI.toast(nuovo ? "Role created." : "Role saved.", "ok"); reload(); });
      });
    }).catch(fail);
  }

  // ---------- roles tab ----------
  function rolesTab(box) {
    var ruoli = [];
    function reload() { return API.get("/roles").then(function (d) { ruoli = d.roles; draw(); }, function (e) { box.innerHTML = UI.errorBox(e); }); }
    function draw() {
      var gestisci = Auth.can("roles.manage");
      box.innerHTML = '<div class="toolbar"><span class="grow muted small">A role decides what its users see and what they may do. Built-in roles can be changed and reset; Administrator always has everything.</span>' +
        (gestisci ? UI.button("New role", "data-new-role", "btn-primary btn-sm", "shield") + UI.button("Import a role", "data-import-role", "btn-sm", "download") : "") +
        UI.button("Compare two roles", "data-compare", "btn-sm", "compare") + "</div>" +
        '<div class="role-grid">' + ruoli.map(function (r) {
          var pagine = r.permissions.filter(function (p) { return p.indexOf("view.") === 0; }).length, strumenti = r.permissions.filter(function (p) { return p.indexOf("run.") === 0; }).length;
          return '<div class="card role-card"><div class="card-body"><div class="role-head">' + roleBadge(r) + (r.builtin ? ' <span class="badge">Built-in</span>' : "") +
            (r.require_2fa ? ' <span class="badge badge-status-info">Two-step</span>' : "") + "</div>" +
            '<p class="cell-sub">' + esc(r.description || "") + "</p>" +
            '<p class="small">' + esc(r.users + " users · " + pagine + " pages · " + strumenti + " tool permissions · " + r.permissions.length + " in all") + "</p>" +
            '<div class="page-actions" style="justify-content:flex-start;flex-wrap:wrap">' +
            UI.button(r.locked || !gestisci ? "View" : "Edit", 'data-edit="' + esc(r.id) + '"', "btn-sm", "settings") +
            UI.button("Members", 'data-members="' + esc(r.id) + '"', "btn-sm btn-ghost", "users") +
            (gestisci ? UI.button("Copy", 'data-copy="' + esc(r.id) + '"', "btn-sm btn-ghost", "download") : "") +
            UI.button("Export", 'data-export="' + esc(r.id) + '"', "btn-sm btn-ghost", "download") +
            (gestisci && r.builtin && !r.locked ? UI.button("Reset", 'data-reset="' + esc(r.id) + '"', "btn-sm btn-ghost", "refresh") : "") +
            (gestisci && !r.builtin ? UI.button("Delete", 'data-delete="' + esc(r.id) + '"', "btn-sm btn-ghost", "trash") : "") + "</div></div></div>";
        }).join("") + "</div>";
    }
    function byId(id) { return ruoli.filter(function (r) { return r.id === id; })[0]; }
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      var id;
      if (b.hasAttribute("data-new-role")) {
        API.get("/roles/templates").then(function (t) {
          return UI.modal("New role", '<p class="modal-text">Start from:</p><select class="tpl" style="width:100%"><option value="">An empty role</option>' +
            t.templates.concat(ruoli.filter(function (r) { return !r.builtin; })).map(function (x) { return '<option value="' + esc(x.id) + '">' + esc(x.name) + "</option>"; }).join("") + "</select>",
          [{ label: "Cancel", cls: "btn-ghost" }, { label: "Continue", cls: "btn-primary", value: function (w) { return w.querySelector(".tpl").value || "none"; } }]);
        }).then(function (base) {
          if (!base) return;
          var modello = base === "none" ? null : byId(base) || null;
          return API.get("/roles/templates").then(function (t) {
            var tpl = t.templates.filter(function (x) { return x.id === base; })[0] || modello;
            editRole({ name: "", description: "", color: "teal", permissions: tpl ? tpl.permissions : [] }, reload);
          });
        }).catch(fail);
      }
      if ((id = b.getAttribute("data-edit"))) API.get("/roles/" + id).then(function (r) { editRole(r, reload); }, fail);
      if ((id = b.getAttribute("data-members"))) API.get("/roles/" + id).then(function (r) {
        UI.modal("Members of " + r.name, UI.table([{ title: "User" }, { title: "State" }], r.members.map(function (m) { return [esc((m.display || m.username) + " (" + m.username + ")"), badge(m.status)]; }), "No user has this role."), [{ label: "Close", cls: "btn-ghost" }]);
      }, fail);
      if ((id = b.getAttribute("data-copy"))) {
        UI.modal("Copy " + byId(id).name, '<form class="form" onsubmit="return false"><label>Name of the copy<input name="name" maxlength="40" value="' + esc(byId(id).name + " (copy)") + '"></label></form>',
          [{ label: "Cancel", cls: "btn-ghost" }, { label: "Copy", cls: "btn-primary", value: function (w) { return w.querySelector("form").name.value; } }])
          .then(function (n) { if (n) return API.post("/roles/" + id + "/copy", { name: n }).then(function () { UI.toast("Role copied.", "ok"); reload(); }); }).catch(fail);
      }
      if ((id = b.getAttribute("data-export"))) API.get("/roles/" + id + "/export").then(function (r) {
        var blob = new Blob([JSON.stringify(r, null, 1)], { type: "application/json" }), a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = "role-" + r.name.replace(/\W+/g, "-").toLowerCase() + ".json"; a.click();
      }, fail);
      if ((id = b.getAttribute("data-reset"))) UI.confirm("Reset " + byId(id).name, "The role goes back to its original permissions.", { ok: "Reset" }).then(function (ok) {
        if (ok) return API.post("/roles/" + id + "/reset").then(function () { UI.toast("Reset.", "ok"); reload(); });
      }).catch(fail);
      if ((id = b.getAttribute("data-delete"))) {
        var r = byId(id), altri = ruoli.filter(function (x) { return x.id !== id; });
        UI.modal("Delete " + r.name, (r.users ? '<p class="modal-text">' + esc(r.users + " users have this role: they move to") + '</p><select class="move" style="width:100%">' +
          altri.map(function (x) { return '<option value="' + esc(x.id) + '"' + (x.id === "viewer" ? " selected" : "") + ">" + esc(x.name) + "</option>"; }).join("") + "</select>" : '<p class="modal-text">No user has this role.</p>'),
        [{ label: "Cancel", cls: "btn-ghost" }, { label: "Delete", cls: "btn-danger", value: function (w) { var s = w.querySelector(".move"); return s ? s.value : "-"; } }]).then(function (dest) {
          if (dest) return API.del("/roles/" + id + (dest !== "-" ? "?reassign=" + encodeURIComponent(dest) : "")).then(function () { UI.toast("Role deleted.", "ok"); reload(); });
        }).catch(fail);
      }
      if (b.hasAttribute("data-import-role")) {
        UI.modal("Import a role", '<input type="file" accept=".json,application/json" class="rf"><textarea class="rt" rows="6" style="width:100%" data-no-i18n placeholder="{&quot;format&quot;: &quot;wmm-role/1&quot;, …}"></textarea>',
          [{ label: "Cancel", cls: "btn-ghost" }, { label: "Import", cls: "btn-primary", value: function (w) { return w.querySelector(".rt").value; } }]).then(function (t) {
          if (!t) return null;
          var dati;
          try { dati = JSON.parse(t); } catch (er) { throw new Error("The file is not valid JSON."); }
          return API.post("/roles/import", { role: dati }).then(function (r) { UI.toast("Role imported" + (r.skipped && r.skipped.length ? ", " + r.skipped.length + " unknown permissions skipped." : "."), "ok"); reload(); });
        }).catch(fail);
        setTimeout(function () {
          var all = document.querySelectorAll("#modal-root .rf"), f = all[all.length - 1];
          if (f) f.addEventListener("change", function () { if (f.files[0]) f.files[0].text().then(function (t) { f.parentNode.querySelector(".rt").value = t; }); });
        }, 50);
      }
      if (b.hasAttribute("data-compare")) compare(ruoli);
    });
    reload();
  }
  function compare(ruoli) {
    var opt = function (sel) { return ruoli.map(function (r, i) { return '<option value="' + esc(r.id) + '"' + (i === sel ? " selected" : "") + ">" + esc(r.name) + "</option>"; }).join(""); };
    UI.modal("Compare two roles", '<div class="form-row"><select class="ca">' + opt(0) + '</select><select class="cb">' + opt(1) + "</select></div>",
      [{ label: "Cancel", cls: "btn-ghost" }, { label: "Compare", cls: "btn-primary", value: function (w) { return [w.querySelector(".ca").value, w.querySelector(".cb").value]; } }]).then(function (v) {
      if (!v) return null;
      return Promise.all([API.get("/roles/compare?a=" + encodeURIComponent(v[0]) + "&b=" + encodeURIComponent(v[1])), loadCatalog()]).then(function (r) {
        var d = r[0], nomi = {};
        r[1].permissions.forEach(function (p) { nomi[p.id] = p.label; });
        var lista = function (x) { return x.length ? '<ul class="check-list">' + x.map(function (p) { return "<li>" + esc(nomi[p] || p) + "</li>"; }).join("") + "</ul>" : '<p class="empty">None.</p>'; };
        UI.modal(d.a + " / " + d.b, '<div class="grid grid-2"><div><h3>' + esc("Only " + d.a) + "</h3>" + lista(d.only_a) + "</div><div><h3>" + esc("Only " + d.b) + "</h3>" + lista(d.only_b) + "</div></div>" +
          '<p class="muted small">' + esc(d.both.length + " permissions in common.") + "</p>", [{ label: "Close", cls: "btn-ghost" }]);
        wide();
      });
    }).catch(fail);
  }

  // ---------- sessions and audit ----------
  function sessionsTab(box) {
    function reload() {
      API.get("/sessions").then(function (d) {
        box.innerHTML = UI.table([{ title: "User" }, { title: "Since" }, { title: "Last activity" }, { title: "Browser" }, { title: "" }], d.sessions.map(function (s) {
          return [esc(s.username) + (s.limited ? ' <span class="badge">Limited</span>' : ""), esc(when(s.created)), esc(when(s.last_seen)), '<span class="cell-sub">' + esc(s.agent.slice(0, 80)) + "</span>",
            Auth.can("sessions.manage") ? '<button class="btn btn-sm btn-ghost" data-revoke="' + esc(s.id) + '">Sign out</button>' : ""];
        }), "No open session.");
      }, function (e) { box.innerHTML = UI.errorBox(e); });
    }
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-revoke]");
      if (b) API.del("/sessions/" + b.getAttribute("data-revoke")).then(function () { UI.toast("Signed out.", "ok"); reload(); }, fail);
    });
    reload();
  }
  function auditTab(box) {
    var f = { user: "", action: "", since: "", until: "", q: "", failed: "" }, offset = 0, voci = [], totale = 0;
    var AZIONI = [["", "Every action"], ["login.", "Sign-ins"], ["user.", "Users"], ["role.", "Roles"], ["policy.", "Policies"], ["session.", "Sessions"], ["api.", "Changes to the PC"],
      ["denied", "Denied"], ["run.reason", "Reasons for runs"], ["2fa.", "Two-step"], ["password.", "Passwords"], ["accounts.", "Accounts on and off"]];
    function qs() { return Object.keys(f).filter(function (k) { return f[k]; }).map(function (k) { return k + "=" + encodeURIComponent(f[k]); }).join("&"); }
    function load(append) {
      if (!append) { offset = 0; voci = []; }
      API.get("/audit?limit=100&offset=" + offset + (qs() ? "&" + qs() : "")).then(function (d) { voci = voci.concat(d.entries); totale = d.total; draw(); }, function (e) { box.innerHTML = UI.errorBox(e); });
    }
    function draw() {
      box.innerHTML = '<div class="toolbar"><input data-a="user" placeholder="User" value="' + esc(f.user) + '" style="max-width:140px">' +
        '<select data-a="action">' + AZIONI.map(function (a) { return '<option value="' + a[0] + '"' + (f.action === a[0] ? " selected" : "") + ">" + esc(a[1]) + "</option>"; }).join("") + "</select>" +
        '<input type="date" data-a="since" value="' + esc(f.since) + '"><input type="date" data-a="until" value="' + esc(f.until) + '">' +
        '<input type="search" data-a="q" placeholder="Text" value="' + esc(f.q) + '" style="max-width:160px">' +
        '<label class="check"><input type="checkbox" data-a="failed"' + (f.failed ? " checked" : "") + "> Only failed</label><span class=\"grow\"></span>" +
        (Auth.can("export.data") ? UI.button("Export CSV", "data-audit-export", "btn-sm", "download") : "") +
        (Auth.can("settings.security") ? UI.button("Delete old entries", "data-audit-prune", "btn-sm btn-ghost", "trash") : "") + "</div>" +
        UI.table([{ title: "When" }, { title: "User" }, { title: "Action" }, { title: "On" }, { title: "Detail" }, { title: "" }], voci.map(function (e) {
          return [esc(when(e.at)), esc(e.user), '<span class="cell-mono">' + esc(e.action) + "</span>", '<span class="cell-sub cell-mono">' + esc(e.target) + "</span>",
            '<span class="cell-sub">' + esc(e.detail.slice(0, 160)) + "</span>", e.ok ? UI.statusIcon("ok") : UI.statusIcon("error")];
        }), "Nothing in the audit log for these filters.") +
        '<p class="muted small">' + esc(voci.length + " of " + totale + " entries") + "</p>" + (voci.length < totale ? UI.button("Show more", "data-more", "btn-sm", "refresh") : "");
    }
    box.addEventListener("change", function (e) {
      var k = e.target.getAttribute("data-a");
      if (!k) return;
      f[k] = e.target.type === "checkbox" ? (e.target.checked ? "1" : "") : e.target.value;
      load(false);
    });
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-more")) { offset += 100; load(true); }
      if (b.hasAttribute("data-audit-export")) API.download("/audit/export.csv" + (qs() ? "?" + qs() : ""), "wmm-audit.csv").catch(fail);
      if (b.hasAttribute("data-audit-prune")) UI.confirm("Delete old entries", "Entries older than the retention of Settings › Security are deleted.", { ok: "Delete" }).then(function (ok) {
        if (ok) return API.post("/audit/prune").then(function (r) { UI.toast(r.deleted + " entries deleted.", "ok"); load(false); });
      }).catch(fail);
    });
    load(false);
  }

  window.Pages.users = {
    title: "Users and roles",
    render: function (el, App) {
      return API.get("/auth/state").then(function (st) {
        if (!st.enabled) {
          el.innerHTML = UI.pageHeader("Users and roles", "Accounts, roles and permissions", "") +
            '<div class="grid">' + UI.card("Accounts are off", '<p class="modal-text">Today anyone who opens the console on this PC can do everything. Turn accounts on to give each person ' +
              "a user name and a role that decides what they see and do, with an audit log of every sign-in and change.</p>",
            '<a class="btn btn-primary btn-sm" href="#/settings?s=security">' + UI.icon("shield") + "Turn accounts on</a>") + "</div>";
          return;
        }
        return API.get("/users/overview").then(function (o) {
          App.setSubtitle(o.users + " users · " + o.roles + " roles");
          var tabs = [["users", "Users", "users"], ["roles", "Roles", "shield"], ["sessions", "Sessions", "activity"]];
          if (Auth.can("audit.view")) tabs.push(["audit", "Audit log", "history"]);
          var attiva = (/[?&]tab=(\w+)/.exec(location.hash) || [])[1] || Components.store("usersTab") || "users";
          if (!tabs.some(function (t) { return t[0] === attiva; })) attiva = "users";
          el.innerHTML = UI.pageHeader("Users and roles", "Who can sign in, what each role sees and may do, and every change", "") +
            '<div class="grid grid-4">' + UI.kpi("Users", Components.num(o.users), o.active + " active", "info") +
              UI.kpi("Locked or disabled", Components.num(o.locked + o.disabled), o.locked + " locked by wrong passwords", o.locked ? "warning" : "ok") +
              UI.kpi("Two-step verification", Components.num(o.two_step), "of " + o.users + " users", o.two_step < o.users ? "info" : "ok") +
              UI.kpi("Failed sign-ins", Components.num(o.failed_24h), "last 24 hours · " + o.sessions + " open sessions", o.failed_24h > 5 ? "warning" : "ok") + "</div>" +
            '<div class="tabs" role="tablist">' + tabs.map(function (t) {
              return '<button type="button" class="tab" role="tab" data-utab="' + t[0] + '" aria-selected="' + (t[0] === attiva) + '">' + UI.icon(t[2]) + "<span>" + esc(t[1]) + "</span></button>";
            }).join("") + "</div>" + '<div class="card"><div class="card-body" id="users-body"></div></div>';
          function show(id) {
            Components.store("usersTab", id);
            el.querySelectorAll("[data-utab]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-utab") === id)); });
            var nuovo = document.createElement("div");
            var vecchio = el.querySelector("#users-body");
            nuovo.id = "users-body";
            vecchio.parentNode.replaceChild(nuovo, vecchio);
            ({ users: usersTab, roles: rolesTab, sessions: sessionsTab, audit: auditTab })[id](nuovo, App);
          }
          el.querySelector(".tabs").addEventListener("click", function (e) { var b = e.target.closest("[data-utab]"); if (b) show(b.getAttribute("data-utab")); });
          show(attiva);
        });
      });
    }
  };
})();
