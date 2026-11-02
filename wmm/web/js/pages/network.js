/* Network: adapters, latency, jitter, packet loss and DNS. */
(function () {
  "use strict";
  window.Pages = window.Pages || {};
  var esc = UI.esc;
  var COLORS = { Router: "#2E9D8F", Cloudflare: "#C27C0E", Google: "#0F6CBD" };

  window.Pages.network = {
    title: "Network",
    render: function (el, App) {
      var self = this;
      return API.get("/areas/network").then(function (v) {
        var d = v.data, parts = UI.areaParts(v, "network"), targets = d.targets || [];
        var up = (d.adapters || []).filter(function (a) { return a.status === "Up"; });
        var internet = targets.filter(function (t) { return t.name !== "Router" && t.lost < t.sent; });
        var best = internet.length ? internet.reduce(function (a, b) { return a.avg <= b.avg ? a : b; }) : null;
        var lost = targets.reduce(function (a, t) { return a + t.lost; }, 0), sent = targets.reduce(function (a, t) { return a + t.sent; }, 0);
        App.setSubtitle("Connectivity, latency and name resolution");

        var kpis = '<div class="grid grid-5">' +
          UI.kpi("Network score", Components.num(v.score), v.recommendations.length + " improvement(s)", UI.tone(v.score)) +
          UI.kpi("Connected adapters", Components.num(up.length) + " <small>/ " + (d.adapters || []).length + "</small>", up.map(function (a) { return a.name + " " + a.speed; }).join(", ") || "Offline", up.length ? "ok" : "error") +
          UI.kpi("Internet latency", best ? Components.num(best.avg) + " <small>ms</small>" : "—", best ? "Best: " + best.name + " · jitter " + best.jitter + " ms" : "No reply", best ? UI.toneOf(best.avg, 60, 100, true) : "error") +
          UI.kpi("Packet loss", Components.num(lost) + " <small>/ " + sent + "</small>", lost ? "Packets lost in the test" : "No loss", lost ? "error" : "ok") +
          UI.kpi("DNS lookup", d.dns_ms != null ? Components.num(d.dns_ms) + " <small>ms</small>" : "—", d.dns_ok ? "Resolution works" : "Resolution failed", d.dns_ok ? UI.toneOf(d.dns_ms, 100, 150, true) : "error") + "</div>";

        var latency = Charts.hbars(targets.map(function (t) { return { label: t.name, value: t.avg, color: COLORS[t.name] || "#5C7080" }; }),
          { format: function (x) { return x + " ms"; }, title: "Average latency", empty: "No measurement" }) +
          '<p class="muted small" style="margin:10px 0 0">Average of ' + (targets[0] ? targets[0].sent : 4) + " pings per target. Router latency measures the local network only.</p>";
        var samples = Charts.line(targets.map(function (t) {
          var base = Date.now() - t.samples.length * 1000;
          return { name: t.name, color: COLORS[t.name], points: t.samples.map(function (s, i) { return { x: base + i * 1000, y: s }; }) };
        }), { min: 0, height: 200, xLabels: false, format: function (x) { return Math.round(x) + " ms"; } }) + '<div class="series-key">' + targets.map(function (t) {
          return '<span><span class="swatch" style="background:' + (COLORS[t.name] || "#5C7080") + '"></span>' + esc(t.name) + " (" + esc(t.address) + ")</span>";
        }).join("") + "</div>";
        var table = UI.table([{ title: "Target" }, { title: "Average", cls: "num" }, { title: "Max", cls: "num" }, { title: "Jitter", cls: "num" }, { title: "Lost", cls: "num" }],
          targets.map(function (t) {
            return ['<span class="cell-title">' + esc(t.name) + '</span> <span class="cell-sub">' + esc(t.address) + "</span>", t.avg + " ms", t.max + " ms", t.jitter + " ms",
              t.lost ? '<span class="badge badge-status-error">' + t.lost + "/" + t.sent + "</span>" : '<span class="badge badge-status-ok">0/' + t.sent + "</span>"];
          }));

        var adapters = UI.table([{ title: "Adapter" }, { title: "Status" }, { title: "Speed", cls: "num" }, { title: "IPv4" }, { title: "Gateway" }, { title: "DNS servers" }, { title: "MAC" }],
          (d.adapters || []).map(function (a) {
            return ['<div class="cell-title">' + esc(a.name) + '</div><div class="cell-sub">' + esc(a.description) + "</div>",
              a.status === "Up" ? '<span class="badge badge-status-ok">Connected</span>' : '<span class="badge">' + esc(a.status) + "</span>",
              esc(a.speed || "—"), '<span class="cell-mono">' + esc(a.ipv4.join(", ") || "—") + "</span>", '<span class="cell-mono">' + esc(a.gateway.join(", ") || "—") + "</span>",
              '<span class="cell-mono">' + esc(a.dns.join(", ") || "—") + "</span>", '<span class="cell-mono">' + esc(a.mac || "—") + "</span>"];
          }), "No physical adapter found.");

        var dns = '<p class="muted" style="margin-top:0">Change the DNS servers of the connected adapters. Company networks usually need the automatic setting.</p>' +
          '<div class="page-actions"><button class="btn btn-sm" data-run="network.dns_cloudflare">Cloudflare 1.1.1.1</button><button class="btn btn-sm" data-run="network.dns_google">Google 8.8.8.8</button>' +
          '<button class="btn btn-sm" data-run="network.dns_auto">Automatic (DHCP)</button><button class="btn btn-sm" data-run="network.flush_dns">' + UI.icon("refresh") + "Flush DNS cache</button></div>" +
          '<p class="muted small" style="margin-bottom:0">' + (d.connections != null ? esc(d.connections) + " established TCP connections at scan time." : "") + "</p>";

        el.innerHTML = parts.header + parts.errors + kpis +
          '<div class="grid grid-3">' + UI.card("Average latency", latency) + UI.card("Ping samples", samples, "", "span-2") + "</div>" +
          '<div class="grid grid-2-1">' + UI.card("Test results", table, "", "card-flush") + UI.card("DNS", dns) + "</div>" +
          '<div class="grid">' + UI.card("Adapters", adapters, "", "card-flush") + "</div>" +
          '<div class="grid">' + parts.recommendations + "</div>" + '<div class="grid">' + parts.actions + "</div>" +
          '<div class="grid grid-3">' + parts.trend + UI.card("Score", parts.score) + parts.runs + "</div>";
        UI.bindArea(el, "network", function () { self.render(el, App); });
      });
    }
  };
})();
