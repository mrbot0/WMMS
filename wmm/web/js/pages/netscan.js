/* Network scanner, in three tabs. Network devices: everything connected to the router (name, maker, MAC, open ports, web
   page, new arrivals). Wi-Fi: the networks around (security, signal, channel, crowding, best channel). Bluetooth: devices
   paired or nearby (kind, signal, rough distance, new ones). Everything only listens: nothing is joined, paired or changed. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var ICON = { "Router / gateway": "network", "This PC": "cpu", "Printer": "print", "NAS": "storage", "Camera": "security", "Windows PC": "cpu" };
  var LEVEL = { ok: "ok", review: "warning", risk: "error", info: "info" };

  var FOLLOW_SCANS = 3;  // the same threshold as wmm/agent/radio.py
  function num(v) { return typeof v === "number" && isFinite(v); }
  function when(d) { return d && d.scanned ? "scanned " + UI.formatDate(d.scanned, true) : "not scanned yet"; }
  function errorBox(d) {
    return d && d.error ? '<div class="callout callout-warning">' + UI.icon("alert") + "<div>" + esc(d.error) +
      (d.settings ? ' <a href="' + esc(d.settings) + '">Open the setting</a>' : "") + "</div></div>" : "";
  }
  function intro(text) { return '<div class="callout callout-info">' + UI.icon("info") + "<div>" + text + "</div></div>"; }
  // The interfaces each scanner can use (loaded once per visit, it takes a few seconds) and the one the user picked.
  var IFACES = null, CHOSEN = {};
  function ifaceLabel(kind, i) {
    if (kind === "devices") return i.alias + " · " + i.network + (i.gateway ? " · gateway " + i.gateway : " · no gateway") + (i.default ? " (active)" : "");
    if (kind === "wifi") return i.name + " · " + (i.connected ? "connected to " + (i.ssid || "a network") : "not connected") + (i.description ? " · " + i.description : "") + (i.default ? " (active)" : "");
    return i.name + (i.active ? " (active)" : " · " + (i.status || "off"));
  }
  function ifaceValue(kind, i) { return kind === "devices" ? i.alias : i.name; }
  function ifaceOptions(kind) {
    if (!IFACES) return '<option value="">Looking for interfaces…</option>';
    var list = IFACES[kind] || [];
    if (!list.length) return '<option value="">No adapter found: the default one is used</option>';
    var chosen = CHOSEN[kind];
    if (chosen && !list.some(function (i) { return ifaceValue(kind, i) === chosen; })) chosen = null;
    return list.map(function (i) {
      var v = ifaceValue(kind, i);
      return '<option value="' + esc(v) + '"' + ((chosen ? v === chosen : i.default) ? " selected" : "") + ">" + esc(ifaceLabel(kind, i)) + "</option>";
    }).join("");
  }
  function scanButton(kind, label) {
    var note = kind === "bluetooth" ? '<span class="cell-sub">Windows always searches with its active Bluetooth adapter.</span>' : "";
    return '<div class="page-actions ns-scanbar" style="justify-content:flex-start;margin-bottom:12px">' + UI.button(label, 'data-scan="' + kind + '"', "btn-primary", "refresh") +
      '<label class="ns-iface"><span>Interface</span><select data-iface="' + kind + '"' + (IFACES && kind !== "bluetooth" ? "" : " disabled") + ">" + ifaceOptions(kind) +
      "</select></label>" + note + "</div>";
  }
  function fillInterfaces(root) {
    Array.prototype.forEach.call(root.querySelectorAll("select[data-iface]"), function (s) {
      var kind = s.getAttribute("data-iface");
      s.innerHTML = ifaceOptions(kind);
      s.disabled = kind === "bluetooth" || !(IFACES && (IFACES[kind] || []).length);
    });
  }

  window.Pages.netscan = {
    title: "Network scanner",
    render: function (el, App) {
      return Promise.all([API.get("/network/devices"), API.get("/network/wifi"), API.get("/network/bluetooth")]).then(function (r) {
        var root = document.createElement("div");
        root.innerHTML = UI.pageHeader("Network scanner", "Devices on your network, Wi-Fi networks and Bluetooth devices nearby. It only listens.", "") +
          '<div data-tab-group="devices"><div id="ns-devices"></div></div>' +
          '<div data-tab-group="wifi"><div id="ns-wifi"></div></div>' +
          '<div data-tab-group="bluetooth"><div id="ns-bluetooth"></div></div>';
        el.innerHTML = "";
        el.appendChild(root);
        var sections = { devices: devices, wifi: wifi, bluetooth: bluetooth };
        sections.devices(root.querySelector("#ns-devices"), r[0]);
        sections.wifi(root.querySelector("#ns-wifi"), r[1]);
        sections.bluetooth(root.querySelector("#ns-bluetooth"), r[2]);
        App.setSubtitle((r[0].devices || []).length + " network devices · " + (r[1].networks || []).length + " Wi-Fi access points · " +
          (r[2].devices || []).length + " Bluetooth devices");
        UI.pageTabs(root, "netscan", [
          { id: "devices", label: "Network devices", icon: "netscan" },
          { id: "wifi", label: "Wi-Fi", icon: "network" },
          { id: "bluetooth", label: "Bluetooth", icon: "explorer" }
        ], { sharedHead: true });

        IFACES = null;
        API.get("/network/interfaces").then(function (i) { IFACES = i || {}; fillInterfaces(root); },
          function () { IFACES = {}; fillInterfaces(root); });
        root.addEventListener("change", function (e) {
          var kind = e.target.getAttribute && e.target.getAttribute("data-iface");
          if (kind) CHOSEN[kind] = e.target.value;
        });

        root.addEventListener("click", function (e) {
          var b = e.target.closest("button");
          if (!b) return;
          var kind = b.getAttribute("data-scan"), ip;
          if (kind) {
            var path = { devices: "/network/scan", wifi: "/network/wifi/scan", bluetooth: "/network/bluetooth/scan" }[kind];
            b.disabled = true;
            b.classList.add("busy");
            UI.toast({ devices: "Scanning the network: about half a minute.", wifi: "Listening for Wi-Fi networks: a few seconds.",
              bluetooth: "Listening for Bluetooth devices: about half a minute." }[kind], "info");
            var scelta = root.querySelector('select[data-iface="' + kind + '"]');
            var body = scelta && !scelta.disabled && scelta.value ? { interface: scelta.value } : {};
            API.post(path, body).then(function (d) {
              sections[kind](root.querySelector("#ns-" + kind), d);
              if (!d.error) UI.toast("Scan completed.", "ok");
            }, function (err) { UI.toast(err.message, "error"); b.disabled = false; b.classList.remove("busy"); });
            return;
          }
          if ((ip = b.getAttribute("data-device"))) detail(root._devices.filter(function (x) { return x.ip === ip; })[0]);
          if (b.hasAttribute("data-upnp-scan")) {
            b.disabled = true;
            UI.toast("Asking the router which ports it opened: a few seconds.", "info");
            API.post("/network/upnp/scan").then(function (u) { upnpBox(root.querySelector("#ns-upnp"), u); b.disabled = false; },
              function (err) { UI.toast(err.message, "error"); b.disabled = false; });
          }
          var addr = b.getAttribute("data-bt-known");
          if (addr) {
            API.post("/network/bluetooth/ignore", { address: addr, ignore: true }).then(function (d) {
              sections.bluetooth(root.querySelector("#ns-bluetooth"), d);
              UI.toast("Marked as known: it is no longer reported as following.", "ok");
            }, function (err) { UI.toast(err.message, "error"); });
          }
        });
        // The device list is redrawn by its scan button; the detail dialog reads the latest one.
        Object.defineProperty(root, "_devices", { get: function () { return root.querySelector("#ns-devices")._list || []; } });
      });
    }
  };

  // ---------- network devices ----------

  function ports(d) {
    return (d.ports || []).map(function (p, i) {
      return '<span class="badge" title="' + esc((d.services || [])[i] || "") + '">' + esc(String(p)) + "</span>";
    }).join(" ") || '<span class="cell-sub">none</span>';
  }

  function devices(box, d) {
    var list = d.devices || [];
    box._list = list;
    var nuovi = list.filter(function (x) { return x.new; });
    var web = list.filter(function (x) { return x.web; });
    var avvisi = list.filter(function (x) { return (x.notes || []).length; });
    var reti = (d.networks || []).map(function (r) { return r.network + " (" + r.alias + ")"; }).join(", ");
    box.innerHTML = scanButton("devices", "Scan the network") +
      (d.scanned ? '<p class="cell-sub">' + esc("Networks: " + reti + " · " + when(d) + " · " + d.seconds + " s") + "</p>"
        : intro("Press <strong>Scan the network</strong>: in about half a minute you see every device connected to your router, with what it is and what it offers.")) +
      '<div class="grid grid-4">' +
      UI.kpi("Devices", Components.num(list.length), d.addresses ? d.addresses + " addresses checked" : "", "info") +
      UI.kpi("New devices", Components.num(nuovi.length), "since the previous scan", nuovi.length ? "warning" : "ok") +
      UI.kpi("With a web page", Components.num(web.length), "router, printer, NAS settings", "info") +
      UI.kpi("Services to check", Components.num(avvisi.length), "Telnet, FTP, VNC, Remote Desktop", avvisi.length ? "warning" : "ok") + "</div>" +
      (nuovi.length ? '<div class="callout callout-warning">' + UI.icon("alert") + "<div><strong>New on the network:</strong> " +
        nuovi.map(function (x) { return esc((x.name || x.ip) + (x.vendor ? " (" + x.vendor + ")" : "")); }).join(", ") +
        ". If you do not recognise one, check it in the router.</div></div>" : "") +
      '<div class="grid">' + UI.card("Devices on the network", '<div class="ns-table" data-table="devices"></div>', "", "card-flush") + "</div>" +
      ((d.missing || []).length ? '<div class="grid">' + UI.card("Not seen in the last scan", UI.table([{ title: "Device" }, { title: "Last IP" }, { title: "Last seen" }],
        d.missing.slice(0, 20).map(function (m) { return [esc(m.name || m.key), '<span class="cell-mono">' + esc(m.ip) + "</span>", esc(UI.formatDate(m.last_seen, true))]; })),
        '<span class="muted small">Switched off, out of range or gone</span>') + "</div>" : "") +
      '<div class="grid grid-2">' + UI.card("Ports the router opened to the internet (UPnP)", '<div id="ns-upnp"><p class="muted">Loading…</p></div>',
        UI.button("Read the router", 'data-upnp-scan', "btn-sm", "refresh")) +
      UI.card("Network watch", '<p class="modal-text">Schedule <strong>Network watch: new devices</strong> (for example every hour): each time it scans the network ' +
        "and sends an e-mail or Telegram alert when a device never seen before joins. Alerts are set in Settings › Alerts.</p>",
        UI.button("Schedule it", 'data-schedule="network.watch"', "btn-sm", "clock")) + "</div>";
    API.get("/network/upnp").then(function (u) { upnpBox(box.querySelector("#ns-upnp"), u); }, function () { upnpBox(box.querySelector("#ns-upnp"), {}); });
    if (!list.length) return;
    Components.dataTable(box.querySelector('[data-table="devices"]'), {
      rows: list, exportName: "wmm-network-devices", placeholder: "Search IP, name, maker, type…", sort: "ip", pageSize: 50,
      filters: [{ key: "type", label: "All kinds", options: Array.from(new Set(list.map(function (x) { return x.type; }))).sort().map(function (t) { return [t, t]; }) }],
      columns: [
        { key: "ip", title: "IP", value: function (x) { return x.ip.split(".").map(function (p) { return ("00" + p).slice(-3); }).join("."); },
          render: function (x) { return '<span class="cell-mono">' + esc(x.ip) + "</span>" + (x.new ? ' <span class="badge badge-status-warning">New</span>' : ""); } },
        { key: "type", title: "Kind", render: function (x) {
          return '<button type="button" class="link-btn cell-title" data-device="' + esc(x.ip) + '">' + UI.icon(ICON[x.type] || "network") + esc(x.type) + "</button>" +
            (x.title ? '<div class="cell-sub">' + esc(x.title) + "</div>" : ""); } },
        { key: "name", title: "Name", render: function (x) { return esc(x.name || "—"); } },
        { key: "vendor", title: "Maker", render: function (x) { return esc(x.vendor || "—"); } },
        { key: "mac", title: "MAC", render: function (x) { return '<span class="cell-mono sensitive">' + esc(x.mac || "—") + "</span>"; } },
        { key: "ports", title: "Open ports", value: function (x) { return (x.ports || []).join(" "); }, render: ports },
        { key: "latency_ms", title: "Response", cls: "num", render: function (x) { return num(x.latency_ms) ? esc(x.latency_ms + " ms") : "—"; } },
        { key: "web", title: "", sortable: false, csv: false, render: function (x) {
          return x.web ? '<a class="btn btn-sm btn-ghost" href="' + esc(x.web) + '" target="_blank" rel="noopener noreferrer">' + UI.icon("explorer") + "Open web page</a>" : ""; } }
      ]
    });
  }

  function detail(x) {
    if (!x) return;
    var righe = [["Kind", esc(x.type)], ["IP address", '<span class="cell-mono">' + esc(x.ip) + "</span>"], ["Name", esc(x.name || "—")],
      ["MAC", '<span class="cell-mono sensitive">' + esc(x.mac || "—") + "</span>"], ["Maker", esc(x.vendor || "Unknown")],
      ["Response", num(x.latency_ms) ? esc(x.latency_ms + " ms") : "No ping answer (found through ARP)"],
      ["First seen", x.first_seen ? esc(UI.formatDate(x.first_seen, true)) : "—"], ["Web page", x.web ? '<a href="' + esc(x.web) + '" target="_blank" rel="noopener noreferrer">' +
        esc(x.title || x.web) + "</a>" : "—"]];
    var servizi = (x.ports || []).length ? UI.table([{ title: "Port" }, { title: "Service" }], x.ports.map(function (p, i) {
      return ['<span class="cell-mono">' + esc(String(p)) + "</span>", esc((x.services || [])[i] || "")];
    })) : '<p class="empty">No common port is open: the device only talks to the internet or answers nothing.</p>';
    var note = (x.notes || []).length ? '<ul class="issue-list">' + x.notes.map(function (n) {
      return '<li class="issue-review">' + UI.icon("alert") + "<span>" + esc(n) + "</span></li>";
    }).join("") + "</ul>" : "";
    UI.modal(x.name || x.ip, (x.new ? '<p><span class="badge badge-status-warning">New since the previous scan</span></p>' : "") + note + UI.definition(righe) +
      "<h3>Open ports</h3>" + servizi, [{ label: "Close", cls: "btn-ghost" }]);
  }

  // ---------- Wi-Fi ----------

  function signalBar(v) {
    if (!num(v)) return "—";
    var tone = v >= 70 ? "ok" : v >= 45 ? "warning" : "error";
    return '<span class="signal-bar signal-' + tone + '" title="' + v + '%"><span style="width:' + Math.max(4, Math.min(100, v)) + '%"></span></span> ' + esc(v + "%");
  }

  function wifi(box, d) {
    var reti = d.networks || [];
    var mia = reti.filter(function (r) { return r.connected; })[0] || reti.filter(function (r) { return r.own; })[0];
    var deboli = reti.filter(function (r) { return r.security && r.security.level === "risk"; });
    var ssid = Array.from(new Set(reti.map(function (r) { return r.ssid || "(hidden)"; })));
    var best = d.best || {};
    var canali = (d.channels || []).slice().sort(function (a, b) { return a.band === b.band ? a.channel - b.channel : a.band < b.band ? -1 : 1; });
    var grafico = canali.length ? Charts.bars(canali.map(function (c) {
      return { label: (c.band === "2.4 GHz" ? "2.4·" : "5·") + c.channel, value: c.count, color: mia && mia.channel === c.channel && mia.band === c.band ? "#0F6CBD" : "#8A97A6" };
    }), { title: "Access points per channel (yours in blue)" }) : '<p class="empty">No channel information.</p>';
    box.innerHTML = scanButton("wifi", "Scan Wi-Fi") + errorBox(d) +
      (d.scanned ? '<p class="cell-sub">' + esc(when(d) + (d.connected && d.connected.adapter ? " · adapter " + d.connected.adapter : "")) + "</p>"
        : intro("Press <strong>Scan Wi-Fi</strong>: in a few seconds you see the networks around you, how safe they are, how strong and which channels are crowded.")) +
      '<div class="grid grid-4">' +
      UI.kpi("Networks", Components.num(ssid.length), reti.length + " access points", "info") +
      UI.kpi("Your network", mia ? esc(mia.ssid) : "—", mia ? esc(mia.signal + "% · " + mia.band + " · channel " + mia.channel) : "not connected to Wi-Fi",
        mia ? (mia.signal >= 60 ? "ok" : "warning") : "info") +
      UI.kpi("Open or weak", Components.num(new Set(deboli.map(function (r) { return r.ssid; })).size), "no password, WEP or TKIP", deboli.length ? "warning" : "ok") +
      UI.kpi("Best channel", (best["2.4 GHz"] ? "2.4 GHz: " + best["2.4 GHz"] : "—") + (best["5 GHz"] ? " · 5 GHz: " + best["5 GHz"] : ""), "least crowded here", "info") + "</div>" +
      ((d.advice || []).length ? '<ul class="suggest-list" style="margin-bottom:14px">' + d.advice.map(function (a) {
        var tone = LEVEL[a.level] || "info";
        return '<li class="suggest suggest-' + tone + '"><span class="suggest-icon">' + UI.icon(tone === "info" ? "recommendations" : "alert") + "</span><div><p>" + esc(a.text) + "</p></div></li>";
      }).join("") + "</ul>" : "") +
      '<div class="grid grid-2-1">' + UI.card("Wi-Fi networks nearby", '<div class="ns-table" data-table="wifi"></div>', "", "card-flush") + UI.card("Channels in use", grafico) + "</div>" +
      '<div class="grid">' + UI.card("Wi-Fi history", '<div id="ns-wifi-history"><p class="muted">Loading…</p></div>',
        UI.button("Schedule samples", 'data-schedule="network.wifi_watch" title="Record a sample every 15-30 minutes"', "btn-sm", "clock")) + "</div>";
    API.get("/network/wifi/history").then(function (h) { wifiHistory(box.querySelector("#ns-wifi-history"), h); }, function () { wifiHistory(box.querySelector("#ns-wifi-history"), {}); });
    if (!reti.length) return;
    Components.dataTable(box.querySelector('[data-table="wifi"]'), {
      rows: reti, exportName: "wmm-wifi-networks", placeholder: "Search networks, BSSID, channel…", sort: "signal", desc: true, pageSize: 25,
      filters: [{ key: "band", label: "All bands", options: Array.from(new Set(reti.map(function (r) { return r.band; }))).sort().map(function (b) { return [b, b]; }) }],
      columns: [
        { key: "ssid", title: "Network", value: function (r) { return r.ssid || "(hidden)"; }, render: function (r) {
          return '<span class="cell-title">' + esc(r.ssid || "Hidden network") + "</span>" + (r.connected ? ' <span class="badge badge-status-ok">Connected</span>' :
            r.own ? ' <span class="badge">Your network</span>' : "") + '<div class="cell-sub cell-mono">' + esc(r.bssid) + (r.vendor ? " · " + esc(r.vendor) : "") + "</div>"; } },
        { key: "security", title: "Security", value: function (r) { return r.security ? r.security.label : ""; }, render: function (r) {
          var s = r.security || {};
          return '<span class="badge badge-status-' + (LEVEL[s.level] || "info") + '" title="' + esc(s.text || "") + '">' + esc(s.label || "—") + "</span>" +
            '<div class="cell-sub">' + esc(r.auth || "") + (r.cipher ? " · " + esc(r.cipher) : "") + "</div>"; } },
        { key: "signal", title: "Signal", render: function (r) { return signalBar(r.signal) + (num(r.dbm) ? '<div class="cell-sub">' + esc(r.dbm + " dBm") + "</div>" : ""); } },
        { key: "band", title: "Band" },
        { key: "channel", title: "Channel", cls: "num", render: function (r) {
          return esc(String(r.channel || "—")) + (r.same_channel ? '<div class="cell-sub">' + esc("+" + r.same_channel + " on it") + "</div>" : ""); } },
        { key: "stations", title: "Stations", cls: "num", render: function (r) { return num(r.stations) ? esc(String(r.stations)) : "—"; } },
        { key: "radio", title: "Standard", render: function (r) { return '<span class="cell-mono">' + esc(r.radio || "—") + "</span>"; } }
      ]
    });
  }

  // ---------- router ports (UPnP) and Wi-Fi history ----------

  function upnpBox(box, u) {
    if (!box) return;
    if (!u || !u.scanned) {
      box.innerHTML = '<p class="modal-text">Press <strong>Read the router</strong>: it asks the router, through UPnP, which ports it opened to the internet ' +
        "and which device asked for each one. Cameras, NAS and consoles often do it by themselves. Nothing is changed.</p>";
      return;
    }
    var m = u.mappings || [];
    var head = '<p class="cell-sub">' + esc((u.router ? (u.router.name || u.router.model || "Router") + (u.router.manufacturer ? " · " + u.router.manufacturer : "") +
      (u.router.external_ip ? " · public address " + u.router.external_ip : "") + " · " : "") + when(u)) + "</p>";
    var note = '<div class="callout ' + (u.risky ? "callout-warning" : "callout-info") + '">' + UI.icon(u.risky ? "alert" : "info") + "<div><span>" + esc(u.note || "") + "</span>" +
      (u.risky ? " <span>Turn UPnP off on the router, or remove these forwards, unless you really need to reach the device from outside.</span>" : "") + "</div></div>";
    box.innerHTML = head + note + (m.length ? UI.table([{ title: "Port" }, { title: "Device" }, { title: "Description" }], m.map(function (x) {
      return ['<span class="cell-mono">' + esc(x.protocol + " " + x.external_port) + "</span>" + (x.enabled ? "" : ' <span class="badge">off</span>'),
        '<span class="cell-mono">' + esc(x.internal_client + ":" + x.internal_port) + "</span>" + (x.device ? '<div class="cell-sub">' + esc(x.device) + "</div>" : ""),
        esc(x.description || "—") + (x.risk ? '<div class="risk-note">' + UI.icon("alert") + esc(x.risk) + "</div>" : "")];
    })) : "");
  }

  function wifiHistory(box, h) {
    if (!box) return;
    var samples = (h && h.samples) || [];
    if (samples.length < 2) {
      box.innerHTML = '<p class="modal-text">Every Wi-Fi scan records the signal, the channel and how crowded it is. Schedule <strong>Wi-Fi history: record a sample</strong> ' +
        "every 15-30 minutes: after a day you see whether the drops depend on the hour, on a neighbour changing channel or on the router.</p>" +
        '<p class="muted small">' + samples.length + " samples so far.</p>";
      return;
    }
    var hours = {};
    (h.by_hour || []).forEach(function (x) { hours[x.hour] = x; });
    var worst = h.worst_hour, bars = "", axis = "";
    for (var i = 0; i < 24; i++) {
      var x = hours[i];
      bars += x && num(x.signal) ? '<span class="' + (x.signal < 50 ? "weak" : "") + '" style="height:' + Math.max(3, x.signal) + '%" title="' +
        esc(i + ":00 · signal " + x.signal + "% · " + x.samples + " samples · " + (x.same_channel || 0) + " networks on the same channel") + '"></span>'
        : '<span class="empty" style="height:3%"></span>';
      axis += "<span>" + (i % 3 === 0 ? i : "") + "</span>";
    }
    var last = samples[samples.length - 1], changes = (h.changes || []).slice(-8).reverse();
    box.innerHTML = '<div class="grid grid-3">' +
      UI.kpi("Samples", Components.num(samples.length), "since " + UI.formatDate(samples[0].t, true), "info") +
      UI.kpi("Weakest hour", worst ? worst.hour + ":00" : "—", worst ? "average signal " + worst.signal + "%" : "", worst && worst.signal < 50 ? "warning" : "ok") +
      UI.kpi("Channel or access point changes", Components.num((h.changes || []).length), esc("last: " + last.ssid + " · channel " + last.channel),
        (h.changes || []).length > 3 ? "warning" : "info") + "</div>" +
      '<div class="muted small">Average signal by hour of the day (orange: below 50%)</div><div class="wifi-hours">' + bars + '</div><div class="wifi-hours-axis">' + axis + "</div>" +
      (changes.length ? "<h3>Latest changes</h3>" + UI.table([{ title: "When" }, { title: "From" }, { title: "To" }], changes.map(function (c) {
        return [esc(UI.formatDate(c.t, true)), '<span class="cell-mono">' + esc(c.from) + "</span>", '<span class="cell-mono">' + esc(c.to) + "</span>"];
      })) : "");
  }

  // ---------- Bluetooth ----------

  function bluetooth(box, d) {
    var list = d.devices || [];
    var accoppiati = list.filter(function (x) { return x.paired; });
    var nuovi = list.filter(function (x) { return x.new; });
    var vicini = list.filter(function (x) { return !x.paired; });
    var seguaci = list.filter(function (x) { return x.follower; });
    box.innerHTML = scanButton("bluetooth", "Scan Bluetooth") + errorBox(d) +
      (seguaci.length ? '<div class="callout callout-warning">' + UI.icon("alert") + "<div><strong>Unknown devices that keep showing up:</strong> " +
        seguaci.map(function (x) { return esc((x.name || x.kind) + " · " + x.address + " · " + x.sightings + " scans in " + x.span_minutes + " min"); }).join("; ") +
        ". <span>A tracker (AirTag, Tile, SmartTag) hidden in a bag or a car behaves like this. If one is yours or a neighbour's, mark it as known.</span></div></div>" : "") +
      (d.scanned ? '<p class="cell-sub">' + esc(when(d) + (d.radio ? " · " + d.radio.name + " (" + d.radio.status + ")" : "") + (d.seconds ? " · " + d.seconds + " s" : "")) + "</p>"
        : intro("Press <strong>Scan Bluetooth</strong>: in about half a minute you see your paired devices and the ones nearby (phones, headphones, watches, lights, trackers).")) +
      '<div class="grid grid-4">' +
      UI.kpi("Bluetooth devices", Components.num(list.length), "paired and nearby", "info") +
      UI.kpi("Paired", Components.num(accoppiati.length), accoppiati.filter(function (x) { return x.connected; }).length + " connected now", "info") +
      UI.kpi("Nearby", Components.num(vicini.length), "not paired with this PC", "info") +
      UI.kpi("New devices", Components.num(nuovi.length), "since the previous scan", nuovi.length ? "warning" : "ok") + "</div>" +
      '<p class="cell-sub">' + UI.icon("info") + " Unpaired devices seen in " + FOLLOW_SCANS + " or more scans over an hour are flagged as possibly following. " +
      '<button type="button" class="link-btn" data-schedule="network.bt_watch">Schedule Bluetooth scans</button> to get an alert.</p>' +
      '<div class="grid">' + UI.card("Bluetooth devices", '<div class="ns-table" data-table="bluetooth"></div>',
        '<span class="muted small">Distance is a rough guess from the signal: walls and bodies change it a lot</span>', "card-flush") + "</div>";
    if (!list.length) return;
    Components.dataTable(box.querySelector('[data-table="bluetooth"]'), {
      rows: list, exportName: "wmm-bluetooth-devices", placeholder: "Search name, kind, address…", sort: "rssi", desc: true, pageSize: 50,
      filters: [{ key: "kind", label: "All kinds", options: Array.from(new Set(list.map(function (x) { return x.kind; }))).sort().map(function (k) { return [k, k]; }) },
        { key: "type", label: "Classic and LE", options: [["Classic", "Classic"], ["Low Energy", "Low Energy"]] }],
      columns: [
        { key: "name", title: "Device", value: function (x) { return x.name || ""; }, render: function (x) {
          return '<span class="cell-title">' + esc(x.name || "Unnamed device") + "</span>" + (x.new ? ' <span class="badge badge-status-warning">New</span>' : "") +
            (x.follower ? ' <span class="badge badge-status-error">May be following</span>' : "") + '<div class="cell-sub">' + esc(x.kind) + "</div>"; } },
        { key: "sightings", title: "Seen", cls: "num", value: function (x) { return x.sightings || 0; }, render: function (x) {
          if (!x.sightings) return "—";
          return esc(x.sightings + " scans") + '<div class="cell-sub">' + esc("over " + x.span_minutes + " min") + "</div>" +
            (x.follower ? '<button type="button" class="btn btn-sm btn-ghost" data-bt-known="' + esc(x.address) + '">Mark as known</button>' : ""); } },
        { key: "paired", title: "State", value: function (x) { return x.connected ? "Connected" : x.paired ? "Paired" : "Nearby"; }, render: function (x) {
          return x.connected ? '<span class="badge badge-status-ok">Connected</span>' : x.paired ? '<span class="badge badge-status-info">Paired</span>' : '<span class="badge">Nearby</span>'; } },
        { key: "rssi", title: "Signal", cls: "num", render: function (x) { return num(x.rssi) ? esc(x.rssi + " dBm") : "—"; } },
        { key: "distance", title: "Distance", render: function (x) { return esc(x.distance || "—"); } },
        { key: "type", title: "Kind of link", render: function (x) { return esc(x.type); } },
        { key: "address", title: "Address", render: function (x) { return '<span class="cell-mono sensitive">' + esc(x.address) + "</span>" + (x.vendor ? '<div class="cell-sub">' + esc(x.vendor) + "</div>" : ""); } },
        { key: "first_seen", title: "First seen", render: function (x) { return x.first_seen ? esc(UI.formatDate(x.first_seen, true)) : "—"; } }
      ]
    });
  }
})();
