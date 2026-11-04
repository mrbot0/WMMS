/* Network scanner: every device on the local networks of this PC with name, maker, MAC, open ports, web page and a guess
   of what it is; new devices since the previous scan and devices that are gone. It only looks, nothing changes. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var ICON = { "Router / gateway": "network", "This PC": "cpu", "Printer": "print", "NAS": "storage", "Camera": "security", "Windows PC": "cpu" };

  function ports(d) {
    return (d.ports || []).map(function (p, i) {
      return '<span class="badge" title="' + esc((d.services || [])[i] || "") + '">' + esc(String(p)) + "</span>";
    }).join(" ") || '<span class="cell-sub">none</span>';
  }

  window.Pages.netscan = {
    title: "Network scanner",
    render: function (el, App) {
      return API.get("/network/devices").then(function (d) { draw(el, App, d); });
    }
  };

  function draw(el, App, d) {
    var devices = d.devices || [];
    var nuovi = devices.filter(function (x) { return x.new; });
    var web = devices.filter(function (x) { return x.web; });
    var avvisi = devices.filter(function (x) { return (x.notes || []).length; });
    var reti = (d.networks || []).map(function (r) { return r.network + " (" + r.alias + ")"; }).join(", ");
    App.setSubtitle(d.scanned ? devices.length + " devices · scanned " + UI.formatDate(d.scanned, true) : "Not scanned yet");
    var root = document.createElement("div");
    root.innerHTML = UI.pageHeader("Network scanner", d.scanned ? "Networks: " + reti + " · " + d.seconds + " s" : "Every device on the networks of this PC",
      UI.button("Scan the network", "data-netscan", "btn-primary", "refresh")) +
      (d.scanned ? "" : '<div class="callout callout-info">' + UI.icon("info") + "<div>Press <strong>Scan the network</strong>: in about half a minute you see " +
        "every device connected to your router, with what it is and what it offers. The scan only looks: it changes nothing on the devices.</div></div>") +
      '<div class="grid grid-4">' +
      UI.kpi("Devices", Components.num(devices.length), d.addresses ? d.addresses + " addresses checked" : "", "info") +
      UI.kpi("New devices", Components.num(nuovi.length), "since the previous scan", nuovi.length ? "warning" : "ok") +
      UI.kpi("With a web page", Components.num(web.length), "router, printer, NAS settings", "info") +
      UI.kpi("Services to check", Components.num(avvisi.length), "Telnet, FTP, VNC, Remote Desktop", avvisi.length ? "warning" : "ok") + "</div>" +
      (nuovi.length ? '<div class="callout callout-warning">' + UI.icon("alert") + "<div><strong>New on the network:</strong> " +
        nuovi.map(function (x) { return esc((x.name || x.ip) + (x.vendor ? " (" + x.vendor + ")" : "")); }).join(", ") +
        ". If you do not recognise one, check it in the router.</div></div>" : "") +
      '<div class="grid">' + UI.card("Devices on the network", '<div id="netscan-table"></div>', "", "card-flush") + "</div>" +
      ((d.missing || []).length ? '<div class="grid">' + UI.card("Not seen in the last scan", UI.table([{ title: "Device" }, { title: "Last IP" }, { title: "Last seen" }],
        d.missing.slice(0, 20).map(function (m) { return [esc(m.name || m.key), '<span class="cell-mono">' + esc(m.ip) + "</span>", esc(UI.formatDate(m.last_seen, true))]; })),
        '<span class="muted small">Switched off, out of range or gone</span>') + "</div>" : "");
    el.innerHTML = "";
    el.appendChild(root);

    if (devices.length) Components.dataTable(root.querySelector("#netscan-table"), {
      rows: devices, exportName: "wmm-network-devices", placeholder: "Search IP, name, maker, type…", sort: "ip", pageSize: 50,
      filters: [{ key: "type", label: "All kinds", options: Array.from(new Set(devices.map(function (x) { return x.type; }))).sort().map(function (t) { return [t, t]; }) }],
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
        { key: "latency_ms", title: "Response", cls: "num", render: function (x) { return x.latency_ms == null ? "—" : esc(x.latency_ms + " ms"); } },
        { key: "web", title: "", sortable: false, csv: false, render: function (x) {
          return x.web ? '<a class="btn btn-sm btn-ghost" href="' + esc(x.web) + '" target="_blank" rel="noopener noreferrer">' + UI.icon("explorer") + "Open web page</a>" : ""; } }
      ]
    });

    root.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      var ip;
      if (b.hasAttribute("data-netscan")) {
        b.disabled = true;
        b.classList.add("busy");
        UI.toast("Scanning the network: about half a minute.", "info");
        API.post("/network/scan").then(function (r) {
          UI.toast(r.devices.length + " devices found" + (r.devices.some(function (x) { return x.new; }) ? ", some are new." : "."), "ok");
          draw(el, App, r);
        }, function (err) { UI.toast(err.message, "error"); b.disabled = false; b.classList.remove("busy"); });
        return;
      }
      if ((ip = b.getAttribute("data-device"))) detail(devices.filter(function (x) { return x.ip === ip; })[0]);
    });
  }

  function detail(x) {
    var righe = [["Kind", esc(x.type)], ["IP address", '<span class="cell-mono">' + esc(x.ip) + "</span>"], ["Name", esc(x.name || "—")],
      ["MAC", '<span class="cell-mono sensitive">' + esc(x.mac || "—") + "</span>"], ["Maker", esc(x.vendor || "Unknown")],
      ["Response", x.latency_ms == null ? "No ping answer (found through ARP)" : esc(x.latency_ms + " ms")],
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
})();
