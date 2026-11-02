/* Event Viewer: critical Windows, hardware, application and service events, fast and filterable, with live refresh. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var LEVEL = { 1: ["critical", "Critical", "error"], 2: ["error", "Error", "error"], 3: ["warning", "Warning", "warning"], 4: ["information", "Information", "info"], 5: ["verbose", "Verbose", "skipped"] };
  var RANGES = [[1, "Last hour"], [24, "Last 24 hours"], [168, "Last 7 days"], [720, "Last 30 days"], [2160, "Last 90 days"]];
  var PRESET_ICON = { critical: "alert", hardware: "cpu", applications: "explorer", services: "services", security: "security", all: "activity" };

  function saved() { return Components.store("events") || { preset: "critical", hours: 168, limit: 500, live: false }; }
  function levelBadge(n) {
    var l = LEVEL[n] || LEVEL[4];
    return '<span class="badge badge-status-' + l[2] + " ev-level ev-" + l[0] + '">' + esc(l[1]) + "</span>";
  }

  /* Events per hour (or per day for long ranges), coloured by their worst level. */
  function timeline(list, hours) {
    var day = hours > 72, slots = day ? Math.ceil(hours / 24) : Math.min(hours, 48), size = (day ? 24 : 1) * 3600e3, now = Date.now();
    var buckets = [];
    for (var i = slots - 1; i >= 0; i--) buckets.push({ value: 0, worst: 4, end: now - i * size });
    list.forEach(function (e) {
      var age = now - new Date(e.time).getTime(), j = slots - 1 - Math.floor(age / size);
      if (j >= 0 && j < slots) { buckets[j].value++; buckets[j].worst = Math.min(buckets[j].worst, e.level); }
    });
    return Charts.bars(buckets.map(function (b) {
      var d = new Date(b.end);
      return { label: day ? d.toLocaleDateString(undefined, { day: "2-digit", month: "short" }) : d.getHours() + ":00", value: b.value,
        color: b.worst <= 2 ? "#C42B1C" : b.worst === 3 ? "#C27C0E" : "#0F6CBD" };
    }), { height: 170, empty: "No events in this range" });
  }

  function detail(App, e, apply) {
    var body = UI.definition([["Time", esc(UI.formatDate(e.time))], ["Level", levelBadge(e.level)], ["Log", esc(e.log)], ["Source", esc(e.provider)],
      ["Event ID", '<span class="cell-mono">' + esc(e.id) + "</span>"], ["Task", esc(e.task)], ["Process ID", esc(e.pid || "—")], ["Record", esc(e.record)]]) +
      '<pre class="log" style="min-height:120px;max-height:40vh;margin-top:12px">' + esc(e.message || "(no message)") + "</pre>";
    UI.modal(e.provider + " · " + e.id, body, [
      { label: "Only this source", cls: "btn-ghost", value: function () { return "source"; } },
      { label: "Only this ID", cls: "btn-ghost", value: function () { return "id"; } },
      { label: "Copy", cls: "", value: function () { return "copy"; } },
      { label: "Close", cls: "btn-primary" }
    ]).then(function (v) {
      if (v === "copy") App.copyText("[" + e.time + "] " + e.log + " · " + e.provider + " · ID " + e.id + " · " + (LEVEL[e.level] || LEVEL[4])[1] + "\n" + e.message, "Event");
      if (v === "source") apply({ providers: e.provider });
      if (v === "id") apply({ id: String(e.id), providers: e.provider });
    });
  }

  window.Pages.events = {
    title: "Event Viewer",
    render: function (el, App) {
      var view = saved(), timer = null, data = null, table = null;
      return API.get("/events/meta").then(function (meta) {
        App.setSubtitle("Critical Windows, hardware, application and service events");
        var presets = Object.keys(meta.presets);
        el.innerHTML = UI.pageHeader("Event Viewer", "Fast, filterable view of the Windows event logs",
          '<span class="muted small" id="ev-time"></span><label class="check live-toggle"><input type="checkbox" id="ev-live"' + (view.live ? " checked" : "") +
          "> Live</label>" + UI.button("Refresh", 'id="ev-refresh"', "", "refresh")) +
          '<div class="tabs" role="tablist" aria-label="Event category">' + presets.map(function (k) {
            return '<button type="button" role="tab" class="tab" data-preset="' + k + '" aria-selected="' + (view.preset === k) + '" tabindex="' + (view.preset === k ? 0 : -1) + '">' +
              UI.icon(PRESET_ICON[k] || "activity") + "<span>" + esc(meta.presets[k].title) + "</span></button>";
          }).join("") + "</div>" +
          '<section class="card"><div class="card-body"><div class="filters ev-filters">' +
          '<label>Time<select id="ev-hours">' + RANGES.map(function (r) { return '<option value="' + r[0] + '"' + (Number(view.hours) === r[0] ? " selected" : "") + ">" + r[1] + "</option>"; }).join("") + "</select></label>" +
          '<label>Logs<select id="ev-logs"><option value="">Category logs</option>' + meta.logs.map(function (l) { return '<option value="' + l + '"' + (view.logs === l ? " selected" : "") + ">" + l + "</option>"; }).join("") + "</select></label>" +
          '<fieldset class="ev-levels"><legend>Levels</legend>' + [1, 2, 3, 4].map(function (n) {
            return '<label class="chip"><input type="checkbox" value="' + n + '"' + ((view.levels || "").split(",").indexOf(String(n)) >= 0 ? " checked" : "") + "><span>" + LEVEL[n][1] + "</span></label>";
          }).join("") + "</fieldset>" +
          '<label>Source<input type="text" id="ev-source" placeholder="e.g. disk, Ntfs" value="' + esc(view.providers || "") + '"></label>' +
          '<label>Event ID<input type="number" id="ev-id" min="0" max="65535" value="' + esc(view.id || "") + '"></label>' +
          '<label>Max events<select id="ev-limit">' + [200, 500, 1000, 2000].map(function (n) { return "<option" + (Number(view.limit) === n ? " selected" : "") + ">" + n + "</option>"; }).join("") + "</select></label>" +
          UI.button("Reset filters", 'id="ev-reset"', "btn-ghost btn-sm", "x") + "</div>" +
          '<p class="muted small" style="margin:8px 0 0">Levels left empty use the category defaults. The search box and the column filters below work instantly on the loaded events.</p></div></section>' +
          '<div id="ev-body">' + UI.loading("Reading the event logs…") + "</div>";

        function params(fresh) {
          var q = ["preset=" + view.preset, "hours=" + view.hours, "limit=" + view.limit];
          if (view.logs) q.push("logs=" + encodeURIComponent(view.logs));
          if (view.levels) q.push("levels=" + view.levels);
          if (view.providers) q.push("providers=" + encodeURIComponent(view.providers));
          if (view.id) q.push("id=" + encodeURIComponent(view.id));
          if (fresh) q.push("fresh=1");
          return q.join("&");
        }
        function save() { Components.store("events", view); }
        function apply(change) { Object.keys(change).forEach(function (k) { view[k] = change[k]; }); save(); App.render(); }

        function draw() {
          var list = data.events, c = data.counts, body = el.querySelector("#ev-body");
          var sources = {};
          list.forEach(function (e) { sources[e.provider] = (sources[e.provider] || 0) + 1; });
          var top = Object.keys(sources).sort(function (a, b) { return sources[b] - sources[a]; }).slice(0, 8);
          var kpis = '<div class="grid grid-5">' +
            UI.kpi("Critical", Components.num(c.critical), "Crashes, power loss, hardware faults", c.critical ? "error" : "ok") +
            UI.kpi("Errors", Components.num(c.error), "Failures reported by Windows and apps", c.error ? "error" : "ok") +
            UI.kpi("Warnings", Components.num(c.warning), "Problems that may need attention", c.warning ? "warning" : "ok") +
            UI.kpi("Events shown", Components.num(list.length), "Read in " + data.elapsed_ms + " ms", "info") +
            UI.kpi("Top source", top.length ? esc(top[0]) : "—", top.length ? sources[top[0]] + " events" : "No events", "info") + "</div>";
          var warn = data.warnings.length ? '<div class="callout callout-warning">' + UI.icon("info") + "<div>" + esc(data.warnings.join(" · ")) + "</div></div>" : "";
          body.innerHTML = warn + kpis + '<div class="grid grid-2-1">' + UI.card("Timeline", timeline(list, Number(view.hours))) +
            UI.card("Top sources", Charts.hbars(top.map(function (s, i) { return { label: s, value: sources[s], color: Charts.PALETTE[i % Charts.PALETTE.length] }; }),
              { empty: "No events" })) + "</div>" +
            '<div class="grid">' + UI.card("Events", '<div id="ev-table"></div>', '<span class="muted small">Click a message for the full event</span>', "card-flush") + "</div>";
          Components.countUp(body);
          table = Components.dataTable(body.querySelector("#ev-table"), {
            rows: list, pageSize: 25, sort: "time", desc: true, exportName: "wmm-events", placeholder: "Search messages, sources, IDs…", alwaysFoot: true,
            filters: [{ key: "level_name", label: "All levels", options: [["critical", "Critical"], ["error", "Error"], ["warning", "Warning"], ["information", "Information"]] },
              { key: "log", label: "All logs", options: meta.logs.map(function (l) { return [l, l]; }) },
              { key: "provider", label: "All sources", options: Object.keys(sources).sort().map(function (s) { return [s, s + " (" + sources[s] + ")"]; }) }],
            columns: [
              { key: "time", title: "Time", render: function (e) { return '<span class="nowrap" title="' + esc(e.time) + '">' + esc(UI.formatDate(e.time)) + "</span>"; } },
              { key: "level", title: "Level", render: function (e) { return levelBadge(e.level); } },
              { key: "log", title: "Log" },
              { key: "provider", title: "Source", render: function (e) { return '<span class="cell-title">' + esc(e.provider) + "</span>"; } },
              { key: "id", title: "ID", cls: "num" },
              { key: "message", title: "Message", render: function (e) {
                return '<button type="button" class="link-btn ev-msg" data-ev="' + esc(e.record + "|" + e.log) + '">' + esc((e.message || "(no message)").split("\n")[0].slice(0, 180)) + "</button>";
              } }
            ]
          });
          body.querySelector("#ev-table").addEventListener("click", function (ev) {
            var b = ev.target.closest("[data-ev]");
            if (!b) return;
            var key = b.getAttribute("data-ev"), e = list.filter(function (x) { return x.record + "|" + x.log === key; })[0];
            if (e) detail(App, e, apply);
          });
        }

        function load(fresh) {
          var stamp = el.querySelector("#ev-time");
          stamp.textContent = "Loading…";
          return API.get("/events?" + params(fresh)).then(function (r) {
            if (!App.isCurrent("events")) return;
            // Live refresh redraws only when something new arrived, so filters and paging stay put.
            var changed = !data || r.events.length !== data.events.length || (r.events[0] && data.events[0] && r.events[0].record !== data.events[0].record);
            data = r;
            stamp.textContent = "Updated " + new Date().toLocaleTimeString();
            if (changed || !table) draw();
          }, function (e) {
            el.querySelector("#ev-body").innerHTML = UI.errorBox(e);
            stamp.textContent = "";
          });
        }
        function setLive(on) {
          clearInterval(timer);
          if (on) timer = setInterval(function () { if (!document.hidden) load(true); }, 10000);
        }

        el.querySelector(".tabs").addEventListener("click", function (e) {
          var t = e.target.closest("[data-preset]");
          if (t) apply({ preset: t.getAttribute("data-preset"), logs: "", levels: "", providers: "", id: "" });
        });
        el.querySelector(".tabs").addEventListener("keydown", function (e) {
          var tabs = Array.prototype.slice.call(el.querySelectorAll(".tab")), i = tabs.indexOf(document.activeElement);
          if (i < 0 || (e.key !== "ArrowRight" && e.key !== "ArrowLeft")) return;
          e.preventDefault();
          tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length].click();
        });
        el.querySelector("#ev-hours").addEventListener("change", function (e) { apply({ hours: Number(e.target.value) }); });
        el.querySelector("#ev-logs").addEventListener("change", function (e) { apply({ logs: e.target.value }); });
        el.querySelector("#ev-limit").addEventListener("change", function (e) { apply({ limit: Number(e.target.value) }); });
        el.querySelector(".ev-levels").addEventListener("change", function () {
          apply({ levels: Array.prototype.map.call(el.querySelectorAll(".ev-levels input:checked"), function (i) { return i.value; }).join(",") });
        });
        ["#ev-source", "#ev-id"].forEach(function (sel) {
          el.querySelector(sel).addEventListener("change", function () {
            apply({ providers: el.querySelector("#ev-source").value.trim(), id: el.querySelector("#ev-id").value.trim() });
          });
        });
        el.querySelector("#ev-reset").addEventListener("click", function () { apply({ logs: "", levels: "", providers: "", id: "", hours: 168, limit: 500 }); });
        el.querySelector("#ev-refresh").addEventListener("click", function () { data = null; load(true); });
        el.querySelector("#ev-live").addEventListener("change", function (e) { view.live = e.target.checked; save(); setLive(view.live); });
        App.onLeave(function () { clearInterval(timer); });
        setLive(view.live);
        return load(false);
      });
    }
  };
})();
