/* 2.12: the cards of the new features, added to the pages they belong to (app.js calls Plus212.decorate after every
   page renders). Performance: why the PC is slow right now. Storage: when the disk will be full, folder map, duplicate
   and forgotten files. Applications: installed recently. Security: browser extensions and listening ports explained.
   Updates: end of support of this Windows and the calendar of the updates. Network: step-by-step internet check.
   Hardware: inventory label with QR code. Support: diagnostic package. Users: temporary roles and access review.
   Dashboard: what changed since yesterday and the goals. */
(function () {
  "use strict";
  var esc = UI.esc;
  function fail(e) { if (e && e.message !== "cancelled") UI.toast(e.message, "error"); }
  function busy(b, on) { if (b) { b.disabled = on; b.classList.toggle("busy", on); } }
  function title(App, id) { return ((App && App.state.actions[id]) || { title: id }).title; }
  function toolButtons(App, ids) {
    return (ids || []).filter(function (id) { return App.state.actions[id]; }).map(function (id) {
      return '<button type="button" class="btn btn-sm" data-tool="' + esc(id) + '">' + UI.icon("play") + esc(title(App, id)) + "</button>";
    }).join(" ");
  }
  function onTools(box, App) {
    box.addEventListener("click", function (e) { var b = e.target.closest("[data-tool]"); if (b) App.actionDetail(b.getAttribute("data-tool")); });
  }
  // A card that loads when its button is pressed (some checks take seconds).
  function lazy(zone, cardTitle, intro, label, load, draw) {
    var box = document.createElement("div");
    box.className = "plus-card";
    zone.appendChild(box);
    box.innerHTML = UI.card(cardTitle, '<p class="modal-text">' + esc(intro) + '</p><div data-plus-out></div>', UI.button(label, "data-plus-load", "btn-sm", "refresh"));
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-plus-load]");
      if (!b) return;
      busy(b, true);
      load().then(function (d) { busy(b, false); draw(box.querySelector("[data-plus-out]"), d, box); }, function (err) { busy(b, false); fail(err); });
    });
    return box;
  }
  function eager(zone, cardTitle, load, draw) {
    var box = document.createElement("div");
    box.className = "plus-card";
    zone.appendChild(box);
    box.innerHTML = UI.card(cardTitle, '<div data-plus-out>' + UI.loading() + "</div>");
    load().then(function (d) { draw(box.querySelector("[data-plus-out]"), d, box); }, function (err) { box.querySelector("[data-plus-out]").innerHTML = UI.errorBox(err); });
    return box;
  }
  function zoneOf(content, top) {
    var z = document.createElement("div");
    z.className = "stack plus-zone";
    var host = content.querySelector("[data-plus-host]");
    if (host) { host.appendChild(z); return z; }
    var head = top && content.querySelector(".page-header");
    if (head) head.insertAdjacentElement("afterend", z); else content.appendChild(z);
    return z;
  }
  function recycleRows(App, rows) {
    if (!rows.length) return false;
    var totale = rows.reduce(function (s, r) { return s + (r.size || 0); }, 0);
    return UI.confirm("Move to the Recycle Bin", rows.length + " files (" + UI.formatBytes(totale) + ") go to the Recycle Bin: you can put them back from there.", { ok: "Move" })
      .then(function (ok) {
        if (!ok) return false;
        return API.post("/plus/recycle", { paths: rows.map(function (r) { return r.path; }) }).then(function (r) {
          UI.toast(r.preview ? "Preview mode: " + r.would_move + " files would be moved." : r.moved + " files moved to the Recycle Bin.", "ok");
        }, fail);
      });
  }

  /* ---------- Performance: why the PC is slow right now ---------- */
  function slowNow(zone, App) {
    var box = lazy(zone, "Why is the PC slow right now?", "Looks at the processor, the memory, the disk and the programs working in the background for two seconds, and says in plain words what slows the PC.",
      "Check now", function () { return API.get("/plus/slow-now"); }, function (out, d) {
        var s = d.sample || {};
        out.innerHTML = '<div class="callout ' + (d.ok ? "callout-info" : "callout-warning") + '">' + UI.icon(d.ok ? "check" : "alert") + "<div><strong>" + esc(d.verdict) + "</strong></div></div>" +
          '<div class="grid grid-4">' + UI.kpi("Processor", s.cpu != null ? Math.round(s.cpu) + "%" : "—", (s.cores || "?") + " cores", s.cpu >= 85 ? "error" : "ok") +
          UI.kpi("Memory free", s.mem_free_mb != null ? UI.formatBytes(s.mem_free_mb * 1048576) : "—", s.mem_total_mb ? "of " + UI.formatBytes(s.mem_total_mb * 1048576) : "", "info") +
          UI.kpi("Disk busy", s.disk_busy != null ? Math.round(s.disk_busy) + "%" : "—", "queue " + (s.disk_queue != null ? s.disk_queue : "?"), s.disk_busy >= 90 ? "warning" : "ok") +
          UI.kpi("On since", s.uptime_days != null ? s.uptime_days + " days" : "—", esc(s.power_plan || ""), s.uptime_days >= 7 ? "warning" : "ok") + "</div>" +
          (d.causes.length ? '<ul class="plus-causes">' + d.causes.map(function (c) {
            return '<li class="plus-cause plus-' + c.level + '">' + UI.statusIcon(c.level === "info" ? "ok" : c.level) + '<div class="grow"><strong>' + esc(c.title) + "</strong>" +
              (c.detail ? '<div class="cell-sub">' + esc(c.detail) + "</div>" : "") + (c.tools.length ? '<div class="plus-tools">' + toolButtons(App, c.tools) + "</div>" : "") + "</div></li>";
          }).join("") + "</ul>" : "") +
          (s.top_cpu && s.top_cpu.length ? "<h3>Busiest programs</h3>" + UI.table([{ title: "Program" }, { title: "Processor" }, { title: "Memory" }], s.top_cpu.map(function (p) {
            return ['<span data-no-i18n>' + esc(p.name) + "</span>", esc(p.cpu + "%"), esc(UI.formatBytes((p.mem_mb || 0) * 1048576))]; })) : "");
      });
    onTools(box, App);
  }

  /* ---------- Storage ---------- */
  function diskForecast(zone) {
    eager(zone, "When will the disk be full?", function () { return API.get("/plus/disk-forecast"); }, function (out, d) {
      var tone = d.days == null ? "ok" : d.days < 60 ? "error" : d.days < 180 ? "warning" : "ok";
      var adesso = Date.now();
      out.innerHTML = '<div class="grid grid-3">' + UI.kpi("Free on C:", d.free_gb != null ? d.free_gb.toFixed(1) + " GB" : "—", d.total_gb ? "of " + Math.round(d.total_gb) + " GB" : "", "info") +
        UI.kpi("Change per month", d.per_month_gb != null ? (d.per_month_gb > 0 ? "+" : "") + d.per_month_gb + " GB" : "—", "from the scans of the last 90 days", d.per_month_gb < 0 ? "warning" : "ok") +
        UI.kpi("Full on", d.full_on ? UI.formatDate(d.full_on) : "Not in sight", d.days != null ? "in about " + d.days + " days" : (d.reason || ""), tone) + "</div>" +
        (d.points.length >= 2 ? Charts.line([{ label: "Free GB", points: d.points.map(function (p) { return { x: new Date(adesso - p.days_ago * 86400000).toISOString(), y: p.free_gb }; }) }],
          { height: 140 }) : "");
    });
  }
  function squarify(items, x, y, w, h) {
    // Squarified treemap (Bruls, Huizing, van Wijk): rows of rectangles as close to squares as possible.
    var out = [], rest = items.slice(), total = rest.reduce(function (s, i) { return s + i.v; }, 0);
    function worst(row, side, area) {
      var s = row.reduce(function (a, r) { return a + r.v; }, 0) * area / total, max = 0, min = Infinity;
      row.forEach(function (r) { var a = r.v * area / total; max = Math.max(max, a); min = Math.min(min, a); });
      return Math.max(side * side * max / (s * s), (s * s) / (side * side * min));
    }
    var area = w * h;
    while (rest.length && total > 0) {
      var side = Math.min(w, h), row = [rest[0]], i = 1;
      while (i < rest.length && worst(row.concat([rest[i]]), side, area) <= worst(row, side, area)) { row.push(rest[i]); i++; }
      rest = rest.slice(row.length);
      var rowSum = row.reduce(function (a, r) { return a + r.v; }, 0), sum = rowSum * area / total;
      if (w >= h) {
        var cw = sum / h, cy = y;
        row.forEach(function (r) { var rh = r.v * area / total / cw; out.push({ item: r, x: x, y: cy, w: cw, h: rh }); cy += rh; });
        x += cw; w -= cw;
      } else {
        var ch = sum / w, cx = x;
        row.forEach(function (r) { var rw = r.v * area / total / ch; out.push({ item: r, x: cx, y: y, w: rw, h: ch }); cx += rw; });
        y += ch; h -= ch;
      }
      total -= rowSum;
      area = w * h;
    }
    return out;
  }
  function folderMap(zone) {
    var colors = ["#0F6CBD", "#0E8A7B", "#6D4AD6", "#C2570C", "#3E4C5E", "#B4009E", "#498205", "#8764B8"];
    function draw(out, d) {
      var items = d.children.filter(function (c) { return c.bytes > 0; }).map(function (c) { return { v: c.bytes, c: c }; });
      if (d.files_bytes > 0) items.push({ v: d.files_bytes, c: { name: "(files here)", bytes: d.files_bytes, path: null } });
      var rects = items.length ? squarify(items, 0, 0, 100, 100) : [];
      out.innerHTML = '<div class="plus-crumb"><span class="cell-mono" data-no-i18n>' + esc(d.path) + "</span> · " + esc(UI.formatBytes(d.total)) +
        (d.parent ? ' <button type="button" class="btn btn-sm btn-ghost" data-tm-go="' + esc(d.parent) + '">Up one level</button>' : "") +
        (d.truncated ? ' <span class="badge badge-status-warning">Partial: the folder is very large</span>' : "") + "</div>" +
        '<div class="treemap" role="list">' + rects.map(function (r, i) {
          var c = r.item.c, small = r.w * r.h < 30;
          return '<div class="tm-box" role="listitem" style="left:' + r.x + "%;top:" + r.y + "%;width:" + r.w + "%;height:" + r.h + "%;background:" + colors[i % colors.length] + '"' +
            (c.path ? ' data-tm-go="' + esc(c.path) + '" tabindex="0"' : "") + ' title="' + esc(c.name + " · " + UI.formatBytes(c.bytes)) + '">' +
            (small ? "" : "<span data-no-i18n>" + esc(c.name) + "</span><small>" + esc(UI.formatBytes(c.bytes)) + "</small>") + "</div>";
        }).join("") + "</div>" + (rects.length ? "" : '<p class="empty">Empty folder.</p>');
    }
    var box = lazy(zone, "Folder map", "Every folder as a rectangle as big as the space it takes: click one to look inside. Starts from your user folder.",
      "Show", function () { return API.get("/plus/folders"); }, draw);
    box.addEventListener("click", function (e) {
      var t = e.target.closest("[data-tm-go]");
      if (!t) return;
      var out = box.querySelector("[data-plus-out]");
      out.innerHTML = UI.loading();
      API.get("/plus/folders?path=" + encodeURIComponent(t.getAttribute("data-tm-go"))).then(function (d) { draw(out, d); }, fail);
    });
    box.addEventListener("keydown", function (e) { if (e.key === "Enter" && e.target.hasAttribute && e.target.hasAttribute("data-tm-go")) e.target.click(); });
  }
  function duplicates(zone, App) {
    lazy(zone, "Duplicate files", "Finds identical files (same content, not just the same name) in Desktop, Documents, Downloads, Pictures, Videos and Music. Select the copies you do not need: they go to the Recycle Bin.",
      "Find duplicates", function () { return API.post("/plus/duplicates", {}); }, function (out, d) {
        if (!d.groups.length) { out.innerHTML = '<p class="empty">No duplicate files larger than 1 MB.</p>'; return; }
        var rows = [];
        d.groups.forEach(function (g, gi) {
          g.files.forEach(function (f, fi) { rows.push({ id: gi + ":" + fi, group: gi + 1, path: f.path, size: g.size, modified: f.modified, copy: fi > 0 }); });
        });
        out.innerHTML = '<p class="cell-sub">' + esc(d.groups.length + " groups · " + UI.formatBytes(d.waste) + " could be freed. The oldest file of each group is marked as the original.") +
          "</p><div data-dup></div>";
        Components.dataTable(out.querySelector("[data-dup]"), {
          rows: rows, exportName: "wmm-duplicates", pageSize: 25, columns: [
            { key: "group", title: "Group" }, { key: "path", title: "File", cls: "cell-mono", render: function (r) { return "<span data-no-i18n>" + esc(r.path) + "</span>"; } },
            { key: "size", title: "Size", render: function (r) { return esc(UI.formatBytes(r.size)); } }, { key: "modified", title: "Changed", render: function (r) { return esc(UI.formatDate(r.modified)); } },
            { key: "copy", title: "Kind", render: function (r) { return r.copy ? '<span class="badge">Copy</span>' : '<span class="badge badge-status-ok">Original</span>'; } }],
          select: { key: "id", actions: [{ label: "Move to the Recycle Bin", icon: "trash", cls: "btn-danger", run: function (sel) { return recycleRows(App, sel); } }] }
        });
      });
  }
  function forgotten(zone, App) {
    lazy(zone, "Forgotten files", "Files larger than 100 MB nobody opened or changed for a year: old videos, disk images, backups. Select what you do not need.",
      "Find them", function () { return API.post("/plus/forgotten", {}); }, function (out, d) {
        if (!d.files.length) { out.innerHTML = '<p class="empty">No large file left untouched for a year.</p>'; return; }
        out.innerHTML = '<p class="cell-sub">' + esc(d.files.length + " files · " + UI.formatBytes(d.total)) + "</p><div data-fg></div>";
        Components.dataTable(out.querySelector("[data-fg]"), {
          rows: d.files.map(function (f) { return Object.assign({ id: f.path }, f); }), exportName: "wmm-forgotten-files", sort: "size", desc: true, columns: [
            { key: "path", title: "File", cls: "cell-mono", render: function (r) { return "<span data-no-i18n>" + esc(r.path) + "</span>"; } },
            { key: "size", title: "Size", render: function (r) { return esc(UI.formatBytes(r.size)); } }, { key: "last", title: "Last used", render: function (r) { return esc(UI.formatDate(r.last)); } }],
          select: { key: "id", actions: [{ label: "Move to the Recycle Bin", icon: "trash", cls: "btn-danger", run: function (sel) { return recycleRows(App, sel); } }] }
        });
      });
  }

  /* ---------- Applications: installed recently ---------- */
  function recentInstalls(zone) {
    var box = document.createElement("div");
    box.className = "plus-card";
    zone.appendChild(box);
    function load(days) {
      box.innerHTML = UI.card("Installed recently", '<div class="toolbar"><label>Period <select data-days>' + [7, 30, 90].map(function (n) {
        return '<option value="' + n + '"' + (n === days ? " selected" : "") + ">" + n + " days</option>"; }).join("") + "</select></label></div><div data-ri>" + UI.loading() + "</div>");
      API.get("/plus/recent-installs?days=" + days).then(function (d) {
        var out = box.querySelector("[data-ri]");
        if (!d.apps.length) { out.innerHTML = '<p class="empty">Nothing installed in this period.</p>'; return; }
        out.innerHTML = '<p class="cell-sub">Programs that arrived on their own (bundled with another download) are the usual source of adware: check the ones you do not remember.</p><div data-ri-t></div>';
        Components.dataTable(out.querySelector("[data-ri-t]"), { rows: d.apps, exportName: "wmm-recent-installs", sort: "installed", desc: true, columns: [
          { key: "name", title: "Program", render: function (r) { return "<strong data-no-i18n>" + esc(r.name) + '</strong><div class="cell-sub" data-no-i18n>' + esc(r.publisher || "") + "</div>"; } },
          { key: "version", title: "Version" }, { key: "installed", title: "Installed", render: function (r) { return esc(UI.formatDate(r.installed)) + '<div class="cell-sub">' + esc(r.days + " days ago") + "</div>"; } },
          { key: "status", title: "State", render: function (r) { return r.status === "risk" ? '<span class="badge badge-status-error">Unsafe</span>' : r.status === "review" ? '<span class="badge badge-status-warning">Review</span>' : "—"; } }] });
      }, function (e) { box.querySelector("[data-ri]").innerHTML = UI.errorBox(e); });
    }
    box.addEventListener("change", function (e) { if (e.target.hasAttribute("data-days")) load(Number(e.target.value)); });
    load(30);
  }

  /* ---------- Security ---------- */
  function extensions(zone) {
    lazy(zone, "Browser extensions: what they can do", "Reads the extensions of Chrome, Edge and Brave and rates what each one may do: an extension that reads every website, your cookies or what you copy can steal accounts.",
      "Check extensions", function () { return API.get("/plus/extensions"); }, function (out, d) {
        if (!d.extensions.length) { out.innerHTML = '<p class="empty">No extensions found in Chrome, Edge or Brave.</p>'; return; }
        var alti = d.extensions.filter(function (x) { return x.level === "high"; }).length;
        out.innerHTML = '<p class="cell-sub">' + esc(d.extensions.length + " extensions, " + alti + " with wide powers. Remove those you do not know or do not use from the browser menu (Extensions).") + "</p><div data-ext></div>";
        Components.dataTable(out.querySelector("[data-ext]"), { rows: d.extensions, exportName: "wmm-browser-extensions", columns: [
          { key: "name", title: "Extension", render: function (r) { return "<strong data-no-i18n>" + esc(r.name) + '</strong><div class="cell-sub">' + esc(r.browser + " · " + r.profile + " · " + r.version) + "</div>"; } },
          { key: "level", title: "Powers", render: function (r) { return '<span class="badge badge-status-' + (r.level === "high" ? "error" : r.level === "medium" ? "warning" : "ok") + '">' +
            esc(r.level === "high" ? "Wide" : r.level === "medium" ? "Some" : "Few") + "</span>"; } },
          { key: "reasons", title: "It can", render: function (r) { return esc(r.reasons.join("; ") || "—"); } }],
          filters: [{ key: "level", label: "Any power", options: [["high", "Wide"], ["medium", "Some"], ["low", "Few"]] }] });
      });
  }
  function bitlocker(zone) {
    eager(zone, "BitLocker and the recovery key", function () { return API.get("/plus/bitlocker"); }, function (out, d) {
      var tone = d.state === "ok" ? "ok" : d.state === "unknown" ? "warning" : "error";
      out.innerHTML = '<div class="callout ' + (tone === "ok" ? "callout-info" : "callout-warning") + '">' + UI.icon(tone === "ok" ? "shield" : "alert") +
        "<div><strong>" + esc(d.title) + "</strong><div>" + esc(d.text) + "</div></div></div>" +
        (d.percent != null ? '<p class="cell-sub">' + esc("Encrypted: " + d.percent + "%" + (d.method ? " · " + d.method : "")) + "</p>" : "");
    });
  }
  function ports(zone) {
    lazy(zone, "Listening ports explained", "Every program that waits for connections from the network, what it is and how risky it is. Ports open only to this PC are harmless.",
      "Show ports", function () { return API.get("/plus/ports"); }, function (out, d) {
        out.innerHTML = "<div data-ports></div>";
        Components.dataTable(out.querySelector("[data-ports]"), { rows: d.ports, exportName: "wmm-listening-ports", columns: [
          { key: "port", title: "Port" }, { key: "name", title: "What it is", render: function (r) { return "<strong>" + esc(r.name) + '</strong><div class="cell-sub">' + esc(r.text) + "</div>"; } },
          { key: "process", title: "Program", render: function (r) { return "<span data-no-i18n>" + esc(r.process || "?") + "</span>"; } },
          { key: "address", title: "Reachable from", render: function (r) { return esc(r.local_only ? "This PC only" : "The network"); } },
          { key: "risk", title: "Risk", render: function (r) { return '<span class="badge badge-status-' + (r.risk === "high" ? "error" : r.risk === "medium" ? "warning" : "ok") + '">' +
            esc(r.risk === "high" ? "High" : r.risk === "medium" ? "Medium" : "Low") + "</span>"; } }],
          filters: [{ key: "risk", label: "Any risk", options: [["high", "High"], ["medium", "Medium"], ["low", "Low"]] }] });
      });
  }

  /* ---------- Updates ---------- */
  function windowsSupport(zone) {
    eager(zone, "End of support of this Windows", function () { return API.get("/plus/windows-support"); }, function (out, d) {
      var tone = d.status === "ended" ? "error" : d.status === "soon" ? "warning" : d.status === "ok" ? "ok" : "info";
      out.innerHTML = '<div class="grid grid-3">' + UI.kpi("Version", d.name || ("Build " + d.build), esc(d.edition || ""), "info") +
        UI.kpi("Security updates until", d.end ? UI.formatDate(d.end) : "—", d.days != null ? (d.days >= 0 ? "in " + d.days + " days" : "ended " + (-d.days) + " days ago") : "", tone) +
        UI.kpi("State", d.status === "ok" ? "Supported" : d.status === "soon" ? "Ends soon" : d.status === "ended" ? "Out of support" : "Unknown", "", tone) + "</div>" +
        '<p class="cell-sub">' + esc(d.note || "") + "</p>";
    });
  }
  function updateCalendar(zone) {
    lazy(zone, "Calendar of the updates", "Every update Windows installed, month by month, with the ones that failed: useful to see when a problem started.",
      "Show calendar", function () { return API.get("/plus/update-calendar"); }, function (out, d) {
        var mesi = [], adesso = new Date();
        for (var i = 11; i >= 0; i--) {
          var t = new Date(adesso.getFullYear(), adesso.getMonth() - i, 1), k = t.getFullYear() + "-" + (t.getMonth() < 9 ? "0" : "") + (t.getMonth() + 1);
          mesi.push({ label: t.toLocaleDateString(undefined, { month: "short", year: "2-digit" }), value: d.months[k] || 0 });
        }
        out.innerHTML = '<div class="grid grid-3">' + UI.kpi("Updates", Components.num(d.updates.length), "in the history", "info") +
          UI.kpi("Failed", Components.num(d.failed), "", d.failed ? "warning" : "ok") + UI.kpi("Last", d.last ? UI.formatDate(d.last) : "—", "", "info") + "</div>" +
          Charts.hbars(mesi) + "<div data-cal></div>";
        Components.dataTable(out.querySelector("[data-cal]"), { rows: d.updates, exportName: "wmm-update-calendar", sort: "date", desc: true, columns: [
          { key: "date", title: "Date", render: function (r) { return esc(UI.formatDate(r.date)); } }, { key: "title", title: "Update", render: function (r) { return "<span data-no-i18n>" + esc(r.title) + "</span>"; } },
          { key: "result", title: "Result", render: function (r) { return '<span class="badge badge-status-' + (r.result === "failed" ? "error" : r.result === "installed" ? "ok" : "warning") + '">' + esc(r.result) + "</span>"; } }],
          filters: [{ key: "result", label: "Any result", options: [["installed", "Installed"], ["failed", "Failed"]] }] });
      });
  }

  /* ---------- Network: step-by-step internet check ---------- */
  function internetCheck(zone, App) {
    var box = lazy(zone, "Internet does not work? Check step by step", "Checks the network adapter, the address, the router, the names (DNS), internet and secure sites in order, and stops at the first that fails: there is the problem, with the tools that fix it.",
      "Check the connection", function () { return API.post("/plus/internet-check", {}); }, function (out, d) {
        out.innerHTML = '<div class="callout ' + (d.ok ? "callout-info" : "callout-warning") + '">' + UI.icon(d.ok ? "check" : "alert") + "<div><strong>" + esc(d.verdict) + "</strong></div></div>" +
          '<ol class="plus-steps">' + d.steps.map(function (s) {
            return '<li class="plus-step ' + (s.ok ? "ok" : "bad") + '">' + UI.statusIcon(s.ok ? "ok" : "error") + '<div class="grow"><strong>' + esc(s.step) + '</strong><div class="cell-sub">' + esc(s.text) + "</div>" +
              (s.tools.length ? '<div class="plus-tools">' + toolButtons(App, s.tools) + "</div>" : "") + "</div></li>";
          }).join("") + "</ol>";
      });
    onTools(box, App);
  }

  /* ---------- Hardware: inventory label ---------- */
  function label(zone) {
    lazy(zone, "Inventory label", "A label with a QR code for the asset register: maker, model, serial number and Windows. Print it on a sticker for the PC.",
      "Make the label", function () { return API.get("/plus/label"); }, function (out, d) {
        var html = '<div class="asset-label"><div class="asset-qr">' + d.qr + "</div><dl>" + Object.keys(d.fields).map(function (k) {
          return "<dt>" + esc(k) + "</dt><dd data-no-i18n>" + esc(d.fields[k]) + "</dd>"; }).join("") + "</dl></div>";
        out.innerHTML = html + '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Print", "data-label-print", "btn-sm btn-primary", "print") + "</div>";
        out.querySelector("[data-label-print]").addEventListener("click", function () {
          var w = window.open("", "_blank", "width=480,height=360");
          if (!w) { UI.toast("The browser blocked the window: allow pop-ups for the console.", "warning"); return; }
          w.document.write("<!doctype html><title>Label</title><style>body{font:12px Segoe UI,sans-serif;margin:8px}.asset-label{display:flex;gap:10px;align-items:center;border:1px solid #000;padding:8px;width:fit-content}" +
            "dl{display:grid;grid-template-columns:auto auto;gap:2px 8px;margin:0}dt{font-weight:600}dd{margin:0}svg{width:120px;height:120px}</style>" + html + "<script>window.print()<\/script>");
          w.document.close();
        });
      });
  }

  /* ---------- Support: diagnostic package ---------- */
  function diagnostic(zone) {
    var box = document.createElement("div");
    zone.appendChild(box);
    box.innerHTML = UI.card("Diagnostic package for the technician", '<p class="modal-text">One zip with the state of this PC: scores, recommendations, system, history, schedules, health check and settings. ' +
      "Passwords, tokens and webhook addresses are removed. Attach it to a ticket or an e-mail.</p>",
      UI.button("Download the package", "data-diag", "btn-sm btn-primary", "download"));
    box.querySelector("[data-diag]").addEventListener("click", function (e) {
      var b = e.currentTarget;
      busy(b, true);
      API.download("/plus/diagnostic.zip", "wmm-diagnostic.zip").then(function () { busy(b, false); UI.toast("Package downloaded.", "ok"); }, function (er) { busy(b, false); fail(er); });
    });
  }

  /* ---------- Users: temporary roles and access review ---------- */
  function delegations(zone) {
    if (!Auth.enabled() || !Auth.can("users.view")) return;
    var box = document.createElement("div");
    zone.appendChild(box);
    function load() {
      Promise.all([API.get("/plus/delegations"), API.get("/roles")]).then(function (r) {
        var d = r[0].delegations, roles = r[1].roles, puo = Auth.can("users.manage") && Auth.can("roles.manage");
        box.innerHTML = UI.card("Temporary roles", '<p class="modal-text">Give a person a role for some hours or days (holidays, an urgent intervention): the previous role comes back by itself.</p>' +
          (d.length ? UI.table([{ title: "User" }, { title: "Role now" }, { title: "Back to" }, { title: "Until" }, { title: "" }], d.map(function (x) {
            return [esc(x.username), esc(x.role_id), esc(x.previous_role), esc(UI.formatDate(x.until)),
              puo ? '<button type="button" class="btn btn-sm" data-del-end="' + esc(x.username) + '">End now</button>' : ""]; })) : '<p class="empty">No temporary role.</p>') +
          (puo ? '<form class="toolbar" data-del-form onsubmit="return false"><label>User<input name="u" maxlength="64"></label><label>Role<select name="r">' + roles.map(function (x) {
            return '<option value="' + esc(x.id) + '">' + esc(x.name) + "</option>"; }).join("") + '</select></label><label>For<select name="h"><option value="4">4 hours</option>' +
            '<option value="8">8 hours</option><option value="24">1 day</option><option value="72">3 days</option><option value="168">1 week</option><option value="336">2 weeks</option></select></label>' +
            UI.button("Give the role", "data-del-add", "btn-sm btn-primary", "check") + "</form>" : ""));
      }, function (e) { box.innerHTML = UI.errorBox(e); });
    }
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-del-add")) {
        var f = box.querySelector("[data-del-form]");
        API.post("/plus/delegations", { username: f.u.value.trim(), role_id: f.r.value, hours: Number(f.h.value) }).then(function () { UI.toast("Temporary role given.", "ok"); load(); }, fail);
      }
      if (b.getAttribute("data-del-end")) API.del("/plus/delegations/" + encodeURIComponent(b.getAttribute("data-del-end"))).then(function () { UI.toast("Previous role restored.", "ok"); load(); }, fail);
    });
    load();
  }
  function accessReview(zone) {
    if (!Auth.enabled() || !Auth.can("users.view") || !Auth.can("audit.view")) return;
    var box = lazy(zone, "Access review", "Who can use the console and who should not anymore: people who never signed in or not for 90 days, administrators without two-step verification, API tokens about to expire or never used.",
      "Review access", function () { return API.get("/plus/access-review"); }, function (out, d) {
        out.innerHTML = '<div class="grid grid-3">' + UI.kpi("People to check", Components.num(d.flagged), "of " + d.users.length, d.flagged ? "warning" : "ok") +
          UI.kpi("Administrators", Components.num(d.admins), "keep them few", d.admins > 3 ? "warning" : "ok") +
          UI.kpi("Last review", d.last_review && d.last_review.at ? UI.formatDate(d.last_review.at) : "Never", d.last_review && d.last_review.by ? "by " + d.last_review.by : "", d.last_review && d.last_review.at ? "ok" : "warning") + "</div>" +
          UI.table([{ title: "User" }, { title: "Role" }, { title: "Last sign-in" }, { title: "Two-step" }, { title: "To check" }], d.users.map(function (u) {
            return ["<strong>" + esc(u.username) + "</strong>", esc(u.role || ""), esc(u.last_login ? UI.formatDate(u.last_login) : "Never"), u.two_step ? "Yes" : "No",
              u.flags.length ? '<span class="badge badge-status-warning">' + esc(u.flags.join("; ")) + "</span>" : "—"]; })) +
          (d.tokens.length ? "<h3>API tokens to check</h3>" + UI.table([{ title: "Token" }, { title: "Owner" }, { title: "Expires" }, { title: "Last used" }], d.tokens.map(function (t) {
            return [esc(t.name), esc(t.username), t.expires_in == null ? "Never" : esc(t.expires_in + " days"), esc(t.last_used ? UI.formatDate(t.last_used) : "Never")]; })) : "") +
          (Auth.can("users.manage") ? '<div class="page-actions" style="justify-content:flex-start">' + UI.button("Mark as reviewed", "data-ar-done", "btn-sm btn-primary", "check") + "</div>" : "");
      });
    box.addEventListener("click", function (e) {
      if (!e.target.closest("[data-ar-done]")) return;
      API.post("/plus/access-review", { note: "" }).then(function () { UI.toast("Review recorded in the audit log.", "ok"); box.querySelector("[data-plus-load]").click(); }, fail);
    });
  }

  /* ---------- Dashboard: what changed since yesterday, goals ---------- */
  function changes(zone) {
    API.get("/plus/changes").then(function (d) {
      if (!d.since || (!d.areas.length && !d.failed.length)) return;
      var box = document.createElement("div");
      zone.appendChild(box);
      box.innerHTML = UI.card("What changed since yesterday", '<p class="cell-sub">Compared with the scans of ' + esc(UI.formatDate(d.since)) + " · " + esc(d.runs + " runs since then") + "</p>" +
        '<ul class="plus-changes">' + d.areas.map(function (a) {
          var su = a.delta > 0, giu = a.delta < 0;
          return '<li><a href="#/' + esc(a.area) + '"><strong>' + esc(UI.AREA_LABEL[a.area] || a.area) + "</strong></a> " + '<span class="badge badge-status-' + (giu ? "error" : su ? "ok" : "info") + '">' +
            esc(a.before + " → " + a.now) + "</span>" + (a.new.length ? '<div class="cell-sub">New: ' + esc(a.new.slice(0, 3).join("; ")) + "</div>" : "") +
            (a.solved.length ? '<div class="cell-sub">Solved: ' + esc(a.solved.slice(0, 3).join("; ")) + "</div>" : "") + "</li>";
        }).join("") + d.failed.map(function (f) { return '<li><span class="badge badge-status-error">Failed</span> ' + esc(f.action_id) + ' <span class="cell-sub">' + esc(f.note || "") + "</span></li>"; }).join("") + "</ul>");
    }, function () { /* optional card */ });
  }
  function goals(zone) {
    API.get("/plus/goals").then(function (d) {
      var attivi = d.goals.filter(function (g) { return g.enabled; });
      if (!attivi.length) return;
      var nomi = { overall: "Overall health", c_free_pct: "Free space on C: (%)", c_free_gb: "Free space on C: (GB)", open_issues: "Open recommendations" };
      var box = document.createElement("div");
      zone.appendChild(box);
      box.innerHTML = UI.card("Goals", UI.checklist(attivi.map(function (g) {
        var nome = nomi[g.metric] || "Score of " + (UI.AREA_LABEL[g.metric.slice(5)] || g.metric);
        return [nome + " " + (g.op === ">=" ? "at least" : "at most") + " " + g.value, g.ok == null ? "warning" : g.ok ? "ok" : "error",
          g.ok == null ? "No data" : g.ok ? "Met" : "Not met", g.current == null ? "No scan yet" : "Now " + g.current];
      })), '<a class="btn btn-sm btn-ghost" href="#/settings?s=automation">Edit</a>');
    }, function () { /* optional card */ });
  }

  var PAGES = {
    dashboard: function (c, App) { var z = zoneOf(c, true); changes(z, App); goals(z, App); },
    performance: function (c, App) { slowNow(zoneOf(c, true), App); },
    storage: function (c, App) { var z = zoneOf(c); diskForecast(z); folderMap(z, App); duplicates(z, App); forgotten(z, App); },
    apps: function (c, App) { recentInstalls(zoneOf(c), App); },
    security: function (c, App) { var z = zoneOf(c); bitlocker(z, App); extensions(z, App); ports(z, App); },
    updates: function (c, App) { var z = zoneOf(c, true); windowsSupport(z, App); updateCalendar(z, App); },
    network: function (c, App) { internetCheck(zoneOf(c, true), App); },
    hardware: function (c, App) { label(zoneOf(c), App); },
    support: function (c, App) { diagnostic(zoneOf(c, true), App); },
    users: function (c, App) { var z = zoneOf(c); delegations(z, App); accessReview(z, App); }
  };
  var SEE = { dashboard: "view.dashboard", performance: "view.performance", storage: "view.storage", apps: "view.apps", security: "view.security", updates: "view.updates",
    network: "view.network", hardware: "view.hardware", support: "view.support", users: "users.view" };

  window.Plus212 = {
    decorate: function (name, content, App) {
      if (!PAGES[name] || (SEE[name] && !Auth.can(SEE[name]))) return;
      try { PAGES[name](content, App); } catch (e) { /* a card never breaks its page */ }
    },
    squarify: squarify
  };
})();
