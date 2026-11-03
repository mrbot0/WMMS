/* Hardware: every component with its hardware IDs and links to search drivers and specs online, live temperatures and fans. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var SENSOR_MS = 5000;
  var MEMORY_TYPE = { 20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5", 35: "LPDDR5" };
  var CLASS_LABEL = { DISPLAY: "Display adapters", NET: "Network", MEDIA: "Sound and video", USB: "USB", HIDCLASS: "Human interface", KEYBOARD: "Keyboards",
    MOUSE: "Mice", MONITOR: "Monitors", DISKDRIVE: "Disk drives", SCSIADAPTER: "Storage controllers", HDC: "Storage controllers", SYSTEM: "System devices",
    PROCESSOR: "Processors", BLUETOOTH: "Bluetooth", CAMERA: "Cameras", IMAGE: "Imaging", AUDIOENDPOINT: "Audio endpoints", SOFTWAREDEVICE: "Software devices",
    PRINTQUEUE: "Print queues", VOLUME: "Volumes", COMPUTER: "Computer", BATTERY: "Batteries", FIRMWARE: "Firmware", SECURITYDEVICES: "Security devices" };

  function classLabel(c) { return CLASS_LABEL[String(c || "").toUpperCase()] || c || ""; }
  function gb(bytes) { return bytes ? (bytes / 1073741824 >= 100 ? Math.round(bytes / 1073741824) : Math.round(bytes / 1073741824 * 10) / 10) + " GB" : "—"; }
  function q(text) { return encodeURIComponent(text); }
  function ext(href, label, iconName, tip) {
    return '<a class="hw-link" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer"' + (tip ? ' data-tip="' + esc(tip) + '"' : "") + ">" + UI.icon(iconName || "globe") + esc(label) + "</a>";
  }
  /* Where to look a device up: the web, the Microsoft driver catalog and the PCI/USB ID database. */
  function searchLinks(ids, name) {
    var out = [];
    if (ids && ids.search) {
      out.push(ext("https://www.google.com/search?q=" + q('"' + ids.search + '" driver'), "Search ID", "search", "Search the web for this hardware ID"));
      out.push(ext("https://www.catalog.update.microsoft.com/Search.aspx?q=" + q(ids.search), "Driver catalog", "download", "Microsoft Update Catalog: official drivers for this ID"));
      if (ids.lookup) {
        var p = ids.lookup.split("/");
        out.push(ext("https://devicehunt.com/view/type/" + p[0] + "/vendor/" + p[1] + "/device/" + p[2], "ID database", "info", "Vendor and device name for this ID"));
      }
    } else if (name) {
      out.push(ext("https://www.google.com/search?q=" + q(name), "Search", "search"));
    }
    return out.length ? '<span class="hw-links">' + out.join("") + "</span>" : "";
  }
  function copyable(text, sensitive) {
    return text ? '<button type="button" class="hw-id' + (sensitive ? " sensitive" : "") + '" data-copy-text="' + esc(text) + '" data-tip="Copy">' + esc(text) + UI.icon("copy") + "</button>"
      : '<span class="cell-sub">—</span>';
  }
  /* Serial numbers, UUIDs and MAC addresses identify this PC: privacy mode blurs them. */
  function secret(text) { return copyable(text, true); }

  /* ---------- temperature history (this visit) and alerts ---------- */
  var HISTORY = 60;          // readings kept per sensor: 5 minutes at one reading every 5 s
  var ALERT_MINUTES = 10;    // the same sensor alerts again only after this time
  var history = {}, alerted = {};
  function remember(s) {
    (s.temperatures || []).forEach(function (t) {
      var key = t.group + "|" + t.name, list = history[key] = history[key] || [];
      list.push(t.celsius);
      if (list.length > HISTORY) list.shift();
      if (t.state === "error" && Date.now() - (alerted[key] || 0) > ALERT_MINUTES * 60000) {
        alerted[key] = Date.now();
        UI.toast(t.name + " is at " + Math.round(t.celsius) + " °C: check the cooling and what is using it.", "warning");
        App.desktopNotify("High temperature", t.name + " is at " + Math.round(t.celsius) + " °C.");
      }
    });
  }
  function sparkline(key) {
    var v = history[key] || [];
    if (v.length < 2) return "";
    var min = Math.min.apply(null, v) - 1, max = Math.max.apply(null, v) + 1, w = 100, h = 24;
    var pts = v.map(function (x, i) { return (i * w / (HISTORY - 1)).toFixed(1) + "," + (h - (x - min) / (max - min) * h).toFixed(1); }).join(" ");
    return '<svg class="spark" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" aria-label="Last ' + v.length + ' readings, from ' +
      Math.round(Math.min.apply(null, v)) + " to " + Math.round(Math.max.apply(null, v)) + ' °C"><polyline points="' + pts + '"/></svg>';
  }
  function kv(rows) {
    return '<dl class="hw-kv">' + rows.filter(function (r) { return r[1] !== undefined && r[1] !== null && r[1] !== ""; }).map(function (r) {
      return "<dt>" + esc(r[0]) + "</dt><dd>" + (r[2] ? r[1] : esc(r[1])) + "</dd>";
    }).join("") + "</dl>";
  }
  function item(title, sub, body, ids) {
    return '<div class="hw-item"><div class="hw-item-head"><div><div class="cell-title">' + esc(title) + "</div>" + (sub ? '<div class="cell-sub">' + esc(sub) + "</div>" : "") + "</div>" +
      searchLinks(ids, title) + "</div>" + body + "</div>";
  }
  function idRows(ids, device) {
    if (!ids || !ids.search) return device ? [["Device instance", copyable(device), true]] : [];
    return [["Hardware ID", copyable(ids.search), true], ["Vendor", (ids.vendor ? ids.vendor + " · " : "") + "0x" + ids.vendor_id],
      ["Device", "0x" + ids.device_id], ["Subsystem", ids.subsys], ["Revision", ids.rev], ["Device instance", copyable(device), true]];
  }

  /* ---------- sensors ---------- */

  function sensorTiles(s) {
    var temps = s.temperatures || [], fans = s.fans || [];
    var groups = {};
    temps.forEach(function (t) { (groups[t.group] = groups[t.group] || { temps: [], fans: [] }).temps.push(t); });
    fans.forEach(function (f) { (groups[f.group] = groups[f.group] || { temps: [], fans: [] }).fans.push(f); });
    var order = ["Processor", "Graphics", "Motherboard", "Motherboard / ACPI", "Memory", "Disks", "System"];
    var rank = function (g) { var i = order.indexOf(g); return i < 0 ? 99 : i; };
    var names = Object.keys(groups).sort(function (a, b) { return rank(a) - rank(b) || a.localeCompare(b); });
    if (!names.length) return '<p class="empty">No temperature or fan sensor is readable without a sensor tool on this PC.</p>';
    return names.map(function (g) {
      var list = groups[g];
      return '<div class="hw-sensor-group"><div class="hw-sensor-title">' + esc(g) + '</div><div class="hw-sensors">' +
        list.temps.map(function (t) {
          var pct = Math.max(4, Math.min(100, t.celsius / (t.group === "Disks" ? 80 : 105) * 100));
          return '<div class="hw-sensor hw-' + t.state + '" data-tip="' + esc(t.source + (t.note ? " · " + t.note : "")) + '"><div class="hw-sensor-name">' + UI.icon("thermometer") + esc(t.name) + "</div>" +
            '<div class="hw-sensor-value">' + Math.round(t.celsius) + "<small>°C</small></div>" +
            '<div class="hw-bar"><span style="width:' + pct + '%"></span></div>' + sparkline(t.group + "|" + t.name) +
            '<div class="hw-sensor-sub">' + (t.max ? "Max " + Math.round(t.max) + " °C" : "") + (t.note ? (t.max ? " · " : "") + esc(t.note) : "") + "</div></div>";
        }).join("") +
        list.fans.map(function (f) {
          var value = f.rpm != null ? Math.round(f.rpm) + "<small> RPM</small>" : f.percent != null ? Math.round(f.percent) + "<small>%</small>" : "—";
          var stopped = (f.rpm === 0 || f.percent === 0);
          var width = f.percent != null ? Math.max(4, f.percent) : f.max ? Math.max(4, f.rpm / f.max * 100) : stopped ? 0 : 50;
          return '<div class="hw-sensor hw-fan' + (stopped ? " is-stopped" : "") + '" data-tip="' + esc(f.source) + '"><div class="hw-sensor-name">' + UI.icon("fan") + esc(f.name) + "</div>" +
            '<div class="hw-sensor-value">' + value + "</div>" +
            '<div class="hw-bar"><span style="width:' + width + '%"></span></div>' +
            '<div class="hw-sensor-sub">' + (stopped ? "Stopped (normal for some fans at low temperature)" : f.max ? "Max " + Math.round(f.max) + " RPM" : "") + "</div></div>";
        }).join("") + "</div></div>";
    }).join("");
  }
  function toolCallout(s) {
    if (s.monitor_tool) {
      return '<p class="muted small hw-source">' + UI.icon("check") + "Processor, motherboard and fan sensors come from " + esc(s.monitor_tool) + ", running on this PC.</p>";
    }
    if ((s.temperatures || []).some(function (t) { return t.group === "Processor"; })) return "";
    return '<div class="callout callout-info hw-tool">' + UI.icon("info") + "<div><strong>Processor temperatures and fan speeds need a sensor driver.</strong> " +
      "Windows does not expose them on most desktops. LibreHardwareMonitor (free, open source) reads them; this page shows its sensors as soon as it runs." +
      '<div class="page-actions" style="margin-top:10px">' + (s.monitor_installed
        ? '<button class="btn btn-primary btn-sm" data-monitor="start">' + UI.icon("play") + "Start LibreHardwareMonitor</button>"
        : '<button class="btn btn-primary btn-sm" data-monitor="install">' + UI.icon("download") + "Install and start it (winget)</button>") +
      ext("https://github.com/LibreHardwareMonitor/LibreHardwareMonitor", "About it", "info") + "</div>" +
      '<p class="muted small" style="margin:8px 0 0">In LibreHardwareMonitor, Options › Run On Windows Startup keeps the sensors available after a restart.</p></div></div>';
  }

  /* ---------- components ---------- */

  function sections(d) {
    var sys = d.system || {};
    var out = {};
    out.system = kv([["Manufacturer", sys.manufacturer], ["Model", sys.model], ["Family", sys.family], ["SKU", sys.sku],
      ["Motherboard", [sys.board_vendor, sys.board_model].filter(Boolean).join(" ")], ["Board version", sys.board_version],
      ["BIOS", [sys.bios_vendor, sys.bios_version].filter(Boolean).join(" ") + (sys.bios_date ? " (" + sys.bios_date + ")" : "")],
      ["Serial number", secret(sys.serial), true], ["Board serial", secret(sys.board_serial), true], ["UUID", secret(sys.uuid), true],
      ["Windows", [sys.os, sys.os_build].filter(Boolean).join(" ") + (sys.os_version ? " · " + sys.os_version : "")]]) +
      '<div class="hw-links-row">' + (sys.board_model ? ext("https://www.google.com/search?q=" + q(sys.board_vendor + " " + sys.board_model + " BIOS download"), "Motherboard BIOS and drivers", "download") +
        ext("https://www.google.com/search?q=" + q(sys.board_vendor + " " + sys.board_model + " specifications manual"), "Motherboard manual", "search") : "") +
      (sys.model && !/system product name|to be filled/i.test(sys.model) ? ext("https://www.google.com/search?q=" + q(sys.manufacturer + " " + sys.model + " support drivers"), "Model support page", "search") : "") + "</div>";
    out.cpu = d.cpu.map(function (c) {
      return item(c.name, c.vendor + (c.socket ? " · " + c.socket : ""), kv([["Cores / threads", c.cores + " / " + c.threads], ["Base clock", c.max_mhz ? (c.max_mhz / 1000).toFixed(2) + " GHz" : ""],
        ["Current clock", c.current_mhz ? (c.current_mhz / 1000).toFixed(2) + " GHz" : ""], ["Cache L2 / L3", (c.l2_kb ? Math.round(c.l2_kb / 1024 * 10) / 10 + " MB" : "—") + " / " + (c.l3_kb ? Math.round(c.l3_kb / 1024) + " MB" : "—")],
        ["Family / model / stepping", c.caption], ["Processor ID", secret(c.id), true], ["Virtualization", c.virtualization === true ? "Enabled in firmware" : c.virtualization === false ? "Disabled in firmware" : ""]]) +
        '<div class="hw-links-row">' + ext("https://www.google.com/search?q=" + q(c.name + " specifications"), "Specifications", "search") + "</div>", null);
    }).join("");
    var slots = d.memory_slots || {};
    out.memory = '<p class="muted small hw-mem-note">' + d.memory.length + " module" + (d.memory.length === 1 ? "" : "s") + (slots.slots ? " in " + slots.slots + " slots" : "") +
      (slots.max_bytes ? " · board maximum " + gb(slots.max_bytes) : "") + "</p>" +
      UI.table([{ title: "Slot" }, { title: "Size" }, { title: "Type" }, { title: "Speed" }, { title: "Maker" }, { title: "Part number" }, { title: "" }], d.memory.map(function (m) {
        var speed = m.configured_mhz || m.mhz;
        return [esc(m.slot || m.bank || "—"), esc(gb(m.bytes)), esc(MEMORY_TYPE[m.type] || "—"),
          esc(speed ? speed + " MT/s" + (m.mhz && m.configured_mhz && m.mhz !== m.configured_mhz ? " (rated " + m.mhz + ")" : "") : "—"),
          esc(m.vendor || "—"), copyable(m.part), m.part ? ext("https://www.google.com/search?q=" + q(m.part), "Search", "search") : ""];
      }), "No memory module reported.");
    out.gpu = d.gpu.map(function (g) {
      return item(g.name, g.vendor, kv([["Video memory", g.vram ? gb(g.vram) : ""], ["Driver", g.driver + (g.driver_date ? " (" + g.driver_date + ")" : "")],
        ["Display", g.resolution ? g.resolution + (g.hz ? " @ " + g.hz + " Hz" : "") : ""], ["Status", g.status]].concat(idRows(g.ids, g.device))), g.ids);
    }).join("");
    out.disks = d.disks.map(function (k) {
      return item(k.model, [k.media, k.bus || k.interface, gb(k.bytes)].filter(function (x) { return x && x !== "Unspecified"; }).join(" · "),
        kv([["Health", k.health], ["Firmware", k.firmware], ["Serial number", secret(k.serial), true], ["Partitions", k.partitions]].concat(idRows(k.ids, k.device))) +
        '<div class="hw-links-row">' + ext("https://www.google.com/search?q=" + q(k.model + " firmware update"), "Firmware updates", "download") + "</div>", null);
    }).join("");
    out.network = d.network.map(function (n) {
      return item(n.description, n.name + " · " + n.status + (n.speed && n.status === "Up" ? " · " + n.speed : ""),
        kv([["MAC address", secret(n.mac), true], ["Driver", (n.driver || "—") + (n.driver_provider ? " · " + n.driver_provider : "") + (n.driver_date ? " (" + n.driver_date + ")" : "")],
          ["Medium", n.media]].concat(idRows(n.ids, n.device))), n.ids);
    }).join("");
    out.monitors = d.monitors.map(function (m) {
      return item(m.name || "Monitor", (m.vendor || "") + (m.year ? " · made in " + m.year : ""), kv([["Product code", m.product], ["Serial number", secret(m.serial), true], ["Device instance", copyable(m.device), true]]) +
        '<div class="hw-links-row">' + ext("https://www.google.com/search?q=" + q((m.vendor || "") + " " + (m.name || m.product) + " monitor specifications"), "Specifications", "search") + "</div>", null);
    }).join("");
    out.audio = d.audio.map(function (a) { return item(a.name, (a.vendor || "") + " · " + a.status, kv(idRows(a.ids, a.device)), a.ids); }).join("");
    if (d.battery) {
      var b = d.battery, wear = b.designed_mwh && b.full_mwh ? Math.round(b.full_mwh / b.designed_mwh * 100) : null;
      out.battery = item(b.name || "Battery", b.vendor, kv([["Charge", b.charge != null ? b.charge + "%" : ""], ["Design capacity", b.designed_mwh ? b.designed_mwh + " mWh" : ""],
        ["Full charge capacity", b.full_mwh ? b.full_mwh + " mWh" + (wear ? " (" + wear + "% of new)" : "") : ""], ["Serial number", secret(b.serial), true]]), null);
    }
    return out;
  }

  function deviceDetail(dev) {
    var body = kv([["Class", classLabel(dev.class)], ["Manufacturer", dev.vendor], ["Status", (dev.status || "—") + (dev.error ? " (error code " + dev.error + ")" : "")],
      ["Driver", (dev.driver || "—") + (dev.driver_date ? " (" + dev.driver_date + ")" : "") + (dev.driver_provider ? " · " + dev.driver_provider : "")],
      ["INF file", dev.inf], ["Service", dev.service]].concat(idRows(dev.ids, dev.device))) +
      (dev.hardware_ids.length ? '<div class="hw-idlist"><div class="hw-sensor-title">All hardware IDs</div>' + dev.hardware_ids.map(copyable).join("") + "</div>" : "") +
      (dev.compatible_ids.length ? '<div class="hw-idlist"><div class="hw-sensor-title">Compatible IDs</div>' + dev.compatible_ids.map(copyable).join("") + "</div>" : "") +
      '<div class="hw-links-row">' + searchLinks(dev.ids, dev.name) + "</div>" +
      (dev.error ? '<div class="callout callout-warning">' + UI.icon("alert") + "<div>Windows reports a problem with this device (code " + esc(dev.error) +
        "). Search its hardware ID in the driver catalog to find the right driver.</div></div>" : "");
    UI.modal(dev.name || dev.device, '<div class="hw-detail">' + body + "</div>", [{ label: "Close", cls: "btn-primary" }]);
  }

  function summary(data, sensors) {
    var s = data.system || {};
    var lines = ["Computer: " + [s.manufacturer, s.model].join(" "),
      "Motherboard: " + [s.board_vendor, s.board_model].join(" ") + " · BIOS " + s.bios_version + " (" + s.bios_date + ")"];
    data.cpu.forEach(function (c) { lines.push("Processor: " + c.name + " (" + c.cores + "C/" + c.threads + "T)"); });
    lines.push("Memory: " + data.memory.map(function (m) { return [gb(m.bytes), MEMORY_TYPE[m.type], m.configured_mhz || m.mhz, m.part].filter(Boolean).join(" "); }).join(", "));
    data.gpu.forEach(function (g) { lines.push("Graphics: " + g.name + " · driver " + g.driver + (g.ids.search ? " · " + g.ids.search : "")); });
    data.disks.forEach(function (k) { lines.push("Disk: " + k.model + " · " + gb(k.bytes) + " · " + (k.media || k.interface)); });
    data.network.forEach(function (n) { lines.push("Network: " + n.description + " · driver " + n.driver); });
    lines.push("Windows: " + s.os + " " + (s.os_build || "") + " (" + s.os_version + ")");
    if (sensors && sensors.temperatures.length) {
      lines.push("Temperatures: " + sensors.temperatures.map(function (t) { return t.name + " " + Math.round(t.celsius) + " °C"; }).join(", "));
    }
    return lines.join("\n");
  }
  function copy(text, done) {
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () { UI.toast(done, "ok"); },
      function () { UI.toast("The clipboard is not available in this browser.", "warning"); });
  }

  window.Pages.hardware = {
    title: "Hardware",
    /* The specifications as text without serial numbers (also used by the Support page). */
    summaryText: function () { return API.get("/hardware").then(function (d) { return summary(d, null); }); },
    render: function (el, App) {
      var stopped = false, timer = null, paused = false, data = null, sensors = null;
      App.setSubtitle("Every component with its hardware IDs, live temperatures and fans");
      App.onLeave(function () { stopped = true; clearTimeout(timer); });
      el.innerHTML = '<div class="hw-page">' + UI.pageHeader("Hardware", "Components, hardware IDs for finding drivers online, temperatures and fans",
        UI.hint("Hardware IDs (PCI\\VEN_…&DEV_…, USB\\VID_…&PID_…) identify a device even without its driver: search them in the Microsoft driver catalog or on the web. " +
          "Serial numbers and the UUID identify this PC: share them only with its manufacturer.") +
        UI.button("Copy summary", 'id="hw-copy"', "", "copy") + UI.button("JSON", 'id="hw-json" title="Download the whole inventory as JSON, to compare PCs or keep a record"', "", "download") +
        UI.button("Read again", 'id="hw-refresh"', "", "refresh")) +
        '<div id="hw-kpis" class="grid grid-4">' + Components.skeleton() + "</div>" +
        '<div class="grid">' + UI.card("Temperatures and fans", '<div id="hw-sensors">' + Components.skeleton() + "</div>",
          '<span class="muted small" id="hw-sensor-time"></span><button class="btn btn-sm" type="button" id="hw-pause">' + UI.icon("clock") + "Pause</button>", "hw-sensor-card") + "</div>" +
        '<div id="hw-body">' + Components.skeleton() + "</div></div>";

      function kpis() {
        var k = el.querySelector("#hw-kpis");
        if (!k || !data) return;
        var cpu = data.cpu[0] || {}, gpu = data.gpu.filter(function (g) { return !/basic|virtual|remote|parsec|meta/i.test(g.name); })[0] || data.gpu[0] || {};
        var total = data.memory.reduce(function (a, m) { return a + (m.bytes || 0); }, 0) || (data.system || {}).ram_total;
        var hot = sensors && sensors.hottest;
        var problems = data.devices.filter(function (x) { return x.error; }).length;
        var hotTone = hot == null ? "" : hot >= 85 ? "error" : hot >= 75 ? "warning" : "ok";
        k.innerHTML = UI.kpi("Processor", esc(cpu.name || "—"), cpu.cores ? cpu.cores + " cores · " + cpu.threads + " threads" : "", "info") +
          UI.kpi("Memory", esc(gb(total)), data.memory.length + " module" + (data.memory.length === 1 ? "" : "s") + ((data.memory_slots || {}).slots ? " of " + data.memory_slots.slots + " slots" : ""), "info") +
          UI.kpi("Graphics", esc(gpu.name || "—"), gpu.vram ? gb(gpu.vram) + " video memory" : "", "info") +
          (problems ? UI.kpi("Devices with problems", String(problems), "All devices › Any status › Problems", "warning")
            : UI.kpi("Hottest sensor", hot != null ? Math.round(hot) + " °C" : "—", hot != null ? "Live, every " + SENSOR_MS / 1000 + " s" : "No readable sensor yet", hotTone));
      }
      function drawSensors() {
        var box = el.querySelector("#hw-sensors");
        if (!box || !sensors) return;
        box.innerHTML = toolCallout(sensors) + sensorTiles(sensors);
        var t = el.querySelector("#hw-sensor-time");
        if (t) t.textContent = paused ? "Paused" : "Updated " + sensors.read_at.slice(11);
        kpis();
      }
      function schedule() { if (!stopped) timer = setTimeout(function () { pollSensors(false); }, SENSOR_MS); }
      function pollSensors(fresh) {
        if (stopped) return;
        clearTimeout(timer);
        if (paused || document.hidden) { schedule(); return; }
        API.get("/hardware/sensors" + (fresh ? "?fresh=1" : "")).then(function (s) {
          if (stopped || !App.isCurrent("hardware")) return;
          sensors = s;
          remember(s);
          drawSensors();
        }, function () {}).then(schedule);
      }
      function drawBody() {
        var parts = sections(data);
        var problems = data.devices.filter(function (x) { return x.error; }).length;
        var body = el.querySelector("#hw-body");
        body.innerHTML = '<div class="grid grid-2">' + UI.card("System and motherboard", parts.system) + UI.card("Processor", parts.cpu || '<p class="empty">No processor reported.</p>') + "</div>" +
          '<div class="grid">' + UI.card("Memory", parts.memory) + "</div>" +
          '<div class="grid grid-2">' + UI.card("Graphics", parts.gpu || '<p class="empty">No graphics adapter.</p>') + UI.card("Disks", parts.disks || '<p class="empty">No disk.</p>') + "</div>" +
          '<div class="grid grid-2">' + UI.card("Network adapters", parts.network || '<p class="empty">No physical adapter.</p>') +
          UI.card("Monitors", parts.monitors || '<p class="empty">No monitor reports its identity.</p>') + "</div>" +
          '<div class="grid grid-2">' + UI.card("Audio", parts.audio || '<p class="empty">No sound device.</p>') + (parts.battery ? UI.card("Battery", parts.battery) : "") + "</div>" +
          '<div class="grid">' + UI.card("All devices", '<div id="hw-devices"></div>', '<span class="muted small">' + data.devices.length + " devices" +
            (problems ? ' · <span class="badge badge-status-warning">' + problems + " with problems</span>" : "") + " · read in " + data.seconds + " s</span>", "card-flush") + "</div>";
        var classes = {};
        data.devices.forEach(function (x) { x.problem = x.error ? "yes" : "no"; x.hwid = x.ids.search || x.device; if (x.class) classes[x.class] = 1; });
        Components.dataTable(body.querySelector("#hw-devices"), {
          rows: data.devices, sort: "class", exportName: "hardware-devices", placeholder: "Search name, vendor, hardware ID or driver…",
          filters: [{ key: "class", label: "All classes", options: Object.keys(classes).sort().map(function (c) { return [c, classLabel(c)]; }).sort(function (a, b) { return a[1].localeCompare(b[1]); }) },
            { key: "problem", label: "Any status", options: [["yes", "Problems"], ["no", "Working"]] }],
          columns: [
            { key: "name", title: "Device", render: function (x) { return '<button type="button" class="link-btn cell-title" data-device="' + esc(x.device) + '">' + esc(x.name || "Unknown device") + "</button>" +
              '<div class="cell-sub">' + esc(x.vendor || x.ids.vendor || "") + "</div>"; } },
            { key: "class", title: "Class", value: function (x) { return classLabel(x.class); } },
            { key: "hwid", title: "Hardware ID", render: function (x) { return copyable(x.hwid); } },
            { key: "driver", title: "Driver", render: function (x) { return x.driver ? esc(x.driver) + '<div class="cell-sub">' + esc([x.driver_date, x.driver_provider].filter(Boolean).join(" · ")) + "</div>" : '<span class="cell-sub">—</span>'; },
              value: function (x) { return (x.driver || "") + " " + (x.driver_provider || ""); } },
            { key: "status", title: "Status", render: function (x) { return x.error ? '<span class="badge badge-status-warning">Code ' + esc(x.error) + "</span>" : UI.statusBadge(x.status === "OK" ? "ok" : x.status ? "warning" : "skipped"); },
              value: function (x) { return x.error ? "Code " + x.error : x.status; } },
            { key: "links", title: "", sortable: false, csv: false, render: function (x) { return searchLinks(x.ids, x.name); } }
          ]
        });
        kpis();
      }
      function load(fresh) {
        var body = el.querySelector("#hw-body");
        if (fresh && body) body.innerHTML = Components.skeleton();
        return API.get("/hardware" + (fresh ? "?fresh=1" : "")).then(function (d) {
          if (stopped || !App.isCurrent("hardware")) return;
          data = d;
          drawBody();
        }, function (e) { if (body) body.innerHTML = '<div class="callout callout-error">' + UI.icon("alert") + "<div>" + esc(e.message) + "</div></div>"; });
      }
      function monitorTool(m) {
        var op = m.getAttribute("data-monitor");
        var go = function () {
          m.disabled = true;
          m.innerHTML = UI.icon("clock") + (op === "install" ? "Installing… (up to a minute)" : "Starting…");
          API.post("/hardware/monitor-tool", { action: op }).then(function (r) {
            UI.toast(r.preview ? "Preview mode: recorded in History, nothing installed." : "LibreHardwareMonitor is running: its sensors appear in a few seconds.", r.preview ? "info" : "ok");
            setTimeout(function () { pollSensors(true); }, 6000);
          }, function (er) { UI.toast(er.message, "error"); m.disabled = false; m.textContent = "Try again"; });
        };
        if (op !== "install") { go(); return; }
        UI.confirm("Install LibreHardwareMonitor?", "It is installed with winget from its official package (open source, MPL-2.0) and started with administrator rights, " +
          "so this page can read processor, motherboard and fan sensors. You can uninstall it from Settings › Apps.", { ok: "Install and start" }).then(function (ok) { if (ok) go(); });
      }

      // On the page's own wrapper, never on #content: listeners there would pile up across visits.
      el.querySelector(".hw-page").addEventListener("click", function (e) {
        var c = e.target.closest("[data-copy-text]");
        if (c) { e.preventDefault(); copy(c.getAttribute("data-copy-text"), "Copied."); return; }
        var dv = e.target.closest("[data-device]");
        if (dv && data) {
          var dev = data.devices.filter(function (x) { return x.device === dv.getAttribute("data-device"); })[0];
          if (dev) deviceDetail(dev);
          return;
        }
        var m = e.target.closest("[data-monitor]");
        if (m) { monitorTool(m); return; }
        var p = e.target.closest("#hw-pause");
        if (p) {
          paused = !paused;
          p.innerHTML = UI.icon(paused ? "play" : "clock") + (paused ? "Resume" : "Pause");
          drawSensors();
          if (!paused) pollSensors(false);
          return;
        }
        if (e.target.closest("#hw-refresh")) { load(true); pollSensors(true); return; }
        if (e.target.closest("#hw-json") && data) {
          var name = "hardware-" + ((App.state.info || {}).hostname || "pc") + "-" + new Date().toISOString().slice(0, 10) + ".json";
          Components.downloadText(name, JSON.stringify({ kind: "wmm-hardware", read_at: data.read_at, inventory: data, sensors: sensors }, null, 2), "application/json");
          return;
        }
        if (e.target.closest("#hw-copy") && data) copy(summary(data, sensors), "Summary copied, without serial numbers: paste it in a ticket or a forum.");
      });

      pollSensors(false);
      return load(false);
    }
  };
})();
