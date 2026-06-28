import { Container } from "@cloudflare/containers";

type Env = {
  PLATO_DASHBOARD: DurableObjectNamespace<PlatoDashboard>;
};

export class PlatoDashboard extends Container {
  defaultPort = 7860;
  sleepAfter = "10m";
  envVars = {
    PLATO_DEMO_MODE: "enabled",
    PLATO_AUTH: "disabled",
    PLATO_USE_FAKEREDIS: "true",
    NEXT_TELEMETRY_DISABLED: "1",
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.hostname !== "plato.eldergenix.com") {
      return new Response("Not Found", { status: 404 });
    }

    const id = env.PLATO_DASHBOARD.idFromName("plato-dashboard");
    const container = env.PLATO_DASHBOARD.get(id);
    return container.fetch(request);
  },
};
