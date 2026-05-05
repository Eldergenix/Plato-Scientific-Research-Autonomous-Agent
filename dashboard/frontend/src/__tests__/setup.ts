import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// next/font/google returns a font object at import time. In Vitest there's
// no Next compiler to resolve it, so stub a minimal identity so importing
// any component that uses it doesn't blow up.
vi.mock("next/font/google", () => {
  const fontFactory = () => ({
    className: "mock-font",
    style: { fontFamily: "mock-font" },
    variable: "--font-mock",
  });
  return new Proxy(
    {},
    {
      get: () => fontFactory,
    },
  );
});

// jsdom doesn't ship matchMedia. Components that read it (theme toggles,
// motion-reduce checks) crash without this stub.
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

// Stub the observers Radix and other libs poke at on mount.
class MockIntersectionObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = vi.fn(() => []);
  root = null;
  rootMargin = "";
  thresholds = [];
}

class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

if (typeof window !== "undefined") {
  if (!window.IntersectionObserver) {
    window.IntersectionObserver =
      MockIntersectionObserver as unknown as typeof IntersectionObserver;
  }
  if (!window.ResizeObserver) {
    window.ResizeObserver =
      MockResizeObserver as unknown as typeof ResizeObserver;
  }
}
