# Quarkdown rendering

> After a successful paper stage, the dashboard renders the paper into
> four parallel HTML+PDF artifacts using the [Quarkdown](https://github.com/iamgio/quarkdown)
> CLI: a paged book, a slide deck, a docs site, and a one-pager. The
> existing LaTeX → `main.pdf` pipeline (`plato/paper_agents/latex.py`)
> stays as-is for archival; Quarkdown is the hybrid web-native layer
> on top.

## Why hybrid

LaTeX gives us submission-grade PDFs but not browseable HTML, fast
preview, slides, or a docs site. Quarkdown reads Markdown with
inline directives and emits all four shapes from the same source.
Rather than replace LaTeX (which the paper graph already produces),
we render Quarkdown as a post-stage hook — both artifacts coexist
under `<project>/paper/`.

## License

The Quarkdown CLI is distributed under **AGPL-3.0**. Plato invokes
it as an arms-length subprocess (`quarkdown c <input> -o <out>` via
`asyncio.create_subprocess_exec`, no shared address space, no linking
against Quarkdown sources). The standard FOSS reading of "mere
aggregation" applies: the AGPL covers the binary itself, not Plato's
process that calls it. Plato remains GPLv3.

If you ship the CLI bundled inside a derived distribution you must
satisfy AGPL-3.0 separately — that's on the distributor, not on
Plato.

## Architecture

```
plato/paper_agents/paper_node.py
        │
        ▼  state["paper"][...]
plato/paper_agents/slide_outline_node.py
        │
        ▼  paper/slide_outline.md (via ScopedWriter / SLIDE_OUTLINE_SCOPE)
        │
        ▼  paper/paper.md  ← (or input_files/results.md fallback)
        │
run_manager._post_paper_render()       (detached task, post-supervisor)
        │
        ▼
render/pipeline.render_all_artifacts()
        │
        ├──▶ transformer.to_qd_paper   ──▶ paged/paper.qd
        ├──▶ transformer.to_qd_plain   ──▶ plain/paper.qd
        ├──▶ transformer.to_qd_docs    ──▶ docs/paper.qd
        └──▶ transformer.to_qd_slides  ──▶ slides/slides.qd
                                              │
                                              ▼
                            render/quarkdown.render_qd()
                            (asyncio.create_subprocess_exec —
                             argv list, never a shell string)
                                              │
                                              ▼
                            quarkdown c <input> -o <out_dir> \
                                --strict --timeout <s> \
                                --pdf --pdf-no-sandbox
                                              │
                                              ▼
                            <doctype>/{paper,slides}.{html,pdf}
```

## Output paths

All artifacts land under `<project_dir>/paper/quarkdown/`:

```
<project>/paper/quarkdown/
├── paged/
│   ├── paper.qd
│   ├── paper.html
│   └── paper.pdf
├── plain/
│   ├── paper.qd
│   ├── paper.html
│   └── paper.pdf
├── docs/
│   ├── paper.qd
│   ├── paper.html
│   └── paper.pdf
└── slides/
    ├── slides.qd
    ├── slides.html
    └── slides.pdf
```

The supervisor publishes the four (or three, when slides are absent)
buckets as a single `render.qd.completed` event whose `artifacts`
map is keyed by doctype — see [`sse-events.md`](sse-events.md).

## Doctypes

| Doctype | What it is | When to use |
|---|---|---|
| `paged` | Multi-page book layout — paginated, with TOC, page numbers, figure captions. | The default "research paper" view. Closest analogue to `main.pdf`. |
| `slides` | Reveal-style presentation. Sourced from `slide_outline.md` (the dedicated slide_outline node), not from the paper body. | A talk-grade deck for the same project. |
| `docs` | Knowledge-base layout — sidebar navigation, fixed header, search-friendly. | Sharing the paper as a reading-doc URL. |
| `plain` | Single-flow one-pager. No pagination, no nav. | Quick previews; embedding in the dashboard's PaperPreview. |

`slides` is the only doctype that reads from a different source
(`paper/slide_outline.md`). The other three all consume
`paper/paper.md` (or `input_files/results.md` as the
backwards-compatible fallback when the paper graph hasn't yet been
updated to publish a single canonical Markdown).

## Slides — when they're rendered

The slide deck is only produced when `paper/slide_outline.md` exists
and is non-empty. That file is written by `slide_outline_node`, which
runs once at the end of the paper revision loop. A paper run that
fails before reaching that node won't have an outline and the slides
bucket is silently skipped (logged at INFO, not WARN — absence is
not an error).

## SSE events

The render emits five event kinds on the per-run channel:

- `render.qd.started`
- `render.qd.completed` (carries an `artifacts` dict)
- `render.qd.skipped` (when `paper_md` was empty)
- `render.qd.failed` (orchestrator-level error only)

Per-doctype subprocess failures don't fire `render.qd.failed`; they
land in `render.qd.completed` with `artifacts[doctype].returncode !=
0` and a per-doctype `stderr` map. See
[`sse-events.md#render`](sse-events.md#render) for the full payload
schemas.

## Customization

`DocMeta` (`render/transformer.py`) is the single source of truth
for the per-document header that lands at the top of every `.qd`
file:

```python
@dataclass
class DocMeta:
    name: str       # → .docname
    author: str     # → .docauthor
    lang: str = "en"
    layout: str = "default"
    theme: str | None = None
```

Override sites:

- **Per project:** the supervisor passes `meta=DocMeta(name=project.name,
  author=project.user_id or $USER)` from `_post_paper_render`. Anything
  the `Project` model carries flows through — change the project name
  via the `/projects/{pid}` PUT endpoint and the next render picks it up.
- **Per doctype:** edit the `to_qd_*` functions in `transformer.py`.
  They each emit a slightly different `.qd` header (e.g. `to_qd_slides`
  flips `doctype` to `slides` and bumps font sizes).
- **Theme:** unset by default — Quarkdown uses its built-in default.
  Set `DocMeta.theme = "dark"` (or any name the Quarkdown release
  ships with) and it lands in every doctype's header.

## Failure modes

| What happens | What the user sees |
|---|---|
| `quarkdown` binary not on `$PATH` | `render.qd.failed` with the FileNotFoundError message. |
| One doctype subprocess hangs past `--timeout` | `RuntimeError("Quarkdown render timed out")` for that doctype only; `_safe_render` swallows it; `render.qd.completed` fires with `artifacts[doctype].returncode == -1` and the exception text in the `stderr` map. |
| `paper_md` is empty | `render.qd.skipped`, no artifacts. The paper run's status is unaffected. |
| Slide outline missing | Slides bucket silently absent from the `artifacts` map. The other three doctypes still ship. |
| One doctype fails (e.g. malformed `.qd`) | The other three render normally. Failed doctype shows non-zero `returncode` and a `stderr` snippet. |
| Headless-chrome PDF crashes | HTML still lands; PDF path is `null`. Frontend disables the "Open PDF" button for that doctype. |

A render failure must never poison the run's success status — the
paper stage is reported succeeded the moment the supervisor exits,
which happens before the render starts. The frontend tracks render
state separately via the `render.qd.*` events.

## Local dev

The Quarkdown CLI is not on PyPI; install it with the upstream
script from [iamgio/quarkdown](https://github.com/iamgio/quarkdown):

```bash
# From the project root:
curl -fsSL https://raw.githubusercontent.com/iamgio/quarkdown/main/install.sh | sh

# Verify:
quarkdown --version
```

CI pins the binary by sha256 (see `.github/workflows/` for the
exact pin) so a malicious upstream replacement is caught at install
time. Local devs can skip the verify step at their own risk; the
backend's render failures will degrade to `render.qd.failed`
events, not data corruption.

For a containerized dev environment, the public-demo image
(`dashboard/spaces/Dockerfile`) installs the CLI in its build stage —
mounting that image is the path-of-least-resistance.
