/* 2.8 cards: blue screens explained and signs of a coming failure (Integrity), who slows the startup (Startup & Apps),
   back to the last good configuration and suspicious programs (Security), the console from a phone and the same tools on
   several PCs (PCs), the periodic report (Settings › Notifications) and the assistant (Toolbox). */
(function () {
  "use strict";
  var esc = UI.esc;
  function it() { return window.I18N && I18N.lang() === "it"; }
  function pick(o, k) { return it() && o[k + "_it"] ? o[k + "_it"] : o[k]; }
  function when(iso) { return iso ? UI.formatDate(iso, true) : "never"; }
  function busy(b, on) { if (b) { b.disabled = on; b.classList.toggle("busy", on); } }
  function title(App, id) { return ((App && App.state.actions[id]) || { title: id }).title; }
  function lazy(box, cardTitle, intro, button, load, draw) {
    box.innerHTML = UI.card(cardTitle, '<p class="modal-text">' + esc(intro) + "</p>", UI.button(button, "data-ins-load", "btn-sm", "refresh"));
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-ins-load]");
      if (!b) return;
      busy(b, true);
      load().then(draw, function (err) { UI.toast(err.message, "error"); busy(b, false); });
    });
  }

  // ---------- blue screens explained ----------
  function bsod(box, App) {
    if (!box) return;
    function draw(d) {
      var corpo = !d.crashes ? '<div class="callout callout-info">' + UI.icon("shield") + "<div>No blue screen on this PC: no dump and no bugcheck in the System log.</div></div>"
        : '<p class="cell-sub">' + esc(d.crashes + " blue screens, " + d.last_30_days + " in the last 30 days") + "</p>" + d.groups.map(function (g) {
          return '<div class="ins-block"><h3><span class="cell-mono">' + esc(g.code) + "</span> " + esc(g.name) + ' <span class="badge badge-status-warning">' +
            esc(g.count + "×") + '</span></h3><p class="cell-sub">' + esc("Last " + when(g.last)) + "</p>" +
            "<p>" + esc(pick(g, "cause")) + "</p><p><strong>" + esc("What to do:") + "</strong> " + esc(pick(g, "fix")) + "</p>" +
            (g.suspects.length ? '<div class="muted small">' + esc("Installed in the week before the first crash:") + "</div><ul class=\"check-list\">" +
              g.suspects.slice(0, 6).map(function (s) { return '<li><span class="grow">' + esc(s.text) + '</span><span class="cell-sub">' + esc(when(s.at)) + "</span></li>"; }).join("") + "</ul>" : "") +
            (g.tools.length ? '<div class="page-actions" style="justify-content:flex-start">' + g.tools.map(function (id) {
              return App && App.state.actions[id] ? '<button class="btn btn-sm" data-run="' + esc(id) + '">' + esc(title(App, id)) + "</button>" : "";
            }).join("") + "</div>" : "") + "</div>";
        }).join("");
      box.innerHTML = UI.card("Blue screens explained", corpo, UI.button("Read again", "data-ins-load", "btn-sm", "refresh"));
    }
    lazy(box, "Blue screens explained", "Reads the stop code of every blue screen from its dump and from the System log, explains it, and lists the drivers " +
      "installed in the week before the first crash. Read-only.", "Read the blue screens", function () { return API.get("/integrity/crashes"); }, draw);
  }

  // ---------- signs of a coming failure ----------
  function warning(box) {
    if (!box) return;
    function draw(d) {
      var righe = d.signals.map(function (s) {
        return ["<strong>" + esc(pick(s, "title")) + '</strong><div class="cell-sub">' + esc(pick(s, "meaning")) + "</div>", esc(String(s.last_7_days)),
          esc(String(s.weekly_before)), s.growing ? '<span class="badge badge-status-warning">Growing</span>' : '<span class="badge badge-status-ok">Steady</span>'];
      });
      var prev = d.forecasts.map(function (p) { return "<li>" + UI.statusIcon("warning") + '<span class="grow">' + esc(pick(p, "text")) + "</span></li>"; }).join("");
      box.innerHTML = UI.card("Signs of a coming failure",
        UI.table([{ title: "Sign" }, { title: "Last 7 days" }, { title: "A week before" }, { title: "" }], righe) +
        (prev ? '<ul class="check-list">' + prev + "</ul>" : "") +
        '<p class="muted small">Scheduled every day, it sends an e-mail or Telegram alert when a sign grows.</p>',
        UI.button("Read again", "data-ins-load", "btn-sm", "refresh") + UI.button("Schedule it", 'data-schedule="integrity.early_warning"', "btn-sm", "clock"));
    }
    lazy(box, "Signs of a coming failure", "Counts hardware errors, disk retries and resets, file system damage, sudden power losses and blue screens week by week, " +
      "with the disk and battery forecasts. Read-only.", "Check now", function () { return API.get("/integrity/early-warning"); }, draw);
  }

  // ---------- who slows the startup ----------
  var KIND = { program: "Program", driver: "Driver", service: "Service" };
  function bootCard(box, App) {
    if (!box) return;
    function draw(d) {
      if (!d.count) {
        box.innerHTML = UI.card("Who slows the startup", '<p class="modal-text">No boot timing found: the Diagnostics-Performance log is empty or needs administrator rights.</p>',
          UI.button("Read again", "data-ins-load", "btn-sm", "refresh"));
        return;
      }
      var serie = d.boots.map(function (b) { return { x: b.at, y: b.seconds }; });
      var righe = d.culprits.slice(0, 15).map(function (c) {
        var s = c.startup;
        return ["<strong>" + esc(c.friendly || c.name) + '</strong><div class="cell-sub cell-mono">' + esc(c.name) + "</div>", esc(KIND[c.kind] || c.kind),
          esc(c.lost_seconds + " s"), esc(String(c.times)),
          s ? '<button class="btn btn-sm" data-boot-toggle="' + esc(s.id) + '" data-on="' + (s.enabled ? "1" : "0") + '">' + esc(s.enabled ? "Remove from startup" : "Put back at startup") + "</button>" : ""];
      });
      box.innerHTML = UI.card("Who slows the startup",
        '<div class="grid grid-3">' + UI.kpi("Average boot", d.average_seconds + " s", d.count + " boots in " + d.days + " days", "info") +
        UI.kpi("Last boot", d.last_seconds + " s", "", "info") +
        UI.kpi("Trend", d.slower ? "Slower" : "Steady", d.earlier_average && d.recent_average ? d.earlier_average + " s → " + d.recent_average + " s" : "", d.slower ? "warning" : "ok") + "</div>" +
        (serie.length > 1 ? Charts.line([{ name: "Boot seconds", points: serie }], { height: 110 }) : "") +
        UI.table([{ title: "What slowed it" }, { title: "Kind" }, { title: "Seconds lost" }, { title: "Times" }, { title: "" }], righe, "Windows named nothing that slowed the startup.") +
        '<p class="muted small">Removing a program from startup is the same switch as Task Manager: put it back here or in the table above. It is recorded in History.</p>',
        UI.button("Read again", "data-ins-load", "btn-sm", "refresh"));
    }
    lazy(box, "Who slows the startup", "Boot times of the last 90 days and the programs, drivers and services Windows measured as slowing them.",
      "Read the startup times", function () { return API.get("/startup/boot"); }, draw);
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-boot-toggle]");
      if (!b) return;
      var acceso = b.getAttribute("data-on") === "1";
      busy(b, true);
      API.post("/startup/" + b.getAttribute("data-boot-toggle") + "/toggle", { enabled: !acceso }).then(function (r) {
        UI.toast(r.preview ? "Preview mode: nothing changed." : acceso ? "Removed from startup." : "Put back at startup.", "ok");
        b.setAttribute("data-on", acceso ? "0" : "1");
        b.textContent = acceso ? "Put back at startup" : "Remove from startup";
        busy(b, false);
      }, function (err) { UI.toast(err.message, "error"); busy(b, false); });
    });
  }

  // ---------- back to the last good configuration ----------
  var CAT = { run_keys: "Startup programs", startup_folders: "Startup folders", services: "Services", tasks: "Scheduled tasks", hosts: "Hosts file",
    proxy: "Proxy settings", defender_exclusions: "Antivirus exclusions", extensions: "Browser extensions", admins: "Local administrators" };
  function goodConfig(box, App) {
    if (!box) return;
    function draw(d) {
      var opzioni = d.days.map(function (g) { return '<option value="' + esc(g) + '">' + esc(UI.formatDate(g)) + "</option>"; }).join("");
      box.innerHTML = UI.card("Back to the last good configuration",
        (d.days.length ? '<p class="modal-text">Choose a day when the PC worked well: the console compares it with now and shows each change before anything runs.</p>' +
          '<div class="form"><label>Day<select id="gc-day">' + opzioni + "</select></label></div>"
          : '<p class="modal-text">Every check of Suspicious changes keeps a dated copy of startup programs, services, tasks, hosts file, proxy and antivirus ' +
            "exclusions (one a day, 90 days). Schedule that check every day to have days to go back to.</p>") +
        (d.last ? '<p class="cell-sub">' + esc("Last return: " + when(d.last.at) + " to " + d.last.day + ", " + d.last.count + " changes" + (d.last.undone ? " (undone)" : "")) + "</p>" : ""),
        (d.days.length ? UI.button("Compare", "data-gc-plan", "btn-sm btn-primary", "history") : "") +
        (d.last && !d.last.undone ? UI.button("Undo the return", "data-gc-revert", "btn-sm", "history") : ""));
    }
    function load() { return API.get("/security/good-config").then(draw, function (e) { box.innerHTML = UI.errorBox(e); }); }
    load();
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-gc-plan")) {
        var giorno = box.querySelector("#gc-day").value;
        busy(b, true);
        UI.toast("Reading the configuration now: about half a minute.", "info");
        API.post("/security/good-config/plan", { day: giorno }).then(function (p) { busy(b, false); showPlan(p, App).then(load); },
          function (err) { UI.toast(err.message, "error"); busy(b, false); });
      }
      if (b.hasAttribute("data-gc-revert")) {
        UI.confirm("Undo the return", "Every change made by the last return is put back as it was before it.", { ok: "Undo" }).then(function (ok) {
          if (!ok) return;
          API.post("/security/good-config/revert").then(function (r) { UI.toast(r.done + " changes put back, " + r.failed + " failed.", r.failed ? "warning" : "ok"); load(); },
            function (err) { UI.toast(err.message, "error"); });
        });
      }
    });
  }
  function showPlan(p, App) {
    var ops = p.ops.map(function (o) {
      return '<label class="check-row"><input type="checkbox" data-op="' + esc(o.id) + '" checked> <span><strong>' + esc(CAT[o.category] || o.category) + ":</strong> " +
        esc(o.text) + "</span></label>";
    }).join("");
    var manuali = p.manual.map(function (m) {
      return "<li>" + UI.statusIcon("info") + '<span class="grow"><strong>' + esc(CAT[m.category] || m.category) + ":</strong> " + esc(m.item) +
        ' <span class="cell-sub">' + esc(m.reason) + "</span></span></li>";
    }).join("");
    var corse = p.runs.map(function (r) { return "<li>" + esc(title(App, r.action_id)) + ' <span class="cell-sub">' + esc(when(r.started) + " · " + r.undo_count + " values") + "</span></li>"; }).join("");
    var corpo = (ops ? '<p class="modal-text">These changes bring the PC back to ' + esc(UI.formatDate(p.day)) + ". Untick what you want to keep. A restore point is created first.</p>" +
        '<div class="gc-ops">' + ops + "</div>" : '<div class="callout callout-info">' + UI.icon("shield") + "<div>Nothing to put back automatically.</div></div>") +
      (manuali ? "<h3>To check by hand</h3><ul class=\"check-list\">" + manuali + "</ul>" : "") +
      (corse ? "<h3>Fixes run since that day that can be undone</h3><p class=\"muted small\">Undo them one by one from History if they caused the problem.</p><ul>" + corse + "</ul>" : "");
    var bottoni = [{ label: "Close", cls: "btn-ghost" }];
    if (p.ops.length) bottoni.push({ label: "Apply the ticked changes", cls: "btn-primary", value: function (w) {
      return Array.prototype.map.call(w.querySelectorAll("[data-op]:checked"), function (c) { return c.getAttribute("data-op"); });
    } });
    return UI.modal("Back to " + UI.formatDate(p.day), corpo, bottoni).then(function (scelte) {
      if (!scelte || !scelte.length) return null;
      return API.post("/security/good-config/apply", { day: p.day, ops: scelte }).then(function (r) {
        UI.modal("Result", UI.table([{ title: "Change" }, { title: "Result" }], r.results.map(function (x) {
          return [esc(x.text), x.ok ? UI.statusBadge("ok") : UI.statusBadge("error") + '<div class="cell-sub">' + esc(x.error) + "</div>"];
        })) + (r.preview ? '<p class="muted small">Preview mode: nothing changed.</p>' : '<p class="muted small">"Undo the return" puts everything back.</p>'),
        [{ label: "Close", cls: "btn-ghost" }]);
      }, function (err) { UI.toast(err.message, "error"); });
    });
  }

  // ---------- suspicious programs ----------
  var LEVEL = { high: ["badge-status-error", "Suspicious"], medium: ["badge-status-warning", "To check"], low: ["", "Unsigned"] };
  var SOURCE = { running: "Running", run_key: "Startup (registry)", startup_folder: "Startup folder", service: "Service", task: "Scheduled task" };
  function suspicious(box) {
    if (!box) return;
    function draw(v) {
      var d = v.last, s = v.settings;
      var corpo = d ? '<p class="cell-sub">' + esc(d.files + " programs checked · " + when(d.checked)) + "</p>" +
          UI.table([{ title: "Program" }, { title: "Why" }, { title: "Where it starts" }, { title: "" }], d.rows.filter(function (r) { return r.level !== "low"; }).map(function (r) {
            var vt = r.virustotal || {};
            return ["<strong>" + esc(r.name) + '</strong><div class="cell-sub cell-mono">' + esc(r.path) + "</div>",
              (it() ? r.reasons_it : r.reasons).map(function (x) { return "<div>" + esc(x) + "</div>"; }).join("") +
                (vt.known ? '<div class="cell-sub">' + esc("VirusTotal: " + vt.malicious + " of " + vt.engines + " engines") + "</div>" : vt.known === false ? '<div class="cell-sub">VirusTotal: never seen</div>' : ""),
              esc(r.sources.map(function (x) { return SOURCE[x.source] || x.source; }).filter(function (x, i, a) { return a.indexOf(x) === i; }).join(", ")),
              '<span class="badge ' + LEVEL[r.level][0] + '">' + esc(LEVEL[r.level][1]) + "</span>"];
          }), "Nothing suspicious among the programs running or starting with Windows.") +
          (d.counts.low ? '<p class="muted small">' + esc(d.counts.low + " unsigned programs installed in Program Files are not listed: common for small or older programs.") + "</p>" : "")
        : '<p class="modal-text">Checks the signature and the location of every program running or starting with Windows. About half a minute, read-only.</p>';
      box.innerHTML = UI.card("Suspicious programs", corpo +
        '<p class="muted small">' + esc(s.virustotal ? "VirusTotal is on: only the fingerprints of the programs listed are looked up, never the files." :
          "Optional: with a free VirusTotal key, the fingerprints of the programs listed are looked up (never the files).") + "</p>",
        UI.button("Check now", "data-susp-check", "btn-sm", "refresh") + UI.button("VirusTotal key", "data-susp-key", "btn-sm btn-ghost", "security"));
    }
    API.get("/security/suspicious").then(draw, function () { draw({ last: null, settings: {} }); });
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-susp-check")) {
        busy(b, true);
        API.post("/security/suspicious").then(function (d) { return API.get("/security/suspicious"); }).then(draw, function (err) { UI.toast(err.message, "error"); busy(b, false); });
      }
      if (b.hasAttribute("data-susp-key")) {
        UI.modal("VirusTotal key", '<p class="modal-text">Create a free account on virustotal.com and copy the API key from your profile. It is kept encrypted for this ' +
          'Windows user. Leave it empty to remove it.</p><form class="form" onsubmit="return false"><label>API key<input name="k" autocomplete="off" spellcheck="false"></label></form>',
        [{ label: "Cancel", cls: "btn-ghost" }, { label: "Save", cls: "btn-primary", value: function (w) { return w.querySelector("[name=k]").value.trim(); } }]).then(function (k) {
          if (k == null) return;
          API.put("/security/suspicious/settings", { virustotal_key: k }).then(function () { UI.toast(k ? "Key saved." : "Key removed.", "ok"); return API.get("/security/suspicious"); })
            .then(draw, function (err) { UI.toast(err.message, "error"); });
        });
      }
    });
  }

  // ---------- console from a phone ----------
  function phone(box) {
    if (!box) return;
    function draw(d) {
      var url = d.addresses.map(function (a) { return "http://" + a + ":" + d.port; });
      var tel = d.devices.map(function (t) {
        return ["<strong>" + esc(t.name) + "</strong>", esc(when(t.paired)), esc(when(t.last_seen)),
          '<button class="btn btn-sm btn-ghost" data-phone-remove="' + esc(t.id) + '">' + UI.icon("trash") + "Remove</button>"];
      });
      box.innerHTML = UI.card("Console from the phone",
        '<p class="modal-text">A page for a phone of the same network: the state of this PC, its problems, and reports and safe fixes. Moderate and high-risk tools never run from a phone.</p>' +
        '<div class="form"><label>Port<input id="phone-port" type="number" min="1024" max="65535" value="' + esc(String(d.port)) + '" style="max-width:120px"></label></div>' +
        (d.enabled ? '<p>' + esc("On the phone open:") + " " + url.map(function (u) { return '<strong class="cell-mono">' + esc(u) + "</strong>"; }).join(" · ") + "</p>" +
          (d.running ? "" : '<p class="text-warning">Turned on but not running: the port may be in use.</p>') : "") +
        (d.pairing_until ? '<p class="cell-sub">' + esc("A pairing code is waiting until " + when(d.pairing_until)) + "</p>" : "") +
        (tel.length ? UI.table([{ title: "Phone" }, { title: "Paired" }, { title: "Last seen" }, { title: "" }], tel) : ""),
        UI.button(d.enabled ? "Turn off" : "Turn on", "data-phone-toggle", d.enabled ? "btn-sm" : "btn-sm btn-primary", "network") +
        (d.enabled ? UI.button("New code", "data-phone-pair", "btn-sm btn-primary", "security") + UI.button("Allow it in the firewall", "data-phone-firewall", "btn-sm btn-ghost", "shield") : ""));
    }
    function load() { return API.get("/phone").then(draw, function (e) { box.innerHTML = UI.errorBox(e); }); }
    load();
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-phone-toggle")) {
        API.get("/phone").then(function (d) {
          return API.put("/phone", { enabled: !d.enabled, port: Number(box.querySelector("#phone-port").value) || d.port });
        }).then(draw, function (err) { UI.toast(err.message, "error"); });
      } else if (b.hasAttribute("data-phone-pair")) {
        API.post("/phone/pair").then(function (r) {
          UI.modal("Pairing code", '<p class="modal-text">Open the address on the phone and type this code within 10 minutes. It works once and is not shown again.</p>' +
            '<pre class="code-block" style="font-size:24px;letter-spacing:3px;text-align:center">' + esc(r.code) + "</pre>" +
            '<p class="cell-mono">' + r.addresses.map(function (a) { return esc("http://" + a + ":" + r.port); }).join("<br>") + "</p>",
          [{ label: "Done", cls: "btn-primary" }]).then(load);
        }, function (err) { UI.toast(err.message, "error"); });
      } else if (b.hasAttribute("data-phone-firewall")) {
        API.post("/phone/firewall").then(function (r) { UI.toast(r.preview ? "Preview mode: simulated." : "Firewall rule added for the local network.", "ok"); },
          function (err) { UI.toast(err.message, "error"); });
      } else if (b.getAttribute("data-phone-remove")) {
        API.del("/phone/devices/" + b.getAttribute("data-phone-remove")).then(draw, function (err) { UI.toast(err.message, "error"); });
      }
    });
  }

  // ---------- the same tools on several PCs ----------
  function batch(App, pcs) {
    var scelte = Object.keys(App.state.actions).map(function (id) { return App.state.actions[id]; })
      .filter(function (a) { return (a.kind === "report" || a.risk === "safe") && a.id.indexOf("custom.") !== 0; })
      .sort(function (x, y) { return x.title.localeCompare(y.title); });
    var body = '<p class="modal-text">Choose the PCs and up to 20 reports or safe fixes. Each PC runs them only if its user allowed remote runs.</p>' +
      '<div class="gc-ops"><label class="check-row"><input type="checkbox" data-pc="this" checked> <span>This PC</span></label>' +
      pcs.filter(function (p) { return p.status === "online"; }).map(function (p) {
        return '<label class="check-row"><input type="checkbox" data-pc="' + esc(p.id) + '" checked> <span>' + esc(p.name) + "</span></label>";
      }).join("") + "</div>" +
      '<select multiple size="10" class="fleet-pick" style="width:100%">' + scelte.map(function (a) {
        return '<option value="' + esc(a.id) + '">' + esc(a.title) + (a.kind === "report" ? " (report)" : " (fix)") + "</option>";
      }).join("") + "</select>";
    return UI.modal("Run on several PCs", body, [{ label: "Cancel", cls: "btn-ghost" }, { label: "Run", cls: "btn-primary", value: function (w) {
      return { pcs: Array.prototype.map.call(w.querySelectorAll("[data-pc]:checked"), function (c) { return c.getAttribute("data-pc"); }),
        actions: Array.prototype.map.call(w.querySelector(".fleet-pick").selectedOptions, function (o) { return o.value; }).slice(0, 20) };
    } }]).then(function (s) {
      if (!s || !s.pcs.length || !s.actions.length) return null;
      return API.post("/fleet/batch", s).then(function (lotto) {
        var host = document.createElement("div");
        var tries = 0;
        function table(l) {
          return UI.table([{ title: "PC" }].concat(l.actions.map(function (id) { return { title: title(App, id) }; })), l.rows.map(function (r) {
            var celle = l.actions.map(function (id) {
              var x = (r.results || []).filter(function (y) { return y.action_id === id; })[0];
              return x ? UI.statusBadge(x.status) + (UI.verdictBadge(x.verify) ? " " + UI.verdictBadge(x.verify) : "") : r.error ? "—" : r.active ? "…" : "—";
            });
            return ["<strong>" + esc(r.name) + "</strong>" + (r.error ? '<div class="cell-sub text-warning">' + esc(r.error) + "</div>" : "")].concat(celle);
          }));
        }
        host.innerHTML = table(lotto);
        UI.modal("Results on several PCs", '<div class="batch-host"></div>', [{ label: "Close", cls: "btn-ghost" }]);
        var slot = document.querySelector("#modal-root .batch-host:last-of-type");
        if (slot) slot.appendChild(host);
        (function poll(l) {
          host.innerHTML = table(l);
          if (l.active && tries++ < 200 && document.body.contains(host)) setTimeout(function () { API.get("/fleet/batch/" + l.id).then(poll); }, 3000);
        })(lotto);
      });
    }).catch(function (e) { UI.toast(e.message, "error"); });
  }

  // ---------- periodic report ----------
  function digest(box) {
    if (!box) return;
    function draw(d) {
      box.innerHTML = '<p class="muted" style="margin-top:0">A summary of the period since the last report (at most a month), sent with the channels above. ' +
        'Schedule "Periodic report" every week or month.</p>' +
        '<div class="form"><label>Language of the report<select id="digest-lang"><option value="it"' + (d.lang === "it" ? " selected" : "") + '>Italiano</option>' +
        '<option value="en"' + (d.lang === "en" ? " selected" : "") + ">English</option></select></label></div>" +
        '<p class="cell-sub">' + esc(d.last_sent ? "Last sent " + when(d.last_sent) : "Never sent") + "</p>" +
        '<details><summary>Preview</summary><pre class="code-block" data-no-i18n>' + esc(d.title + "\n\n" + d.text) + "</pre></details>" +
        '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Send now", "data-digest-send", "btn-sm btn-primary", "play") +
        UI.button("Schedule it", 'data-schedule="integrity.periodic_report"', "btn-sm", "clock") + "</div>";
    }
    function load() { box.innerHTML = UI.loading("Preparing the report…"); return API.get("/digest").then(draw, function (e) { box.innerHTML = UI.errorBox(e); }); }
    load();
    box.addEventListener("change", function (e) {
      if (e.target.id === "digest-lang") API.put("/digest", { lang: e.target.value }).then(load, function (err) { UI.toast(err.message, "error"); });
    });
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-digest-send]");
      if (!b) return;
      busy(b, true);
      API.post("/digest/send").then(function (r) {
        UI.toast(r.sent ? "Report sent." : "Not delivered: " + Object.keys(r.channels).map(function (k) { return k + " " + r.channels[k]; }).join(" · "), r.sent ? "ok" : "warning");
        load();
      }, function (err) { UI.toast(err.message, "error"); busy(b, false); });
    });
  }

  // ---------- assistant ----------
  var conv = null;
  function assistant(App) {
    API.get("/assistant").then(function (s) {
      if (!s.installed || !s.configured) return setup(App, s);
      chat(App);
    }, function (e) { UI.toast(e.message, "error"); });
  }
  function setup(App, s) {
    var body = '<p class="modal-text">The assistant uses Claude through your own Anthropic API key: the description of the problem and the ' +
      "output of the reports it runs are sent to Anthropic. It never runs a fix by itself.</p>" + '<p class="cell-sub cell-mono">' + esc(s.model) + "</p>" +
      (s.installed ? "" : '<p class="modal-text">' + esc("First the official component is installed (pip install anthropic, about a minute).") + "</p>") +
      '<form class="form" onsubmit="return false"><label>Anthropic API key<input name="k" autocomplete="off" spellcheck="false" placeholder="sk-ant-…"></label></form>';
    UI.modal("Set up the assistant", body, [{ label: "Cancel", cls: "btn-ghost" }, { label: "Save", cls: "btn-primary", value: function (w) { return w.querySelector("[name=k]").value.trim(); } }])
      .then(function (k) {
        if (k == null) return null;
        var passo = s.installed ? Promise.resolve() : (UI.toast("Installing the component…", "info"), API.post("/assistant/install"));
        return passo.then(function () { return k ? API.put("/assistant/key", { api_key: k }) : API.get("/assistant"); }).then(function (n) {
          if (n.installed && n.configured) chat(App); else UI.toast("The key is still missing.", "warning");
        });
      }).catch(function (e) { UI.toast(e.message, "error"); });
  }
  function bubble(m, App) {
    if (m.role === "user") return '<div class="as-msg as-user">' + esc(m.text) + "</div>";
    var passi = (m.steps || []).length ? '<div class="cell-sub">' + esc("Reports read: " + m.steps.map(function (s) { return s.title; }).join(", ")) + "</div>" : "";
    var prop = (m.proposals || []).map(function (p, i) {
      return '<div class="as-prop"><button class="btn btn-sm ' + (p.risk === "safe" ? "btn-primary" : "") + '" data-as-run="' + esc(p.action_id) + '">' + esc((i + 1) + ". " + title(App, p.action_id)) +
        "</button> " + UI.riskBadge(p.risk) + '<div class="cell-sub">' + esc(p.reason) + "</div></div>";
    }).join("");
    return '<div class="as-msg as-bot"><div class="as-text">' + esc(m.text).replace(/\n/g, "<br>") + "</div>" + passi + prop + "</div>";
  }
  function chat(App) {
    var body = '<div class="as-log"></div><form class="form as-form" onsubmit="return false"><label>Describe the problem<textarea name="q" rows="3" maxlength="4000"></textarea></label>' +
      '<div class="page-actions" style="justify-content:flex-start"><button class="btn btn-primary" data-as-send>Send</button><button class="btn btn-ghost" data-as-new>New conversation</button>' +
      '<span class="muted small as-state"></span></div></form><p class="muted small">Answers come from Claude and may be wrong: check the proposed fixes before running them.</p>';
    UI.modal("Assistant", body, [{ label: "Close", cls: "btn-ghost" }]);
    var all = document.querySelectorAll("#modal-root .as-log"), log = all[all.length - 1], w = log.closest(".modal") || log.parentNode;
    function show(v) {
      log.innerHTML = v.history.map(function (m) { return bubble(m, App); }).join("") + (v.error ? '<div class="callout callout-warning">' + esc(v.error) + "</div>" : "");
      log.scrollTop = log.scrollHeight;
      w.querySelector(".as-state").textContent = v.state === "working" ? "Thinking and reading this PC…" : "";
      w.querySelector("[data-as-send]").disabled = v.state === "working";
    }
    function poll(id) {
      API.get("/assistant/chat/" + id).then(function (v) { show(v); if (v.state === "working" && document.body.contains(log)) setTimeout(function () { poll(id); }, 1500); });
    }
    if (conv) poll(conv);
    w.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-as-send")) {
        var q = w.querySelector("[name=q]");
        if (!q.value.trim()) return;
        API.post("/assistant/chat", { conversation: conv, message: q.value }).then(function (v) { conv = v.id; q.value = ""; show(v); poll(v.id); },
          function (err) { UI.toast(err.message, "error"); });
      } else if (b.hasAttribute("data-as-new")) { conv = null; log.innerHTML = ""; }
      else if (b.getAttribute("data-as-run")) { App.runActions([b.getAttribute("data-as-run")]); }
    });
  }

  window.Insights28 = { bsod: bsod, warning: warning, boot: bootCard, goodConfig: goodConfig, suspicious: suspicious, phone: phone, batch: batch,
    digest: digest, assistant: assistant };
})();
