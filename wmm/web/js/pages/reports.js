/* Reports: build, preview and export customer-ready reports. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var SCOPES = ["full", "dashboard"].concat(UI.AREAS);

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
            return '<option value="' + s + '">' + esc(Report.SCOPE_LABEL[s]) + (s === "full" ? " (all areas)" : "") + "</option>";
          }).join("") + "</select></label>" +
          '<label>Technician<input name="technician" maxlength="80" placeholder="Name shown on the report" value="' + esc(remembered("technician")) + '"></label>' + '<span class="muted small">Empty: the default technician from Settings is used.</span>' +
          '<label>Notes for the customer<textarea name="notes" maxlength="4000" placeholder="Work performed, advice, next steps…"></textarea></label>' +
          '<div class="page-actions">' +
          UI.button("Update preview", 'id="rep-preview"', "", "refresh") +
          UI.button("Download HTML", 'id="rep-html"', "btn-primary", "download") +
          UI.button("Print / Save as PDF", 'id="rep-print"', "", "print") + "</div></form>") +
        UI.card("Data export",
          '<p class="muted" style="margin-top:0">Raw data for spreadsheets, ticketing systems or a central console.</p><div class="page-actions">' +
          '<a class="btn" id="csv" download>' + UI.icon("download") + "History CSV</a>" +
          '<a class="btn" id="json" download>' + UI.icon("download") + "Full JSON</a></div>") +
        "</div>" + UI.card("Preview", '<iframe class="report-frame" title="Report preview" sandbox="allow-same-origin"></iframe>') + "</div>";

      var form = el.querySelector("#report-form"), frame = el.querySelector("iframe");
      function options() {
        remember("technician", form.technician.value.trim());
        return { technician: form.technician.value.trim(), notes: form.notes.value.trim() };
      }
      function links() {
        var scope = form.scope.value;
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
      el.querySelector("#rep-preview").addEventListener("click", preview);
      el.querySelector("#rep-html").addEventListener("click", function () { Report.download(form.scope.value, options()); });
      el.querySelector("#rep-print").addEventListener("click", function () { Report.print(form.scope.value, options()); });
      links();
      return preview();
    }
  };
})();
