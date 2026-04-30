#!/usr/bin/env python3
"""Detect import cycles in the ``plato/`` package.

Walks every ``*.py`` file under ``plato/``, parses the import statements
via ``ast``, and runs Tarjan's SCC algorithm on the resulting directed
import graph. Any strongly-connected component of size > 1, or any
self-import, exits with status 1 and prints the offending modules.

Used by ``.github/workflows/lint.yml`` (CI) but executable standalone:

    python .github/scripts/check_import_cycles.py
    python .github/scripts/check_import_cycles.py --root plato

Exit codes:
    0 — no cycles
    1 — cycles or self-imports detected
    2 — usage / IO error
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from collections import defaultdict


def module_name(path: str, root: str) -> str:
    """Convert a filesystem path under ``root`` into a Python module name."""
    rel = os.path.relpath(path, ".")
    if rel.endswith(".py"):
        rel = rel[:-3]
    parts = rel.split(os.sep)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def collect_imports(path: str, current_mod: str, package: str) -> set[str]:
    """Pull every absolute or relative ``plato.*`` import out of ``path``."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
    except (SyntaxError, UnicodeDecodeError) as exc:
        print(f"warning: could not parse {path}: {exc}", file=sys.stderr)
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(package):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base_parts = current_mod.split(".")
                if node.level > len(base_parts):
                    continue
                base = ".".join(base_parts[: len(base_parts) - node.level])
                target = f"{base}.{node.module}" if node.module else base
                if target.startswith(package):
                    found.add(target)
            elif node.module and node.module.startswith(package):
                found.add(node.module)
    return found


def find_cycles(graph: dict[str, set[str]], modules: set[str]) -> tuple[list[list[str]], list[str]]:
    """Tarjan's SCC. Returns (strongly_connected_components, self_imports)."""
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[list[str]] = []

    sys.setrecursionlimit(10000)

    def strongconnect(v: str) -> None:
        indices[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in indices:
                if w in graph or w in modules:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])
        if lowlink[v] == indices[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for node in set(graph.keys()) | modules:
        if node not in indices:
            strongconnect(node)

    cycles = [c for c in sccs if len(c) > 1]
    self_imports = [m for m in graph if m in graph[m]]
    return cycles, self_imports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default="plato",
        help="Top-level package directory to scan (default: plato)",
    )
    parser.add_argument(
        "--package",
        default=None,
        help="Python package prefix to filter imports by (default: same as --root)",
    )
    args = parser.parse_args()

    root = args.root
    package = args.package or root

    if not os.path.isdir(root):
        print(f"error: --root {root!r} is not a directory", file=sys.stderr)
        return 2

    graph: dict[str, set[str]] = defaultdict(set)
    modules: set[str] = set()
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            full = os.path.join(dirpath, fname)
            mod = module_name(full, root)
            if not mod:
                continue
            modules.add(mod)
            for imp in collect_imports(full, mod, package):
                graph[mod].add(imp)

    cycles, self_imports = find_cycles(graph, modules)

    if cycles or self_imports:
        print(f"Import cycles detected in {root}/:", file=sys.stderr)
        for c in cycles:
            print("  cycle: " + " -> ".join(sorted(c)), file=sys.stderr)
        for m in self_imports:
            print(f"  self-import: {m}", file=sys.stderr)
        return 1

    print(f"No import cycles detected across {len(modules)} modules in {root}/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
