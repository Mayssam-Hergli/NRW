// Sign-in path (not sign-up): avoids Supabase's confirmation-email rate
// limit entirely, tests session restore + profile fetch + realtime data
// against the real deployed build.
import { chromium } from "playwright-core";

const BASE_URL = process.env.SMOKE_URL ?? "http://localhost:4173/NRW/";
const email = process.env.SMOKE_EMAIL;
const password = process.env.SMOKE_PASSWORD;
if (!email || !password) {
  throw new Error("Set SMOKE_EMAIL and SMOKE_PASSWORD");
}

const browser = await chromium.launch();
const page = await browser.newPage();

const consoleMessages = [];
page.on("console", (msg) => consoleMessages.push(`[${msg.type()}] ${msg.text()}`));
page.on("pageerror", (err) => consoleMessages.push(`[pageerror] ${err}`));
page.on("requestfailed", (req) => consoleMessages.push(`[requestfailed] ${req.url()} ${req.failure()?.errorText}`));

console.log("Navigating to", BASE_URL);
await page.goto(BASE_URL, { waitUntil: "networkidle" });
await page.waitForSelector("form");

// Sign-in mode is the toggle target from the default sign-up mode.
await page.click("form button.secondary");
await page.waitForTimeout(200);

const inputs = page.locator("form input");
await inputs.nth(0).fill(email);
await inputs.nth(1).fill(password);
await page.click('form button[type="submit"]');

try {
  await page.waitForSelector("text=Flotte", { timeout: 15000 });
  console.log("PASS: signed in and reached dispatcher view.");
} catch {
  const bodyText = await page.textContent("body");
  console.log("FAIL: did not reach dispatcher view.");
  console.log("Page text:", bodyText?.slice(0, 800));
}

await page.waitForTimeout(2500);
const bodyText = await page.textContent("body");
console.log("Seeded device (TN-1234-GW) visible?", bodyText?.includes("TN-1234-GW"));
console.log("Connection badge visible?", /En direct|Hors ligne|Connexion/.test(bodyText ?? ""));
console.log("Alert text visible?", /affaibli|refroidissement|Froid/.test(bodyText ?? ""));

console.log("\n--- console/network log ---");
for (const line of consoleMessages) console.log(line);

await browser.close();
