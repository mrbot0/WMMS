/* Actions: the whole catalog with search, filters, favorites, multi-select and estimated duration. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var view = { query: "", area: "", risk: "", favorites: false, sort: "name" };
  var RISK_RANK = { safe: 0, moderate: 1, high: 2 };
  var SORTS = {
    name: function (x, y) { return x.title.localeCompare(y.title); },
    duration: function (x, y) { return x.minutes - y.minutes; },
    risk: function (x, y) { return RISK_RANK[x.risk] - RISK_RANK[y.risk]; },
    recent: null  // needs the last runs, set in render
  };

  /* Everything known about one action, with run, schedule and favorite in one place. */
  function detail(App, a, r) {
    var fav = favorites().indexOf(a.id) >= 0;
    UI.modal(a.title, '<p class="modal-text">' + esc(a.description) + "</p>" +
      (a.risk !== "safe" && a.warning ? '<div class="callout callout-warning">' + UI.icon("shield") + "<div>" + esc(a.warning) + " A restore point is created first.</div></div>" : "") +
      UI.definition([["Area", esc(UI.AREA_LABEL[a.area])], ["Risk", UI.riskBadge(a.risk)], ["Estimated time", esc(UI.duration(a.minutes))],
        ["Last run", r ? UI.statusBadge(r.status) + " " + esc(UI.relative(r.finished || r.started)) + (r.note ? " · " + esc(r.note) : "") : "Never"],
        ["Identifier", '<span class="cell-mono">' + esc(a.id) + "</span>"]]),
      [{ label: fav ? "Remove favorite" : "Add to favorites", cls: "btn-ghost", value: function () { return "fav"; } },
        { label: "Schedule", cls: "", value: function () { return "schedule"; } },
        { label: "Run now", cls: "btn-primary", value: function () { return "run"; } }]
    ).then(function (v) {
      if (v === "run") App.runActions([a.id]);
      if (v === "schedule") App.schedule(a.id);
      if (v === "fav") { var on = toggleFavorite(a.id); UI.toast(on ? "Added to favorites." : "Removed from favorites.", "ok"); App.render(); }
    });
  }

  function favorites() { return Components.store("favorites") || []; }
  function toggleFavorite(id) {
    var list = favorites(), i = list.indexOf(id);
    if (i >= 0) list.splice(i, 1); else list.push(id);
    Components.store("favorites", list);
    return i < 0;
  }
  function order(ids) {
    var rank = function (x) { return x === "integrity.dism" ? 0 : x === "integrity.sfc" ? 1 : 2; };
    return ids.slice().sort(function (a, b) { return rank(a) - rank(b); });
  }
  function minutes(total) { return total < 1 ? "< 1 min" : total < 60 ? "~" + Math.round(total) + " min" : "~" + (total / 60).toFixed(1) + " h"; }

  window.Pages.actions = {
    title: "Actions",
    render: function (el, App) {
      return API.get("/history?limit=2000").then(function (h) {
        var all = Object.keys(App.state.actions).map(function (id) { return App.state.actions[id]; });
        var last = {};
        h.runs.forEach(function (r) { if (!last[r.action_id]) last[r.action_id] = r; });
        var picked = {}, visible = [];
        SORTS.recent = function (x, y) {
          var a = last[x.id] ? last[x.id].started : "", b = last[y.id] ? last[y.id].started : "";
          return a < b ? 1 : a > b ? -1 : 0;
        };
        App.setSubtitle(all.length + " maintenance actions across " + UI.AREAS.length + " areas");

        var counts = { safe: 0, moderate: 0, high: 0 };
        all.forEach(function (a) { counts[a.risk]++; });
        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Actions", String(all.length), UI.AREAS.length + " areas", "info") +
          UI.kpi("Safe", String(counts.safe), "Run without confirmation", "ok") +
          UI.kpi("Moderate / high", counts.moderate + " <small>/ " + counts.high + "</small>", "Confirmation and restore point", "warning") +
          UI.kpi("Favorites", String(favorites().length), "Shown first and on the dashboard", "info") + "</div>";
        var sel = function (key, label, options) {
          return "<label>" + label + '<select data-v="' + key + '"><option value="">All</option>' + options.map(function (o) {
            return '<option value="' + o[0] + '"' + (view[key] === o[0] ? " selected" : "") + ">" + esc(o[1]) + "</option>";
          }).join("") + "</select></label>";
        };
        el.innerHTML = UI.pageHeader("Actions", "Select several actions to run them as one job, in a safe order",
          '<span class="muted small" id="pick-info">Nothing selected</span>' + UI.button("Select visible", 'id="pick-visible"', "", "check") + UI.button("Clear", 'id="pick-clear" disabled', "", "x") +
          UI.button("Run selected", 'id="pick-run" disabled', "btn-primary", "play")) + kpis +
          '<div class="grid">' + UI.card("Filters", '<div class="filters"><label>Search<input type="search" data-v="query" value="' + esc(view.query) + '" placeholder="Search actions…"></label>' +
            sel("area", "Area", UI.AREAS.map(function (a) { return [a, UI.AREA_LABEL[a]]; })) +
            sel("risk", "Risk", [["safe", "Safe"], ["moderate", "Moderate"], ["high", "High risk"]]) +
            '<label>Sort by<select data-v="sort">' + [["name", "Name"], ["duration", "Shortest first"], ["risk", "Safest first"], ["recent", "Recently run"]].map(function (o) {
              return '<option value="' + o[0] + '"' + (view.sort === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
            }).join("") + "</select></label>" +
            '<label class="check"><input type="checkbox" data-v="favorites"' + (view.favorites ? " checked" : "") + "> Favorites only</label></div>") + "</div>" +
          '<div id="action-list"></div>';
        var list = el.querySelector("#action-list");

        function draw() {
          var fav = favorites(), q = view.query.toLowerCase();
          var shown = all.filter(function (a) {
            return (!view.area || a.area === view.area) && (!view.risk || a.risk === view.risk) && (!view.favorites || fav.indexOf(a.id) >= 0) &&
              (!q || (a.title + " " + a.description + " " + a.id).toLowerCase().indexOf(q) >= 0);
          });
          visible = shown.map(function (a) { return a.id; });
          var html = UI.AREAS.map(function (area) {
            var items = shown.filter(function (a) { return a.area === area; }).sort(function (x, y) {
              return (fav.indexOf(y.id) >= 0) - (fav.indexOf(x.id) >= 0) || SORTS[view.sort](x, y) || x.title.localeCompare(y.title);
            });
            if (!items.length) return "";
            return '<div class="section-title" data-area="' + area + '"><span class="tile-icon" style="width:26px;height:26px">' + UI.icon(area) + "</span>" + esc(UI.AREA_LABEL[area]) +
              '<span class="extra">' + items.length + " actions</span></div>" + '<div class="action-grid">' + items.map(function (a) {
                var r = last[a.id], star = fav.indexOf(a.id) >= 0;
                return '<div class="action-card' + (picked[a.id] ? " picked" : "") + '" data-id="' + esc(a.id) + '"><div class="action-top">' +
                  '<input type="checkbox" data-pick aria-label="Select ' + esc(a.title) + '"' + (picked[a.id] ? " checked" : "") + ">" +
                  '<button type="button" class="cell-title grow link-btn" data-detail title="Details">' + esc(a.title) + "</button>" +
                  '<button type="button" class="star' + (star ? " on" : "") + '" data-star title="' + (star ? "Remove from favorites" : "Add to favorites") + '" aria-pressed="' + star + '">★</button></div>' +
                  '<div class="cell-sub">' + esc(a.description) + "</div>" +
                  '<div class="action-foot">' + UI.riskBadge(a.risk) + '<span class="badge">' + UI.icon("clock") + esc(UI.duration(a.minutes)) + "</span>" +
                  (r ? UI.statusBadge(r.status) + '<span class="cell-sub">' + esc(UI.relative(r.finished || r.started)) + "</span>" : '<span class="cell-sub">Never run</span>') +
                  '<span class="grow"></span><button class="btn btn-sm" data-run="' + esc(a.id) + '">' + UI.icon("play") + 'Run</button><button class="btn btn-sm" data-schedule="' + esc(a.id) + '">' +
                  UI.icon("clock") + "</button></div></div>";
              }).join("") + "</div>";
          }).join("");
          list.innerHTML = html || '<section class="card"><div class="empty-state">' + UI.icon("search") + "<h2>No action matches</h2><p>Change the filters or the search text.</p></div></section>";
          update();
        }
        function update() {
          var ids = Object.keys(picked);
          var total = ids.reduce(function (s, id) { return s + App.state.actions[id].minutes; }, 0);
          var risky = ids.filter(function (id) { return App.state.actions[id].risk !== "safe"; }).length;
          el.querySelector("#pick-info").textContent = ids.length ? ids.length + " selected · " + minutes(total) + (risky ? " · " + risky + " need confirmation" : "") : "Nothing selected";
          el.querySelector("#pick-run").disabled = !ids.length;
          el.querySelector("#pick-clear").disabled = !ids.length;
        }
        list.addEventListener("change", function (e) {
          if (!e.target.hasAttribute("data-pick")) return;
          var card = e.target.closest("[data-id]"), id = card.getAttribute("data-id");
          if (e.target.checked) picked[id] = 1; else delete picked[id];
          card.classList.toggle("picked", e.target.checked);
          update();
        });
        list.addEventListener("click", function (e) {
          var info = e.target.closest("[data-detail]");
          if (info) { var id = info.closest("[data-id]").getAttribute("data-id"); detail(App, App.state.actions[id], last[id]); return; }
          var star = e.target.closest("[data-star]");
          if (!star) return;
          var on = toggleFavorite(star.closest("[data-id]").getAttribute("data-id"));
          if (on) FX.burst(star);
          UI.toast(on ? "Added to favorites: shown on the dashboard." : "Removed from favorites.", "ok");
          draw();
        });
        el.querySelectorAll("[data-v]").forEach(function (input) {
          input.addEventListener(input.type === "search" ? "input" : "change", function () {
            view[input.getAttribute("data-v")] = input.type === "checkbox" ? input.checked : input.value;
            draw();
          });
        });
        el.querySelector("#pick-clear").addEventListener("click", function () { picked = {}; draw(); });
        el.querySelector("#pick-visible").addEventListener("click", function () {
          visible.forEach(function (id) { picked[id] = 1; });
          draw();
        });
        el.querySelector("#pick-run").addEventListener("click", function () {
          App.runActions(order(Object.keys(picked)));
          picked = {};
          draw();
        });
        draw();
      });
    }
  };
})();
