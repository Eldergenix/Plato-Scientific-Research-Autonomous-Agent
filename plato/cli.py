import sys
import argparse


def main():
    parser = argparse.ArgumentParser(prog="plato")
    subparsers = parser.add_subparsers(dest="command")

    # `plato run` — legacy Streamlit GUI
    subparsers.add_parser("run", help="Run the legacy Plato Streamlit app (PlatoApp)")

    # `plato dashboard` — new Linear-themed web dashboard
    dash = subparsers.add_parser(
        "dashboard",
        help="Run the Plato web dashboard (Next.js + FastAPI)",
    )
    dash.add_argument("--host", default="127.0.0.1", help="API host")
    dash.add_argument("--port", type=int, default=7878, help="API port")
    dash.add_argument(
        "--demo",
        action="store_true",
        help="Boot in demo mode (locks code-execution stages, $-cap per session)",
    )
    dash.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't auto-open the dashboard in a browser",
    )

    args = parser.parse_args()

    if args.command == "run":
        try:
            from plato_app.cli import run
            run()
        except ImportError:
            print("❌ PlatoApp not installed. Install with: pip install plato-app")
            sys.exit(1)
    elif args.command == "dashboard":
        _run_dashboard(args)
    else:
        parser.print_help()


def _run_dashboard(args) -> None:
    """Boot the FastAPI gateway from the plato-dashboard package.

    The frontend is served either as static files (after `npm run build`)
    from the same uvicorn process, or developers can run `npm run dev` in
    `dashboard/frontend/` to get HMR.
    """
    import os
    import webbrowser

    if args.demo:
        os.environ["PLATO_DEMO_MODE"] = "enabled"
    os.environ.setdefault("PLATO_HOST", args.host)
    os.environ.setdefault("PLATO_PORT", str(args.port))

    try:
        from plato_dashboard.api.server import cli as run_api
    except ImportError:
        print(
            "❌ plato-dashboard not installed.\n"
            "   Install with: pip install \"plato[dashboard]\"\n"
            "   Or from source: pip install -e dashboard/backend"
        )
        sys.exit(1)

    if not args.no_browser:
        url = f"http://{args.host}:{args.port}"
        try:
            webbrowser.open_new_tab(url)
        except Exception:  # noqa: BLE001
            pass
        print(f"→ {url}")

    run_api()
