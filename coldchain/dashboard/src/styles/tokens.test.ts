// jsdom has no real CSS engine -- it doesn't evaluate @media queries to
// decide which rules apply, so a DOM-level "render and check computed
// style under dark mode" test would not actually exercise anything (it
// would pass or fail independent of the CSS). This instead verifies the
// stylesheet's actual structure: every token defined on :root also has a
// dark-mode override in both the automatic (prefers-color-scheme) block
// and the explicit (data-theme="dark") block, so an explicit toggle also
// works and neither path can silently drift from the other.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "tokens.css"), "utf-8");

function tokensDefinedIn(block: string): string[] {
  const matches = block.matchAll(/(--[\w-]+)\s*:/g);
  return Array.from(matches, (m) => m[1]);
}

function extractBlock(source: string, selectorPattern: RegExp): string {
  const match = source.match(selectorPattern);
  if (!match) throw new Error(`selector not found: ${selectorPattern}`);
  const start = match.index! + match[0].length;
  let depth = 1;
  let i = start;
  while (depth > 0 && i < source.length) {
    if (source[i] === "{") depth++;
    if (source[i] === "}") depth--;
    i++;
  }
  return source.slice(start, i - 1);
}

describe("design tokens: dark mode parity", () => {
  const rootBlock = extractBlock(css, /:root\s*\{/);
  const rootTokens = tokensDefinedIn(rootBlock).sort();

  it(":root defines the exact token set from the spec", () => {
    expect(rootTokens).toEqual(
      [
        "--bg",
        "--panel",
        "--ink",
        "--muted",
        "--rule",
        "--primary",
        "--nominal",
        "--warn",
        "--signal",
        "--signal-text",
      ].sort(),
    );
  });

  it("prefers-color-scheme:dark block redefines every root token", () => {
    const mediaBlock = extractBlock(css, /@media \(prefers-color-scheme:\s*dark\)\s*\{/);
    const innerBlock = extractBlock(mediaBlock, /:root:not\(\[data-theme="light"\]\)\s*\{/);
    expect(tokensDefinedIn(innerBlock).sort()).toEqual(rootTokens);
  });

  it('[data-theme="dark"] block redefines every root token', () => {
    const block = extractBlock(css, /:root\[data-theme="dark"\]\s*\{/);
    expect(tokensDefinedIn(block).sort()).toEqual(rootTokens);
  });

  it("no token is only ever defined inside a media or data-theme block", () => {
    // Guards against the mistake the design-token spec explicitly calls
    // out: giving a color its only definition inside a conditional block.
    for (const token of rootTokens) {
      expect(rootBlock).toMatch(new RegExp(`${token}\\s*:`));
    }
  });
});
