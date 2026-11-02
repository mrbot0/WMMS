/* Playbooks: ready-made maintenance sequences that run in one click. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  window.Pages.playbooks = {
    title: "Playbooks",
    render: function (el, App) {
      return Promise.all([API.get("/playbooks"), API.get("/history?limit=500")]).then(function (r) {
        var books = r[0].playbooks, runs = r[1].runs;
        App.setSubtitle("Ready-made maintenance sequences, ordered and safe by design");
        var cards = books.map(function (p) {
          var last = runs.filter(function (x) { return p.actions.indexOf(x.action_id) >= 0; })[0];
          return '<section class="card"><header class="card-head"><h2>' + UI.icon("playbooks") + esc(p.title) + '</h2><div class="card-tools">' + UI.riskBadge(p.risk) + "</div></header>" +
            '<div class="card-body"><p class="muted" style="margin:0 0 10px">' + esc(p.description) + '</p><div class="playbook-meta"><span class="badge">' + p.steps.length + " steps</span>" +
            '<span class="badge">' + UI.icon("clock") + " ~" + Math.max(1, Math.round(p.minutes)) + " min</span>" +
            (last ? '<span class="badge">Last step run ' + esc(UI.relative(last.started)) + "</span>" : "") + "</div>" +
            '<ol class="playbook-steps">' + p.steps.map(function (s) {
              return '<li><span class="grow"><span class="cell-title">' + esc(s.title) + '</span> <span class="cell-sub">· ' + esc(UI.AREA_LABEL[s.area]) + "</span></span>" + UI.riskBadge(s.risk) + "</li>";
            }).join("") + "</ol>" +
            '<div class="page-actions" style="margin-top:14px"><button class="btn btn-primary" data-playbook="' + esc(p.id) + '">' + UI.icon("play") + "Run playbook</button></div></div></section>";
        }).join("");
        el.innerHTML = UI.pageHeader("Playbooks", "Actions that are not safe ask for confirmation once and create a restore point first", "") +
          '<div class="callout callout-info">' + UI.icon("info") + "<div>Playbooks run their steps in order in a single job. Follow the progress in the Activity panel; results are saved in History.</div></div>" +
          '<div class="playbooks">' + cards + "</div>";
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
