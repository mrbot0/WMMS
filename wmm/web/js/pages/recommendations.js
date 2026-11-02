/* Recommendations: every improvement across areas, with filters and bulk apply. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var filters = { area: "", impact: "", risk: "", query: "", dismissed: false };

  /* Improvements the technician chose to ignore on this PC (kept in this browser). */
  function keyOf(x) { return x.area + "|" + x.title; }
  function dismissed() { return Components.store("recDismissed") || []; }

  window.Pages.recommendations = {
    title: "Recommendations",
    render: function (el, App) {
      // #/recommendations?area=security opens the list filtered on one area (dashboard tiles link here).
      var fromUrl = /[?&]area=(\w+)/.exec(location.hash);
      if (fromUrl && UI.AREAS.indexOf(fromUrl[1]) >= 0) filters.area = fromUrl[1];
      return API.get("/recommendations").then(function (r) {
        var hidden = dismissed();
        var everything = r.items.map(function (x) { x.dismissed = hidden.indexOf(keyOf(x)) >= 0; return x; });
        var all = everything.filter(function (x) { return !x.dismissed; });
        var hiddenCount = everything.length - all.length;
        App.setSubtitle("All recommended improvements from the latest scans");
        var byArea = {};
        all.forEach(function (x) { byArea[x.area] = (byArea[x.area] || 0) + 1; });
        var areaSeries = Object.keys(byArea).sort(function (a, b) { return byArea[b] - byArea[a]; }).map(function (a) {
          return { label: UI.AREA_LABEL[a] || a, value: byArea[a], color: Charts.PALETTE[UI.AREAS.indexOf(a) % Charts.PALETTE.length] };
        });
        var count = function (k, v) { return all.filter(function (x) { return x[k] === v; }).length; };
        var actionable = all.filter(function (x) { return x.action_id; });
        var safeIds = unique(actionable.filter(function (x) { return x.risk === "safe"; }).map(function (x) { return x.action_id; }));

        var kpis = '<div class="grid grid-5">' +
          UI.kpi("Open improvements", Components.num(all.length), Object.keys(byArea).length + " areas", all.length ? "info" : "ok") +
          UI.kpi("High impact", Components.num(count("impact", "high")), "Fix during this visit", count("impact", "high") ? "error" : "ok") +
          UI.kpi("Medium impact", Components.num(count("impact", "medium")), "Recommended", count("impact", "medium") ? "warning" : "ok") +
          UI.kpi("One-click fixes", Components.num(actionable.length), safeIds.length + " safe, no confirmation", "info") +
          UI.kpi("Manual steps", Components.num(all.length - actionable.length), "Advice for the technician", "info") + "</div>";

        var sel = function (key, label, options) {
          return "<label>" + label + '<select data-f="' + key + '"><option value="">All</option>' + options.map(function (o) {
            return '<option value="' + o[0] + '"' + (filters[key] === o[0] ? " selected" : "") + ">" + esc(o[1]) + "</option>";
          }).join("") + "</select></label>";
        };
        var bar = '<div class="filters">' + '<label>Search<input type="search" data-f="query" value="' + esc(filters.query) + '" placeholder="Search improvements…"></label>' +
          sel("area", "Area", Object.keys(byArea).concat(filters.area && !byArea[filters.area] ? [filters.area] : []).map(function (a) { return [a, UI.AREA_LABEL[a] || a]; })) +
          sel("impact", "Impact", [["high", "High"], ["medium", "Medium"], ["low", "Low"]]) +
          sel("risk", "Risk", [["safe", "Safe"], ["moderate", "Moderate"], ["high", "High risk"]]) +
          '<label class="check"><input type="checkbox" data-f="dismissed"' + (filters.dismissed ? " checked" : "") + (hiddenCount ? "" : " disabled") +
          "> Show dismissed (" + hiddenCount + ")</label></div>";

        el.innerHTML = UI.pageHeader("Recommendations", "Generated from the latest scan of each area",
          UI.button("Scan all", 'id="rec-scan"', "", "refresh") + UI.button("Apply all safe fixes", 'id="rec-safe"' + (safeIds.length ? "" : " disabled"), "", "bolt") +
          UI.button("Apply selected", 'id="rec-selected" disabled', "btn-primary", "play")) + kpis +
          '<div class="grid grid-2-1"><div class="stack">' + UI.card("Filters", bar) + UI.card("Improvements", '<div id="rec-list"></div>', '<span class="muted small" id="rec-count"></span>') + "</div>" +
          '<div class="stack">' + UI.card("By area", '<div class="chart-row">' + Charts.donut(areaSeries, { center: all.length, sub: "open", empty: "Nothing open" }) + Charts.legend(areaSeries) + "</div>") +
          UI.card("By impact", Charts.hbars([
            { label: "High", value: count("impact", "high"), color: "#C42B1C" }, { label: "Medium", value: count("impact", "medium"), color: "#C27C0E" }, { label: "Low", value: count("impact", "low"), color: "#0F6CBD" }
          ])) + "</div></div>";

        var list = el.querySelector("#rec-list"), selectedBtn = el.querySelector("#rec-selected");
        function shown() {
          var q = filters.query.toLowerCase();
          return (filters.dismissed ? everything : all).filter(function (x) {
            return (!filters.area || x.area === filters.area) && (!filters.impact || x.impact === filters.impact) && (!filters.risk || x.risk === filters.risk) &&
              (!q || (x.title + " " + x.reason).toLowerCase().indexOf(q) >= 0);
          });
        }
        function draw() {
          var items = shown();
          el.querySelector("#rec-count").textContent = items.length + " of " + (filters.dismissed ? everything : all).length;
          if (!items.length) { list.innerHTML = UI.recommendations([]); return; }
          list.innerHTML = '<ul class="recs">' + items.map(function (x) {
            var check = x.action_id ? '<input type="checkbox" class="rec-check" data-pick="' + esc(x.action_id) + '" aria-label="Select ' + esc(x.title) + '">' : '<span class="rec-check" style="width:13px"></span>';
            var dismiss = '<button class="btn btn-sm btn-ghost" data-dismiss="' + esc(keyOf(x)) + '" title="' + (x.dismissed ? "Show this improvement again" : "Hide this improvement on this PC") + '">' +
              (x.dismissed ? "Restore" : UI.icon("x")) + "</button>";
            return '<li class="rec rec-' + esc(x.impact) + (x.dismissed ? " rec-dismissed" : "") + '">' + check + '<div class="rec-main"><div class="rec-title">' + esc(x.title) + ' <span class="muted small">· ' +
              esc(UI.AREA_LABEL[x.area] || x.area) + '</span></div><div class="rec-reason">' + esc(x.reason) + '</div><div class="rec-badges">' + UI.impactBadge(x.impact) + UI.riskBadge(x.risk) +
              '<span class="badge">Scanned ' + esc(UI.relative(x.scanned)) + "</span></div></div>" + '<div class="rec-actions">' +
              (x.action_id ? '<button class="btn btn-sm btn-primary" data-run="' + esc(x.action_id) + '">' + UI.icon("play") + 'Apply</button><button class="btn btn-sm" data-schedule="' + esc(x.action_id) + '">' + UI.icon("clock") + "Schedule</button>"
                : '<a class="btn btn-sm" href="#/' + esc(x.area) + '">Open ' + esc(UI.AREA_LABEL[x.area] || x.area) + "</a>") + dismiss + "</div></li>";
          }).join("") + "</ul>";
          update();
        }
        function picked() { return unique(Array.prototype.map.call(list.querySelectorAll("[data-pick]:checked"), function (c) { return c.getAttribute("data-pick"); })); }
        function update() {
          var n = picked().length;
          selectedBtn.disabled = !n;
          selectedBtn.lastChild.textContent = n ? "Apply selected (" + n + ")" : "Apply selected";
        }
        list.addEventListener("change", update);
        list.addEventListener("click", function (e) {
          var b = e.target.closest("[data-dismiss]");
          if (!b) return;
          var key = b.getAttribute("data-dismiss"), keys = dismissed(), i = keys.indexOf(key);
          if (i >= 0) keys.splice(i, 1); else keys.push(key);
          Components.store("recDismissed", keys);
          UI.toast(i >= 0 ? "Improvement shown again." : "Improvement hidden. Tick Show dismissed to see it.", "info");
          App.render();
        });
        el.querySelectorAll("[data-f]").forEach(function (input) {
          input.addEventListener(input.tagName === "SELECT" || input.type === "checkbox" ? "change" : "input", function () {
            filters[input.getAttribute("data-f")] = input.type === "checkbox" ? input.checked : input.value;
            draw();
          });
        });
        selectedBtn.addEventListener("click", function () { App.runActions(order(picked())); });
        el.querySelector("#rec-safe").addEventListener("click", function () { App.runActions(order(safeIds)); });
        el.querySelector("#rec-scan").addEventListener("click", App.scanAll);
        draw();
      });
    }
  };

  function unique(list) { return list.filter(function (x, i) { return list.indexOf(x) === i; }); }
  /* DISM before SFC, like the playbooks. */
  function order(ids) {
    return ids.slice().sort(function (a, b) {
      var rank = function (x) { return x === "integrity.dism" ? 0 : x === "integrity.sfc" ? 1 : 2; };
      return rank(a) - rank(b);
    });
  }
})();
