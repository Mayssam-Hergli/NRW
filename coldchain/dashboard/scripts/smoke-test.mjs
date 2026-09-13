// One-off manual verification script (not part of the test suite) --
// drives the built site with a real headless browser to check what a
// vitest jsdom test can't: real Supabase Auth sign-up, RLS-gated writes,
// and Realtime updates actually rendering.
import { chromium } from "playwright-core";

const BASE_URL = process.env.SMOKE_URL ?? "http://localhost:4173/NRW/";
// Supabase Auth's email validation rejects example.com/similar placeholder
// domains outright (confirmed while writing this script) -- needs an
// address on a real, deliverable domain even for a throwaway smoke test.
const email = process.env.SMOKE_EMAIL ?? `smoke-${Date.now()}@example.com`;
const password = "smoke-test-password-123";

const browser = await chromium.launch();
const page = await browser.newPage();

const consoleErrors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (err) => consoleErrors.push(String(err)));

console.log("Navigating to", BASE_URL);
await page.goto(BASE_URL, { waitUntil: "networkidle" });

await page.waitForSelector("form");
console.log("Auth form rendered.");

// Default form locale is fr: fields in DOM order are email, password,
// display name; selects in DOM order are role, account locale (the
// language-toggle select in the header is outside the <form>).
const inputs = page.locator("form input");
await inputs.nth(0).fill(email);
await inputs.nth(1).fill(password);
await inputs.nth(2).fill("Smoke Test Dispatcher");

const selects = page.locator("form select");
await selects.nth(0).selectOption("dispatcher");
await selects.nth(1).selectOption("fr");

await page.click('form button[type="submit"]');

try {
  await page.waitForSelector("text=Flotte", { timeout: 15000 });
  console.log("Signed up and landed on dispatcher view (saw 'Flotte').");
} catch {
  const bodyText = await page.textContent("body");
  console.log("Did not reach dispatcher view. Page text:", bodyText?.slice(0, 500));
}

// Give Realtime a moment, then check the fleet list picked up the seeded
// device and an active connection badge is showing.
await page.waitForTimeout(2000);
const bodyText = await page.textContent("body");
console.log("Contains seeded device id (TN-1234-GW)?", bodyText?.includes("TN-1234-GW"));
console.log("Contains a connection badge?", /En direct|Hors ligne|Connexion/.test(bodyText ?? ""));

if (consoleErrors.length > 0) {
  console.log("\nConsole errors observed:");
  for (const err of consoleErrors) console.log(" -", err);
} else {
  console.log("\nNo console errors observed.");
}

await browser.close();
