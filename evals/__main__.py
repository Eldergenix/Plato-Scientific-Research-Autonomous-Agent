"""``python -m evals`` shim — same entry point as ``python -m evals.runner``."""
from __future__ import annotations

from evals.runner import main


if __name__ == "__main__":
    main()
