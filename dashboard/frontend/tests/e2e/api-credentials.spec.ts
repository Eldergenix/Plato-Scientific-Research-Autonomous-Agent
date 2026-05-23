import { expect, test } from "@playwright/test";
import { api } from "../../src/lib/api";

const rawProject = {
  id: "project-1",
  name: "Credentialed project",
  created_at: "2026-05-19T12:00:00.000Z",
  updated_at: "2026-05-19T12:00:00.000Z",
  journal: "NONE",
  stages: {
    data: { id: "data", label: "Data", status: "empty" },
    idea: { id: "idea", label: "Idea", status: "empty" },
    literature: { id: "literature", label: "Literature", status: "empty" },
    method: { id: "method", label: "Method", status: "empty" },
    results: { id: "results", label: "Results", status: "empty" },
    paper: { id: "paper", label: "Paper", status: "empty" },
    referee: { id: "referee", label: "Referee", status: "empty" },
  },
  active_run: null,
  total_tokens: 0,
  total_cost_cents: 0,
  user_id: "alice",
  cost_caps: null,
  approvals: null,
};

test.describe("frontend API credentials", () => {
  test("core JSON requests include cookies for split self-hosted deployments", async () => {
    const previousFetch = globalThis.fetch;
    const requests: RequestInit[] = [];
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(init ?? {});
      return new Response(JSON.stringify([rawProject]), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;

    try {
      await api.listProjects();
    } finally {
      globalThis.fetch = previousFetch;
    }

    expect(requests[0]?.credentials).toBe("include");
  });

  test("paper artifact probes include cookies for split self-hosted deployments", async () => {
    const previousFetch = globalThis.fetch;
    const requests: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ input, init });
      if (init?.method === "HEAD") {
        return new Response(null, { status: 404 });
      }
      return new Response("\\section{Intro}", {
        status: 200,
        headers: { "content-type": "text/plain" },
      });
    }) as typeof fetch;

    try {
      await api.getPaperArtifacts("project-1");
    } finally {
      globalThis.fetch = previousFetch;
    }

    expect(requests).toHaveLength(3);
    expect(requests.map((request) => request.init?.credentials)).toEqual([
      "include",
      "include",
      "include",
    ]);
    expect(String(requests[0]?.input)).toContain("/projects/project-1/files/paper/main.pdf");
    expect(String(requests[1]?.input)).toContain(
      "/projects/project-1/files/paper/submission_package.zip",
    );
    expect(String(requests[2]?.input)).toContain("/projects/project-1/files/paper/main.tex");
  });

  test("run event streams include cookies for split self-hosted deployments", () => {
    const previousEventSource = globalThis.EventSource;
    const instances: Array<{ url: string | URL; init?: EventSourceInit }> = [];

    class StubEventSource {
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;

      constructor(url: string | URL, init?: EventSourceInit) {
        instances.push({ url, init });
      }

      close() {
        return undefined;
      }
    }

    globalThis.EventSource = StubEventSource as unknown as typeof EventSource;
    try {
      const unsubscribe = api.subscribeRunEvents("project-1", "run-1", () => undefined);
      unsubscribe();
    } finally {
      globalThis.EventSource = previousEventSource;
    }

    expect(String(instances[0]?.url)).toContain("/projects/project-1/runs/run-1/events");
    expect(instances[0]?.init?.withCredentials).toBe(true);
  });
});
