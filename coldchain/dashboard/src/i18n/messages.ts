// Typed wrapper around src/generated/messages.json (the one source of
// truth is shared/messages.py -- see scripts/export_messages.py). This
// file carries logic only, never string data: the render() port below
// must behave identically to shared/messages.py::render(), but the actual
// copy always comes from the generated JSON.
import raw from "../generated/messages.json";
import type { FaultCause, Locale, Severity } from "../lib/types";

export type Audience = "driver" | "dispatcher" | "report";

interface MessagesData {
  locales: Locale[];
  defaultLocale: Locale;
  audiences: Audience[];
  driverMaxChars: number;
  bannedDriverJargon: string[];
  severityLabel: Record<Severity, Record<Locale, string>>;
  safeNowClause: Record<Locale, string>;
  countdownClause: Record<Locale, string>;
  causeCopy: Record<FaultCause, Record<Audience, Record<Locale, string>>>;
  allCauses: FaultCause[];
  allSeverities: Severity[];
}

export const messages = raw as unknown as MessagesData;

export const LOCALES = messages.locales;
export const DEFAULT_LOCALE = messages.defaultLocale;
export const DRIVER_MAX_CHARS = messages.driverMaxChars;

export function isRtl(locale: Locale): boolean {
  return locale === "ar";
}

function safetyClause(severity: Severity): Record<Locale, string> {
  return severity === "watch" ? messages.safeNowClause : messages.countdownClause;
}

/** {name} and {name:.Nf} placeholders only -- the full set shared/messages.py
 * templates actually use. Throws on a placeholder the caller didn't supply,
 * matching render()'s KeyError-on-missing behaviour, rather than silently
 * emitting a half-filled sentence. */
function formatTemplate(template: string, values: Record<string, unknown>): string {
  return template.replace(/\{(\w+)(?::\.(\d+)f)?\}/g, (_match, name: string, precision?: string) => {
    if (!(name in values) || values[name] === undefined) {
      throw new Error(`missing placeholder {${name}} rendering template: ${template}`);
    }
    const value = values[name];
    if (precision !== undefined) {
      return Number(value).toFixed(Number(precision));
    }
    return String(value);
  });
}

export interface RenderOptions {
  cause: FaultCause;
  severity: Severity;
  audience: Audience;
  locale: Locale;
  evidence?: Record<string, number>;
  ctx?: Record<string, unknown>;
}

/** Port of shared/messages.py::render(). evidence and ctx are merged (ctx
 * wins on collision) into the named placeholders the cause's template
 * uses; severity_label is filled in automatically unless overridden. */
export function render({ cause, severity, audience, locale, evidence, ctx }: RenderOptions): string {
  if (!LOCALES.includes(locale)) {
    throw new Error(`unknown locale: ${locale}`);
  }
  if (!messages.audiences.includes(audience)) {
    throw new Error(`unknown audience: ${audience}`);
  }
  const causeEntry = messages.causeCopy[cause];
  if (!causeEntry) {
    throw new Error(`no message copy for cause: ${cause}`);
  }

  const merged: Record<string, unknown> = {
    ...(evidence ?? {}),
    ...(ctx ?? {}),
  };
  if (merged.severity_label === undefined) {
    merged.severity_label = messages.severityLabel[severity][locale];
  }

  let template: string;
  if (audience === "driver") {
    const instruction = causeEntry.driver[locale];
    const clause = safetyClause(severity)[locale];
    template = `${instruction} ${clause}`;
  } else {
    template = causeEntry[audience][locale];
  }

  return formatTemplate(template, merged);
}

/** render(), but falls back to `fallback` instead of throwing when the
 * evidence/ctx a caller has on hand doesn't cover every placeholder a
 * cause's template needs (evidence shape varies by which model raised the
 * alert). Every call site has a natural fallback already on hand: the
 * AlertRecord's own stored `message` field, rendered once at issuance
 * time server-side. */
export function renderSafe(options: RenderOptions, fallback: string): string {
  try {
    return render(options);
  } catch {
    return fallback;
  }
}
