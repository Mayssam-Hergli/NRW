import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// globals:false in vitest.config.ts means testing-library's automatic
// afterEach(cleanup) registration (which relies on detecting a global
// test framework) doesn't fire on its own -- without this, DOM from one
// test's render() leaks into the next, and multi-render tests in the same
// file see duplicate elements.
afterEach(() => {
  cleanup();
});

// jsdom has no layout/media-query engine -- matchMedia isn't implemented at
// all, so anything that calls it (none of our own code does today, but a
// dependency might) needs a stub to avoid throwing in tests.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
