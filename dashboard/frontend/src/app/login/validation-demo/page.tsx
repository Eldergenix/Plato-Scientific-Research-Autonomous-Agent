"use client";

/**
 * Test fixture page for ``ValidationReportCard``.
 *
 * The integration commit owns ``/runs/[runId]/page.tsx`` where this card
 * will eventually live. Until then, this page mounts the card with
 * deterministic mock data so the F13 drilldown e2e suite has a stable
 * URL to drive. Nested under ``/login/`` because that's part of this
 * stream's owned scope.
 */

import * as React from "react";
import {
  ValidationReportCard,
  type ValidationReport,
} from "@/components/manifest/validation-report-card";

const MOCK_REPORT: ValidationReport = {
  // 7 of 12 verified → 0.583 → derived status "fail" (< 0.7).
  validation_rate: 7 / 12,
  total_references: 12,
  verified_references: 7,
  failures: [
    {
      source_id: "arxiv:2403.00001",
      reason: "missing_abstract",
      detail: "Abstract field empty after parse.",
      source_type: "arxiv",
      title: "Efficient Neural Network Pruning Using Iterative Sparse Retraining",
      verdict: "LIKELY",
      folder: "References/Likely Hallucinations",
      tags: ["needs-review", "likely-hallucination", "author-mismatch"],
      hallucination_assessment: {
        verdict: "LIKELY",
        explanation: "No dedicated page with matching title and authors was found.",
        link: null,
      },
      corrections: {
        bibtex:
          "@article{verified2024,\n  author = {Ada Lovelace and Grace Hopper},\n  title = {Verified replacement paper},\n  year = {2024}\n}",
      },
      notes: {
        markdown:
          "### Efficient Neural Network Pruning Using Iterative Sparse Retraining\n\n- Verdict: LIKELY\n- Folder: References/Likely Hallucinations\n- Tags: needs-review, likely-hallucination, author-mismatch",
        plain_text:
          "Efficient Neural Network Pruning Using Iterative Sparse Retraining\nVerdict: LIKELY\nFolder: References/Likely Hallucinations\nTags: needs-review, likely-hallucination, author-mismatch",
      },
    },
    {
      source_id: "arxiv:2403.00002",
      reason: "missing_abstract",
      detail: "Abstract field empty after parse.",
      source_type: "arxiv",
    },
    {
      source_id: "doi:10.1000/xyz123",
      reason: "fetch_timeout",
      detail: "Crossref returned 504 after 8 retries.",
      source_type: "crossref",
    },
    {
      source_id: "ss:abc-001",
      reason: "schema_mismatch",
      detail: "Field 'authors' has unexpected nested array shape.",
      source_type: "semantic_scholar",
    },
    {
      source_id: "ss:abc-002",
      reason: "schema_mismatch",
      detail: null,
      source_type: "semantic_scholar",
    },
  ],
};

export default function ValidationDemoPage() {
  return (
    <main className="min-h-screen bg-(--color-bg-page) p-6">
      <div className="mx-auto w-full max-w-[680px]">
        <ValidationReportCard report={MOCK_REPORT} defaultExpanded />
      </div>
    </main>
  );
}
