#!/usr/bin/env python3
"""Build a deterministic arXiv source archive from the generated LaTeX paper."""

from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[2]
PREPRINT = ROOT / "preprint"
LATEX_SOURCE = PREPRINT / "latex" / "plato-bio.tex"
OUTPUT = PREPRINT / "arxiv" / "Plato-Bio-arXiv-source.zip"

FIGURE_PATTERN = re.compile(r"(\\includegraphics\[[^]]*]\{)([^}]+)(\})")


def add_bytes(archive: ZipFile, name: str, payload: bytes) -> None:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, payload)


def main() -> int:
    tex = LATEX_SOURCE.read_text(encoding="utf-8")
    assets: dict[str, Path] = {}

    def rewrite_figure(match: re.Match[str]) -> str:
        source = (LATEX_SOURCE.parent / match.group(2)).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Missing figure file: {source}")
        if not source.is_relative_to(PREPRINT.resolve()):
            raise RuntimeError(f"Figure path escapes the preprint directory: {source}")

        archive_name = f"figures/{source.name}"
        previous = assets.get(archive_name)
        if previous is not None and previous != source:
            raise RuntimeError(
                f"Figure basename collision for {archive_name}: {previous} and {source}"
            )
        assets[archive_name] = source
        return f"{match.group(1)}{archive_name}{match.group(3)}"

    arxiv_tex = FIGURE_PATTERN.sub(rewrite_figure, tex)
    if not assets:
        raise RuntimeError("No manuscript figures were found in the generated LaTeX source")
    arxiv_tex = arxiv_tex.replace(r"\graphicspath{{../figures/}}", r"\graphicspath{{figures/}}")
    if re.search(r"\\includegraphics\[[^]]*]\{\.\./", arxiv_tex):
        raise RuntimeError("The packaged TeX still contains a parent-relative figure path")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w") as archive:
        add_bytes(archive, "plato-bio.tex", arxiv_tex.encode("utf-8"))
        for archive_name, source in sorted(assets.items()):
            add_bytes(archive, archive_name, source.read_bytes())

    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
