/* Actions: the whole catalog with search, filters, favorites, multi-select and estimated duration. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var view = { query: "", area: "", risk: "", kind: "", favorites: false, sort: "name" };
  var RISK_RANK = { safe: 0, moderate: 1, high: 2 };
  var SORTS = {
    name: function (x, y) { return x.title.localeCompare(y.title); },
    duration: function (x, y) { return x.minutes - y.minutes; },
    risk: function (x, y) { return RISK_RANK[x.risk] - RISK_RANK[y.risk]; },
    recent: null  // needs the last runs, set in render
  };

  function favorites() { return App.favorites(); }
  function toggleFavorite(id) { return App.toggleFavorite(id); }
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

        var counts = { safe: 0, moderate: 0, high: 0 }, reports = 0;
        all.forEach(function (a) { counts[a.risk]++; if (a.kind === "report") reports++; });
        var kpis = '<div class="grid grid-5">' +
          UI.kpi("Actions", String(all.length), UI.AREAS.length + " areas", "info") +
          UI.kpi("Safe", String(counts.safe), "Run without confirmation", "ok") +
          UI.kpi("Moderate / high", counts.moderate + " <small>/ " + counts.high + "</small>", "Confirmation and restore point", "warning") +
          UI.kpi("Reports", String(reports), "Read-only diagnostics", "ok") +
          UI.kpi("Favorites", String(favorites().length), "Shown first and on the dashboard", "info") + "</div>";
        var sel = function (key, label, options) {
          return "<label>" + label + '<select data-v="' + key + '"><option value="">All</option>' + options.map(function (o) {
            return '<option value="' + o[0] + '"' + (view[key] === o[0] ? " selected" : "") + ">" + esc(o[1]) + "</option>";
          }).join("") + "</select></label>";
        };
        el.innerHTML = UI.pageHeader("Actions", "Select several actions to run them as one job, in a safe order",
          '<span class="muted small" id="pick-info">Nothing selected</span>' + UI.button("Select visible", 'id="pick-visible"', "", "check") + UI.button("Clear", 'id="pick-clear" disabled', "", "x") +
          UI.button("Save as playbook", 'id="pick-save" disabled title="Keep the selection as one of My playbooks, to run it again with one click"', "", "playbooks") +
          UI.button("Run selected", 'id="pick-run" disabled', "btn-primary", "play")) + kpis +
          '<div class="grid">' + UI.card("Filters", '<div class="filters"><label>Search<input type="search" data-v="query" value="' + esc(view.query) + '" placeholder="Search actions…"></label>' +
            sel("area", "Area", UI.AREAS.map(function (a) { return [a, UI.AREA_LABEL[a]]; })) +
            sel("risk", "Risk", [["safe", "Safe"], ["moderate", "Moderate"], ["high", "High risk"]]) +
            sel("kind", "Kind", [["fix", "Fixes"], ["report", "Reports (read-only)"]]) +
            '<label>Sort by<select data-v="sort">' + [["name", "Name"], ["duration", "Shortest first"], ["risk", "Safest first"], ["recent", "Recently run"]].map(function (o) {
              return '<option value="' + o[0] + '"' + (view.sort === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
            }).join("") + "</select></label>" +
            '<label class="check"><input type="checkbox" data-v="favorites"' + (view.favorites ? " checked" : "") + "> Favorites only</label></div>") + "</div>" +
          '<div id="action-list"></div>';
        var list = el.querySelector("#action-list");

        function draw() {
          var fav = favorites(), q = view.query.toLowerCase();
          var shown = all.filter(function (a) {
            return (!view.area || a.area === view.area) && (!view.risk || a.risk === view.risk) && (!view.kind || a.kind === view.kind) &&
              (!view.favorites || fav.indexOf(a.id) >= 0) &&
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
                return UI.toolCard(a, last[a.id], { pick: true, picked: !!picked[a.id], star: fav.indexOf(a.id) >= 0 });
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
          el.querySelector("#pick-save").disabled = !ids.length;
        }
        el.querySelector("#pick-save").addEventListener("click", function () {
          var ids = order(Object.keys(picked));
          UI.modal("Save as playbook", '<form class="form" onsubmit="return false"><label>Name<input name="n" maxlength="60" placeholder="e.g. Monthly visit at the office" required></label>' +
            '<p class="muted small" style="margin:0">' + ids.length + " actions, in a safe order. It appears in Playbooks › My playbooks.</p></form>",
            [{ label: "Cancel", cls: "btn-ghost" }, { label: "Save", cls: "btn-primary", value: function (w) { return w.querySelector("input").value.trim(); } }]).then(function (name) {
            if (!name) return;
            Pages.playbooks.saveMine(name, ids);
            UI.toast("Saved in Playbooks › My playbooks.", "ok");
          });
        });
        list.addEventListener("change", function (e) {
          if (!e.target.hasAttribute("data-pick")) return;
          var card = e.target.closest("[data-id]"), id = card.getAttribute("data-id");
          if (e.target.checked) picked[id] = 1; else delete picked[id];
          card.classList.toggle("picked", e.target.checked);
          update();
        });
        list.addEventListener("click", function (e) {
          var info = e.target.closest("[data-detail]");
          if (info) { App.actionDetail(info.closest("[data-id]").getAttribute("data-id")); return; }
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
