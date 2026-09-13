import { useEffect } from "react";
import { isRtl } from "../i18n/messages";
import type { Locale } from "./types";

/** Sets dir="rtl"/lang on <html> for the given locale. Pulled out of App.tsx
 * so it's unit-testable without mounting the whole auth-wired app. */
export function useDocumentLocale(locale: Locale): void {
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = isRtl(locale) ? "rtl" : "ltr";
  }, [locale]);
}
