// Static scan, not a DOM test: jsdom doesn't evaluate CSS well enough to
// meaningfully assert "this renders mirrored under RTL", so this instead
// enforces the actual rule Arabic support depends on -- no physical
// left/right CSS property or value appears anywhere in source, only
// logical ones (margin-inline-start, not margin-left).
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)));

const SCANNABLE_EXT = new Set([".ts", ".tsx", ".css"]);
const EXCLUDE_DIRS = new Set(["generated"]);

// Word-boundary so this doesn't false-positive on e.g. "margin-inline-start"
// (which correctly contains neither "margin-left" nor "margin-right") or
// on unrelated words like "align-items".
const FORBIDDEN_PATTERNS: RegExp[] = [
  /margin-left/,
  /margin-right/,
  /padding-left/,
  /padding-right/,
  /\btext-align\s*:\s*['"]?left/,
  /\btext-align\s*:\s*['"]?right/,
  /\bleft\s*:\s*['"]?\d/, // inline style `left: ...` (position) -- use insetInlineStart
  /\bright\s*:\s*['"]?\d/,
];

function walk(dir: string, files: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (EXCLUDE_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      walk(full, files);
    } else if (SCANNABLE_EXT.has(full.slice(full.lastIndexOf(".")))) {
      files.push(full);
    }
  }
  return files;
}

describe("RTL: no physical left/right CSS", () => {
  it("no source file under src/ uses margin-left/right, padding-left/right, or text-align left/right", () => {
    const violations: string[] = [];
    for (const file of walk(SRC_DIR)) {
      if (file.endsWith(".test.ts") || file.endsWith(".test.tsx")) continue;
      const content = readFileSync(file, "utf-8");
      for (const pattern of FORBIDDEN_PATTERNS) {
        if (pattern.test(content)) {
          violations.push(`${file}: matches ${pattern}`);
        }
      }
    }
    expect(violations, violations.join("\n")).toEqual([]);
  });
});
