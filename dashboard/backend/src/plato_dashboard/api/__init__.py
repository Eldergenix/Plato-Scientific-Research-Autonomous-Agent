"""API package.

The citation-graph view router is mounted directly inside ``server.create_app``
so every entry point — `uvicorn server:app`, the CLI, and the test fixtures —
sees the same set of routes. The previous monkey-patch on `create_app` ran
*after* `server.py` had already created the module-level `app`, which meant
the citation-graph route was silently missing whenever uvicorn imported
``plato_dashboard.api.server:app`` directly.
"""

from __future__ import annotations
