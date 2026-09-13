import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useDocumentLocale } from "./useDocumentLocale";

afterEach(() => {
  document.documentElement.dir = "";
  document.documentElement.lang = "";
});

describe("useDocumentLocale", () => {
  it("sets dir=rtl for ar", () => {
    renderHook(() => useDocumentLocale("ar"));
    expect(document.documentElement.dir).toBe("rtl");
    expect(document.documentElement.lang).toBe("ar");
  });

  it("sets dir=ltr for fr and en", () => {
    renderHook(() => useDocumentLocale("fr"));
    expect(document.documentElement.dir).toBe("ltr");

    renderHook(() => useDocumentLocale("en"));
    expect(document.documentElement.dir).toBe("ltr");
  });
});
