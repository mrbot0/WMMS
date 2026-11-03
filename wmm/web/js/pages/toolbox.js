/* Toolbox: every tool by area, with Fixes / Reports, search, sorting, multi-select and keyboard navigation. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var KINDS = [["", "All tools"], ["fix", "Fixes"], ["report", "Reports"]];

  function saved() { return Components.store("toolbox") || { area: "", kind: "", query: "", sort: "name", never: false }; }

  window.Pages.toolbox = {
    title: "Toolbox",
    render: function (el, App) {
      var view = saved();
      // #/toolbox?area=network opens on that area (links from the area pages).
      var asked = /[?&]area=(\w+)/.exec(location.hash);
      if (asked && UI.AREAS.indexOf(asked[1]) >= 0) view.area = asked[1];
      return API.get("/history?limit=2000").then(function (h) {
        var all = Object.keys(App.state.actions).map(function (id) { return App.state.actions[id]; });
        var last = {}, week = Date.now() - 7 * 864e5, recent = {};
        h.runs.forEach(function (r) {
          if (!last[r.action_id]) last[r.action_id] = r;
          if (new Date(r.started).getTime() > week) recent[r.action_id] = 1;
        });
        var reports = all.filter(function (a) { return a.kind === "report"; }).length;
        var picked = {};
        App.setSubtitle(all.length + " tools: " + (all.length - reports) + " fixes and " + reports + " read-only reports");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Tools", Components.num(all.length), UI.AREAS.length + " areas", "info") +
          UI.kpi("Fixes", Components.num(all.length - reports), "Change settings or delete files", "warning") +
          UI.kpi("Reports", Components.num(reports), "Read-only diagnostics", "ok") +
          UI.kpi("Used this week", Components.num(Object.keys(recent).length), "Different tools run in 7 days", "info") + "</div>";
        var tabs = '<div class="tabs" role="tablist" aria-label="Area">' + [["", "All", "dashboard"]].concat(UI.AREAS.map(function (a) { return [a, UI.AREA_LABEL[a], a]; })).map(function (t) {
          var n = all.filter(function (a) { return !t[0] || a.area === t[0]; }).length;
          return '<button type="button" role="tab" class="tab" data-area="' + t[0] + '" aria-selected="' + (view.area === t[0]) + '" tabindex="' + (view.area === t[0] ? 0 : -1) + '">' +
            UI.icon(t[2]) + "<span>" + esc(t[1]) + '</span><span class="tab-count">' + n + "</span></button>";
        }).join("") + "</div>";
        var segmented = '<div class="segmented" role="radiogroup" aria-label="Kind">' + KINDS.map(function (k) {
          return '<button type="button" role="radio" data-kind="' + k[0] + '" aria-checked="' + (view.kind === k[0]) + '">' + esc(k[1]) + "</button>";
        }).join("") + "</div>";

        el.innerHTML = UI.pageHeader("Toolbox", "Every maintenance tool in one place",
          '<span class="muted small" id="tb-info">Nothing selected</span>' +
          UI.button(view.list ? "Cards" : "List", 'id="tb-layout" title="Compact list or cards with descriptions"', "", view.list ? "dashboard" : "playbooks") +
          UI.button("Copy", 'id="tb-copy" disabled title="Names and IDs of the selected tools, for a ticket or a script"', "", "copy") +
          UI.button("Run diagnostics", 'id="tb-reports"', "", "reports") +
          UI.button("Clear", 'id="tb-clear" disabled', "", "x") + UI.button("Run selected", 'id="tb-run" disabled', "btn-primary", "play")) + kpis +
          '<section class="card toolbox"><div class="card-body">' + tabs +
          '<div class="tb-bar">' + segmented + UI.hint("Fixes change a setting or delete files. Reports only read the PC and open their output when they finish.") +
          '<label class="dt-search">' + UI.icon("search") + '<span class="sr-only">Search tools</span>' +
          '<input type="search" id="tb-q" placeholder="Search tools… (press / )" value="' + esc(view.query) + '"></label>' +
          '<label class="tb-sort">Sort<select id="tb-sort">' + [["name", "Name"], ["duration", "Shortest first"], ["recent", "Recently run"]].map(function (o) {
            return '<option value="' + o[0] + '"' + (view.sort === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
          }).join("") + '</select></label><label class="check"><input type="checkbox" id="tb-never"' + (view.never ? " checked" : "") + "> Never run</label>" +
          '<label class="check"><input type="checkbox" id="tb-favs"' + (view.favs ? " checked" : "") + "> Favorites</label>" +
          '<label class="check" title="Only tools that run without confirmation"><input type="checkbox" id="tb-safe"' + (view.safe ? " checked" : "") + "> Safe only</label></div>" +
          '<div id="tb-list" aria-live="polite"></div></div></section>';
        var list = el.querySelector("#tb-list"), visibleReports = [];

        function shown() {
          var words = view.query.toLowerCase().split(/\s+/).filter(Boolean), favs = App.favorites();
          var sorts = {
            name: function (x, y) { return x.title.localeCompare(y.title); },
            duration: function (x, y) { return x.minutes - y.minutes || x.title.localeCompare(y.title); },
            recent: function (x, y) {
              var a = last[x.id] ? last[x.id].started : "", b = last[y.id] ? last[y.id].started : "";
              return a < b ? 1 : a > b ? -1 : x.title.localeCompare(y.title);
            }
          };
          return all.filter(function (a) {
            var text = (a.title + " " + a.description + " " + a.id).toLowerCase();
            return (!view.area || a.area === view.area) && (!view.kind || a.kind === view.kind) && (!view.never || !last[a.id]) &&
              (!view.favs || favs.indexOf(a.id) >= 0) && (!view.safe || a.risk === "safe") &&
              words.every(function (w) { return text.indexOf(w) >= 0; });
          }).sort(sorts[view.sort] || sorts.name);
        }
        function draw() {
          Components.store("toolbox", { area: view.area, kind: view.kind, query: view.query, sort: view.sort, never: view.never, favs: view.favs, safe: view.safe, list: view.list });
          var items = shown();
          visibleReports = items.filter(function (a) { return a.kind === "report"; }).map(function (a) { return a.id; });
          var areas = view.area ? [view.area] : UI.AREAS;
          var html = areas.map(function (area) {
            var group = items.filter(function (a) { return a.area === area; });
            if (!group.length) return "";
            return (view.area ? "" : '<div class="section-title">' + UI.icon(area) + esc(UI.AREA_LABEL[area]) + '<span class="extra">' + group.length + " tools</span></div>") +
              '<div class="action-grid">' + group.map(function (a) { return UI.toolCard(a, last[a.id], { pick: true, picked: !!picked[a.id] }); }).join("") + "</div>";
          }).join("");
          list.innerHTML = html || '<div class="empty-state">' + UI.icon("search") + "<h2>No tool matches</h2><p>Change the area, the kind or the search text.</p></div>";
          list.classList.toggle("tb-list", !!view.list);
          el.querySelector("#tb-reports").disabled = !visibleReports.length;
          el.querySelector("#tb-reports").title = visibleReports.length + " read-only reports in the current view";
          update();
        }
        function update() {
          var ids = Object.keys(picked);
          var total = ids.reduce(function (s, id) { return s + App.state.actions[id].minutes; }, 0);
          el.querySelector("#tb-info").textContent = ids.length ? ids.length + " selected · " + UI.duration(total) : "Nothing selected";
          el.querySelector("#tb-run").disabled = el.querySelector("#tb-clear").disabled = el.querySelector("#tb-copy").disabled = !ids.length;
        }
        function selectTab(btn) {
          view.area = btn.getAttribute("data-area");
          el.querySelectorAll(".tab").forEach(function (t) {
            var on = t === btn;
            t.setAttribute("aria-selected", String(on));
            t.tabIndex = on ? 0 : -1;
          });
          btn.focus();
          draw();
        }

        var tabList = el.querySelector(".tabs");
        tabList.addEventListener("click", function (e) { var t = e.target.closest(".tab"); if (t) selectTab(t); });
        // Arrow keys move between tabs, Home / End jump to the ends (WAI-ARIA tabs pattern).
        tabList.addEventListener("keydown", function (e) {
          var tabs = Array.prototype.slice.call(tabList.querySelectorAll(".tab")), i = tabs.indexOf(document.activeElement);
          if (i < 0) return;
          var next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
          if (next == null) return;
          e.preventDefault();
          selectTab(tabs[(next + tabs.length) % tabs.length]);
        });
        el.querySelector(".segmented").addEventListener("click", function (e) {
          var b = e.target.closest("[data-kind]");
          if (!b) return;
          view.kind = b.getAttribute("data-kind");
          el.querySelectorAll("[data-kind]").forEach(function (x) { x.setAttribute("aria-checked", String(x === b)); });
          draw();
        });
        el.querySelector("#tb-q").addEventListener("input", function (e) { view.query = e.target.value; draw(); });
        el.querySelector("#tb-layout").addEventListener("click", function (e) {
          view.list = !view.list;
          e.currentTarget.lastChild.textContent = view.list ? "Cards" : "List";
          draw();
        });
        el.querySelector("#tb-copy").addEventListener("click", function () {
          App.copyText(Object.keys(picked).map(function (id) { var a = App.state.actions[id]; return a.title + " (" + id + ", " + a.risk + ", ~" + Math.max(1, Math.round(a.minutes)) + " min)"; }).join("\n"), "Tools");
        });
        el.querySelector("#tb-sort").addEventListener("change", function (e) { view.sort = e.target.value; draw(); });
        el.querySelector("#tb-favs").addEventListener("change", function (e) {
          view.favs = e.target.checked;
          if (view.favs && !App.favorites().length) UI.toast("No favorites yet: star a tool in its details or in Actions.", "info");
          draw();
        });
        el.querySelector("#tb-safe").addEventListener("change", function (e) { view.safe = e.target.checked; draw(); });
        el.querySelector("#tb-never").addEventListener("change", function (e) { view.never = e.target.checked; draw(); });
        list.addEventListener("change", function (e) {
          if (!e.target.hasAttribute("data-pick")) return;
          var card = e.target.closest("[data-id]"), id = card.getAttribute("data-id");
          if (e.target.checked) picked[id] = 1; else delete picked[id];
          card.classList.toggle("picked", e.target.checked);
          update();
        });
        list.addEventListener("click", function (e) {
          var info = e.target.closest("[data-detail]");
          if (info) App.actionDetail(info.closest("[data-id]").getAttribute("data-id"));
        });
        // Enter on a focused card opens its details.
        list.addEventListener("keydown", function (e) {
          if (e.key === "Enter" && e.target.classList && e.target.classList.contains("tool-card")) App.actionDetail(e.target.getAttribute("data-id"));
        });
        el.querySelector("#tb-clear").addEventListener("click", function () { picked = {}; draw(); });
        el.querySelector("#tb-run").addEventListener("click", function () { App.runActions(App.order(Object.keys(picked))); picked = {}; draw(); });
        el.querySelector("#tb-reports").addEventListener("click", function () { App.runActions(visibleReports); });
        // "/" focuses the search box while this page is open.
        function slash(e) {
          if (e.key !== "/" || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || !App.isCurrent("toolbox")) return;
          e.preventDefault();
          e.stopImmediatePropagation();
          el.querySelector("#tb-q").focus();
        }
        document.addEventListener("keydown", slash, true);
        App.onLeave(function () { document.removeEventListener("keydown", slash, true); });
        draw();
      });
    }
  };
})();
