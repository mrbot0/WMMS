/* Client for the local agent API (/api/v1). Every write carries the session token. */
(function () {
  "use strict";
  // The agent opens the console with #k=<token>; keep it for this tab and drop it from the address bar.
  var TOKEN = "";
  var found = /[#&]k=([0-9a-f]{32})/.exec(location.hash);
  try {
    if (found) sessionStorage.setItem("wmm.token", found[1]);
    TOKEN = sessionStorage.getItem("wmm.token") || "";
  } catch (e) { /* storage unavailable */ }
  if (found) {
    TOKEN = TOKEN || found[1];
    history.replaceState(null, "", location.pathname + location.search + "#/dashboard");
  }
  var BASE = "/api/v1";
  function setToken(value) {
    TOKEN = value || "";
    try { if (TOKEN) sessionStorage.setItem("wmm.token", TOKEN); else sessionStorage.removeItem("wmm.token"); } catch (e) { /* storage unavailable */ }
  }

  function request(method, path, body) {
    var options = { method: method, headers: { "Accept": "application/json" }, credentials: "same-origin" };
    if (method !== "GET") options.headers["X-WMM-Token"] = TOKEN;
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(BASE + path, options).then(function (response) {
      return response.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!response.ok) {
          var message = (data && data.error) || ("Request failed (" + response.status + ")");
          // Permission problems open a guided dialog (request access / restart as administrator).
          if (response.status === 403 && /token/i.test(message)) {
            setToken("");
            message = "This window is not connected to the agent. Use Request access to connect it.";
            window.dispatchEvent(new CustomEvent("wmm-unauthorized"));
          } else if (response.status === 409 && /administrator rights/i.test(message)) {
            window.dispatchEvent(new CustomEvent("wmm-need-admin"));
          } else if (data && data.error && response.status >= 404) {
            message += " (HTTP " + response.status + ")";  // helps support tell "not found" from an agent error
          }
          var error = new Error(message);
          error.status = response.status;
          throw error;
        }
        return data;
      });
    }, function () {
      throw new Error("The agent is not reachable. Make sure Windows Maintenance Manager is still running.");
    });
  }

  window.API = {
    get: function (path) { return request("GET", path); },
    post: function (path, body) { return request("POST", path, body === undefined ? {} : body); },
    patch: function (path, body) { return request("PATCH", path, body); },
    put: function (path, body) { return request("PUT", path, body); },
    del: function (path) { return request("DELETE", path); },
    url: function (path) { return BASE + path; },
    hasToken: function () { return !!TOKEN; },
    setToken: setToken
  };
})();
