/* Accounts in the console (2.9): the sign-in screen (user name, password, then the 6-digit code when two-step
   verification is on), the forced password change and two-step set-up, the user menu in the top bar, and what the
   signed-in user's role may see and do. With accounts off, Auth.ready() resolves at once and everything is allowed. */
(function () {
  "use strict";
  var esc = UI.esc;
  var me = null, enabled = false;

  function can(perm) { return !enabled || !!(me && me.permissions && me.permissions.indexOf(perm) >= 0); }
  function canSee(page) {
    if (!enabled || !me) return true;
    if (/^cat-/.test(page)) return true;
    return can("view." + page);
  }
  function anyVisible(pages) { return pages.some(canSee); }

  function overlay(html) {
    var box = document.getElementById("auth-overlay");
    if (!box) {
      box = document.createElement("div");
      box.id = "auth-overlay";
      box.className = "auth-overlay";
      document.body.appendChild(box);
    }
    box.innerHTML = '<div class="auth-card" role="dialog" aria-modal="true">' + html + "</div>";
    var first = box.querySelector("input");
    if (first) first.focus();
    return box;
  }
  function closeOverlay() { var b = document.getElementById("auth-overlay"); if (b) b.remove(); }
  function header(state, sub) {
    return '<div class="auth-brand">' + UI.icon("shield") + "<div><strong>" + esc(state.org_name || "Windows Maintenance Manager") + "</strong>" +
      '<div class="cell-sub">' + esc(sub || state.hostname || "") + "</div></div></div>";
  }
  function error(box, text) { var e = box.querySelector(".auth-error"); e.textContent = text || ""; e.hidden = !text; }

  // ---------- sign in ----------
  function signIn(state) {
    return new Promise(function (resolve) {
      var box = overlay(header(state, "Sign in to continue") +
        '<form class="form" data-login onsubmit="return false">' +
        '<label>User name<input name="username" autocomplete="username" autocapitalize="off" spellcheck="false" required></label>' +
        '<label>Password<input name="password" type="password" autocomplete="current-password" required></label>' +
        '<label class="auth-code" hidden>Code from the authenticator app<input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="\\d{6}"></label>' +
        '<p class="auth-error callout callout-warning" hidden></p>' +
        '<button class="btn btn-primary" type="submit">Sign in</button></form>' +
        '<p class="muted small">Forgot the password? An administrator can give you a temporary one.</p>');
      var form = box.querySelector("[data-login]");
      form.addEventListener("submit", function () {
        var b = form.querySelector("button");
        b.disabled = true;
        error(box, "");
        API.post("/auth/login", { username: form.username.value, password: form.password.value, code: form.code.value }).then(function (r) {
          API.setSession(r.token);
          return afterLogin(r, state);
        }).then(resolve, function (e) {
          b.disabled = false;
          if (e.status === 428) {
            box.querySelector(".auth-code").hidden = false;
            form.code.focus();
            error(box, "");
            return;
          }
          error(box, e.message);
        });
      });
    });
  }

  // A limited session (temporary or expired password, two-step required by the role) goes through each step, then on.
  function afterLogin(r, state) {
    return API.get("/auth/me").then(function (u) {
      me = u;
      if (!u.limited) { closeOverlay(); return u; }
      var adesso = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 19);
      var pw = u.must_change || (u.password_expires && u.password_expires < adesso);
      return (pw ? changePassword(state, true) : enroll(state, true)).then(function () { return afterLogin(r, state); });
    });
  }

  // ---------- password ----------
  function rules(p) { return "At least " + p.min_length + " characters and " + p.classes + " of: lowercase, uppercase, digits, symbols."; }
  function changePassword(state, forced) {
    return new Promise(function (resolve, reject) {
      var box = overlay(header(state, forced ? "Choose a new password" : "Change your password") +
        '<form class="form" data-pw onsubmit="return false">' +
        (forced ? '<p class="modal-text">Your password is temporary or has expired: choose a new one to continue.</p>' : "") +
        '<label>Current password<input name="old" type="password" autocomplete="current-password" required></label>' +
        '<label>New password<input name="new" type="password" autocomplete="new-password" required></label>' +
        '<label>New password again<input name="again" type="password" autocomplete="new-password" required></label>' +
        '<p class="muted small">' + esc(rules(state)) + "</p>" +
        '<p class="auth-error callout callout-warning" hidden></p>' +
        '<div class="page-actions" style="justify-content:flex-start"><button class="btn btn-primary" type="submit">Save</button>' +
        (forced ? "" : '<button class="btn btn-ghost" type="button" data-cancel>Cancel</button>') + "</div></form>");
      var form = box.querySelector("[data-pw]");
      var cancel = box.querySelector("[data-cancel]");
      if (cancel) cancel.addEventListener("click", function () { closeOverlay(); reject(new Error("cancelled")); });
      form.addEventListener("submit", function () {
        if (form["new"].value !== form.again.value) { error(box, "The two new passwords are different."); return; }
        API.post("/auth/password", { old: form.old.value, "new": form["new"].value }).then(function () {
          UI.toast("Password changed. Your other sessions were signed out.", "ok");
          closeOverlay();
          resolve();
        }, function (e) { error(box, e.message); });
      });
    });
  }

  // ---------- two-step verification ----------
  function enroll(state, forced) {
    return API.post("/auth/2fa/begin").then(function (s) {
      return new Promise(function (resolve, reject) {
        var box = overlay(header(state, "Two-step verification") +
          '<form class="form" data-2fa onsubmit="return false">' +
          (forced ? '<p class="modal-text">Your role requires two-step verification. Set it up now to continue.</p>' : "") +
          '<p class="modal-text">In an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password, Bitwarden…) add an account by hand with this key:</p>' +
          '<pre class="code-block" data-no-i18n style="font-size:18px;letter-spacing:2px;text-align:center">' + esc(s.secret.replace(/(.{4})/g, "$1 ").trim()) + "</pre>" +
          '<p class="cell-sub cell-mono" style="word-break:break-all">' + esc(s.uri) + "</p>" +
          '<label>The 6-digit code the app shows<input name="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" required></label>' +
          '<p class="auth-error callout callout-warning" hidden></p>' +
          '<div class="page-actions" style="justify-content:flex-start"><button class="btn btn-primary" type="submit">Turn on</button>' +
          (forced ? "" : '<button class="btn btn-ghost" type="button" data-cancel>Cancel</button>') + "</div></form>");
        var form = box.querySelector("[data-2fa]");
        var cancel = box.querySelector("[data-cancel]");
        if (cancel) cancel.addEventListener("click", function () { closeOverlay(); reject(new Error("cancelled")); });
        form.addEventListener("submit", function () {
          API.post("/auth/2fa/confirm", { code: form.code.value }).then(function () {
            UI.toast("Two-step verification is on.", "ok");
            closeOverlay();
            resolve();
          }, function (e) { error(box, e.message); });
        });
      });
    });
  }

  // ---------- user menu ----------
  function chip() {
    if (!enabled || !me) return "";
    return '<button type="button" class="user-chip" data-user-menu title="' + esc(me.username + " · " + me.role) + '">' + UI.icon("users") +
      '<span class="user-chip-name">' + esc(me.display || me.username) + '</span><span class="cell-sub">' + esc(me.role) + "</span></button>";
  }
  function menu(App) {
    UI.modal(me.display || me.username, UI.definition([["User name", '<span class="cell-mono">' + esc(me.username) + "</span>"], ["Role", esc(me.role)],
      ["Two-step verification", me.totp_on ? "On" : "Off"], ["Last sign-in", esc(me.last_login ? UI.formatDate(me.last_login) : "—")]]),
    [{ label: "My account", value: function () { return "account"; } }, { label: "Change password", value: function () { return "pw"; } },
      { label: "Sign out", cls: "btn-primary", value: function () { return "out"; } }]).then(function (v) {
      if (v === "account") location.hash = "#/settings?s=account";
      if (v === "pw") API.get("/auth/state").then(function (s) { return changePassword(s, false); }).catch(function () {});
      if (v === "out") signOut();
    });
  }
  function signOut() {
    API.post("/auth/logout").catch(function () {}).then(function () { API.setSession(""); location.reload(); });
  }
  document.addEventListener("click", function (e) { if (e.target.closest("[data-user-menu]")) menu(window.App); });
  // A session that expires while the console is open: sign in again, then reload the page.
  window.addEventListener("wmm-signin", function () {
    if (document.getElementById("auth-overlay")) return;
    API.get("/auth/state").then(function (s) { return signIn(s); }).then(function () { location.reload(); });
  });

  // ---------- run rules (Settings › Runs) ----------
  function runExtras(list, info) {
    var regole = (info && info.run_rules) || {};
    var fix = list.filter(function (a) { return a.kind !== "report"; });
    var alto = fix.some(function (a) { return a.risk === "high"; });
    var vietati = list.filter(function (a) { return a.allowed === false; });
    if (vietati.length) return Promise.reject(new Error("Your role does not allow running: " + vietati.map(function (a) { return a.title; }).join(", ") + "."));
    if (regole.block_high_risk && alto) return Promise.reject(new Error("High-risk tools are blocked on this PC (Settings › Runs)."));
    if (!fix.length || (!regole.require_reason && !(regole.confirm_high_with_name && alto))) return Promise.resolve({});
    var body = '<form class="form" onsubmit="return false">' +
      (regole.require_reason ? '<label>Reason or ticket number<input name="reason" maxlength="300" required></label>' : "") +
      (regole.confirm_high_with_name && alto ? '<label>Type the name of this PC (' + esc(info.hostname) + ') to confirm<input name="confirm_name" autocomplete="off"></label>' : "") + "</form>";
    return UI.modal("Before running", body, [{ label: "Cancel", cls: "btn-ghost" }, { label: "Continue", cls: "btn-primary", value: function (w) {
      var f = w.querySelector("form");
      return { reason: f.reason ? f.reason.value : "", confirm_name: f.confirm_name ? f.confirm_name.value : "" };
    } }]).then(function (v) { if (!v) throw new Error("cancelled"); return v; });
  }

  // ---------- start ----------
  function ready() {
    return API.get("/auth/state").then(function (state) {
      enabled = !!state.enabled;
      if (!enabled) return null;
      return API.get("/auth/me").then(function (u) {
        if (!u.accounts) { enabled = false; return null; }
        me = u;
        return u.limited ? afterLogin({}, state) : u;
      }, function () { API.setSession(""); return signIn(state); });
    });
  }

  window.Auth = { ready: ready, can: can, canSee: canSee, anyVisible: anyVisible, me: function () { return me; }, enabled: function () { return enabled; },
    chip: chip, changePassword: changePassword, enroll: enroll, signOut: signOut, runExtras: runExtras };
})();
