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

  /* Undo: System Restore brings the whole PC back to the point made before the change (Windows restarts to apply it). */
  function undo(started, what) {
    API.get("/restore-points").then(function (r) {
      var points = r.points || [], at = String(started).slice(0, 19);
      var point = points.filter(function (p) { return p.created && p.created <= at; })[0];
      var body = point
        ? '<p class="modal-text">To undo <strong>' + esc(what) + "</strong> (" + esc(UI.formatDate(started, true)) + "), choose this restore point in System Restore:</p>" +
          UI.definition([["Restore point", "#" + esc(point.seq)], ["Created", esc(UI.formatDate(point.created, true))], ["Description", esc(point.description || "—")]]) +
          '<div class="callout callout-warning">' + UI.icon("alert") + "<div>Windows restarts to apply it. Programs installed and settings changed after that moment are undone too; " +
          "your documents are not touched. Save your work first.</div></div>"
        : '<div class="callout callout-warning">' + UI.icon("alert") + "<div>" + esc(r.note || "No restore point older than this change was found.") +
          " System Restore can still show the points Windows keeps.</div></div>";
      return UI.modal("Undo " + what, body, [{ label: "Cancel", cls: "btn-ghost" }, { label: "Open System Restore", cls: "btn-primary", value: function () { return true; } }]);
    }).then(function (ok) {
      if (!ok) return;
      return API.post("/restore-points/open").then(function (x) {
        UI.toast(x.preview ? "Preview mode: System Restore was not opened." : "System Restore is open on the PC: pick the point and follow the steps.", x.preview ? "info" : "ok");
      });
    }).catch(function (e) { UI.toast(e.message, "error"); });
  }

  window.Pages.history = {
    title: "History",
    render: function (el, App) {
      var self = this;
      // #/history?area=cleanup opens the runs of one area (area pages link here).
      var fromUrl = /[?&]area=(\w+)/.exec(location.hash);
      if (fromUrl && UI.AREAS.indexOf(fromUrl[1]) >= 0) filters.area = fromUrl[1];
      return API.get("/history?limit=5000" + (filters.area ? "&area=" + filters.area : "")).then(function (h) {
        var midnight = new Date(); midnight.setHours(0, 0, 0, 0);
        var since = filters.days === "today" ? midnight.getTime() : filters.days ? Date.now() - Number(filters.days) * 86400e3 : 0;
        var runs = h.runs.filter(function (r) { return new Date(r.started).getTime() >= since && (!filters.failed || r.status === "error" || r.status === "warning"); });
        // The actions run most often in the period, for "what keeps needing a fix?".
        var counts = {};
        runs.forEach(function (r) { counts[r.action_id] = (counts[r.action_id] || 0) + 1; });
        var top = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; }).slice(0, 6);
        var topMax = top.length ? counts[top[0]] : 1;
        var topCard = top.length ? '<ul class="top-actions">' + top.map(function (id) {
          return '<li><span class="cell-title" style="width:46%">' + esc(App.action(id) ? App.action(id).title : id) + '</span><div class="bar-inline"><div style="width:' +
            Math.round(100 * counts[id] / topMax) + '%;background:var(--accent)"></div></div><span class="legend-value">' + counts[id] + "×</span></li>";
        }).join("") + "</ul>" : '<p class="empty">No runs in this period.</p>';
        var title = function (id) { var a = App.action(id); return a ? a.title : id; };
        var freed = runs.reduce(function (a, r) { return a + (r.bytes_freed || 0); }, 0);
        var ok = runs.filter(function (r) { return r.status === "ok" || r.status === "preview"; }).length;
        var areas = filters.area ? [filters.area] : UI.AREAS;
        App.setSubtitle("Every scan and action recorded on this device");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Runs", Components.num(runs.length), filters.days === "today" ? "Today" : filters.days ? "Last " + filters.days + " days" : "All time", "info") +
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

        var days = [], index = {}, span = filters.days === "today" ? 7 : Math.min(filters.days ? Number(filters.days) : 90, 120);
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
        var perDayCounts = {};
        h.runs.forEach(function (r) { var k = isoDay(r.started); perDayCounts[k] = (perDayCounts[k] || 0) + 1; });

        // Before/after: the latest score of each area at two moments.
        var dates = [];
        UI.AREAS.forEach(function (a) { (h.trends[a] || []).forEach(function (p) { var k = isoDay(p.created); if (dates.indexOf(k) < 0) dates.push(k); }); });
        dates.sort();
        var compare = dates.length < 2 ? '<p class="empty">Scan on at least two different days to compare.</p>' :
          '<div class="filters" style="margin-bottom:12px"><label>Before<select id="cmp-a">' + dates.map(function (x, i) { return '<option value="' + x + '"' + (i === 0 ? " selected" : "") + ">" + esc(UI.formatDate(x + "T23:59:59", false)) + "</option>"; }).join("") +
          '</select></label><label>After<select id="cmp-b">' + dates.map(function (x, i) { return '<option value="' + x + '"' + (i === dates.length - 1 ? " selected" : "") + ">" + esc(UI.formatDate(x + "T23:59:59", false)) + "</option>"; }).join("") +
          '</select></label></div><div id="cmp-table"></div>';

        el.innerHTML = UI.pageHeader("History", "Retained locally in dati\\wmm.db",
          '<button type="button" class="btn" data-api-download="/export/' + esc(filters.area || "all") + '.csv">' + UI.icon("download") + "Export CSV</button>" +
          '<button type="button" class="btn" data-api-download="/export/' + esc(filters.area || "all") + '.json">' + UI.icon("download") + "Export JSON</button>") +
          '<div class="grid">' + UI.card("Filters", '<div class="filters"><label>Area<select data-filter="area"><option value="">All areas</option>' + UI.AREAS.map(function (a) {
            return '<option value="' + a + '"' + (filters.area === a ? " selected" : "") + ">" + esc(UI.AREA_LABEL[a]) + "</option>";
          }).join("") + '</select></label><label>Period<select data-filter="days">' + [["today", "Today"], ["7", "Last 7 days"], ["30", "Last 30 days"], ["90", "Last 90 days"], ["", "All time"]].map(function (o) {
            return '<option value="' + o[0] + '"' + (filters.days === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
          }).join("") + "</select></label>" +
            '<label class="check"><input type="checkbox" id="hist-failed"' + (filters.failed ? " checked" : "") + "> Only warnings and errors</label>" +
            UI.button("Reset", 'id="hist-reset"' + (filters.area || filters.failed || filters.days !== "30" ? "" : " disabled"), "btn-sm btn-ghost", "x") + "</div>") + "</div>" + kpis +
          '<div class="grid grid-2">' + UI.card("Score trend", trend) + UI.card("Runs per day", perDay) + "</div>" +
          '<div class="grid grid-2-1">' + UI.card("Before / after", compare) + UI.card("Activity calendar", Charts.heatmap(perDayCounts, { weeks: 20 })) + "</div>" +
          '<div class="grid">' + UI.card("Most run actions", topCard, '<span class="muted small">In the selected period</span>') + "</div>" +
          '<div class="grid">' + UI.card("Runs", '<div id="runs-table"></div>', "", "card-flush") + "</div>";

        el.querySelectorAll("[data-filter]").forEach(function (select) {
          select.addEventListener("change", function () { filters[select.getAttribute("data-filter")] = select.value; self.render(el, App); });
        });
        el.querySelector("#hist-failed").addEventListener("change", function (e) { filters.failed = e.target.checked; self.render(el, App); });
        el.querySelector("#hist-reset").addEventListener("click", function () {
          filters.area = ""; filters.days = "30"; filters.failed = false;
          if (/[?&]area=/.test(location.hash)) location.hash = "#/history"; else self.render(el, App);
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
            { key: "verify", title: "Verified", value: function (r) { return r.verify ? r.verify.verdict : ""; }, render: function (r) {
              return (UI.verdictBadge(r.verify) || '<span class="muted">—</span>') + (r.undone ? ' <span class="badge" title="' + esc(UI.formatDate(r.undone, true)) + '">Undone</span>' : ""); } },
            { key: "log", title: "Log", sortable: false, csv: false, render: function (r) {
              return '<details class="log-details" data-log-run="' + r.id + '"><summary>View</summary><pre class="log">Loading…</pre>' +
                '<button type="button" class="btn btn-sm btn-ghost" data-copy-log hidden>' + UI.icon("copy") + "Copy log</button></details>"; } },
            { key: "again", title: "", sortable: false, csv: false, render: function (r) {
              var a = App.state.actions[r.action_id], kind = App.action(r.action_id);
              // A change that went through (not a read-only report) can be undone with the restore point made before it.
              var undo = r.status === "ok" && kind && kind.risk !== "safe" && kind.kind !== "report"
                ? '<button type="button" class="btn btn-sm btn-ghost" data-undo="' + esc(r.started) + '" data-undo-title="' + esc(title(r.action_id)) + '" title="Bring the PC back to the restore point made before this change">' +
                  UI.icon("history") + "Restore point…</button>" : "";
              // A fix that changed registry values can put back exactly those, without a restore point.
              var precise = r.undo_count && !r.undone ? '<button type="button" class="btn btn-sm" data-precise-undo="' + r.id + '" data-title="' + esc(title(r.action_id)) +
                '" title="Put back only the ' + r.undo_count + ' registry values this fix changed">' + UI.icon("history") + "Undo</button>" : "";
              return '<span class="row-actions">' + (a ? '<button type="button" class="btn btn-sm" data-run="' + esc(r.action_id) + '" title="Run ' + esc(a.title) + ' again">' +
                UI.icon("refresh") + "Again</button>" : "") + precise + undo + "</span>";
            } }
          ],
          after: function (box) {
            box.querySelectorAll("[data-undo]").forEach(function (b) {
              b.addEventListener("click", function () { undo(b.getAttribute("data-undo"), b.getAttribute("data-undo-title")); });
            });
            box.querySelectorAll("[data-log-run]").forEach(function (det) {
              det.addEventListener("toggle", function () {
                if (!det.open || det.loaded) return;
                det.loaded = true;
                API.get("/history/runs/" + det.getAttribute("data-log-run") + "/log").then(function (r) {
                  det.querySelector("pre").textContent = r.log || "(no output)";
                  var copy = det.querySelector("[data-copy-log]");
                  copy.hidden = !r.log;
                  copy.addEventListener("click", function () { App.copyText(r.log, "Log"); });
                }, function (e) { det.querySelector("pre").textContent = e.message; });
              });
            });
          }
        });
      });
    }
  };
})();
