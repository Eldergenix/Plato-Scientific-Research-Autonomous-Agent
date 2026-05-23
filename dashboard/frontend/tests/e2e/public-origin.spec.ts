import { expect, test } from "@playwright/test";
import {
  publicHost,
  publicOrigin,
  publicProto,
  publicRequestUrl,
} from "../../src/lib/public-origin";

function requestLike(headers: Record<string, string>, url = "http://internal.local/path?q=1") {
  return {
    headers: new Headers(headers),
    url,
  };
}

test.describe("public origin helpers", () => {
  test("prefer the request host over a spoofed forwarded host", () => {
    const request = requestLike({
      host: "discovering.app",
      "x-forwarded-host": "attacker.example",
      "x-forwarded-proto": "https",
    });

    expect(publicHost(request)).toBe("discovering.app");
    expect(publicOrigin(request)).toBe("https://discovering.app");
    expect(publicRequestUrl(request)).toBe("https://discovering.app/path?q=1");
  });

  test("fall back to a valid forwarded host when host is missing", () => {
    const request = requestLike({
      "x-forwarded-host": "plato-production-9fea.up.railway.app",
      "x-forwarded-proto": "https",
    });

    expect(publicOrigin(request)).toBe("https://plato-production-9fea.up.railway.app");
  });

  test("reject invalid forwarded host and proto values", () => {
    const request = requestLike({
      "x-forwarded-host": "evil.example/path",
      "x-forwarded-proto": "javascript",
    });

    expect(publicHost(request)).toBe("internal.local");
    expect(publicProto(request)).toBe("http");
    expect(publicOrigin(request)).toBe("http://internal.local");
  });

  test("allows a configured public origin to override proxy headers", () => {
    const previous = process.env.PLATO_PUBLIC_ORIGIN;
    process.env.PLATO_PUBLIC_ORIGIN = "https://discovering.app/";

    try {
      const request = requestLike({
        host: "internal.local",
        "x-forwarded-host": "attacker.example",
        "x-forwarded-proto": "http",
      });

      expect(publicOrigin(request)).toBe("https://discovering.app");
      expect(publicRequestUrl(request)).toBe("https://discovering.app/path?q=1");
    } finally {
      if (previous == null) {
        delete process.env.PLATO_PUBLIC_ORIGIN;
      } else {
        process.env.PLATO_PUBLIC_ORIGIN = previous;
      }
    }
  });
});
