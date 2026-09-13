// Proves realtime push specifically: signs in, waits a fixed window
// (during which the caller inserts a marker packet in a separate
// process), then checks whether the DOM updated without a page refresh --
// the thing vitest/jsdom cannot exercise at all.
import { chromium } from "playwright-core";

const BASE_URL = process.env.SMOKE_URL ?? "http://localhost:4173/NRW/";
const email = process.env.SMOKE_EMAIL;
const password = process.env.SMOKE_PASSWORD;
const marker = process.env.SMOKE_MARKER_TEMP;

const browser = await chromium.launch();
const page = await browser.newPage();

await page.goto(BASE_URL, { waitUntil: "networkidle" });
await page.click("form button.secondary");
await page.waitForTimeout(200);
const inputs = page.locator("form input");
await inputs.nth(0).fill(email);
await inputs.nth(1).fill(password);
await page.click('form button[type="submit"]');
await page.waitForSelector("text=Flotte", { timeout: 15000 });

const before = await page.textContent("body");
console.log("Marker present BEFORE insert?", before?.includes(marker));

console.log("Waiting 8s for the marker packet to be inserted externally...");
await page.waitForTimeout(15000);

const after = await page.textContent("body");
console.log("Marker present AFTER insert, no page refresh?", after?.includes(marker));

await browser.close();
