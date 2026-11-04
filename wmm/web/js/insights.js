/* 2.7 cards shared by several pages: guided diagnosis (Toolbox), your own tools (Toolbox), suspicious changes (Security),
   disk and battery trend (Hardware), connection log and known exploited vulnerabilities (Network scanner), remote runs
   (PCs). Each function fills the box it is given and handles its own buttons. */
(function () {
  "use strict";
  var esc = UI.esc;
  function when(iso) { return iso ? UI.formatDate(iso, true) : "never"; }
  function busy(b, on) { if (b) { b.disabled = on; b.classList.toggle("busy", on); } }
  // Closes the topmost dialog (UI.modal closes on a click on its backdrop).
  function closeTop() {
    var all = document.querySelectorAll("#modal-root .modal-backdrop"), top = all[all.length - 1];
    if (top) top.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }

  // ---------- guided diagnosis ----------
  var STATE = { needed: ["badge-status-warning", "Needed"], fine: ["badge-status-ok", "Already fine"], unknown: ["", "Not readable"],
    manual: ["", "Try if the others do not help"] };
  function diagnose(symptom, App) {
    UI.toast("Reading the state of this PC: a few seconds. Nothing is changed.", "info");
    return API.post("/symptoms/" + symptom.id + "/diagnose").then(function (d) {
      var it = window.I18N && I18N.lang() === "it";
      var body = '<p class="modal-text"><span>' + esc(d.note) + "</span></p>" +
        UI.table([{ title: "Fix" }, { title: "What this PC shows now" }, { title: "" }], d.steps.map(function (p) {
          var a = App.state.actions[p.action_id] || { title: p.action_id }, s = STATE[p.state] || STATE.unknown;
          return ["<strong>" + esc(a.title) + "</strong>" + (p.label ? '<div class="cell-sub">' + esc(p.label) + "</div>" : ""),
            p.reading ? '<span class="cell-mono">' + esc(p.reading) + "</span>" : "—", '<span class="badge ' + s[0] + '">' + esc(s[1]) + "</span>"];
        })) + (d.reports.length ? '<p class="muted small"><span>To understand the cause, also read the reports:</span> ' +
          d.reports.map(function (id) { return esc((App.state.actions[id] || { title: id }).title); }).join(", ") + ".</p>" : "");
      var buttons = [{ label: "Close", cls: "btn-ghost" }];
      if (d.reports.length) buttons.push({ label: "Run the reports", value: function () { return "reports"; } });
      if (d.recommended.length) buttons.push({ label: "Run the recommended fixes", cls: "btn-primary", value: function () { return "fixes"; } });
      return UI.modal(it ? d.title_it : d.title, body, buttons).then(function (scelta) {
        if (scelta === "fixes") App.runActions(d.recommended);
        if (scelta === "reports") App.runActions(d.reports);
      });
    }).catch(function (e) { UI.toast(e.message, "error"); });
  }

  // ---------- your own tools ----------
  function opt(list, current, labels) {
    return list.map(function (v) { return '<option value="' + v + '"' + (v === current ? " selected" : "") + ">" + esc(labels ? labels[v] : v) + "</option>"; }).join("");
  }
  function toolForm(t) {
    t = t || { kind: "fix", risk: "moderate", area: "integrity", minutes: 1 };
    return '<form class="form ct-form" onsubmit="return false">' +
      '<label>Name<input name="title" maxlength="80" required value="' + esc(t.title || "") + '"></label>' +
      '<label>Description<input name="description" maxlength="300" value="' + esc(t.description || "") + '"></label>' +
      '<div class="form-row"><label>Kind<select name="kind">' + opt(["fix", "report"], t.kind, { fix: "Fix (changes the PC)", report: "Report (read-only)" }) + "</select></label>" +
      '<label>Area<select name="area">' + opt(UI.AREAS, t.area, UI.AREA_LABEL) + "</select></label>" +
      '<label>Risk<select name="risk">' + opt(["safe", "moderate", "high"], t.risk, { safe: "Safe", moderate: "Moderate", high: "High" }) + "</select></label>" +
      '<label>Minutes<input name="minutes" type="number" min="0.1" max="120" step="0.1" value="' + esc(String(t.minutes || 1)) + '"></label></div>' +
      '<label>PowerShell script<textarea name="script" rows="6" required spellcheck="false" data-no-i18n>' + esc(t.script || "") + "</textarea></label>" +
      '<label>Warning shown before it runs (optional)<input name="warning" maxlength="200" value="' + esc(t.warning || "") + '"></label>' +
      '<fieldset class="ct-fix"><legend>Check and undo (fixes only, optional)</legend>' +
      '<label>Check script: prints one line, read before and after<textarea name="check" rows="2" spellcheck="false" data-no-i18n>' + esc(t.check || "") + "</textarea></label>" +
      '<div class="form-row"><label>What is checked<input name="check_label" maxlength="80" value="' + esc(t.check_label || "") + '"></label>' +
      '<label>Healthy value (the exact line)<input name="healthy" maxlength="200" value="' + esc(t.healthy || "") + '"></label></div>' +
      '<label>Undo script: History › Undo runs it<textarea name="undo" rows="3" spellcheck="false" data-no-i18n>' + esc(t.undo || "") + "</textarea></label></fieldset></form>";
  }
  function readForm(w) {
    var f = w.querySelector(".ct-form"), d = {};
    ["title", "description", "kind", "area", "risk", "minutes", "script", "warning", "check", "check_label", "healthy", "undo"].forEach(function (k) {
      d[k] = f.elements[k].value;
    });
    d.minutes = parseFloat(d.minutes) || 1;
    return d;
  }
  function reloadCatalog(App) {
    return API.get("/actions").then(function (r) {
      Object.keys(App.state.actions).forEach(function (id) { if (id.indexOf("custom.") === 0) delete App.state.actions[id]; });
      r.actions.forEach(function (a) { App.state.actions[a.id] = a; });
      App.render();
    });
  }
  function editTool(App, t) {
    return UI.modal(t ? "Edit " + t.title : "New tool", toolForm(t), [{ label: "Cancel", cls: "btn-ghost" },
      { label: "Save", cls: "btn-primary", value: function (w) { return readForm(w); } }]).then(function (d) {
      if (!d) return null;
      return (t ? API.put("/custom-tools/" + t.id, d) : API.post("/custom-tools", d)).then(function () {
        UI.toast("Saved: the tool is in the Toolbox, in its area.", "ok");
        return reloadCatalog(App);
      });
    }).catch(function (e) { UI.toast(e.message, "error"); });
  }
  function manageTools(App) {
    return API.get("/custom-tools").then(function (d) {
      var body = '<div class="ct-list">' + (d.tools.length ? UI.table([{ title: "Tool" }, { title: "Area" }, { title: "" }], d.tools.map(function (t) {
        return ["<strong>" + esc(t.title) + "</strong>" + '<div class="cell-sub">' + esc((t.kind === "report" ? "Report" : "Fix") + " · " + t.risk +
          (t.check ? " · check" : "") + (t.undo ? " · undo" : "")) + "</div>", esc(UI.AREA_LABEL[t.area] || t.area),
          '<button type="button" class="btn btn-sm" data-ct-edit="' + esc(t.id) + '">Edit</button> <button type="button" class="btn btn-sm btn-ghost" data-ct-del="' +
          esc(t.id) + '" title="Delete">' + UI.icon("trash") + "</button>"];
      })) : '<p class="modal-text">No tool of your own yet. A tool is a PowerShell script with an area and a risk; for fixes you can add a check, read before ' +
        "and after, and an undo script.</p>") + "</div>";
      var finestra = UI.modal("Your tools", body, [{ label: "Close", cls: "btn-ghost" }, { label: "New tool", cls: "btn-primary", value: function () { return "new"; } }]);
      var lista = document.querySelector("#modal-root .modal-backdrop:last-child .ct-list");
      if (lista) lista.addEventListener("click", function (e) {
        var ed = e.target.closest("[data-ct-edit]"), del = e.target.closest("[data-ct-del]");
        if (ed) {
          var t = d.tools.filter(function (x) { return x.id === ed.getAttribute("data-ct-edit"); })[0];
          closeTop();
          editTool(App, t);
        }
        if (del) {
          API.del("/custom-tools/" + del.getAttribute("data-ct-del")).then(function () { UI.toast("Tool deleted.", "ok"); closeTop(); reloadCatalog(App); },
            function (err) { UI.toast(err.message, "error"); });
        }
      });
      return finestra.then(function (v) { if (v === "new") return editTool(App); });
    }).catch(function (e) { UI.toast(e.message, "error"); });
  }

  // ---------- suspicious changes (Security) ----------
  var CAT = {};
  var KIND = { added: ["badge-status-warning", "New"], changed: ["badge-status-info", "Changed"], removed: ["", "Removed"] };
  function driftRows(list, kind) {
    return list.map(function (v) {
      var extra = v.detail && ["line", "installed", "excluded"].indexOf(v.detail) < 0 ? '<div class="cell-sub cell-mono">' + esc(v.detail.slice(0, 160)) + "</div>" : "";
      return ['<span class="badge ' + KIND[kind][0] + '">' + esc(KIND[kind][1]) + "</span>", esc(CAT[v.category] || v.category),
        '<span class="cell-mono">' + esc(v.item) + "</span>" + extra];
    });
  }
  function drift(box) {
    if (!box) return;
    function draw(d) {
      CAT = d.categories || CAT;
      var l = d.last, list = l ? driftRows(l.added || [], "added").concat(driftRows(l.changed || [], "changed"), driftRows(l.removed || [], "removed")) : [];
      var corpo = !d.checked
        ? '<p class="modal-text">Takes a snapshot of startup programs, scheduled tasks, services, browser extensions, proxy, hosts file, antivirus exclusions ' +
          "and administrators. Every later check reports what appeared or changed: the first sign of adware and malware.</p>"
        : '<p class="cell-sub">' + esc("Last check " + when(d.checked) + " · baseline from " + when(d.baseline_from)) + "</p>" +
          (l && l.first ? '<div class="callout callout-info">' + UI.icon("info") + "<div>First snapshot taken: the next check compares with it.</div></div>"
            : list.length ? UI.table([{ title: "" }, { title: "Where" }, { title: "What" }], list.slice(0, 60))
              : '<div class="callout callout-info">' + UI.icon("shield") + "<div>Nothing changed since the previous check.</div></div>");
      box.innerHTML = UI.card("Suspicious changes", corpo,
        UI.button("Check now", "data-drift-check", "btn-sm", "refresh") + UI.button("Schedule it", 'data-schedule="security.drift_watch"', "btn-sm", "clock"));
    }
    API.get("/security/drift").then(draw, function () { draw({}); });
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-drift-check]");
      if (!b) return;
      busy(b, true);
      UI.toast("Taking a snapshot: up to a minute.", "info");
      API.post("/security/drift").then(draw, function (err) { UI.toast(err.message, "error"); busy(b, false); });
    });
  }

  // ---------- disk and battery trend (Hardware) ----------
  function trends(box) {
    if (!box) return;
    function draw(d) {
      var righe = (d.disks || []).map(function (x) {
        return ["<strong>" + esc(x.name) + "</strong>" + '<div class="cell-sub">' + esc(x.media + " · " + x.health) + "</div>",
          x.wear != null ? esc(x.wear + "%") : "—", x.wear_per_month != null ? esc("+" + x.wear_per_month + "% / month") : "—",
          x.worn_out ? '<span class="badge badge-status-warning">' + esc(x.worn_out) + "</span>" : "—",
          x.new_errors ? '<span class="badge badge-status-error">' + esc(String(x.new_errors)) + "</span>" : "0"];
      });
      var batt = (d.batteries || []).map(function (b) {
        return ["<strong>" + esc(b.name) + "</strong>", esc(b.capacity_pct + "%"), b.loss_per_month != null ? esc("-" + b.loss_per_month + "% / month") : "—",
          b.below_limit ? '<span class="badge badge-status-warning">' + esc(b.below_limit) + "</span>" : "—", ""];
      });
      var serie = (d.disks || [])[0] && d.disks[0].series;
      var corpo = d.samples
        ? '<p class="cell-sub">' + esc(d.samples + " daily readings since " + when(d.first)) + "</p>" +
          UI.table([{ title: "Device" }, { title: "Now" }, { title: "Trend" }, { title: "Estimated end" }, { title: "New errors" }], righe.concat(batt)) +
          (d.samples < 8 ? '<p class="muted small">The estimates need at least a week of readings: schedule the trend once a day.</p>' : "") +
          (serie && serie.length > 1 ? Charts.line([{ name: "Wear", points: serie.map(function (p) { return { x: p.t, y: p.value }; }) }], { height: 110 }) : "")
        : '<p class="modal-text">Records once a day the wear, temperature and errors of every disk and the battery capacity, and estimates when a disk ' +
          "will be worn out or the battery will hold less than 60%. SMART values need administrator rights.</p>";
      box.innerHTML = UI.card("Disk and battery trend", corpo,
        UI.button("Read now", "data-trend-read", "btn-sm", "refresh") + UI.button("Schedule it", 'data-schedule="storage.health_trend"', "btn-sm", "clock"));
    }
    API.get("/hardware/trends").then(draw, function () { draw({}); });
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-trend-read]");
      if (!b) return;
      busy(b, true);
      API.post("/hardware/trends").then(draw, function (err) { UI.toast(err.message, "error"); busy(b, false); });
    });
  }

  // ---------- connection log and vulnerabilities (Network scanner) ----------
  var CAUSE = { local: "Router or Wi-Fi", provider: "Provider", dns: "DNS" };
  function connection(box) {
    if (!box) return;
    function draw(d) {
      var s = d.samples || [], last = s[s.length - 1], out = (d.outages || []).slice(-8).reverse();
      var bars = s.slice(-96).map(function (c) {
        var bad = c.gateway && c.gateway_ms == null ? "local" : c.internet_ms == null ? "provider" : c.dns_ms == null ? "dns" : "";
        var h = c.internet_ms == null ? 100 : Math.min(100, Math.max(4, c.internet_ms / 2));
        return '<span class="' + (bad ? "weak" : "") + '" style="height:' + h + '%" title="' + esc(UI.formatDate(c.t, true) + " · " +
          (bad ? CAUSE[bad] : "internet " + c.internet_ms + " ms")) + '"></span>';
      }).join("");
      var corpo = s.length
        ? '<div class="grid grid-3">' + UI.kpi("Readings", Components.num(s.length), "since " + when(s[0].t), "info") +
          UI.kpi("Outages", Components.num((d.outages || []).length), last ? "last reading " + when(last.t) : "", (d.outages || []).length ? "warning" : "ok") +
          UI.kpi("Average internet time", d.average_ms != null ? d.average_ms + " ms" : "—",
            last ? "router " + (last.gateway_ms != null ? last.gateway_ms + " ms" : "no answer") : "", "info") + "</div>" +
          '<div class="muted small">Last readings (orange: no answer)</div><div class="wifi-hours conn-bars">' + bars + "</div>" +
          (out.length ? "<h3>Latest outages</h3>" + UI.table([{ title: "From" }, { title: "To" }, { title: "Cause" }], out.map(function (o) {
            return [esc(UI.formatDate(o.from, true)), esc(UI.formatDate(o.until, true)), esc(CAUSE[o.cause] || o.cause)];
          })) : "")
        : '<p class="modal-text">Each reading times the router, the internet and name resolution. Scheduled every 5-10 minutes it shows when the ' +
          "connection drops and whether the cause is the Wi-Fi or router, the provider or DNS.</p>";
      box.innerHTML = UI.card("Connection log", corpo,
        UI.button("Read now", "data-conn-read", "btn-sm", "refresh") + UI.button("Schedule it", 'data-schedule="network.connection_watch"', "btn-sm", "clock"));
    }
    API.get("/network/connection").then(draw, function () { draw({}); });
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-conn-read]");
      if (!b) return;
      busy(b, true);
      API.post("/network/connection").then(draw, function (err) { UI.toast(err.message, "error"); busy(b, false); });
    });
  }
  function kev(box) {
    if (!box) return;
    function draw(d) {
      var f = (d && d.found) || [];
      var corpo = d && d.checked
        ? '<p class="cell-sub">' + esc(d.devices_checked + " devices compared with " + d.catalog_entries + " vulnerabilities · CISA catalog " + (d.catalog_version || "")) + "</p>" +
          (f.length ? UI.table([{ title: "Device" }, { title: "Vulnerabilities" }], f.map(function (x) {
            return ["<strong>" + esc(x.device || x.ip) + "</strong>" + '<div class="cell-sub cell-mono">' + esc(x.ip + " · " + x.vendor) + "</div>",
              x.matches.slice(0, 4).map(function (v) { return '<div><span class="cell-mono">' + esc(v.cveID) + "</span> " + esc(v.vulnerabilityName) + "</div>"; }).join("") +
              (x.ransomware ? '<span class="badge badge-status-error">Used by ransomware</span>' : "")];
          })) + '<p class="muted small">Update the firmware of these devices from the maker\'s site. A match means the model is in the catalog, not that your firmware is vulnerable.</p>'
            : '<div class="callout callout-info">' + UI.icon("shield") + "<div>No device of the network matches the catalog.</div></div>")
        : '<p class="modal-text">Compares the maker and model of routers, NAS and cameras found by the scan with the CISA catalog of vulnerabilities ' +
          "used in real attacks (downloaded once a day).</p>";
      box.innerHTML = UI.card("Known exploited vulnerabilities", corpo,
        UI.button("Check now", "data-kev-check", "btn-sm", "refresh") + UI.button("Schedule it", 'data-schedule="network.kev_report"', "btn-sm", "clock"));
    }
    draw(null);
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-kev-check]");
      if (!b) return;
      busy(b, true);
      UI.toast("Downloading the CISA catalog and comparing the devices.", "info");
      API.post("/network/kev").then(draw, function (err) { UI.toast(err.message, "error"); busy(b, false); });
    });
  }

  // ---------- remote runs (PCs) ----------
  var LEVEL = [["off", "Off"], ["reports", "Reports only"], ["safe", "Reports and safe fixes"]];
  function remoteSetting(share) {
    return '<label class="tb-label" for="fleet-remote">Remote runs from other consoles</label> <select id="fleet-remote"' + (share.enabled ? "" : " disabled") + ">" +
      LEVEL.map(function (l) { return '<option value="' + l[0] + '"' + (share.remote_runs === l[0] ? " selected" : "") + ">" + esc(l[1]) + "</option>"; }).join("") +
      '</select><p class="muted small">Moderate and high-risk tools never run from another PC. Requests are signed with the key, so it never travels.</p>';
  }
  function remoteRun(App, pc) {
    var scelte = Object.keys(App.state.actions).map(function (id) { return App.state.actions[id]; })
      .filter(function (a) { return a.kind === "report" || a.risk === "safe"; }).sort(function (x, y) { return x.title.localeCompare(y.title); });
    var body = '<p class="modal-text">Choose up to 20 reports or safe fixes to run on <strong>' + esc(pc.name) + "</strong>. That PC runs them only if its user allowed remote runs.</p>" +
      '<select multiple size="12" class="fleet-pick" style="width:100%">' + scelte.map(function (a) {
        return '<option value="' + esc(a.id) + '">' + esc(a.title) + (a.kind === "report" ? " (report)" : " (fix)") + "</option>";
      }).join("") + "</select>";
    return UI.modal("Run on " + pc.name, body, [{ label: "Cancel", cls: "btn-ghost" }, { label: "Run", cls: "btn-primary", value: function (w) {
      return Array.prototype.map.call(w.querySelector(".fleet-pick").selectedOptions, function (o) { return o.value; });
    } }]).then(function (ids) {
      if (!ids || !ids.length) return null;
      return API.post("/fleet/pcs/" + pc.id + "/run", { actions: ids.slice(0, 20) }).then(function (r) {
        UI.toast("Started on " + pc.name + ": the results appear when it finishes.", "ok");
        var tries = 0;
        (function poll() {
          API.get("/fleet/pcs/" + pc.id + "/runs/" + r.id).then(function (j) {
            if (j.active && tries++ < 240) { setTimeout(poll, 3000); return; }
            UI.modal("Results on " + pc.name, UI.table([{ title: "Tool" }, { title: "Result" }, { title: "Check" }, { title: "Note" }], j.results.map(function (x) {
              var a = App.state.actions[x.action_id] || { title: x.action_id };
              return [esc(a.title), UI.statusBadge(x.status), UI.verdictBadge(x.verify) || "—", '<span class="cell-sub">' + esc(x.note) + "</span>"];
            })), [{ label: "Close", cls: "btn-ghost" }]);
          }, function (err) { UI.toast(err.message, "error"); });
        })();
      });
    }).catch(function (e) { UI.toast(e.message, "error"); });
  }

  window.Insights = { diagnose: diagnose, manageTools: manageTools, editTool: editTool, drift: drift, trends: trends, connection: connection, kev: kev,
    remoteSetting: remoteSetting, remoteRun: remoteRun };
})();
