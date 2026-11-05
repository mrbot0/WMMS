/* Recommendations: every improvement across areas, with filters and bulk apply. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var filters = { area: "", impact: "", risk: "", query: "", dismissed: false };

  /* Improvements the technician chose to ignore on this PC (kept in this browser). */
  function keyOf(x) { return x.area + "|" + x.title; }

  /* 2.12: "Why?" explains a recommendation in plain words: what was found, why it matters, what the fix does, the risk,
     how long it takes and how to go back. */
  var IMPACT_WHY = { high: "It has a clear effect on speed, space, safety or stability: worth doing during this visit.",
    medium: "It helps, but nothing breaks if it waits for the next visit.", low: "A small improvement: do it when convenient." };
  var RISK_WHY = { safe: "Safe: it changes nothing that could stop something working.",
    moderate: "Moderate: it changes a setting. A restore point is created first and the change can be undone from History.",
    high: "High: it touches delicate parts of Windows. A restore point is created first; read the warning before running it." };
  function explain(App, x) {
    if (!x) return;
    var a = x.action_id ? App.state.actions[x.action_id] : null;
    var righe = [["What was found", x.reason || x.title], ["Why it matters", IMPACT_WHY[x.impact] || ""]];
    if (a) {
      righe.push(["What the fix does", a.description]);
      righe.push(["Risk", (RISK_WHY[a.risk] || a.risk) + (a.warning ? " " + a.warning : "")]);
      righe.push(["How long", a.minutes < 1 ? "Less than a minute." : "About " + Math.round(a.minutes) + " minutes."]);
      righe.push(["Going back", a.kind === "report" ? "Nothing to undo: it only reads." : a.risk === "safe" ? "Usually nothing to undo; History shows what it did."
        : "History › the run › Undo puts back the values it changed; the restore point covers the rest."]);
    } else {
      righe.push(["What to do", "Open " + (UI.AREA_LABEL[x.area] || x.area) + " to see the details: this improvement has no one-click fix."]);
    }
    righe.push(["Found", "By the scan of " + UI.AREA_LABEL[x.area] + ", " + UI.relative(x.scanned) + "."]);
    UI.modal(x.title, '<dl class="why-list">' + righe.map(function (r) { return "<dt>" + esc(r[0]) + "</dt><dd>" + esc(r[1]) + "</dd>"; }).join("") + "</dl>",
      a ? [{ label: "Close", cls: "btn-ghost" }, { label: "Apply", cls: "btn-primary", value: function () { return "run"; } }] : [{ label: "Close", cls: "btn-primary" }])
      .then(function (v) { if (v === "run") App.runActions([x.action_id]); });
  }
  function dismissed() { return Components.store("recDismissed") || []; }
  /* Snoozed improvements come back by themselves after a week. */
  var SNOOZE_DAYS = 7;
  function snoozed() {
    var all = Components.store("recSnoozed") || {}, now = Date.now(), live = {};
    Object.keys(all).forEach(function (k) { if (all[k] > now) live[k] = all[k]; });
    return live;
  }

  window.Pages.recommendations = {
    title: "Recommendations",
    render: function (el, App) {
      // #/recommendations?area=security opens the list filtered on one area (dashboard tiles link here).
      var fromUrl = /[?&]area=(\w+)/.exec(location.hash);
      if (fromUrl && UI.AREAS.indexOf(fromUrl[1]) >= 0) filters.area = fromUrl[1];
      return API.get("/recommendations").then(function (r) {
        var hidden = dismissed(), sleeping = snoozed(), recView = Components.store("recView") || { group: false };
        var everything = r.items.map(function (x) {
          x.snoozedUntil = sleeping[keyOf(x)] || 0;
          x.dismissed = hidden.indexOf(keyOf(x)) >= 0 || !!x.snoozedUntil;
          return x;
        });
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
          "> Show dismissed and snoozed (" + hiddenCount + ")</label>" +
          '<label class="check"><input type="checkbox" id="rec-group"' + (recView.group ? " checked" : "") + "> Group by area</label></div>";

        el.innerHTML = UI.pageHeader("Recommendations", "Generated from the latest scan of each area",
          UI.button("Copy checklist", 'id="rec-copy" title="The listed improvements as a Markdown checklist, for a ticket or an email"', "", "copy") +
          UI.button("CSV", 'id="rec-csv" title="Download the listed improvements as CSV"', "", "download") +
          UI.button("Scan all", 'id="rec-scan"', "", "refresh") + UI.button("Apply all safe fixes", 'id="rec-safe"' + (safeIds.length ? "" : " disabled"), "", "bolt") +
          UI.button("Apply selected", 'id="rec-selected" disabled', "btn-primary", "play")) + kpis +
          '<div class="grid grid-2-1"><div class="stack">' + UI.card("Filters", bar) + UI.card("Improvements", '<div id="rec-list"></div>', '<span class="muted small" id="rec-count"></span>' +
            '<button type="button" class="btn btn-sm" id="rec-pick-all" title="Tick every one-click fix in the list">Select all fixes</button>') + "</div>" +
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
          var groups = recView.group ? UI.AREAS.filter(function (a) { return items.some(function (x) { return x.area === a; }); }) : [null];
          list.innerHTML = groups.map(function (g) {
            var part = g ? items.filter(function (x) { return x.area === g; }) : items;
            return (g ? '<div class="rec-group-title">' + UI.icon(g) + esc(UI.AREA_LABEL[g]) + ' <span class="muted small">' + part.length + "</span></div>" : "") +
              '<ul class="recs">' + part.map(item).join("") + "</ul>";
          }).join("");
          update();
        }
        function item(x) {
            var check = x.action_id ? '<input type="checkbox" class="rec-check" data-pick="' + esc(x.action_id) + '" aria-label="Select ' + esc(x.title) + '">' : '<span class="rec-check" style="width:13px"></span>';
            var dismiss = x.snoozedUntil ? '<button class="btn btn-sm btn-ghost" data-unsnooze="' + esc(keyOf(x)) + '" title="Snoozed until ' + esc(UI.formatDate(new Date(x.snoozedUntil).toISOString(), false)) + '">Wake up</button>'
              : '<button class="btn btn-sm btn-ghost" data-dismiss="' + esc(keyOf(x)) + '" title="' + (x.dismissed ? "Show this improvement again" : "Hide this improvement on this PC") + '">' +
              (x.dismissed ? "Restore" : UI.icon("x")) + "</button>";
            var snooze = x.dismissed ? "" : '<button class="btn btn-sm btn-ghost" data-snooze="' + esc(keyOf(x)) + '" title="Hide it for ' + SNOOZE_DAYS + ' days, then show it again">' + UI.icon("clock") + "</button>";
            dismiss = '<button class="btn btn-sm btn-ghost" data-why="' + esc(keyOf(x)) + '" title="Why it is recommended, what it changes, how to undo it">Why?</button>' + snooze + dismiss;
            return '<li class="rec rec-' + esc(x.impact) + (x.dismissed ? " rec-dismissed" : "") + (x.snoozedUntil ? " rec-snoozed" : "") + '">' + check + '<div class="rec-main"><div class="rec-title">' + esc(x.title) + ' <span class="muted small">· ' +
              esc(UI.AREA_LABEL[x.area] || x.area) + '</span></div><div class="rec-reason">' + esc(x.reason) + '</div><div class="rec-badges">' + UI.impactBadge(x.impact) + UI.riskBadge(x.risk) +
              '<span class="badge">Scanned ' + esc(UI.relative(x.scanned)) + "</span></div></div>" + '<div class="rec-actions">' +
              (x.action_id ? '<button class="btn btn-sm btn-primary" data-run="' + esc(x.action_id) + '">' + UI.icon("play") + 'Apply</button><button class="btn btn-sm" data-schedule="' + esc(x.action_id) + '">' + UI.icon("clock") + "Schedule</button>"
                : '<a class="btn btn-sm" href="#/' + esc(x.area) + '">Open ' + esc(UI.AREA_LABEL[x.area] || x.area) + "</a>") + dismiss + "</div></li>";
        }
        function picked() { return unique(Array.prototype.map.call(list.querySelectorAll("[data-pick]:checked"), function (c) { return c.getAttribute("data-pick"); })); }
        function update() {
          var n = picked().length;
          selectedBtn.disabled = !n;
          selectedBtn.lastChild.textContent = n ? "Apply selected (" + n + ")" : "Apply selected";
        }
        list.addEventListener("change", update);
        list.addEventListener("click", function (e) {
          var why = e.target.closest("[data-why]");
          if (why) { explain(App, everything.filter(function (x) { return keyOf(x) === why.getAttribute("data-why"); })[0]); return; }
          var sn = e.target.closest("[data-snooze],[data-unsnooze]");
          if (sn) {
            var all = snoozed(), k = sn.getAttribute("data-snooze") || sn.getAttribute("data-unsnooze");
            if (sn.hasAttribute("data-snooze")) all[k] = Date.now() + SNOOZE_DAYS * 86400e3; else delete all[k];
            Components.store("recSnoozed", all);
            UI.toast(sn.hasAttribute("data-snooze") ? "Snoozed for " + SNOOZE_DAYS + " days: it comes back by itself." : "Improvement shown again.", "info");
            App.render();
            return;
          }
          var b = e.target.closest("[data-dismiss]");
          if (!b) return;
          var key = b.getAttribute("data-dismiss"), keys = dismissed(), i = keys.indexOf(key);
          if (i >= 0) keys.splice(i, 1); else keys.push(key);
          Components.store("recDismissed", keys);
          UI.toast(i >= 0 ? "Improvement shown again." : "Improvement hidden. Tick Show dismissed to see it.", "info");
          // At the fun level the item slides away before the list is drawn again.
          if (FX.fun() && i < 0) { b.closest(".rec").classList.add("fx-out"); setTimeout(App.render, 300); } else App.render();
        });
        el.querySelectorAll("[data-f]").forEach(function (input) {
          input.addEventListener(input.tagName === "SELECT" || input.type === "checkbox" ? "change" : "input", function () {
            filters[input.getAttribute("data-f")] = input.type === "checkbox" ? input.checked : input.value;
            draw();
          });
        });
        selectedBtn.addEventListener("click", function () { App.runActions(order(picked())); });
        el.querySelector("#rec-group").addEventListener("change", function (e) {
          recView.group = e.target.checked;
          Components.store("recView", recView);
          draw();
        });
        el.querySelector("#rec-pick-all").addEventListener("click", function () {
          var boxes = list.querySelectorAll("[data-pick]"), all = Array.prototype.every.call(boxes, function (c) { return c.checked; });
          boxes.forEach(function (c) { c.checked = !all; });
          update();
        });
        el.querySelector("#rec-copy").addEventListener("click", function () {
          var items = shown();
          if (!items.length) { UI.toast("No improvement in the list.", "info"); return; }
          App.copyText(["Improvements for " + (App.state.info ? App.state.info.hostname : "this PC") + " (" + UI.formatDate(new Date().toISOString(), false) + "):", ""].concat(items.map(function (x) {
            return "- [ ] **" + x.title + "** (" + (UI.AREA_LABEL[x.area] || x.area) + ", " + x.impact + " impact)" + (x.reason ? " – " + x.reason : "");
          })).join("\n"), "Checklist");
        });
        el.querySelector("#rec-csv").addEventListener("click", function () {
          var cell = function (v) { v = String(v == null ? "" : v); return /[",\n;]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
          var rows = [["area", "title", "impact", "risk", "reason", "action", "scanned"]].concat(shown().map(function (x) {
            return [UI.AREA_LABEL[x.area] || x.area, x.title, x.impact, x.risk, x.reason, x.action_id || "", x.scanned];
          }));
          Components.downloadText("wmm-recommendations.csv", String.fromCharCode(0xFEFF) + rows.map(function (r) { return r.map(cell).join(","); }).join("\n"), "text/csv;charset=utf-8");
        });
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
