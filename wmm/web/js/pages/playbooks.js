/* Playbooks: ready-made maintenance sequences that run in one click. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  // Playbooks are shown by purpose; one not listed here lands in "More".
  var GROUPS = [
    ["Every visit", "sparkle", "Routine maintenance and updates.", ["quick", "full", "deep_clean", "update_all"]],
    ["Fix a problem", "integrity", "When something does not work.", ["repair", "network_fix", "print_fix"]],
    ["Check (read-only)", "reports", "Reports only: nothing on the PC changes.", ["health_check", "security_audit"]],
    ["Tune for a use", "performance", "Make the PC fit the way it is used.", ["performance", "gaming", "laptop", "privacy"]],
    ["Secure", "security", "Protection for a new or exposed PC.", ["security", "new_pc"]]
  ];

  window.Pages.playbooks = {
    title: "Playbooks",
    render: function (el, App) {
      return Promise.all([API.get("/playbooks"), API.get("/history?limit=500")]).then(function (r) {
        var books = r[0].playbooks, runs = r[1].runs;
        App.setSubtitle("Ready-made maintenance sequences, ordered and safe by design");
        var card = function (p) {
          var last = runs.filter(function (x) { return p.actions.indexOf(x.action_id) >= 0; })[0];
          var readOnly = p.actions.every(function (id) { var a = App.action(id); return a && a.kind === "report"; });
          return '<section class="card"><header class="card-head"><h2>' + UI.icon("playbooks") + esc(p.title) + '</h2><div class="card-tools">' +
            (readOnly ? UI.kindBadge("report") : UI.riskBadge(p.risk)) + "</div></header>" +
            '<div class="card-body"><p class="muted" style="margin:0 0 10px">' + esc(p.description) + '</p><div class="playbook-meta"><span class="badge">' + p.steps.length + " steps</span>" +
            '<span class="badge">' + UI.icon("clock") + " ~" + Math.max(1, Math.round(p.minutes)) + " min</span>" +
            (last ? '<span class="badge">Last step run ' + esc(UI.relative(last.started)) + "</span>" : "") + "</div>" +
            '<ol class="playbook-steps">' + p.steps.map(function (s) {
              return '<li><span class="grow"><span class="cell-title">' + esc(s.title) + '</span> <span class="cell-sub">· ' + esc(UI.AREA_LABEL[s.area]) + "</span></span>" + UI.riskBadge(s.risk) + "</li>";
            }).join("") + "</ol>" +
            '<div class="page-actions" style="margin-top:14px"><button class="btn btn-primary" data-playbook="' + esc(p.id) + '">' + UI.icon("play") + "Run playbook</button></div></div></section>";
        };
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
      });
    }
  };
})();
