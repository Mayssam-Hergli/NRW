import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { createClient } from '@supabase/supabase-js';
import { chromium } from 'playwright-core';

const env = Object.fromEntries(readFileSync(new URL('../../.env', import.meta.url), 'utf8').split(/\r?\n/).filter(line => line.includes('=') && !line.startsWith('#')).map(line => { const i = line.indexOf('='); return [line.slice(0, i), line.slice(i + 1)]; }));
const admin = createClient(env.SUPABASE_URL, env.SUPABASE_SECRET_KEY, { auth: { persistSession: false, autoRefreshToken: false } });
const email = `login-check-${randomUUID()}@vallum-test.com`;
const password = randomUUID() + 'Aa9!';
let userId;
let browser;
try {
  const { data, error } = await admin.auth.admin.createUser({ email, password, email_confirm: true, user_metadata: { role: 'dispatcher', locale: 'fr', display_name: 'Login validation' } });
  if (error) throw error;
  userId = data.user.id;
  browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:5173/NRW/');
  await page.getByRole('button', { name: 'Connexion', exact: true }).click();
  await page.locator('input[type=email]').fill(email);
  await page.locator('input[type=password]').fill(password);
  await page.locator('button[type=submit]').click();
  await page.getByRole('tab').first().waitFor({ timeout: 20000 });
  await page.reload();
  await page.getByRole('tab').first().waitFor({ timeout: 20000 });
  const result = await admin.from('profiles').select('role,locale').eq('id', userId).single();
  if (result.error || result.data.role !== 'dispatcher') throw new Error('Profile recovery failed');
  console.log('PASS: real browser login, missing profile recovery, and session persistence after reload.');
} finally {
  await browser?.close();
  if (userId) {
    const { error } = await admin.auth.admin.deleteUser(userId);
    if (error) throw error;
    console.log('Temporary validation user removed.');
  }
}
