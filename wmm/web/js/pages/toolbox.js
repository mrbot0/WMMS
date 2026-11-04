/* Toolbox: the whole catalog of tools (it replaces the old Actions page). A side panel picks the area and the filters,
   the main column searches and shows the tools as cards or a list, and a selection bar runs, saves or copies a batch. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var KINDS = [["", "All"], ["fix", "Fixes"], ["report", "Reports"]];
  var RISKS = [["", "Any"], ["safe", "Safe"], ["moderate", "Moderate"], ["high", "High"]];
  var SORTS = [["name", "Name"], ["duration", "Shortest first"], ["risk", "Safest first"], ["recent", "Recently run"]];
  var RISK_RANK = { safe: 0, moderate: 1, high: 2 };

  function saved() {
    var v = Components.store("toolbox") || {};
    // Views saved before 1.9 had a "safe only" switch: it becomes the Safe risk filter.
    return { area: v.area || "", kind: v.kind || "", risk: v.risk || (v.safe ? "safe" : ""), query: v.query || "", sort: v.sort || "name",
      never: !!v.never, favs: !!v.favs, list: !!v.list };
  }
  // Search ignores case and accents ("piu" finds "più"), and looks at the Italian text too when the console is in Italian.
  function fold(text) { return String(text || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""); }
  function local(text) { return window.I18N ? I18N.t(text) : text; }
  function minutes(total) { return total < 1 ? "< 1 min" : total < 60 ? "~" + Math.round(total) + " min" : "~" + (total / 60).toFixed(1) + " h"; }
  function choice(name, options, current) {
    return '<div class="segmented tb-seg" role="radiogroup" aria-label="' + name + '">' + options.map(function (o) {
      return '<button type="button" role="radio" data-' + name + '="' + o[0] + '" aria-checked="' + (current === o[0]) + '">' + esc(o[1]) + "</button>";
    }).join("") + "</div>";
  }

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
        var safeFixes = all.filter(function (a) { return a.kind !== "report" && a.risk === "safe"; }).length;
        var picked = {}, visible = [];
        App.setSubtitle(all.length + " tools: " + (all.length - reports) + " fixes and " + reports + " read-only reports");

        var kpis = '<div class="grid grid-5">' +
          UI.kpi("Tools", Components.num(all.length), UI.AREAS.length + " areas", "info") +
          UI.kpi("Fixes", Components.num(all.length - reports), safeFixes + " safe, the others ask first", "warning") +
          UI.kpi("Reports", Components.num(reports), "Read-only diagnostics", "ok") +
          UI.kpi("Favorites", '<span id="tb-fav-count">' + App.favorites().length + "</span>", "Starred tools, shown first and on the dashboard", "info") +
          UI.kpi("Used this week", Components.num(Object.keys(recent).length), "Different tools run in 7 days", "info") + "</div>";

        var areas = '<nav class="tb-areas" role="tablist" aria-label="Area" aria-orientation="vertical">' +
          [["", "All areas", "dashboard"]].concat(UI.AREAS.map(function (a) { return [a, UI.AREA_LABEL[a], a]; })).map(function (t) {
            var n = all.filter(function (a) { return !t[0] || a.area === t[0]; }).length;
            return '<button type="button" role="tab" class="tb-area" data-area="' + t[0] + '" aria-selected="' + (view.area === t[0]) + '" tabindex="' + (view.area === t[0] ? 0 : -1) + '">' +
              UI.icon(t[2]) + '<span class="grow">' + esc(t[1]) + '</span><span class="tab-count">' + n + "</span></button>";
          }).join("") + "</nav>";
        var filters = '<div class="tb-filters">' +
          '<div class="tb-filter"><span class="tb-label">Kind ' + UI.hint("Fixes change a setting or delete files. Reports only read the PC and open their output when they finish.") + "</span>" + choice("kind", KINDS, view.kind) + "</div>" +
          '<div class="tb-filter"><span class="tb-label">Risk ' + UI.hint("Safe tools run without asking. Moderate and high ones ask first and create a restore point.") + "</span>" + choice("risk", RISKS, view.risk) + "</div>" +
          '<div class="tb-filter"><label class="tb-label" for="tb-sort">Sort</label><select id="tb-sort">' + SORTS.map(function (o) {
            return '<option value="' + o[0] + '"' + (view.sort === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
          }).join("") + "</select></div>" +
          '<label class="check"><input type="checkbox" id="tb-favs"' + (view.favs ? " checked" : "") + "> Favorites only</label>" +
          '<label class="check"><input type="checkbox" id="tb-never"' + (view.never ? " checked" : "") + "> Never run</label>" +
          '<button type="button" class="btn btn-sm btn-ghost" id="tb-reset">' + UI.icon("x") + "Reset filters</button></div>";

        el.innerHTML = UI.pageHeader("Toolbox", "Every maintenance tool in one place: find it, run it, schedule it or combine several",
          UI.button("Run diagnostics", 'id="tb-reports" title="Run every read-only report in the current view"', "", "reports") +
          UI.button(view.list ? "Cards" : "List", 'id="tb-layout" title="Compact list or cards with descriptions"', "", view.list ? "dashboard" : "playbooks")) + kpis +
          '<div class="tb-layout">' +
          '<aside class="card tb-side"><div class="card-body">' + areas + filters + "</div></aside>" +
          '<section class="tb-main"><div class="tb-search-row"><label class="dt-search">' + UI.icon("search") + '<span class="sr-only">Search tools</span>' +
          '<input type="search" id="tb-q" placeholder="Search a tool or describe the problem, e.g. Internet is slow… (press / )" value="' + esc(view.query) + '"></label>' +
          '<span class="muted small" id="tb-count"></span>' + UI.button("Select visible", 'id="tb-pick-visible"', "btn-sm", "check") + "</div>" +
          '<div id="tb-symptoms" class="tb-symptoms" aria-live="polite"></div><div id="tb-list" aria-live="polite"></div>' +
          '<div class="tb-selbar" id="tb-selbar" hidden><span id="tb-info"></span><span class="grow"></span>' +
          UI.button("Clear", 'id="tb-clear"', "btn-sm btn-ghost", "x") + UI.button("Copy", 'id="tb-copy" title="Names and IDs of the selected tools, for a ticket or a script"', "btn-sm", "copy") +
          UI.button("Save as playbook", 'id="tb-save" title="Keep the selection as one of My playbooks, to run it again with one click"', "btn-sm", "playbooks") +
          UI.button("Run selected", 'id="tb-run"', "btn-sm btn-primary", "play") + "</div></section></div>";
        var list = el.querySelector("#tb-list");

        function shown() {
          var words = fold(view.query).split(/\s+/).filter(Boolean), favs = App.favorites();
          var byName = function (x, y) { return local(x.title).localeCompare(local(y.title)); };
          var sorts = {
            name: byName,
            duration: function (x, y) { return x.minutes - y.minutes || byName(x, y); },
            risk: function (x, y) { return RISK_RANK[x.risk] - RISK_RANK[y.risk] || byName(x, y); },
            recent: function (x, y) {
              var a = last[x.id] ? last[x.id].started : "", b = last[y.id] ? last[y.id].started : "";
              return a < b ? 1 : a > b ? -1 : byName(x, y);
            }
          };
          return all.filter(function (a) {
            var text = a._search || (a._search = fold(a.title + " " + a.description + " " + a.id + " " + local(a.title) + " " + local(a.description)));
            return (!view.area || a.area === view.area) && (!view.kind || a.kind === view.kind) && (!view.risk || a.risk === view.risk) &&
              (!view.never || !last[a.id]) && (!view.favs || favs.indexOf(a.id) >= 0) && words.every(function (w) { return text.indexOf(w) >= 0; });
          }).sort(function (x, y) {
            // Favorites first, like on the old Actions page, then the chosen order.
            return (favs.indexOf(y.id) >= 0) - (favs.indexOf(x.id) >= 0) || (sorts[view.sort] || sorts.name)(x, y);
          });
        }
        function draw() {
          Components.store("toolbox", view);
          var items = shown(), favs = App.favorites();
          visible = items.map(function (a) { return a.id; });
          var groups = view.area ? [view.area] : UI.AREAS;
          var html = groups.map(function (area) {
            var group = items.filter(function (a) { return a.area === area; });
            if (!group.length) return "";
            return (view.area ? "" : '<div class="section-title">' + UI.icon(area) + esc(UI.AREA_LABEL[area]) + '<span class="extra">' + group.length + " tools</span></div>") +
              '<div class="action-grid">' + group.map(function (a) {
                return UI.toolCard(a, last[a.id], { pick: true, picked: !!picked[a.id], star: favs.indexOf(a.id) >= 0 });
              }).join("") + "</div>";
          }).join("");
          var sym = el.querySelector("#tb-symptoms");
          list.innerHTML = html || (sym && sym.children.length
            ? '<p class="muted">No tool name contains these words: the suggestions above fit the problem you described.</p>'
            : '<div class="empty-state">' + UI.icon("search") + "<h2>No tool matches</h2><p>Change the area, the filters or the search text.</p></div>");
          list.classList.toggle("tb-list", view.list);
          el.querySelector("#tb-count").textContent = items.length + " of " + all.length + " tools";
          var reportIds = items.filter(function (a) { return a.kind === "report"; });
          el.querySelector("#tb-reports").disabled = !reportIds.length;
          el.querySelector("#tb-reports").title = reportIds.length + " read-only reports in the current view";
          el.querySelector("#tb-fav-count").textContent = favs.length;
          update();
        }
        function update() {
          var ids = Object.keys(picked);
          var total = ids.reduce(function (s, id) { return s + App.state.actions[id].minutes; }, 0);
          var risky = ids.filter(function (id) { return App.state.actions[id].risk !== "safe"; }).length;
          el.querySelector("#tb-selbar").hidden = !ids.length;
          el.querySelector("#tb-info").innerHTML = "<strong>" + ids.length + " selected</strong> · " + esc(minutes(total)) +
            (risky ? ' · <span class="badge badge-moderate">' + risky + " ask first</span>" : "");
        }
        function selectArea(btn) {
          view.area = btn.getAttribute("data-area");
          el.querySelectorAll(".tb-area").forEach(function (t) {
            var on = t === btn;
            t.setAttribute("aria-selected", String(on));
            t.tabIndex = on ? 0 : -1;
          });
          btn.focus();
          draw();
        }
        function setChoice(name, value) {
          view[name] = value;
          el.querySelectorAll("[data-" + name + "]").forEach(function (x) { x.setAttribute("aria-checked", String(x.getAttribute("data-" + name) === value)); });
          draw();
        }

        var areaList = el.querySelector(".tb-areas");
        areaList.addEventListener("click", function (e) { var t = e.target.closest(".tb-area"); if (t) selectArea(t); });
        // Arrow keys move between areas, Home / End jump to the ends (WAI-ARIA tabs pattern, vertical).
        areaList.addEventListener("keydown", function (e) {
          var tabs = Array.prototype.slice.call(areaList.querySelectorAll(".tb-area")), i = tabs.indexOf(document.activeElement);
          if (i < 0) return;
          var next = e.key === "ArrowDown" ? i + 1 : e.key === "ArrowUp" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
          if (next == null) return;
          e.preventDefault();
          selectArea(tabs[(next + tabs.length) % tabs.length]);
        });
        el.querySelector(".tb-filters").addEventListener("click", function (e) {
          var k = e.target.closest("[data-kind]"), r = e.target.closest("[data-risk]");
          if (k) setChoice("kind", k.getAttribute("data-kind"));
          if (r) setChoice("risk", r.getAttribute("data-risk"));
        });
        el.querySelector("#tb-q").addEventListener("input", function (e) { view.query = e.target.value; draw(); askSymptoms(); });

        /* Search by symptom: the text is also matched against problems ("non vedo gli altri PC", "Internet lento"); the panel
           proposes the reports to read first and the fixes to try after, in order. */
        var symptomTimer = null, symptomAsked = "";
        function askSymptoms() {
          clearTimeout(symptomTimer);
          symptomTimer = setTimeout(function () {
            var q = view.query.trim();
            if (q === symptomAsked) return;
            symptomAsked = q;
            if (q.length < 3) { drawSymptoms([]); return; }
            API.get("/symptoms?q=" + encodeURIComponent(q)).then(function (r) { if (q === view.query.trim()) drawSymptoms(r.matches || []); }, function () { drawSymptoms([]); });
          }, 250);
        }
        function chips(ids, start) {
          return '<span class="tb-chips">' + ids.map(function (id, i) {
            var a = App.state.actions[id];
            return a ? '<button type="button" class="tb-chip" data-step="' + esc(id) + '" title="' + esc(a.description) + '"><span class="step-n">' + (start + i + 1) + "</span>" +
              UI.icon(a.kind === "report" ? "reports" : a.area) + esc(a.title) + "</button>" : "";
          }).join("") + "</span>";
        }
        function drawSymptoms(matches) {
          var box = el.querySelector("#tb-symptoms");
          if (!box) return;
          var it = window.I18N && I18N.lang() === "it";
          box.innerHTML = matches.map(function (m, i) {
            return '<div class="tb-symptom" data-symptom="' + i + '"><div class="tb-symptom-head">' + UI.icon("search") + "<strong data-no-i18n>" + esc(it ? m.title_it : m.title) +
              '</strong><span class="badge badge-report">Suggested for this problem</span></div><div class="tb-steps">' +
              (m.reports.length ? '<span class="tb-label">Read first</span>' + chips(m.reports, 0) : "") +
              (m.fixes.length ? '<span class="tb-label">Then try</span>' + chips(m.fixes, m.reports.length) : "") + "</div>" +
              '<div class="tb-symptom-actions">' + (m.reports.length ? UI.button("Run the reports", 'data-sym-reports="' + i + '"', "btn-sm btn-primary", "reports") : "") +
              (m.fixes.length ? UI.button("Select the fixes", 'data-sym-fixes="' + i + '" title="Pick them in the selection bar, then run the ones the reports point to"', "btn-sm", "check") : "") +
              "</div></div>";
          }).join("");
          box.onclick = function (e) {
            var step = e.target.closest("[data-step]"), rep = e.target.closest("[data-sym-reports]"), fix = e.target.closest("[data-sym-fixes]");
            if (step) App.actionDetail(step.getAttribute("data-step"));
            if (rep) App.runActions(matches[+rep.getAttribute("data-sym-reports")].reports);
            if (fix) {
              matches[+fix.getAttribute("data-sym-fixes")].fixes.forEach(function (id) { picked[id] = 1; });
              draw();
              UI.toast("Fixes selected: read the reports, then run the ones you need from the selection bar.", "ok");
            }
          };
          if (!visible.length) draw();  // the empty list points to the suggestions once they are there
        }
        askSymptoms();
        el.querySelector("#tb-sort").addEventListener("change", function (e) { view.sort = e.target.value; draw(); });
        el.querySelector("#tb-favs").addEventListener("change", function (e) {
          view.favs = e.target.checked;
          if (view.favs && !App.favorites().length) UI.toast("No favorites yet: press the star on a tool.", "info");
          draw();
        });
        el.querySelector("#tb-never").addEventListener("change", function (e) { view.never = e.target.checked; draw(); });
        el.querySelector("#tb-reset").addEventListener("click", function () {
          view = { area: "", kind: "", risk: "", query: "", sort: "name", never: false, favs: false, list: view.list };
          Components.store("toolbox", view);
          App.render();
        });
        el.querySelector("#tb-layout").addEventListener("click", function (e) {
          view.list = !view.list;
          e.currentTarget.lastChild.textContent = view.list ? "Cards" : "List";
          draw();
        });
        el.querySelector("#tb-pick-visible").addEventListener("click", function () {
          var allPicked = visible.length && visible.every(function (id) { return picked[id]; });
          visible.forEach(function (id) { if (allPicked) delete picked[id]; else picked[id] = 1; });
          draw();
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
          var on = App.toggleFavorite(star.closest("[data-id]").getAttribute("data-id"));
          if (on) FX.burst(star);
          UI.toast(on ? "Added to favorites: shown first here and on the dashboard." : "Removed from favorites.", "ok");
          draw();
        });
        // Enter on a focused card opens its details.
        list.addEventListener("keydown", function (e) {
          if (e.key === "Enter" && e.target.classList && e.target.classList.contains("tool-card")) App.actionDetail(e.target.getAttribute("data-id"));
        });
        el.querySelector("#tb-clear").addEventListener("click", function () { picked = {}; draw(); });
        el.querySelector("#tb-copy").addEventListener("click", function () {
          App.copyText(Object.keys(picked).map(function (id) { var a = App.state.actions[id]; return a.title + " (" + id + ", " + a.risk + ", " + minutes(a.minutes) + ")"; }).join("\n"), "Tools");
        });
        el.querySelector("#tb-save").addEventListener("click", function () {
          var ids = App.order(Object.keys(picked));
          UI.modal("Save as playbook", '<form class="form" onsubmit="return false"><label>Name<input name="n" maxlength="60" placeholder="e.g. Monthly visit at the office" required></label>' +
            '<p class="muted small" style="margin:0">' + ids.length + " tools, in a safe order. It appears in Playbooks › My playbooks.</p></form>",
            [{ label: "Cancel", cls: "btn-ghost" }, { label: "Save", cls: "btn-primary", value: function (w) { return w.querySelector("input").value.trim(); } }]).then(function (name) {
            if (!name) return;
            Pages.playbooks.saveMine(name, ids);
            UI.toast("Saved in Playbooks › My playbooks.", "ok");
          });
        });
        el.querySelector("#tb-run").addEventListener("click", function () { App.runActions(App.order(Object.keys(picked))); picked = {}; draw(); });
        el.querySelector("#tb-reports").addEventListener("click", function () {
          App.runActions(visible.filter(function (id) { return App.state.actions[id].kind === "report"; }));
        });
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

  /* The old Actions page lives on as an address: links and bookmarks to #/actions open the Toolbox. */
  window.Pages.actions = {
    title: "Toolbox",
    alias: "toolbox",
    render: function (el, App) {
      history.replaceState(null, "", "#/toolbox" + (location.hash.indexOf("?") > 0 ? location.hash.slice(location.hash.indexOf("?")) : ""));
      App.state.page = "toolbox";  // so the page's own checks (App.isCurrent) and the menu see the Toolbox
      return window.Pages.toolbox.render(el, App);
    }
  };
})();
