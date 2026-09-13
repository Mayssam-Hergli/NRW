// Visual verification: screenshots of the landing page, auth form, and
// (via sign-in) the dispatcher/quality views after the redesign.
import { chromium } from "playwright-core";

const BASE_URL = process.env.SMOKE_URL ?? "http://localhost:4174/NRW/";
const email = process.env.SMOKE_EMAIL;
const password = process.env.SMOKE_PASSWORD;
const OUT_DIR = process.env.OUT_DIR ?? ".";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 430, height: 900 } });

await page.goto(BASE_URL, { waitUntil: "networkidle" });
await page.screenshot({ path: `${OUT_DIR}/01-landing.png`, fullPage: true });
console.log("saved 01-landing.png");

await page.click("text=Créer un compte gratuit");
await page.waitForSelector("form");
await page.screenshot({ path: `${OUT_DIR}/02-signup-form.png`, fullPage: true });
console.log("saved 02-signup-form.png");

// Attempt a real signup with a fresh email to see the confirmation-needed
// message render (expected, given mailer_autoconfirm is off on this
// project).
const freshEmail = `samsoum2004+tour${Date.now()}@gmail.com`;
const inputs = page.locator("form input");
await inputs.nth(0).fill(freshEmail);
await inputs.nth(1).fill("tour-password-123");
await inputs.nth(2).fill("Tour User");
await page.click('form button[type="submit"]');
await page.waitForTimeout(2000);
await page.screenshot({ path: `${OUT_DIR}/03-signup-result.png`, fullPage: true });
console.log("saved 03-signup-result.png");

// Now sign in with the known-good pre-confirmed test account.
if (email && password) {
  const signInInputs = page.locator("form input");
  await signInInputs.nth(0).fill("");
  await signInInputs.nth(0).fill(email);
  await signInInputs.nth(1).fill(password);
  await page.click('form button[type="submit"]');
  await page.waitForSelector("text=Flotte", { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT_DIR}/04-dispatcher.png`, fullPage: true });
  console.log("saved 04-dispatcher.png");

  await page.click("text=Qualité");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT_DIR}/05-quality.png`, fullPage: true });
  console.log("saved 05-quality.png");

  const certButton = page.locator("text=Certificat").first();
  if (await certButton.count()) {
    await certButton.click();
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${OUT_DIR}/06-certificate.png`, fullPage: true });
    console.log("saved 06-certificate.png");
  }
}

await browser.close();
