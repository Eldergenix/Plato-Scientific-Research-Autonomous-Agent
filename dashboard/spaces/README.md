---
title: Plato Dashboard
emoji: 💡
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: gpl-3.0
---

# Plato Dashboard

A Linear-themed web dashboard for [Plato](https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent) — a multi-agent scientific research assistant. **Demo mode** locks code-execution stages and caps spend at $0.50 per session, so the hosted demo is safe to share publicly.

## Features

- Run the four read-only Plato stages — **Data**, **Idea**, **Method**, **Literature** — straight from the browser
- Linear-inspired UI with command palette, log streaming, and real-time progress
- Bring-your-own keys for OpenAI / Anthropic / Google — no shared credentials
- Per-session spend cap ($0.50 by default) and idle timeout (30 min)
- Fully open-source under GPL-3.0

[Live demo](https://plato-production-9fea.up.railway.app) · [Repo](https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent)

## Setup — Bring Your Own Keys

By default the hosted demo runs in demo mode without any provider keys configured, which means runs will fail at the LLM-call step. To run real workloads against your own quota, add keys through your deployment provider's encrypted secrets:

| Secret name           | Provider  |
| --------------------- | --------- |
| `OPENAI_API_KEY`      | OpenAI    |
| `ANTHROPIC_API_KEY`   | Anthropic |
| `GOOGLE_API_KEY`      | Google    |

Restart the deployment after adding secrets so the runtime picks them up. You can also enter keys per-session through the in-app **Keys** dialog; they live only in your browser session and are never persisted by Plato.

## Running locally

If you'd rather run this on your own hardware (with full code-execution stages and no spend cap), use the production image instead:

```bash
git clone https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent.git
cd Plato-Scientific-Research-Autonomous-Agent
docker compose -f dashboard/compose.yaml up --build
# → http://localhost:7878
```

## Hosted demo limits

- **Demo mode is enforced.** Stages that execute generated code (data analysis, paper) are disabled.
- **$0.50 cap per session** — exceeded sessions are paused.
- **30-minute idle timeout** — long-running jobs may be killed.
- **One concurrent run per visitor.**

For unrestricted use, self-host. The Dockerfile is the same multi-stage build as the hosted demo, just with the full LaTeX toolchain and demo-mode off.
