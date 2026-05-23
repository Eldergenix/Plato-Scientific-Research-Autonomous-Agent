import { createServer } from "node:http";
import { spawn } from "node:child_process";

const frontendPort = process.env.PLAYWRIGHT_FRONTEND_PORT ?? "3201";
const backendPort = process.env.PLAYWRIGHT_BACKEND_PORT ?? "7878";
const backendOrigin = `http://127.0.0.1:${backendPort}`;
const nextScript = process.env.PLAYWRIGHT_NEXT_SCRIPT ?? "dev";
const childEnv = { ...process.env, PLATO_API_PROXY_TARGET: backendOrigin };
if (childEnv.NO_COLOR && childEnv.FORCE_COLOR) {
  delete childEnv.NO_COLOR;
  delete childEnv.FORCE_COLOR;
}

let ownsBackend = false;

const backend = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", backendOrigin);

  if (req.method === "GET" && url.pathname === "/api/v1/auth/me") {
    const userId = req.headers["x-plato-user"];
    res.writeHead(200, { "content-type": "application/json" });
    res.end(
      JSON.stringify({
        user_id: typeof userId === "string" && userId.length > 0 ? userId : null,
        auth_required: false,
      }),
    );
    return;
  }

  res.writeHead(404, { "content-type": "application/json" });
  res.end(JSON.stringify({ detail: "not found" }));
});

await new Promise((resolve, reject) => {
  backend.once("error", (error) => {
    if (error && error.code === "EADDRINUSE") {
      resolve();
      return;
    }
    reject(error);
  });
  backend.listen(Number(backendPort), "127.0.0.1", () => {
    ownsBackend = true;
    resolve();
  });
});

const child = spawn("npm", ["run", nextScript, "--", "--port", frontendPort], {
  stdio: "inherit",
  env: childEnv,
});

const shutdown = () => {
  child.kill("SIGTERM");
  if (ownsBackend) backend.close();
};

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

child.on("exit", (code, signal) => {
  const finish = () => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 0);
  };
  if (ownsBackend) {
    backend.close(finish);
  } else {
    finish();
  }
});
