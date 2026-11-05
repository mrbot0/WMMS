/* PCs of the network: the read-only summary of other PCs where Windows Maintenance Manager shares it, side by side with
   this one, the sharing of this PC (key, port, firewall) and, when the other PC allows it, reports or safe fixes run on it. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;

  // Summaries come from other PCs: numbers are checked here too, text always goes through esc().
  function score(v) { return typeof v !== "number" ? '<span class="cell-sub">—</span>' : '<span class="badge badge-status-' + UI.tone(v) + '">' + Math.round(v) + "</span>"; }
  function free(s) {
    if (!s || typeof s.c_free_gb !== "number" || typeof s.c_total_gb !== "number" || !s.c_total_gb) return "—";
    var pct = s.c_free_gb / s.c_total_gb;
    return '<span class="' + (pct < 0.1 ? "text-warning" : "") + '">' + esc(s.c_free_gb.toFixed(1) + " GB (" + Math.round(pct * 100) + "%)") + "</span>";
  }
  function row(nome, indirizzo, stato, s, errore, id) {
    var insicuri = s && Array.isArray(s.unsafe_apps) ? s.unsafe_apps : null;
    return { id: id || "", name: nome, address: indirizzo, status: stato, overall: s ? s.overall : null, issues: s ? s.open_issues : null,
      unsafe: insicuri ? insicuri.length : null, unsafeNames: insicuri ? insicuri.join(", ") : "", free: s, version: s ? s.version : "",
      last_scan: s ? s.last_scan : null, error: errore || "" };
  }

  window.Pages.fleet = {
    title: "PCs",
    render: function (el, App) {
      return API.get("/fleet").then(function (d) {
        var righe = [row(d.this_pc.hostname + " (this PC)", "—", "online", d.this_pc)].concat(d.pcs.map(function (p) {
          return row(p.name, p.address + ":" + p.port, p.status, p.summary, p.error, p.id);
        }));
        var online = d.pcs.filter(function (p) { return p.status === "online"; }).length;
        var weak = righe.filter(function (r) { return r.overall != null && r.overall < 60; }).length;
        App.setSubtitle(d.pcs.length + " PCs of the network · " + online + " reachable");
        var root = document.createElement("div");
        root.innerHTML = UI.pageHeader("PCs", "Health of the PCs of the network, read-only", UI.button("Refresh", "data-fleet-refresh", "", "refresh") +
          UI.button("Run on several PCs", "data-fleet-batch", "", "play") + UI.button("Add a PC", "data-fleet-add", "btn-primary", "network")) +
          '<div class="grid grid-4">' +
          UI.kpi("PCs", Components.num(righe.length), online + " of " + d.pcs.length + " others reachable", "info") +
          UI.kpi("Need attention", Components.num(weak), "health under 60", weak ? "warning" : "ok") +
          UI.kpi("Unsafe programs", Components.num(righe.reduce(function (s, r) { return s + (r.unsafe || 0); }, 0)), "on the PCs that report them", "info") +
          UI.kpi("This PC shares", d.share.enabled ? "On" : "Off", d.share.enabled ? "port " + d.share.port + (d.share.running ? "" : " · not running") : "other consoles cannot read it",
            d.share.enabled ? "ok" : "info") + "</div>" +
          '<div class="grid">' + UI.card("PCs of the network", '<div id="fleet-table"></div>', "", "card-flush") + "</div>" +
          '<div class="grid">' + UI.card("Share this PC", share(d.share)) + "</div>" + '<div class="grid" id="ins-phone"></div>';
        el.innerHTML = "";
        el.appendChild(root);
        Insights28.phone(root.querySelector("#ins-phone"));

        Components.dataTable(root.querySelector("#fleet-table"), {
          rows: righe, exportName: "wmm-pcs", placeholder: "Search PCs…", sort: "overall", pageSize: 25, empty: "No PC yet.",
          columns: [
            { key: "name", title: "PC", render: function (r) { return '<span class="cell-title">' + esc(r.name) + '</span><div class="cell-sub cell-mono">' + esc(r.address) + "</div>"; } },
            { key: "status", title: "State", render: function (r) {
              return r.status === "online" ? '<span class="badge badge-status-ok">Reachable</span>' : '<span class="badge badge-status-error">Not reachable</span>' +
                '<div class="cell-sub">' + esc(r.error) + "</div>"; } },
            { key: "overall", title: "Health", cls: "num", render: function (r) { return score(r.overall); } },
            { key: "issues", title: "Improvements", cls: "num", render: function (r) { return r.issues == null ? "—" : esc(String(r.issues)); } },
            { key: "unsafe", title: "Unsafe programs", cls: "num", render: function (r) {
              return r.unsafe == null ? '<span class="cell-sub" title="Open Applications on that PC once">—</span>' : '<span title="' + esc(r.unsafeNames) + '">' + r.unsafe + "</span>"; } },
            { key: "free", title: "Free on C:", value: function (r) { return r.free && r.free.c_free_gb; }, render: function (r) { return free(r.free); } },
            { key: "last_scan", title: "Last scan", render: function (r) { return r.last_scan ? esc(UI.relative(r.last_scan)) : "—"; } },
            { key: "version", title: "Version", render: function (r) { return '<span class="cell-mono">' + esc(r.version || "—") + "</span>"; } },
            { key: "id", title: "", sortable: false, csv: false, render: function (r) {
              return r.id ? (r.status === "online" ? '<button class="btn btn-sm" type="button" data-fleet-run="' + esc(r.id) + '" title="Run reports or safe fixes on this PC">' +
                UI.icon("play") + "Run…</button> " : "") + '<button class="btn btn-sm btn-ghost" type="button" data-fleet-remove="' + esc(r.id) + '" title="Remove from the list">' +
                UI.icon("trash") + "</button>" : ""; } }
          ]
        });

        root.addEventListener("change", function (e) {
          if (e.target.id !== "fleet-remote") return;
          API.put("/fleet/share", { enabled: d.share.enabled, port: d.share.port, remote_runs: e.target.value }).then(function () {
            UI.toast(e.target.value === "off" ? "Remote runs turned off." : "Saved: other consoles with the key can run what you allowed.", "ok");
          }, function (err) { UI.toast(err.message, "error"); App.render(); });
        });
        root.addEventListener("click", function (e) {
          var b = e.target.closest("button");
          if (!b) return;
          var id;
          if (b.hasAttribute("data-fleet-refresh")) { App.render(); return; }
          if (b.hasAttribute("data-fleet-add")) { add(App); return; }
          if (b.hasAttribute("data-fleet-batch")) { Insights28.batch(App, d.pcs); return; }
          if ((id = b.getAttribute("data-fleet-run"))) {
            Insights.remoteRun(App, righe.filter(function (r) { return r.id === id; })[0]);
            return;
          }
          if ((id = b.getAttribute("data-fleet-remove"))) {
            UI.confirm("Remove this PC", "It leaves this list; nothing changes on the PC itself.", { ok: "Remove" }).then(function (ok) {
              if (ok) API.del("/fleet/pcs/" + id).then(function () { App.render(); }, function (err) { UI.toast(err.message, "error"); });
            });
            return;
          }
          if (b.hasAttribute("data-share-key")) { newKey(App); return; }
          if (b.hasAttribute("data-share-toggle")) {
            var porta = Number(root.querySelector("#share-port").value) || 8766;
            API.put("/fleet/share", { enabled: !d.share.enabled, port: porta }).then(function () { App.render(); }, function (err) { UI.toast(err.message, "error"); });
            return;
          }
          if (b.hasAttribute("data-share-firewall")) {
            API.post("/fleet/share/firewall").then(function (r) {
              UI.toast(r.preview ? "Preview mode: the firewall rule was simulated." : "Firewall rule added: PCs of the local network can read the summary.", r.preview ? "info" : "ok");
            }, function (err) { UI.toast(err.message, "error"); });
          }
        });
      });
    }
  };

  function share(s) {
    return '<p class="muted" style="margin-top:0">Other consoles can read a short summary of this PC: health scores, number of improvements, unsafe programs, ' +
      "free space on C:, version and last scan. Only PCs that know the key can read it, and they can run tools here only if you allow it below.</p>" +
      '<div class="form"><label>Port<input id="share-port" type="number" min="1024" max="65535" value="' + esc(String(s.port)) + '" style="max-width:120px"></label></div>' +
      '<div class="page-actions" style="justify-content:flex-start">' +
      UI.button(s.has_key ? "Create a new key" : "Create the key", "data-share-key", s.has_key ? "btn-sm" : "btn-sm btn-primary", "security") +
      (s.has_key ? UI.button(s.enabled ? "Stop sharing" : "Share this PC", "data-share-toggle", s.enabled ? "btn-sm" : "btn-sm btn-primary", "network") : "") +
      (s.enabled ? UI.button("Allow it in the firewall", "data-share-firewall", "btn-sm btn-ghost", "shield") : "") + "</div>" +
      '<div class="form" style="margin-top:10px">' + Insights.remoteSetting(s) + "</div>" +
      '<p class="cell-sub">The summary travels in clear text on the local network: share it on trusted networks (office, home), not on public Wi-Fi.</p>';
  }

  function newKey(App) {
    UI.confirm("Create a sharing key", "A new key replaces the old one: consoles that use the old key stop reading this PC until you give them the new one.", { ok: "Create" })
      .then(function (ok) {
        if (!ok) return;
        API.post("/fleet/share/key").then(function (r) {
          UI.modal("Sharing key", '<p class="modal-text">Copy it now into the console of the other PC (PCs › Add a PC): it is not shown again.</p>' +
            '<pre class="code-block">' + esc(r.key) + "</pre>", [{ label: "Copy and close", cls: "btn-primary", value: function () { return true; } }])
            .then(function () { App.copyText(r.key, "Key"); App.render(); });
        }, function (err) { UI.toast(err.message, "error"); });
      });
  }

  function add(App) {
    UI.modal("Add a PC", '<form class="form" onsubmit="return false">' +
      '<label>Name<input name="name" maxlength="60" placeholder="Reception"></label>' +
      '<div class="form-row"><label>PC name or IP address<input name="address" placeholder="192.168.1.20"></label>' +
      '<label>Port<input name="port" type="number" value="8766" style="max-width:110px"></label></div>' +
      '<label>Key<input name="key" autocomplete="off" placeholder="Shown on that PC when you created it"></label>' +
      '<span class="hint">Only addresses of the local network are accepted. On that PC: PCs › Share this PC.</span></form>',
      [{ label: "Cancel", cls: "btn-ghost" }, { label: "Add", cls: "btn-primary", value: function (w) {
        var f = w.querySelector("form");
        return { name: f.name.value, address: f.address.value.trim(), port: Number(f.port.value) || 8766, key: f.key.value.trim() };
      } }]).then(function (v) {
      if (!v) return;
      API.post("/fleet/pcs", v).then(function () { UI.toast(v.name + " added.", "ok"); App.render(); }, function (err) { UI.toast(err.message, "error"); });
    });
  }
})();
