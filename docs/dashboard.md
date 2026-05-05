# Self-hosted dashboard

The Plato dashboard is a multi-tenant web app that wraps the agent runtime
in a FastAPI backend and a Next.js 15 frontend. It supersedes the legacy
Streamlit GUI documented at [app.md](app.md) and is the recommended way to
run Plato locally for any non-trivial workflow.

## What you get

* Multi-stage UI for the **Planner → Research → Code → Results → Paper**
  pipeline with live SSE event streams for every stage.
* Multi-tenant project namespacing — each user gets an isolated project
  tree with cross-tenant reads/writes 403'd by both the router layer and
  the `ProjectStore` itself.
* Per-project **cost caps** with server-side enforcement (the worker
  refuses to start a stage that would exceed the cap).
* **Approval gates** between stages, a key vault that encrypts API keys
  at rest with Fernet, an SBOM/license-audit panel, and a citation graph
  view fed by the retrieval orchestrator.
* Real-time **agent swimlane** visualization driven by `node.entered` /
  `node.exited` events emitted by the LangGraph supervisor.

## Install

```bash
pip install "plato[dashboard]"
```

The `[dashboard]` extra pulls in FastAPI, uvicorn, arq, redis, and the
Pydantic settings stack the gateway needs.

## Run locally

```bash
plato dashboard
```

This boots the FastAPI gateway on `http://127.0.0.1:7878` and serves the
prebuilt static frontend from the same origin. Set `PLATO_AUTH=enabled`
and `PLATO_USE_FAKEREDIS=false` to point at a real Redis if you want
multi-worker SSE fan-out.

For the full deploy story (Docker, HuggingFace Spaces, Railway, GitHub
Pages), see [docker.md](docker.md) and the dashboard README in the repo
root.
