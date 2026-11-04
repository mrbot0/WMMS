/* Browser check of the console (Playwright, headless Chromium). Run by tests/test_e2e.py against an agent in preview mode:
     node tests/e2e/console_check.js http://127.0.0.1:PORT TOKEN
   It opens every page and fails on script errors, error boxes or pages that never finish loading; then it checks page
   tabs, the keyboard shortcuts that once clashed, deep links to a tab and the Italian interface. Prints JSON. */
"use strict";
const { chromium } = require("playwright");

const BASE = process.argv[2];
const TOKEN = process.argv[3];
const PAGES = ["dashboard", "recommendations", "performance", "cleanup", "storage", "startup", "apps", "services", "integrity", "security",
  "updates", "network", "hardware", "events", "processes", "registry", "netscan", "toolbox", "activity", "playbooks", "schedules", "fleet", "scripts",
  "history", "reports", "support", "settings"];

async function settle(page) {
  // A page is ready when its skeleton is gone (or after 20 s, which counts as a failure).
  await page.waitForFunction(() => !document.querySelector("#content .skeleton") && document.querySelector("#content").children.length > 0, null, { timeout: 20000 });
  await page.waitForTimeout(300);
}

(async () => {
  const failures = [];
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "en-US" });
  await context.addInitScript(([token]) => {
    sessionStorage.setItem("wmm.token", token);
    localStorage.setItem("wmm.tourDone", "true");
    localStorage.setItem("wmm.guidesOff", "true");
    if (!localStorage.getItem("wmm.lang")) localStorage.setItem("wmm.lang", JSON.stringify("en"));
  }, [TOKEN]);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e && e.message || e)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });

  await page.goto(BASE + "/#/dashboard");
  for (const name of PAGES) {
    errors.length = 0;
    try {
      await page.evaluate((n) => { location.hash = "#/" + n; }, name);
      await settle(page);
      const box = await page.$("#content .callout-error");
      if (box) failures.push({ page: name, problem: "error box: " + (await box.innerText()).slice(0, 200) });
    } catch (e) {
      failures.push({ page: name, problem: "did not load: " + String(e.message).slice(0, 200) });
    }
    if (errors.length) failures.push({ page: name, problem: "script errors: " + errors.slice(0, 3).join(" | ") });
  }

  // Page tabs: a deep link opens the tab, Shift + right arrow moves to the next one, [ and ] still change page.
  await page.evaluate(() => { location.hash = "#/apps?tab=security"; });
  await settle(page);
  const linked = await page.$eval('[data-page-tab][aria-selected="true"]', (b) => b.getAttribute("data-page-tab"));
  if (linked !== "security") failures.push({ page: "apps", problem: "deep link opened " + linked });
  await page.evaluate(() => { if (document.activeElement) document.activeElement.blur(); });
  await page.keyboard.press("Shift+ArrowRight");
  const next = await page.$eval('[data-page-tab][aria-selected="true"]', (b) => b.getAttribute("data-page-tab"));
  if (next !== "updates") failures.push({ page: "apps", problem: "Shift+ArrowRight selected " + next });
  if (!/#\/apps/.test(page.url())) failures.push({ page: "apps", problem: "Shift+ArrowRight changed page" });
  await page.evaluate(() => { if (document.activeElement) document.activeElement.blur(); });
  await page.keyboard.press("]");
  await page.waitForTimeout(500);
  if (/#\/apps/.test(page.url())) failures.push({ page: "apps", problem: "] did not change page" });

  // Table tools: the Markdown and JSON buttons.
  await page.evaluate(() => { location.hash = "#/apps?tab=programs"; });
  await settle(page);
  const tools = await page.$$eval('[data-tab-group="programs"] .dt-bar button', (b) => b.map((x) => x.textContent.trim()));
  for (const t of ["MD", "JSON"]) if (tools.indexOf(t) < 0) failures.push({ page: "apps", problem: "table button missing: " + t });

  // Italian interface.
  errors.length = 0;
  await page.evaluate(() => { localStorage.setItem("wmm.lang", JSON.stringify("it")); location.hash = "#/apps"; });
  await page.reload();
  await settle(page);
  const nav = await page.$$eval(".nav-label", (n) => n.map((x) => x.textContent));
  if (nav.indexOf("Applicazioni") < 0 || nav.indexOf("Pulizia") < 0) failures.push({ page: "i18n", problem: "menu not in Italian: " + nav.slice(0, 6).join(", ") });
  if (errors.length) failures.push({ page: "i18n", problem: "script errors: " + errors.slice(0, 3).join(" | ") });

  await browser.close();
  process.stdout.write(JSON.stringify({ pages: PAGES.length, failures: failures }));
  process.exit(failures.length ? 1 : 0);
})().catch((e) => { process.stdout.write(JSON.stringify({ pages: 0, failures: [{ page: "runner", problem: String(e && e.stack || e) }] })); process.exit(2); });
