// Clean visual check of the authenticated app views (fresh page load,
// straight to sign-in, no signup detour).
import { chromium } from "playwright-core";

const BASE_URL = process.env.SMOKE_URL ?? "http://localhost:4174/NRW/";
const email = process.env.SMOKE_EMAIL;
const password = process.env.SMOKE_PASSWORD;
const OUT_DIR = process.env.OUT_DIR ?? ".";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 430, height: 900 } });

await page.goto(BASE_URL, { waitUntil: "networkidle" });
await page.click("text=J'ai déjà un compte");
await page.waitForSelector("form");

const inputs = page.locator("form input");
await inputs.nth(0).fill(email);
await inputs.nth(1).fill(password);
await page.click('form button[type="submit"]');
await page.waitForSelector("text=Flotte", { timeout: 15000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT_DIR}/dispatcher.png`, fullPage: true });
console.log("saved dispatcher.png");

await page.getByRole("tab", { name: "Qualité" }).click();
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT_DIR}/quality.png`, fullPage: true });
console.log("saved quality.png");

const certButton = page.locator("button:has-text('Certificat')").first();
await certButton.click();
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT_DIR}/certificate.png`, fullPage: true });
console.log("saved certificate.png");

await page.locator("text=← Retour").click();
await page.getByRole("tab", { name: "Chauffeur" }).click();
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT_DIR}/driver.png`, fullPage: true });
console.log("saved driver.png");

await browser.close();
