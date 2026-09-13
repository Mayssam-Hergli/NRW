// Fails if regenerating src/generated/{messages,profiles}.json from their
// Python sources (already done by the prebuild step that runs just before
// this) produced a diff against what's committed -- i.e. someone changed
// shared/messages.py or shared/profiles.py and forgot to run
// `npm run gen:data` and commit the result. A plain content comparison
// against "the file before this script ran" would be vacuous here
// (prebuild already overwrote it), so this shells out to git and diffs
// against HEAD instead.
import { execFileSync } from "node:child_process";

// Relative to this script's own directory (dashboard/scripts/), not the
// git repo root, since that's the cwd git diff is invoked from below.
const generatedFiles = ["../src/generated/messages.json", "../src/generated/profiles.json"];

let diff;
try {
  diff = execFileSync("git", ["diff", "--stat", "HEAD", "--", ...generatedFiles], {
    cwd: import.meta.dirname,
    encoding: "utf-8",
  }).trim();
} catch (err) {
  console.warn(
    "Could not run `git diff` to check generated data sync (not a git checkout?). Skipping.",
    err.message,
  );
  process.exit(0);
}

if (diff !== "") {
  console.error(
    "Generated data changed after regenerating from shared/messages.py / shared/profiles.py:\n\n" +
      diff +
      "\n\nRun `npm run gen:data` and commit the result.",
  );
  process.exit(1);
}

console.log("Generated data is in sync with shared/messages.py and shared/profiles.py");
