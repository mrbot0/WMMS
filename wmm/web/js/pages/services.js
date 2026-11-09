/* Services: start types, the analysis of the services of this PC (what can be turned off), backup and startup programs. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var START = { "auto": "Automatic", "delayed-auto": "Automatic (delayed)", demand: "Manual", disabled: "Disabled", boot: "Boot", system: "System" };
  var KIND_TONE = { telemetry: "warning", updater: "info", insecure: "error", unused: "info", remote: "warning", suspicious: "error", heavy: "warning" };

  function auditTable(audit) {
    var list = (audit && audit.findings) || [];
    if (!list.length) {
      return '<p class="empty">Nothing to turn off: every service left on is used by Windows, by your hardware or by your programs.</p>';
    }
    var rows = list.map(function (f) {
      return "<tr>" +
        '<td><input type="checkbox" data-audit="' + esc(f.name) + '"' + (f.selected ? " checked" : "") + ' aria-label="' + esc(f.display) + '"></td>' +
        '<td><div class="cell-title">' + esc(f.display) + '</div><div class="cell-sub cell-mono">' + esc(f.name) + (f.company ? " · " + esc(f.company) : "") + "</div></td>" +
        '<td><span class="badge badge-status-' + (KIND_TONE[f.category] || "info") + '">' + esc(f.label) + "</span>" +
        (f.selected ? "" : '<div class="cell-sub">To review</div>') + "</td>" +
        '<td class="wrap">' + esc(f.reason) + "</td>" +
        '<td class="num">' + (f.running && !f.shared && f.memory_mb ? esc(f.memory_mb + " MB") : f.running ? "Running" : "—") + "</td>" +
        "<td>" + esc(START[f.start] || f.start) + " → <strong>" + esc(START[f.target] || f.target) + "</strong></td></tr>";
    }).join("");
    return '<div class="table-wrap"><table class="table"><thead><tr><th></th><th>Service</th><th>Why</th><th>What it does</th><th class="num">Memory</th>' +
      "<th>Start type</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  function auditIntro(audit) {
    var a = audit || {}, list = a.findings || [];
    var scelti = list.filter(function (f) { return f.selected; }).length;
    return '<p class="muted" style="margin-top:0">' + esc((a.services || 0) + " services analysed, " + (a.third_party || 0) + " from other makers. ") +
      esc(scelti + " can be changed without losing anything (ticked); " + (list.length - scelti) + " are worth a look before changing them.") +
      " Antivirus, drivers and hardware tools, backup and sync, licences, VPNs and virtual machines are never proposed.</p>" +
      (a.managed ? '<div class="callout callout-info">' + UI.icon("info") + "<div>This PC is managed by a company: updaters and remote management are left for IT to decide.</div></div>" : "");
  }

  window.Pages.services = {
    title: "Services",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/services").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "services"), t = d.totals || {};
        var audit = d.audit || { findings: [] };
        var findings = audit.findings || [];
        var daCambiare = findings.filter(function (f) { return f.selected; }).length;
        App.setSubtitle("Windows services and startup programs");

        var kpis = '<div class="grid grid-4">' +
          UI.kpi("Services score", String(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Running services", String(t.running || 0), "of " + (t.total || 0) + " installed", "info") +
          UI.kpi("To turn off", String(daCambiare), findings.length + " found by the analysis of this PC", daCambiare ? "warning" : "ok") +
          UI.kpi("Startup programs", String((d.startup || []).length), (d.backup_count || 0) + " service(s) in the restore backup", (d.startup || []).length > 15 ? "warning" : "ok") +
          "</div>";

        var startSeries = [
          { label: "Automatic", value: t.auto || 0, color: "#0F6CBD" },
          { label: "Manual", value: t.manual || 0, color: "#2E9D8F" },
          { label: "Disabled", value: t.disabled || 0, color: "#8A8886" }
        ];
        var other = (t.total || 0) - startSeries.reduce(function (a, s) { return a + s.value; }, 0);
        if (other > 0) startSeries.push({ label: "Boot / system", value: other, color: "#8764B8" });
        var startTypes = '<div class="chart-row">' + Charts.donut(startSeries, { center: t.total || 0, sub: "services" }) + Charts.legend(startSeries) + "</div>";
        var stateSeries = [{ label: "Running", value: t.running || 0, color: "#107C41" }, { label: "Stopped", value: t.stopped || 0, color: "#C8CDD2" }];
        var states = '<div class="chart-row">' + Charts.donut(stateSeries, { center: t.running || 0, sub: "running" }) + Charts.legend(stateSeries) + "</div>";
        var kinds = {};
        findings.forEach(function (f) { kinds[f.label] = (kinds[f.label] || 0) + 1; });
        var kindChart = findings.length ? Charts.hbars(Object.keys(kinds).map(function (k) { return { label: k, value: kinds[k] }; }), { title: "Found by the analysis" })
          : '<p class="empty">Nothing to turn off.</p>';

        var startup = (d.startup || []).length
          ? '<div class="tag-list">' + d.startup.map(function (n) { return '<span class="badge">' + esc(n) + "</span>"; }).join("") + "</div>" +
            '<p class="muted small" style="margin-top:12px">Disable the ones you do not need in Task Manager › Startup apps.</p>'
          : '<p class="empty">No startup programs found.</p>';
        var backup = '<p class="muted" style="margin-top:0">' + (d.backup_count ? d.backup_count + " service(s) changed by this suite can be restored to their original start type." :
          "No service has been changed by this suite yet.") + ' <span class="muted small">' + (d.protected_present || 0) + " protected services (Defender, Windows Update, networking, audio…) are never modified.</span></p>" +
          (d.backup_count ? '<button class="btn" data-run="services.restore">' + UI.icon("refresh") + "Restore modified services</button>" : "");
        var tools = UI.button("Analyse again", 'data-audit-refresh', "btn-ghost", "refresh") + " " +
          UI.button("Apply selected", 'data-audit-apply', "btn-primary", "check");

        el.innerHTML = parts.header + parts.errors + kpis +
          '<div class="grid grid-3">' + UI.card("Start types", startTypes) + UI.card("Service state", states) + UI.card("Found by kind", kindChart) + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" + '<div class="grid">' + parts.actions + "</div>" +
          '<div class="grid">' + UI.card("Service analysis", '<div id="audit-intro">' + auditIntro(audit) + '</div><div id="audit-table">' + auditTable(audit) + "</div>", tools) + "</div>" +
          '<div class="grid grid-2">' + UI.card("Restore backup", backup) + UI.card("Startup programs", startup) + "</div>" +
          '<div class="grid">' + UI.card("All services", '<div id="all-services"></div>', '<span class="muted small">' + (d.all || []).length + " installed</span>", "card-flush") + "</div>" +
          '<div class="grid grid-2">' + parts.trend + parts.runs + "</div>";
        Components.dataTable(el.querySelector("#all-services"), {
          rows: d.all || [], exportName: "wmm-services", placeholder: "Search services…", sort: "display",
          filters: [{ key: "state", label: "All states", options: [["Running", "Running"], ["Stopped", "Stopped"]] },
            { key: "start", label: "All start types", options: Object.keys(START).map(function (k) { return [k, START[k]]; }) }],
          columns: [
            { key: "display", title: "Service", render: function (r) { return '<div class="cell-title">' + esc(r.display) + '</div><div class="cell-mono">' + esc(r.name) + "</div>"; } },
            { key: "start", title: "Start type", value: function (r) { return START[r.start] || r.start; } },
            { key: "state", title: "State", render: function (r) { return r.state === "Running" ? '<span class="badge badge-status-ok">Running</span>' : '<span class="badge">' + esc(r.state) + "</span>"; } },
            { key: "protected", title: "Protected", value: function (r) { return r.protected ? "Yes" : ""; },
              render: function (r) { return r.protected ? '<span class="badge badge-status-info">' + UI.icon("shield") + "Never modified</span>" : ""; } }
          ]
        });

        function busy(b, on) { b.disabled = on; b.classList.toggle("busy", on); }
        el.querySelector("[data-audit-refresh]").addEventListener("click", function (e) {
          var b = e.currentTarget;
          busy(b, true);
          API.get("/services/audit").then(function (a) {
            el.querySelector("#audit-intro").innerHTML = auditIntro(a);
            el.querySelector("#audit-table").innerHTML = auditTable(a);
            UI.toast("Analysis updated.", "ok");
          }, function (err) { UI.toast(err.message, "error"); }).then(function () { busy(b, false); });
        });
        el.querySelector("[data-audit-apply]").addEventListener("click", function (e) {
          var b = e.currentTarget;
          var nomi = Array.prototype.map.call(el.querySelectorAll("input[data-audit]:checked"), function (c) { return c.getAttribute("data-audit"); });
          if (!nomi.length) { UI.toast("Tick the services to change first.", "info"); return; }
          UI.confirm("Change " + nomi.length + " service(s)", "The ticked services are stopped and disabled or set to Manual. Their original start type goes into the backup: " +
            "Restore modified services puts them back.", { ok: "Change them" }).then(function (ok) {
            if (!ok) return;
            busy(b, true);
            UI.withRestorePoint("/services/audit/apply", { services: nomi }).then(function (r) {
              UI.toast(r && r.preview ? "Preview mode: nothing was changed." : nomi.length + " service(s) changed.", "ok");
              self.render(el, App);
            }, function (err) { if (!err.cancelled) UI.toast(err.message, "error"); busy(b, false); });
          });
        });
        UI.bindArea(el, "services", function () { self.render(el, App); });
      });
    }
  };
})();
