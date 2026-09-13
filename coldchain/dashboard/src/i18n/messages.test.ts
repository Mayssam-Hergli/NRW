import { describe, expect, it } from "vitest";
import type { FaultCause, Locale, Severity } from "../lib/types";
import { DRIVER_MAX_CHARS, LOCALES, messages, render } from "./messages";

const AUDIENCES = messages.audiences;

describe("message catalogue parity", () => {
  it("every FaultCause from the Python enum has copy for every audience and locale", () => {
    expect(messages.allCauses.length).toBeGreaterThan(0);
    for (const cause of messages.allCauses) {
      const entry = messages.causeCopy[cause as FaultCause];
      expect(entry, `missing causeCopy entry for ${cause}`).toBeDefined();
      for (const audience of AUDIENCES) {
        const byLocale = entry[audience];
        expect(byLocale, `missing ${cause}/${audience}`).toBeDefined();
        for (const locale of LOCALES) {
          expect(byLocale[locale], `missing ${cause}/${audience}/${locale}`).toBeTruthy();
        }
      }
    }
  });

  it("every Severity from the Python enum has a label in every locale", () => {
    expect(messages.allSeverities.length).toBeGreaterThan(0);
    for (const severity of messages.allSeverities) {
      for (const locale of LOCALES) {
        expect(messages.severityLabel[severity as Severity][locale]).toBeTruthy();
      }
    }
  });
});

describe("driver message length", () => {
  const nonWatchSeverities: Severity[] = ["warning", "critical"];

  it("renders under DRIVER_MAX_CHARS for every cause, locale, and severity branch", () => {
    for (const cause of messages.allCauses as FaultCause[]) {
      for (const locale of LOCALES) {
        // "watch" uses the no-placeholder safe-now clause.
        const watchText = render({ cause, severity: "watch", audience: "driver", locale });
        expect(watchText.length, `${cause}/${locale}/watch: "${watchText}"`).toBeLessThanOrEqual(
          DRIVER_MAX_CHARS,
        );

        // warning/critical use the countdown clause, which has a
        // placeholder -- exercise it with a realistic two-digit minute
        // count, same as the Python test does.
        for (const severity of nonWatchSeverities) {
          const text = render({
            cause,
            severity,
            audience: "driver",
            locale,
            ctx: { eta_min: 38 },
          });
          expect(text.length, `${cause}/${locale}/${severity}: "${text}"`).toBeLessThanOrEqual(
            DRIVER_MAX_CHARS,
          );
        }
      }
    }
  });
});

describe("render() locale independence", () => {
  it("same cause and evidence render different strings per locale with identical placeholder values", () => {
    const evidence = { dev_pp: 22 };
    const locales: Locale[] = ["fr", "en", "ar"];
    const rendered = locales.map((locale) =>
      render({
        cause: "refrigerant_loss",
        severity: "warning",
        audience: "dispatcher",
        locale,
        evidence,
        ctx: { vehicle: "TN-1234", ambient_c: 34 },
      }),
    );
    // All different (three distinct languages)...
    expect(new Set(rendered).size).toBe(3);
    // ...but every one contains the same numeric placeholder values.
    for (const text of rendered) {
      expect(text).toContain("22");
    }
  });

  it("throws on a missing placeholder rather than emitting a half-filled sentence", () => {
    expect(() =>
      render({ cause: "refrigerant_loss", severity: "warning", audience: "dispatcher", locale: "fr" }),
    ).toThrow();
  });
});
