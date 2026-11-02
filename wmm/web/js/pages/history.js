/* History: score trends, activity calendar, before/after comparison and every recorded run. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var filters = { area: "", days: "30" };
  var STATUS_COLORS = [["ok", "Success", "#107C41"], ["warning", "Warning", "#C27C0E"], ["error", "Error", "#C42B1C"], ["skipped", "Skipped", "#8A8886"], ["preview", "Preview", "#5C7080"]];

  function dayKey(d) { return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate(); }
  function isoDay(iso) { return String(iso).slice(0, 10); }
  function scoreAt(trend, when) {
    var found = null;
    (trend || []).forEach(function (p) { if (new Date(p.created).getTime() <= when) found = p.score; });
    return found;
  }

  window.Pages.history = {
    title: "History",
    render: function (el, App) {
      var self = this;
      return API.get("/history?limit=5000" + (filters.area ? "&area=" + filters.area : "")).then(function (h) {
        var since = filters.days ? Date.now() - Number(filters.days) * 86400e3 : 0;
        var runs = h.runs.filter(function (r) { return new Date(r.started).getTime() >= since; });
        var title = function (id) { var a = App.action(id); return a ? a.title : id; };
        var freed = runs.reduce(function (a, r) { return a + (r.bytes_freed || 0); }, 0);
        var ok = runs.filter(function (r) { return r.status === "ok" || r.status === "preview"; }).length;
        var areas = filters.area ? [filters.area] : UI.AREAS;
        App.setSubtitle("Every scan and action recorded on this device");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Runs", Components.num(runs.length), filters.days ? "Last " + filters.days + " days" : "All time", "info") +
          UI.kpi("Success rate", runs.length ? Components.num(Math.round(100 * ok / runs.length)) + "<small>%</small>" : "—", ok + " successful", runs.length && ok / runs.length < 0.8 ? "warning" : "ok") +
          UI.kpi("Space freed", esc(UI.formatBytes(freed)), "By the listed runs", "info") +
          UI.kpi("Scheduled runs", Components.num(runs.filter(function (r) { return r.origin === "schedule"; }).length), runs.filter(function (r) { return r.origin === "auto"; }).length + " automatic", "info") + "</div>";

        var trendSeries = areas.filter(function (a) { return (h.trends[a] || []).length; }).map(function (a) {
          return { name: UI.AREA_LABEL[a], color: Charts.PALETTE[UI.AREAS.indexOf(a) % Charts.PALETTE.length],
            points: h.trends[a].filter(function (p) { return new Date(p.created).getTime() >= since; }).map(function (p) { return { x: p.created, y: p.score }; }) };
        });
        var trend = Charts.line(trendSeries, { min: 0, max: 100 }) + '<div class="series-key">' + trendSeries.map(function (t) {
          return '<span><span class="swatch" style="background:' + t.color + '"></span>' + esc(t.name) + "</span>";
        }).join("") + "</div>";

        var days = [], index = {}, span = Math.min(filters.days ? Number(filters.days) : 90, 120);
        for (var i = span - 1; i >= 0; i--) {
          var d = new Date(Date.now() - i * 86400e3);
          index[dayKey(d)] = days.length;
          days.push(d.toLocaleDateString(undefined, { day: "2-digit", month: "short" }));
        }
        var stacks = STATUS_COLORS.map(function (s) { return { name: s[1], color: s[2], values: days.map(function () { return 0; }) }; });
        runs.forEach(function (r) {
          var k = index[dayKey(new Date(r.started))], s = STATUS_COLORS.map(function (x) { return x[0]; }).indexOf(r.status);
          if (k != null && s >= 0) stacks[s].values[k]++;
        });
        var perDay = Charts.stacked(days, stacks) + '<div class="series-key">' + STATUS_COLORS.map(function (s) {
          return '<span><span class="swatch" style="background:' + s[2] + '"></span>' + s[1] + "</span>";
        }).join("") + "</div>";
        var counts = {};
        h.runs.forEach(function (r) { var k = isoDay(r.started); counts[k] = (counts[k] || 0) + 1; });

        // Before/after: the latest score of each area at two moments.
        var dates = [];
        UI.AREAS.forEach(function (a) { (h.trends[a] || []).forEach(function (p) { var k = isoDay(p.created); if (dates.indexOf(k) < 0) dates.push(k); }); });
        dates.sort();
        var compare = dates.length < 2 ? '<p class="empty">Scan on at least two different days to compare.</p>' :
          '<div class="filters" style="margin-bottom:12px"><label>Before<select id="cmp-a">' + dates.map(function (x, i) { return '<option value="' + x + '"' + (i === 0 ? " selected" : "") + ">" + esc(UI.formatDate(x + "T23:59:59", false)) + "</option>"; }).join("") +
          '</select></label><label>After<select id="cmp-b">' + dates.map(function (x, i) { return '<option value="' + x + '"' + (i === dates.length - 1 ? " selected" : "") + ">" + esc(UI.formatDate(x + "T23:59:59", false)) + "</option>"; }).join("") +
          '</select></label></div><div id="cmp-table"></div>';

        el.innerHTML = UI.pageHeader("History", "Retained locally in dati\\wmm.db",
          '<a class="btn" href="' + API.url("/export/" + (filters.area || "all") + ".csv") + '" download>' + UI.icon("download") + "Export CSV</a>" +
          '<a class="btn" href="' + API.url("/export/" + (filters.area || "all") + ".json") + '" download>' + UI.icon("download") + "Export JSON</a>") +
          '<div class="grid">' + UI.card("Filters", '<div class="filters"><label>Area<select data-filter="area"><option value="">All areas</option>' + UI.AREAS.map(function (a) {
            return '<option value="' + a + '"' + (filters.area === a ? " selected" : "") + ">" + esc(UI.AREA_LABEL[a]) + "</option>";
          }).join("") + '</select></label><label>Period<select data-filter="days">' + [["7", "Last 7 days"], ["30", "Last 30 days"], ["90", "Last 90 days"], ["", "All time"]].map(function (o) {
            return '<option value="' + o[0] + '"' + (filters.days === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
          }).join("") + "</select></label></div>") + "</div>" + kpis +
          '<div class="grid grid-2">' + UI.card("Score trend", trend) + UI.card("Runs per day", perDay) + "</div>" +
          '<div class="grid grid-2-1">' + UI.card("Before / after", compare) + UI.card("Activity calendar", Charts.heatmap(counts, { weeks: 20 })) + "</div>" +
          '<div class="grid">' + UI.card("Runs", '<div id="runs-table"></div>', "", "card-flush") + "</div>";

        el.querySelectorAll("[data-filter]").forEach(function (select) {
          select.addEventListener("change", function () { filters[select.getAttribute("data-filter")] = select.value; self.render(el, App); });
        });
        function drawCompare() {
          var box = el.querySelector("#cmp-table");
          if (!box) return;
          var a = new Date(el.querySelector("#cmp-a").value + "T23:59:59").getTime(), b = new Date(el.querySelector("#cmp-b").value + "T23:59:59").getTime();
          var between = h.runs.filter(function (r) { var t = new Date(r.started).getTime(); return t > a && t <= b; });
          box.innerHTML = UI.table([{ title: "Area" }, { title: "Before", cls: "num" }, { title: "After", cls: "num" }, { title: "Change", cls: "num" }], UI.AREAS.map(function (area) {
            var x = scoreAt(h.trends[area], a), y = scoreAt(h.trends[area], b);
            var delta = x != null && y != null ? y - x : null;
            return [esc(UI.AREA_LABEL[area]), x == null ? "—" : x, y == null ? "—" : y,
              delta == null ? "—" : '<span class="' + (delta > 0 ? "delta-up" : delta < 0 ? "delta-down" : "delta-flat") + '">' + (delta > 0 ? "▲ +" : delta < 0 ? "▼ " : "") + delta + "</span>"];
          })) + '<p class="muted small" style="margin:10px 0 0">' + between.length + " actions between the two dates · " +
            UI.formatBytes(between.reduce(function (s, r) { return s + (r.bytes_freed || 0); }, 0)) + " freed.</p>";
        }
        if (el.querySelector("#cmp-a")) {
          el.querySelector("#cmp-a").addEventListener("change", drawCompare);
          el.querySelector("#cmp-b").addEventListener("change", drawCompare);
          drawCompare();
        }
        Components.dataTable(el.querySelector("#runs-table"), {
          rows: runs, exportName: "wmm-history", placeholder: "Search actions, notes…", sort: "started", desc: true, pageSize: 15, alwaysFoot: true,
          filters: [{ key: "status", label: "All results", options: STATUS_COLORS.map(function (s) { return [s[0], s[1]]; }) },
            { key: "origin", label: "All origins", options: [["manual", "Manual"], ["auto", "Automatic"], ["schedule", "Scheduled"]] }],
          columns: [
            { key: "started", title: "Date", render: function (r) { return esc(UI.formatDate(r.started)); } },
            { key: "action", title: "Action", value: function (r) { return title(r.action_id); }, render: function (r) { return '<span class="cell-title">' + esc(title(r.action_id)) + "</span>"; } },
            { key: "area", title: "Area", value: function (r) { return UI.AREA_LABEL[r.area] || r.area; } },
            { key: "origin", title: "Origin", value: function (r) { return UI.ORIGIN_LABEL[r.origin] || r.origin; } },
            { key: "status", title: "Result", render: function (r) { return UI.statusBadge(r.status); } },
            { key: "note", title: "Note", render: function (r) { return '<span class="cell-sub">' + esc(r.note || "") + "</span>"; } },
            { key: "bytes_freed", title: "Freed", cls: "num", render: function (r) { return r.bytes_freed ? esc(UI.formatBytes(r.bytes_freed)) : "—"; } },
            { key: "log", title: "Log", sortable: false, csv: false, render: function (r) { return '<details class="log-details" data-log="' + r.id + '"><summary>View</summary><pre class="log">Loading…</pre></details>'; } }
          ],
          after: function (box) {
            box.querySelectorAll("[data-log]").forEach(function (det) {
              det.addEventListener("toggle", function () {
                if (!det.open || det.loaded) return;
                det.loaded = true;
                API.get("/history/runs/" + det.getAttribute("data-log") + "/log").then(function (r) {
                  det.querySelector("pre").textContent = r.log || "(no output)";
                }, function (e) { det.querySelector("pre").textContent = e.message; });
              });
            });
          }
        });
      });
    }
  };
})();
