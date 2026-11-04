/* Settings › Notifications › Email and Telegram alerts: channels, events and a test message.
   Secrets are never shown again: an empty field keeps the saved password or token. */
(function () {
  "use strict";
  var esc = UI.esc;

  function field(name, label, value, attrs, hint) {
    return "<label>" + esc(label) + '<input name="' + name + '" value="' + esc(value || "") + '" ' + (attrs || "") + ">" +
      (hint ? '<span class="hint">' + esc(hint) + "</span>" : "") + "</label>";
  }

  function draw(box, s) {
    var secret = function (has) { return 'type="password" autocomplete="new-password" placeholder="' + (has ? "Saved: leave empty to keep it" : "") + '"'; };
    box.innerHTML = '<form class="form" data-alerts onsubmit="return false">' +
      '<p class="muted" style="margin-top:0">Alerts reach you even when the console is closed: a scheduled run that failed, drive C: almost full, ' +
      "new unsafe programs. The same alert is sent at most once a day.</p>" +
      "<h3>Telegram</h3>" +
      field("telegram_token", "Bot token", "", secret(s.has_telegram_token), "From @BotFather on Telegram. Stored encrypted on this PC.") +
      field("telegram_chat", "Chat ID", s.telegram_chat, 'placeholder="123456789"', "Your chat with the bot, or a group or @channel where the bot can write.") +
      "<h3>Email</h3>" +
      '<div class="form-row">' + field("smtp_host", "SMTP server", s.smtp_host, 'placeholder="smtp.gmail.com"') +
      field("smtp_port", "Port", s.smtp_port, 'placeholder="587" inputmode="numeric" style="max-width:90px"') + "</div>" +
      '<div class="form-row">' + field("smtp_user", "User", s.smtp_user, 'autocomplete="off"') +
      field("smtp_password", "Password", "", secret(s.has_smtp_password), "For Gmail and Outlook use an app password.") + "</div>" +
      field("smtp_from", "Sender (optional)", s.smtp_from, 'placeholder="the user above"') +
      field("email_to", "Send to", s.email_to, 'placeholder="you@example.com, colleague@example.com"') +
      "<h3>When</h3>" + Object.keys(s.event_titles).map(function (k) {
        return '<label class="check"><input type="checkbox" data-event="' + esc(k) + '"' + (s.events.indexOf(k) >= 0 ? " checked" : "") + "> " + esc(s.event_titles[k]) + "</label>";
      }).join("") +
      '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Save", "data-alerts-save", "btn-primary", "check") +
      UI.button("Send a test", "data-alerts-test", "", "bell") +
      ((s.has_telegram_token || s.has_smtp_password) ? UI.button("Forget the saved secrets", "data-alerts-forget", "btn-ghost", "trash") : "") + "</div>" +
      '<p class="cell-sub" data-alerts-state>' + esc(s.channels.length ? "Active: " + s.channels.join(" and ") + "." : "No channel is set up yet.") + "</p></form>";
  }

  function values(form) {
    var v = {};
    form.querySelectorAll("input[name]").forEach(function (i) { v[i.name] = i.value; });
    v.events = Array.prototype.filter.call(form.querySelectorAll("[data-event]"), function (c) { return c.checked; }).map(function (c) { return c.getAttribute("data-event"); });
    return v;
  }

  function mount(box) {
    if (!box) return;
    box.innerHTML = UI.loading("Reading the alert settings…");
    API.get("/notifications").then(function (s) {
      draw(box, s);
      box.addEventListener("click", function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        var form = box.querySelector("[data-alerts]");
        var save = function (extra) { return API.put("/notifications", Object.assign(values(form), extra || {})); };
        if (b.hasAttribute("data-alerts-save")) {
          save().then(function (r) { draw(box, r); UI.toast("Alert settings saved.", "ok"); }, function (err) { UI.toast(err.message, "error"); });
        } else if (b.hasAttribute("data-alerts-test")) {
          b.disabled = true;
          save().then(function (r) { draw(box, r); return API.post("/notifications/test"); }).then(function (r) {
            var parti = Object.keys(r.results).map(function (k) { return k + ": " + r.results[k]; });
            UI.toast((r.ok ? "Test sent. " : "Test not delivered. ") + parti.join(" · "), r.ok ? "ok" : "warning");
          }, function (err) { UI.toast(err.message, "error"); }).then(function () { var t = box.querySelector("[data-alerts-test]"); if (t) t.disabled = false; });
        } else if (b.hasAttribute("data-alerts-forget")) {
          UI.confirm("Forget the saved secrets", "The bot token and the email password are deleted from this PC. Alerts stop until you type them again.", { ok: "Forget them", danger: true })
            .then(function (ok) { if (ok) save({ clear_secrets: true }).then(function (r) { draw(box, r); UI.toast("Secrets deleted.", "ok"); }, function (err) { UI.toast(err.message, "error"); }); });
        }
      });
    }, function (e) { box.innerHTML = UI.errorBox(e); });
  }

  window.AlertsPanel = { mount: mount };

  /* Settings › This agent › Program updates: the latest GitHub release, checked and installed by the agent. */
  function mountUpdates(box) {
    if (!box) return;
    function show(r) {
      var latest = r.latest ? "Latest release: <strong>" + esc(r.latest) + "</strong>" + (r.published ? " (" + esc(UI.formatDate(r.published, false)) + ")" : "") : esc(r.reason || "");
      box.innerHTML = '<p class="muted" style="margin-top:0">Installed: <strong>' + esc(r.current) + "</strong>. " + latest + "</p>" +
        (r.available ? '<div class="callout callout-info">' + UI.icon("download") + "<div>Version " + esc(r.latest) + " is ready. The package is checked against " +
          "its SHA-256 before it replaces the program; your data stays as it is." + (r.page ? ' <a href="' + esc(r.page) + '" target="_blank" rel="noopener noreferrer">What changes</a>' : "") +
          "</div></div>" : "") +
        '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Check now", "data-update-check", "btn-sm", "refresh") +
        (r.available ? UI.button("Install " + r.latest, "data-update-install", "btn-sm btn-primary", "download") : "") + "</div>";
    }
    function check() {
      box.innerHTML = UI.loading("Asking GitHub for the latest release…");
      return API.get("/update/check").then(show, function (e) { box.innerHTML = UI.errorBox(e) + UI.button("Check now", "data-update-check", "btn-sm", "refresh"); });
    }
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-update-check")) { check(); return; }
      if (b.hasAttribute("data-update-install")) {
        UI.confirm("Install the update", "The program files are replaced by the new version; history, settings and schedules stay. Restart the console afterwards.",
          { ok: "Install" }).then(function (ok) {
          if (!ok) return;
          b.disabled = true;
          b.classList.add("busy");
          API.post("/update/install").then(function (r) {
            UI.toast(r.preview ? "Preview mode: the update was simulated, nothing changed." : "Version " + r.installed + " installed: restart Windows Maintenance Manager to use it.",
              r.preview ? "info" : "ok");
            check();
          }, function (err) { UI.toast(err.message, "error"); b.disabled = false; b.classList.remove("busy"); });
        });
      }
    });
    check();
  }

  window.UpdatesPanel = { mount: mountUpdates };
})();
