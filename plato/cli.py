import sys
import argparse
from importlib.metadata import PackageNotFoundError, version


def _plato_version() -> str:
    """Resolve the installed Plato version, with a graceful dev fallback."""
    try:
        return version("plato")
    except PackageNotFoundError:
        return "0.0.0+dev"


def main():
    parser = argparse.ArgumentParser(prog="plato")
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {_plato_version()}",
        help="Print the installed Plato version and exit.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # `plato run` — legacy Streamlit GUI
    run_parser = subparsers.add_parser(
        "run",
        help="Run the legacy Plato Streamlit app (PlatoApp)",
    )
    run_parser.add_argument(
        "--validate-citations",
        action="store_true",
        help=(
            "After the pipeline finishes, walk the project directory and "
            "validate every citation. Writes validation_report.json next to "
            "the latest run."
        ),
    )
    run_parser.add_argument(
        "--project-dir",
        default=None,
        help=(
            "Project directory to validate when --validate-citations is set. "
            "Required if PlatoApp can't be imported but validation is requested."
        ),
    )

    # `plato validate` — standalone citation validation
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate every citation in a Plato project against Crossref/arXiv/URL liveness",
    )
    validate_parser.add_argument(
        "project_dir",
        help="Path to a Plato project directory.",
    )
    validate_parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Override the validation report output path.",
    )
    validate_parser.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="Minimum validation_rate to count as passing (default: 1.0).",
    )

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

    # `plato loop` — autonomous overnight research loop (Phase 4 / R10)
    loop = subparsers.add_parser(
        "loop",
        help="Run the autonomous overnight research loop on a project directory",
    )
    loop.add_argument(
        "--project-dir",
        required=True,
        help="Path to the Plato project directory",
    )
    loop.add_argument(
        "--hours",
        type=float,
        default=8.0,
        help="Wall-clock time budget in hours (default: 8.0)",
    )
    loop.add_argument(
        "--max-iters",
        type=int,
        default=None,
        help="Maximum loop iterations (default: unbounded)",
    )
    loop.add_argument(
        "--max-cost-usd",
        type=float,
        default=50.0,
        help="Cumulative manifest cost cap in USD (default: 50.0)",
    )
    loop.add_argument(
        "--branch-prefix",
        default="plato-runs",
        help="Tracking-branch prefix for git checkpoints (default: plato-runs)",
    )

    args = parser.parse_args()

    if args.command == "run":
        _run_app(args)
    elif args.command == "validate":
        from plato import cli_validate

        argv = [args.project_dir]
        if args.output is not None:
            argv.extend(["--output", args.output])
        if args.threshold != 1.0:
            argv.extend(["--threshold", str(args.threshold)])
        sys.exit(cli_validate.main(argv))
    elif args.command == "dashboard":
        _run_dashboard(args)
    elif args.command == "loop":
        _run_loop(args)
    else:
        # No subcommand → print help to stderr and exit non-zero so CI /
        # shell-script callers can distinguish "no command" from a
        # successful run.
        parser.print_help(sys.stderr)
        sys.exit(2)


def _run_app(args) -> None:
    """Run the legacy PlatoApp Streamlit pipeline, then optionally validate."""
    try:
        from plato_app.cli import run
    except ImportError:
        print("❌ PlatoApp not installed. Install with: pip install plato-app")
        sys.exit(1)

    run()

    if getattr(args, "validate_citations", False):
        if not args.project_dir:
            print(
                "❌ --validate-citations requires --project-dir <path> so the "
                "validator knows where the runs/ and paper/refs.bib live.",
                file=sys.stderr,
            )
            sys.exit(2)
        from plato import cli_validate

        rc = cli_validate.main([args.project_dir])
        if rc != 0:
            sys.exit(rc)


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


def _run_loop(args) -> None:
    """Boot the autonomous research loop (Phase 4 / R10).

    Uses lazy imports so ``plato --help`` works even when the heavy Plato
    dependency graph isn't fully importable in the current environment.
    """
    import asyncio
    import logging

    from plato.loop import ResearchLoop
    from plato.loop.research_loop import latest_manifest_score

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # Quiet down noisy third-party loggers — LangChain emits a lot of
    # INFO-level chatter on every chain step, and httpx/openai dump
    # every request at DEBUG. Cap them at WARNING so the user sees
    # only the loop progress plus genuine warnings/errors.
    for noisy in ("langchain", "langchain_core", "langgraph", "httpx", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def _plato_factory():
        # Lazy import: failing here is non-fatal — caller may pass a custom
        # factory in programmatic use.
        from plato import Plato  # noqa: WPS433 — intentional inline import

        return Plato(project_dir=args.project_dir)

    def _score_fn(_plato):
        return latest_manifest_score(args.project_dir)

    loop = ResearchLoop(
        project_dir=args.project_dir,
        max_iters=args.max_iters,
        time_budget_hours=args.hours,
        max_cost_usd=args.max_cost_usd,
        branch_prefix=args.branch_prefix,
    )
    summary = asyncio.run(loop.run(_plato_factory, _score_fn))
    print(
        "loop complete: "
        f"iterations={summary['iterations']} "
        f"kept={summary['kept']} discarded={summary['discarded']} "
        f"best={summary['best_composite']:.4f} "
        f"tsv={summary['tsv_path']}"
    )
