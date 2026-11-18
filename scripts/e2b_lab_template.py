#!/usr/bin/env python3
"""Build (or rebuild) the ``plato-lab`` E2B template the research agents run in.

    pip install e2b==2.64.0
    E2B_API_KEY=... python scripts/e2b_lab_template.py
    E2B_API_KEY=... python scripts/e2b_lab_verify.py      # then verify every tool

The template definition lives in ``plato/scientist/workspace/lab.py``. The build ends with
smoke tests that load every preinstalled tool and library, so a broken install fails the
build instead of surfacing later in an agent's session. Only ``e2b`` is needed here, not
the scientist service's dependencies. The key is read from the environment and never
printed.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from pathlib import Path

_LAB = Path(__file__).resolve().parents[1] / "plato" / "scientist" / "workspace" / "lab.py"


def _load_lab():
    spec = importlib.util.spec_from_file_location("plato_ws_lab", _LAB)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    lab = _load_lab()
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=lab.TEMPLATE_NAME)
    ap.add_argument("--cpu", type=int, default=4, help="vCPUs of sandboxes from this template")
    ap.add_argument("--memory-mb", type=int, default=8192)
    ap.add_argument("--skip-cache", action="store_true", help="rebuild every layer")
    ap.add_argument("--dockerfile", action="store_true", help="print the Dockerfile and exit")
    args = ap.parse_args()

    from e2b import Template

    template = lab.lab_template()
    if args.dockerfile:
        print(Template.to_dockerfile(template))
        return 0
    if not os.environ.get("E2B_API_KEY"):
        print("E2B_API_KEY is not set", file=sys.stderr)
        return 2
    started = time.monotonic()
    for attempt in range(1, 4):
        try:
            info = Template.build_in_background(
                template,
                args.name,
                cpu_count=args.cpu,
                memory_mb=args.memory_mb,
                skip_cache=args.skip_cache,
            )
            break
        except Exception as exc:  # e.g. httpx.WriteError "channel closed" before any build exists
            import httpx

            if attempt == 3 or not isinstance(exc, httpx.TransportError):
                raise
            print(f"starting the build failed ({type(exc).__name__}); retrying", file=sys.stderr)
            time.sleep(10 * attempt)
    print(f"build {info.build_id} of template {info.template_id} started", flush=True)
    # Poll ourselves rather than through Template.build, so a slow status request (seen as an
    # httpx ReadTimeout) is retried instead of abandoning a build that is still running.
    offset, failures = 0, 0
    while True:
        try:
            st = Template.get_build_status(info, logs_offset=offset)
            failures = 0
        except Exception as exc:  # transport errors while polling are not build errors
            failures += 1
            if failures > 20:
                print(f"giving up polling after {failures} errors: {exc}", file=sys.stderr)
                return 1
            time.sleep(min(60, 5 * failures))
            continue
        for entry in st.log_entries:
            print(entry, flush=True)
        offset += len(st.log_entries)
        status = getattr(st.status, "value", st.status)
        if status == "ready":
            break
        if status == "error":
            print(f"build failed: {st.reason}", file=sys.stderr)
            return 1
        time.sleep(5)
    print(f"built {args.name} in {time.monotonic() - started:.0f}s: {info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
