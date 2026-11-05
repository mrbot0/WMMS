/* Critical flows in the browser (2.11), with accounts on, against an agent in preview mode:
     node tests/e2e/flows_check.js http://127.0.0.1:PORT TOKEN '{"admin": [user, password], "viewer": [...], "helpdesk": [...], "tool": "id", "tenant": "name"}'
   1. a viewer signs in with the form and does not see what the role does not allow;
   2. a help-desk user runs a tool that needs approval and gets a request instead of a run;
   3. the administrator sees the request, approves it, and finds users and the clients of the central server. Prints JSON. */
"use strict";
const { chromium } = require("playwright");

const BASE = process.argv[2];
const TOKEN = process.argv[3];
const DATI = JSON.parse(process.argv[4]);

async function signIn(page, who) {
  await page.evaluate(() => { sessionStorage.removeItem("wmm.session"); });
  await page.goto(BASE + "/#/dashboard");
  await page.reload();
  await page.waitForSelector("[data-login]", { timeout: 15000 });
  await page.fill("[data-login] input[name=username]", who[0]);
  await page.fill("[data-login] input[name=password]", who[1]);
  await page.click("[data-login] button[type=submit]");
  await page.waitForFunction(() => !document.getElementById("auth-overlay") && document.querySelector("#content") && document.querySelector("#content").children.length > 0,
    null, { timeout: 20000 });
  await page.waitForTimeout(400);
}

async function nav(page) {
  return page.$$eval(".nav-label", (n) => n.map((x) => x.textContent.trim()));
}

(async () => {
  const failures = [];
  let steps = 0;
  const check = (ok, step, problem) => { steps++; if (!ok) failures.push({ step: step, problem: problem }); };
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "en-US" });
  await context.addInitScript(([token]) => {
    sessionStorage.setItem("wmm.token", token);
    localStorage.setItem("wmm.tourDone", "true");
    localStorage.setItem("wmm.guidesOff", "true");
    localStorage.setItem("wmm.lang", JSON.stringify("en"));
  }, [TOKEN]);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e && e.message || e)));
  await page.goto(BASE + "/#/dashboard");

  // 1. Viewer: signs in with the form, the menu follows the role, an admin route is refused.
  await signIn(page, DATI.viewer);
  const menu = await nav(page);
  check(menu.indexOf("Dashboard") >= 0, "viewer", "no Dashboard in the menu: " + menu.join(", "));
  check(menu.indexOf("Registry") < 0 && menu.indexOf("Users and roles") < 0, "viewer", "the menu shows pages the role cannot see: " + menu.join(", "));
  const vietato = await page.evaluate(() => API.get("/users").then(() => "allowed", (e) => e.message));
  check(/not allow|users\.view/.test(vietato), "viewer", "GET /users was not refused: " + vietato);

  // 2. Help desk: a tool that needs a second person becomes an approval request.
  await signIn(page, DATI.helpdesk);
  const esito = await page.evaluate((tool) => API.post("/runs", { actions: [tool], confirmed: true }).then((r) => r, (e) => ({ error: e.message })), DATI.tool);
  check(esito && esito.approval && esito.approval.id, "approval", "the run did not become an approval request: " + JSON.stringify(esito).slice(0, 300));

  // 3. Administrator: sees and approves the request, sees the users and the clients of the central server.
  await signIn(page, DATI.admin);
  await page.evaluate(() => { location.hash = "#/enterprise?tab=approvals"; });
  await page.waitForTimeout(1500);
  const testo = await page.innerText("#content");
  check(testo.indexOf(DATI.helpdesk[0]) >= 0, "admin", "the approval request of " + DATI.helpdesk[0] + " is not listed");
  const deciso = await page.evaluate((id) => API.post("/approvals/" + id + "/approve", { note: "ok" }).then((r) => r.status || "done", (e) => "error: " + e.message),
    esito && esito.approval ? esito.approval.id : 0);
  check(!/^error/.test(deciso), "admin", "approving failed: " + deciso);
  await page.evaluate(() => { location.hash = "#/users"; });
  await page.waitForTimeout(1500);
  check((await page.innerText("#content")).indexOf(DATI.viewer[0]) >= 0, "admin", "the users page does not list " + DATI.viewer[0]);
  await page.evaluate(() => { location.hash = "#/enterprise?tab=clients"; });
  await page.waitForTimeout(1500);
  check((await page.innerText("#content")).indexOf(DATI.tenant) >= 0, "admin", "the clients tab does not list " + DATI.tenant);
  check(errors.length === 0, "scripts", "script errors: " + errors.slice(0, 3).join(" | "));

  await browser.close();
  process.stdout.write(JSON.stringify({ steps: steps, failures: failures }));
  process.exit(failures.length ? 1 : 0);
})().catch((e) => { process.stdout.write(JSON.stringify({ steps: 0, failures: [{ step: "runner", problem: String(e && e.stack || e) }] })); process.exit(2); });
