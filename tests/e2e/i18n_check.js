/* Italian check (2.11): every page and every tab of the console in Italian, with the translation audit on
   (wmm.i18nAudit). Prints the English text that reached the screen untranslated:
     node tests/e2e/i18n_check.js http://127.0.0.1:PORT TOKEN
   tests/test_e2e.py fails when a string is not in tests/e2e/i18n_baseline.json (old debt, which can only shrink). */
"use strict";
const { chromium } = require("playwright");

const BASE = process.argv[2];
const TOKEN = process.argv[3];
const PAGES = ["dashboard", "recommendations", "performance", "cleanup", "storage", "startup", "apps", "services", "integrity", "security",
  "updates", "network", "hardware", "events", "processes", "registry", "netscan", "toolbox", "activity", "playbooks", "schedules", "fleet", "enterprise",
  "scripts", "history", "reports", "support", "settings", "users"];
const TABS = "[data-page-tab], [data-etab], [data-utab], [data-tab], [data-sect]";
// Only sentences in English: product names, codes, paths and units stay as they are.
const ENGLISH = /\b(the|and|of|to|is|for|on|with|this|your|not|from|by|or|are|will|can|has|have|was|be|at|an|all(?!')|when|what|how|which|that|these|only|every|you|its|than|after|before|need|needs|does|yet)\b/i;

async function settle(page) {
  await page.waitForFunction(() => !document.querySelector("#content .skeleton") && document.querySelector("#content").children.length > 0, null, { timeout: 20000 });
  await page.waitForTimeout(250);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "it-IT" });
  await context.addInitScript(([token]) => {
    sessionStorage.setItem("wmm.token", token);
    localStorage.setItem("wmm.tourDone", "true");
    localStorage.setItem("wmm.guidesOff", "true");
    localStorage.setItem("wmm.lang", JSON.stringify("it"));
    localStorage.setItem("wmm.i18nAudit", "1");
  }, [TOKEN]);
  const page = await context.newPage();
  await page.goto(BASE + "/#/dashboard");
  const problems = [];
  for (const name of PAGES) {
    try {
      await page.evaluate((n) => { location.hash = "#/" + n; }, name);
      await settle(page);
      const count = (await page.$$(TABS)).length;
      for (let i = 0; i < count; i++) {
        const all = await page.$$(TABS);
        if (!all[i]) continue;
        try {
          await all[i].click({ timeout: 2000 });
          await page.waitForTimeout(400);
        } catch (e) { /* hidden or disabled tab */ }
      }
    } catch (e) {
      problems.push(name + ": " + String(e.message).slice(0, 120));
    }
  }
  const misses = await page.evaluate(() => (window.I18N && window.I18N.misses ? window.I18N.misses() : null));
  await browser.close();
  if (misses === null) { process.stdout.write(JSON.stringify({ pages: 0, untranslated: [], problems: ["I18N.misses is missing"] })); process.exit(2); }
  const untranslated = misses.filter((s) => ENGLISH.test(s) && /[a-z]{3}/.test(s) && !/^[\w.\-]+@|^https?:|^[A-Z]:\\|^wmm[_:]/.test(s)).sort();
  process.stdout.write(JSON.stringify({ pages: PAGES.length, untranslated: untranslated, problems: problems }));
  process.exit(0);
})().catch((e) => { process.stdout.write(JSON.stringify({ pages: 0, untranslated: [], problems: [String(e && e.stack || e)] })); process.exit(2); });
