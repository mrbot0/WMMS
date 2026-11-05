/* Console from the phone (2.8). The pairing code is kept in this browser and never sent: every request is signed with
   HMAC-SHA256 (the same format as the requests between PCs). crypto.subtle is not available on a plain http page of the
   local network, so SHA-256 is computed here. */
(function () {
  "use strict";
  var K = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be,
    0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc,
    0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
    0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585,
    0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814,
    0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];

  function utf8(s) { return Array.prototype.slice.call(new TextEncoder().encode(s)); }
  function sha256(bytes) {
    var h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var m = bytes.slice(), l = bytes.length * 8;
    m.push(0x80);
    while (m.length % 64 !== 56) m.push(0);
    for (var s = 7; s >= 0; s--) m.push(s >= 4 ? 0 : (l >>> (s * 8)) & 0xff);
    var w = new Array(64);
    for (var i = 0; i < m.length; i += 64) {
      for (var t = 0; t < 16; t++) w[t] = (m[i + 4 * t] << 24) | (m[i + 4 * t + 1] << 16) | (m[i + 4 * t + 2] << 8) | m[i + 4 * t + 3];
      for (t = 16; t < 64; t++) {
        var a0 = w[t - 15], a1 = w[t - 2];
        var s0 = ((a0 >>> 7) | (a0 << 25)) ^ ((a0 >>> 18) | (a0 << 14)) ^ (a0 >>> 3);
        var s1 = ((a1 >>> 17) | (a1 << 15)) ^ ((a1 >>> 19) | (a1 << 13)) ^ (a1 >>> 10);
        w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
      }
      var a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], k = h[7];
      for (t = 0; t < 64; t++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var ch = (e & f) ^ (~e & g), t1 = (k + S1 + ch + K[t] + w[t]) | 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var maj = (a & b) ^ (a & c) ^ (b & c), t2 = (S0 + maj) | 0;
        k = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      h = [(h[0] + a) | 0, (h[1] + b) | 0, (h[2] + c) | 0, (h[3] + d) | 0, (h[4] + e) | 0, (h[5] + f) | 0, (h[6] + g) | 0, (h[7] + k) | 0];
    }
    var out = [];
    h.forEach(function (x) { out.push((x >>> 24) & 0xff, (x >>> 16) & 0xff, (x >>> 8) & 0xff, x & 0xff); });
    return out;
  }
  function hmac(key, msg) {
    var k = utf8(key);
    if (k.length > 64) k = sha256(k);
    while (k.length < 64) k.push(0);
    var inner = k.map(function (x) { return x ^ 0x36; }), outer = k.map(function (x) { return x ^ 0x5c; });
    return hex(sha256(outer.concat(sha256(inner.concat(msg)))));
  }
  function hex(b) { return b.map(function (x) { return (x < 16 ? "0" : "") + x.toString(16); }).join(""); }
  function random(n) { var a = new Uint8Array(n); crypto.getRandomValues(a); return hex(Array.prototype.slice.call(a)); }
  (typeof window !== "undefined" ? window : globalThis).WMMPhone = { sha256: function (s) { return hex(sha256(utf8(s))); }, hmac: function (k, m) { return hmac(k, utf8(m)); } };
  if (typeof document === "undefined") return;  // loaded by the tests (Node): only the signature code

  var KEY = "wmm.phone";
  function saved() { try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; } }
  function call(method, path, body, cred) {
    cred = cred || saved();
    var data = body ? JSON.stringify(body) : "", time = String(Math.floor(Date.now() / 1000)), nonce = random(12);
    var sig = hmac(cred.secret, utf8([method, path, time, nonce].join("\n") + "\n").concat(utf8(data)));
    return fetch(path, { method: method, body: body ? data : undefined, cache: "no-store",
      headers: { "Content-Type": "application/json", "X-WMM-Phone-Device": cred.device, "X-WMM-Phone-Time": time, "X-WMM-Phone-Nonce": nonce,
        "X-WMM-Phone-Sig": sig } }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error(j.error || ("HTTP " + r.status)); e.status = r.status; throw e; }
        return j;
      });
    });
  }

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return "&#" + c.charCodeAt(0) + ";"; }); }
  function msg(text, cls) { var m = $("msg"); m.className = "msg " + (cls || ""); m.textContent = text; if (!text) m.classList.add("hidden"); }
  var AREA = { cleanup: "Pulizia", integrity: "Integrità", services: "Servizi", performance: "Prestazioni", storage: "Archiviazione", network: "Rete",
    startup: "Avvio e app", security: "Sicurezza", updates: "Aggiornamenti" };

  function showPair() { $("pair").classList.remove("hidden"); $("app").classList.add("hidden"); }
  function pair() {
    var code = $("code").value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (code.length !== 16) { msg("Il codice ha 16 caratteri.", "error"); return; }
    var cred = { secret: code, device: random(16) };
    $("pair-go").disabled = true;
    call("POST", "/phone/v1/hello", {}, cred).then(function () {
      localStorage.setItem(KEY, JSON.stringify(cred));
      msg("");
      start();
    }).catch(function (e) { msg(e.status === 403 ? "Codice sbagliato o scaduto: chiedine uno nuovo dalla console." : e.message, "error"); })
      .then(function () { $("pair-go").disabled = false; });
  }

  function home() {
    return call("GET", "/phone/v1/summary").then(function (d) {
      var s = d.summary || {};
      $("host").textContent = s.hostname || "PC";
      $("sub").textContent = "Versione " + (s.version || "?") + (s.last_scan ? " · ultima scansione " + new Date(s.last_scan).toLocaleString("it-IT") : "");
      var punti = Object.keys(s.scores || {}).filter(function (a) { return s.scores[a] != null; }).map(function (a) {
        var v = s.scores[a];
        return '<div class="row"><span>' + esc(AREA[a] || a) + '</span><strong class="' + (v >= 80 ? "ok" : v >= 60 ? "warning" : "error") + '">' + v + "</strong></div>";
      }).join("");
      var problemi = (d.problems || []).map(function (p) { return '<div class="row"><span>' + esc(p.title) + '</span><span class="muted">' + esc(AREA[p.area] || "") + "</span></div>"; }).join("");
      $("tab-home").innerHTML = '<div class="card"><div class="grid"><div><div class="muted">Salute</div><div class="score">' + (s.overall == null ? "—" : s.overall) + "</div></div>" +
        '<div><div class="muted">Problemi aperti</div><div class="score">' + (s.open_issues == null ? "—" : s.open_issues) + "</div></div></div>" +
        (s.c_free_gb != null ? '<p class="muted">Spazio libero su C: ' + s.c_free_gb + " GB di " + s.c_total_gb + "</p>" : "") + "</div>" +
        '<div class="card"><h2>Aree</h2>' + (punti || '<p class="muted">Nessuna scansione ancora.</p>') + "</div>" +
        '<div class="card"><h2>Problemi</h2>' + (problemi || '<p class="muted">Nessun problema aperto.</p>') + "</div>";
    });
  }

  var tools = [];
  function renderTools() {
    var gruppi = {};
    tools.forEach(function (t) { (gruppi[t.area] = gruppi[t.area] || []).push(t); });
    $("tab-tools").innerHTML = Object.keys(gruppi).map(function (a) {
      return '<div class="card"><h2>' + esc(AREA[a] || a) + "</h2>" + gruppi[a].map(function (t) {
        return '<div class="row"><span>' + esc(t.title) + '<br><span class="muted">' + (t.kind === "report" ? "Rapporto (solo lettura)" : "Correzione sicura") +
          '</span></span><button data-run="' + esc(t.id) + '">Esegui</button></div>';
      }).join("") + "</div>";
    }).join("");
  }
  function run(id, button) {
    button.disabled = true;
    call("POST", "/phone/v1/runs", { actions: [id] }).then(function (r) {
      msg("In esecuzione sul PC…");
      function poll() {
        call("GET", "/phone/v1/runs/" + r.id).then(function (j) {
          if (j.active) { setTimeout(poll, 2000); return; }
          var res = (j.results || [])[0] || {};
          var v = res.verify ? " · verifica: " + (res.verify.after || res.verify.verdict) : "";
          msg("Finito: " + (res.status || "?") + (res.note ? " — " + res.note : "") + v, res.status === "error" ? "error" : "ok");
          button.disabled = false;
        }).catch(function (e) { msg(e.message, "error"); button.disabled = false; });
      }
      poll();
    }).catch(function (e) { msg(e.message, "error"); button.disabled = false; });
  }

  function start() {
    $("pair").classList.add("hidden");
    $("app").classList.remove("hidden");
    home().catch(function (e) {
      if (e.status === 403) { localStorage.removeItem(KEY); msg("Questo telefono non è più abbinato.", "error"); showPair(); } else msg(e.message, "error");
    });
    call("GET", "/phone/v1/tools").then(function (d) { tools = d.tools || []; renderTools(); }).catch(function () {});
  }

  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-tab]");
    if (t) {
      document.querySelectorAll("[data-tab]").forEach(function (b) { b.classList.toggle("on", b === t); });
      $("tab-home").classList.toggle("hidden", t.dataset.tab !== "home");
      $("tab-tools").classList.toggle("hidden", t.dataset.tab !== "tools");
      if (t.dataset.tab === "home") home().catch(function (er) { msg(er.message, "error"); });
    }
    var r = e.target.closest("[data-run]");
    if (r) run(r.dataset.run, r);
    if (e.target.id === "pair-go") pair();
    if (e.target.id === "forget") { localStorage.removeItem(KEY); showPair(); }
  });
  if (document.getElementById("pair")) { if (saved()) start(); else showPair(); }
})();
