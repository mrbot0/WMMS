/* Playbooks: ready-made maintenance sequences that run in one click. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  // Playbooks are shown by purpose; one not listed here lands in "More".
  var GROUPS = [
    ["My playbooks", "user", "Saved from Actions or copied from a playbook below; kept in this browser.", []],
    ["Every visit", "sparkle", "Routine maintenance and updates.", ["quick", "full", "deep_clean", "update_all"]],
    ["Fix a problem", "integrity", "When something does not work.", ["repair", "network_fix", "print_fix"]],
    ["Check (read-only)", "reports", "Reports only: nothing on the PC changes.", ["health_check", "security_audit"]],
    ["Tune for a use", "performance", "Make the PC fit the way it is used.", ["performance", "gaming", "laptop", "privacy"]],
    ["Secure", "security", "Protection for a new or exposed PC.", ["security", "new_pc"]]
  ];

  /* My playbooks: action lists saved in this browser (from Actions, or copied from a built-in playbook). */
  function mine() { return Components.store("myPlaybooks") || []; }
  function saveMine(title, actions) {
    var list = mine().filter(function (p) { return p.title !== title; });
    list.push({ id: "my-" + Date.now().toString(36), title: title, actions: actions, created: new Date().toISOString() });
    Components.store("myPlaybooks", list);
  }

  window.Pages.playbooks = {
    title: "Playbooks",
    saveMine: saveMine,
    render: function (el, App) {
      return Promise.all([API.get("/playbooks"), API.get("/history?limit=500")]).then(function (r) {
        var books = r[0].playbooks, runs = r[1].runs;
        // Own playbooks get the same shape as the built-in ones; actions removed from the catalog are skipped.
        var own = mine().map(function (p) {
          var steps = p.actions.map(function (id) { return App.action(id); }).filter(Boolean);
          var rank = { safe: 0, moderate: 1, high: 2 };
          return { id: p.id, own: true, title: p.title, description: "My playbook · saved " + UI.formatDate(p.created, false), actions: steps.map(function (a) { return a.id; }),
            steps: steps, minutes: steps.reduce(function (s, a) { return s + (a.minutes || 0); }, 0),
            risk: steps.reduce(function (w, a) { return rank[a.risk] > rank[w] ? a.risk : w; }, "safe") };
        });
        books = own.concat(books);
        App.setSubtitle("Ready-made maintenance sequences, ordered and safe by design");
        var card = function (p) {
          var last = runs.filter(function (x) { return p.actions.indexOf(x.action_id) >= 0; })[0];
          var readOnly = p.actions.every(function (id) { var a = App.action(id); return a && a.kind === "report"; });
          return '<section class="card"><header class="card-head"><h2>' + UI.icon("playbooks") + esc(p.title) + '</h2><div class="card-tools">' +
            (readOnly ? UI.kindBadge("report") : UI.riskBadge(p.risk)) + "</div></header>" +
            '<div class="card-body"><p class="muted" style="margin:0 0 10px">' + esc(p.description) + '</p><div class="playbook-meta"><span class="badge">' + p.steps.length + " steps</span>" +
            '<span class="badge">' + UI.icon("clock") + " ~" + Math.max(1, Math.round(p.minutes)) + " min</span>" +
            '<span class="badge eta" title="If started now">Ends around ' + esc(new Date(Date.now() + Math.max(1, p.minutes) * 60000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })) + "</span>" +
            (last ? '<span class="badge">Last step run ' + esc(UI.relative(last.started)) + "</span>" : "") + "</div>" +
            '<ol class="playbook-steps">' + p.steps.map(function (s) {
              return '<li><span class="grow"><span class="cell-title">' + esc(s.title) + '</span> <span class="cell-sub">· ' + esc(UI.AREA_LABEL[s.area]) + "</span></span>" + UI.riskBadge(s.risk) + "</li>";
            }).join("") + "</ol>" +
            '<div class="page-actions" style="margin-top:14px"><button class="btn btn-primary" data-playbook="' + esc(p.id) + '">' + UI.icon("play") + "Run playbook</button>" +
            '<button class="btn btn-ghost" data-copy-playbook="' + esc(p.id) + '" title="The steps as a checklist, to follow by hand or attach to a ticket">' + UI.icon("copy") + "Copy steps</button>" +
            (p.own ? '<button class="btn btn-ghost" data-delete-mine="' + esc(p.id) + '">' + UI.icon("trash") + "Delete</button>"
              : '<button class="btn btn-ghost" data-copy-mine="' + esc(p.id) + '" title="Copy it to My playbooks, then change it from Actions">' + UI.icon("plus") + "Make my copy</button>") +
            // Own playbooks live in this browser, so Task Scheduler (running as SYSTEM) cannot run them.
            (p.own ? "" : '<button class="btn" data-schedule-playbook="' + esc(p.id) + '" title="Run it as a routine: every day, week, month or at startup">' + UI.icon("clock") + "Schedule</button>") +
            "</div></div></section>";
        };
        GROUPS[0][3] = own.map(function (p) { return p.id; });
        var placed = [].concat.apply([], GROUPS.map(function (g) { return g[3]; }));
        var cards = GROUPS.concat([["More", "playbooks", "", books.map(function (b) { return b.id; }).filter(function (id) { return placed.indexOf(id) < 0; })]])
          .map(function (g) {
            var list = g[3].map(function (id) { return books.filter(function (b) { return b.id === id; })[0]; }).filter(Boolean);
            return list.length ? '<div class="section-title">' + UI.icon(g[1]) + esc(g[0]) + '<span class="extra">' + esc(g[2]) + "</span></div>" +
              '<div class="playbooks">' + list.map(card).join("") + "</div>" : "";
          }).join("");
        el.innerHTML = UI.pageHeader("Playbooks", "Actions that are not safe ask for confirmation once and create a restore point first", "") +
          '<div class="callout callout-info">' + UI.icon("info") + "<div>Playbooks run their steps in order in a single job. Follow the progress in the Activity panel; results are saved in History.</div></div>" +
          cards;
        el.querySelectorAll("[data-playbook]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var p = books.filter(function (b) { return b.id === btn.getAttribute("data-playbook"); })[0];
            App.runActions(p.actions);
          });
        });
        el.querySelectorAll("[data-copy-mine]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var p = books.filter(function (b) { return b.id === btn.getAttribute("data-copy-mine"); })[0];
            saveMine(p.title + " (my copy)", p.actions.slice());
            UI.toast("Copied to My playbooks.", "ok");
            App.render();
          });
        });
        el.querySelectorAll("[data-delete-mine]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var id = btn.getAttribute("data-delete-mine");
            UI.confirm("Delete this playbook?", "It is removed from My playbooks. Nothing on the PC changes.", { ok: "Delete", danger: true }).then(function (ok) {
              if (!ok) return;
              Components.store("myPlaybooks", mine().filter(function (p) { return p.id !== id; }));
              App.render();
            });
          });
        });
        el.querySelectorAll("[data-copy-playbook]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var p = books.filter(function (b) { return b.id === btn.getAttribute("data-copy-playbook"); })[0];
            App.copyText([p.title + " (~" + Math.max(1, Math.round(p.minutes)) + " min)", p.description, ""].concat(p.steps.map(function (s, i) {
              return "- [ ] " + (i + 1) + ". " + s.title + " (" + (UI.AREA_LABEL[s.area] || s.area) + ", " + (UI.RISK_LABEL[s.risk] || s.risk).toLowerCase() + ")";
            })).join("\n"), "Steps");
          });
        });
        el.querySelectorAll("[data-schedule-playbook]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var p = books.filter(function (b) { return b.id === btn.getAttribute("data-schedule-playbook"); })[0];
            window.Pages.schedules.applyRoutine({ ref: "playbook:" + p.id, title: p.title, description: p.description, risk: p.risk,
              minutes: p.minutes, actions: p.steps, suggested: null }, function () { location.hash = "#/schedules"; });
          });
        });
      });
    }
  };
})();
