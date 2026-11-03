/* Reports: build, preview and export customer-ready reports. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var SCOPES = ["visit", "full", "dashboard"].concat(UI.AREAS);
  /* Sentences technicians write in almost every report: one click adds them to the notes. */
  var PHRASES = [
    ["Cleanup done", "Temporary files, caches and old logs were removed to free disk space."],
    ["Windows repaired", "The Windows image and system files were checked and repaired (DISM and SFC)."],
    ["Updates installed", "Windows, drivers and applications were updated to the latest versions."],
    ["Security checked", "Antivirus, firewall and Windows security settings were checked and are active."],
    ["Startup lighter", "Programs that slowed down the start of Windows were disabled."],
    ["Backup advice", "We recommend an automatic backup of your documents to an external drive or the cloud."],
    ["Restart needed", "Please restart the PC to complete the maintenance."],
    ["Next visit", "We recommend the next maintenance in 6 months."]
  ];

  function startOfToday() {
    var d = new Date(), p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T00:00";
  }
  function remembered(key) { try { return localStorage.getItem("wmm." + key) || ""; } catch (e) { return ""; } }
  function remember(key, value) { try { localStorage.setItem("wmm." + key, value); } catch (e) { /* storage unavailable */ } }

  window.Pages.reports = {
    title: "Reports",
    render: function (el, App) {
      App.setSubtitle("Customer-ready reports with charts, exportable as HTML, PDF, CSV and JSON");
      el.innerHTML = UI.pageHeader("Reports", "Reports are generated from the latest scans and the history of this device", "") +
        '<div class="grid grid-1-2"><div>' + UI.card("Report options",
          '<form class="form" id="report-form" onsubmit="return false">' +
          '<label>Report<select name="scope">' + SCOPES.map(function (s) {
            return '<option value="' + s + '">' + esc(Report.SCOPE_LABEL[s]) + (s === "full" ? " (all areas)" : s === "visit" ? " (what this visit changed)" : "") + "</option>";
          }).join("") + "</select></label>" +
          '<label data-since-row>Changes since<input type="datetime-local" name="since" value="' + esc(startOfToday()) + '"></label>' +
          '<span class="muted small" data-since-row>Scores at that moment are compared with the latest ones; every operation since then is listed.</span>' +
          '<label>Technician<input name="technician" maxlength="80" placeholder="Name shown on the report" value="' + esc(remembered("technician")) + '"></label>' + '<span class="muted small">Empty: the default technician from Settings is used.</span>' +
          '<label>Notes for the customer<textarea name="notes" maxlength="4000" placeholder="Work performed, advice, next steps…">' + esc(remembered("reportNotes")) + "</textarea></label>" +
          '<div class="phrases" aria-label="Common phrases">' + PHRASES.map(function (p, i) {
            return '<button type="button" class="btn btn-sm btn-ghost" data-phrase="' + i + '" title="' + esc(p[1]) + '">+ ' + esc(p[0]) + "</button>";
          }).join("") + '</div><span class="muted small" id="notes-saved">The notes are kept in this browser until you clear them.</span>' +
          '<div class="page-actions">' +
          UI.button("Update preview", 'id="rep-preview"', "", "refresh") +
          UI.button("Download HTML", 'id="rep-html"', "btn-primary", "download") +
          UI.button("Print / Save as PDF", 'id="rep-print"', "", "print") + "</div>" +
          '<div class="page-actions" style="justify-content:flex-start">' +
          UI.button("Copy as text", 'id="rep-copy" title="The report without layout, to paste in an email or a ticket"', "btn-sm", "copy") +
          UI.button("Email draft", 'id="rep-mail" title="Opens your email program with a summary; attach the downloaded report"', "btn-sm", "bell") + "</div></form>") +
        UI.card("Data export",
          '<p class="muted" style="margin-top:0">Raw data for spreadsheets, ticketing systems or a central console.</p><div class="page-actions">' +
          '<a class="btn" id="csv" download>' + UI.icon("download") + "History CSV</a>" +
          '<a class="btn" id="json" download>' + UI.icon("download") + "Full JSON</a></div>") +
        "</div>" + UI.card("Preview", '<iframe class="report-frame" title="Report preview" sandbox="allow-same-origin"></iframe>') + "</div>";

      var form = el.querySelector("#report-form"), frame = el.querySelector("iframe");
      function options() {
        remember("technician", form.technician.value.trim());
        return { technician: form.technician.value.trim(), notes: form.notes.value.trim(), since: form.since.value || null };
      }
      function links() {
        var scope = form.scope.value;
        el.querySelectorAll("[data-since-row]").forEach(function (n) { n.hidden = scope !== "visit"; });
        var area = UI.AREAS.indexOf(scope) >= 0 ? scope : "all";
        el.querySelector("#csv").href = API.url("/export/" + area + ".csv");
        el.querySelector("#json").href = API.url("/export/" + area + ".json");
      }
      function preview() {
        frame.srcdoc = '<p style="font-family:Segoe UI;padding:24px;color:#55606B">Building the report…</p>';
        return Report.build(form.scope.value, options()).then(function (html) { frame.srcdoc = html; },
          function (e) { frame.srcdoc = '<p style="font-family:Segoe UI;padding:24px;color:#C42B1C">' + esc(e.message) + "</p>"; });
      }
      form.scope.addEventListener("change", function () { links(); preview(); });
      form.since.addEventListener("change", preview);
      // The notes survive a reload or a closed tab: they are written for one visit and kept until cleared.
      var noteTimer = null;
      form.notes.addEventListener("input", function () {
        clearTimeout(noteTimer);
        noteTimer = setTimeout(function () { remember("reportNotes", form.notes.value); el.querySelector("#notes-saved").textContent = "Draft saved " + new Date().toLocaleTimeString() + "."; }, 600);
      });
      el.querySelector(".phrases").addEventListener("click", function (e) {
        var b = e.target.closest("[data-phrase]");
        if (!b) return;
        var text = PHRASES[Number(b.getAttribute("data-phrase"))][1], cur = form.notes.value.trim();
        if (cur.indexOf(text) >= 0) return;
        form.notes.value = (cur ? cur + "\n" : "") + text;
        form.notes.dispatchEvent(new Event("input"));
      });
      el.querySelector("#rep-preview").addEventListener("click", preview);
      el.querySelector("#rep-html").addEventListener("click", function () { Report.download(form.scope.value, options()); });
      el.querySelector("#rep-print").addEventListener("click", function () { Report.print(form.scope.value, options()); });
      function reportText() {
        var doc = frame.contentDocument;
        return doc && doc.body ? doc.body.innerText.replace(/\n{3,}/g, "\n\n").trim() : "";
      }
      el.querySelector("#rep-copy").addEventListener("click", function () {
        var text = reportText();
        if (text.length < 40) { UI.toast("The preview is still being built: try again in a moment.", "info"); return; }
        App.copyText(text, "Report");
      });
      // mailto bodies are cut by many mail programs after a couple of thousand characters: the summary stays short.
      var MAIL_CHARS = 1800;
      el.querySelector("#rep-mail").addEventListener("click", function () {
        var text = reportText(), info = App.state.info || {};
        var subject = "Maintenance report · " + (info.hostname || "PC") + " · " + UI.formatDate(new Date().toISOString(), false);
        var body = (form.notes.value.trim() ? form.notes.value.trim() + "\n\n" : "") + (text.length > MAIL_CHARS ? text.slice(0, MAIL_CHARS) + "…\n\n(The full report is attached.)" : text);
        location.href = "mailto:?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
      });
      links();
      return preview();
    }
  };
})();
