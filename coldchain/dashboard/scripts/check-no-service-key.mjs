// Runs after `vite build`. Scans every file in dist/ for anything that
// looks like a Supabase service-role credential, and fails the build hard
// if it finds one. This is the one credential that bypasses RLS entirely
// (see infra/rls.sql) -- it must never reach a browser, so this check runs
// on the actual built output, not just source, to catch it being pulled in
// transitively (an errant import, a copied .env, a debug console.log).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";

const distDir = join(import.meta.dirname, "..", "dist");

// New-format Supabase secret keys start with this prefix. Also flag the
// literal env var name and the legacy "service_role" JWT claim, in case
// someone pastes a legacy-format key or a raw claim instead.
const FORBIDDEN_PATTERNS = [/sb_secret_[A-Za-z0-9_-]+/, /SUPABASE_SERVICE_KEY/, /"role":"service_role"/];

const SCANNABLE_EXT = new Set([".js", ".mjs", ".cjs", ".css", ".html", ".map", ".json", ".txt"]);

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      walk(full, files);
    } else if (SCANNABLE_EXT.has(extname(full))) {
      files.push(full);
    }
  }
  return files;
}

let found = false;
let files;
try {
  files = walk(distDir);
} catch {
  console.error(`dist/ not found at ${distDir} -- did \`vite build\` run first?`);
  process.exit(1);
}

for (const file of files) {
  const content = readFileSync(file, "utf-8");
  for (const pattern of FORBIDDEN_PATTERNS) {
    if (pattern.test(content)) {
      console.error(`Found forbidden pattern ${pattern} in ${file}`);
      found = true;
    }
  }
}

if (found) {
  console.error(
    "\nBuild output contains what looks like a Supabase service-role credential. " +
      "Refusing to ship this bundle -- see infra/rls.sql and README's env var table.",
  );
  process.exit(1);
}

console.log(`Scanned ${files.length} file(s) in dist/ -- no service-role key found.`);
