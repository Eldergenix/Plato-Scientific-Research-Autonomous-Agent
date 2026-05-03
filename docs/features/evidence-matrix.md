# Claim → Evidence Matrix

> R5. Atomic claim extraction from retrieved sources, paired with
> claim-to-source linking that the reviewer panel uses to flag
> unsupported sentences in the drafted paper.

The matrix turns "we cited 12 papers" into "of the 30 atomic claims
this draft makes, 27 trace to a supporting passage in a cited
paper" — a real grounding metric, not just a citation count.

## Data model

Three Pydantic models in `plato/state/models.py`:

```python
class Claim(BaseModel):
    id: str
    text: str  # bounded at 8 KiB (iter 6)
    source_id: str | None
    quote_span: tuple[int, int] | None  # char offsets into source.abstract
    section: str | None  # "abstract" | "results" | etc.

class EvidenceLink(BaseModel):
    claim_id: str
    source_id: str
    support: Literal["supports", "refutes", "neutral", "unclear"]
    strength: Literal["weak", "moderate", "strong"]
    quote_span: tuple[int, int] | None
```

## Pipeline

```
literature_summary
   ↓
claim_extractor          # plato/langgraph_agents/claim_extractor.py
   ↓ (writes state["claims"])
evidence_matrix_node     # plato/paper_agents/evidence_matrix_node.py
   ↓ (writes state["evidence_links"] + evidence_matrix.jsonl)
reviewer_panel_fanout
```

`claim_extractor` is an LLM-driven node that asks the model to
emit one Claim per atomic factual statement in each retrieved
source's abstract, with the supporting span. Output land in
`state["claims"]`.

`evidence_matrix_node` then asks the LLM to classify support
between every claim drafted by Plato and every claim extracted
from sources. The `support` axis is one of supports / refutes /
neutral / unclear.

## Persistence

`evidence_matrix.jsonl` is streamed line-by-line into
`<project_dir>/runs/<run_id>/`. Each line is either a Claim row
(presence of `text` + `id`) or an EvidenceLink row (`support` +
`claim_id`). The dashboard's evidence-matrix table walks the file
and groups claims by their support links.

When a SQL `Store` is active (`state["store"]`), claims and links
are also persisted via `Store.add_claim` / `Store.add_evidence_link`.

## Drafting consumption (iter 5)

The four section prompts (introduction / methods / results /
conclusions) call `build_evidence_pack(state)` which selects the
top-20 most-supported claims by `EvidenceLink` count and wraps
them in `<external kind="evidence-pack">` markers (R12). The
LLM is instructed to ground its writing in those claims.

## Reviewer-panel consumption

`unsupported_claim_rate = unsupported_claims / total_claims` is
computed by `evidence_matrix_node` and stored on
`state["unsupported_claim_rate"]`. The reviewer panel reads this
to gate the redraft loop — if the rate exceeds a threshold,
methodology-axis severity rises.

## See also

- `tests/unit/test_claim_extractor.py` + `test_evidence_matrix.py`
  for happy-path + edge-case coverage.
- `dashboard/frontend/src/components/manifest/evidence-matrix-table.tsx`
  for the rendered claims × sources table.
