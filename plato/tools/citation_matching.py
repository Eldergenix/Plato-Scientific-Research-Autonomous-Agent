"""Metadata matching, hallucination triage, and correction helpers."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from plato.state.models import Source


TITLE_MATCH_THRESHOLD = 0.75
AUTHOR_OVERLAP_THRESHOLD = 0.60
SUSPICIOUS_ISSUES = {
    "unverified",
    "author_overlap_below_threshold",
    "identifier_conflict",
    "url_verification_failed",
    "title_mismatch",
    "doi_conflict",
    "arxiv_conflict",
}


def normalize_doi(doi: str) -> str:
    s = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if s.lower().startswith(prefix):
            s = s[len(prefix) :]
            break
    return s.lower()


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def coerce_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    return [
        part.strip()
        for part in re.split(r"\s+and\s+|;\s*", str(value).replace("\n", " "))
        if part.strip()
    ]


def coerce_year(value: Any) -> int | None:
    match = re.search(r"\d{4}", str(value or ""))
    return int(match.group(0)) if match else None


def normalize_text(text: str) -> str:
    text = collapse_ws(text).lower()
    text = text.replace("pre-trained", "pretrained")
    return re.sub(r"[^a-z0-9]+", "", text)


def title_similarity(left: str, right: str) -> float:
    l_norm = normalize_text(left)
    r_norm = normalize_text(right)
    if not l_norm or not r_norm:
        return 0.0
    if l_norm == r_norm:
        return 1.0
    return SequenceMatcher(None, l_norm, r_norm).ratio()


def crossref_metadata(payload: dict[str, Any]) -> dict[str, Any] | None:
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    return crossref_work_metadata(message)


def crossref_work_metadata(work: dict[str, Any]) -> dict[str, Any]:
    titles = work.get("title") or []
    title = titles[0] if isinstance(titles, list) and titles else work.get("title")
    venue_titles = work.get("container-title") or [""]
    venue = venue_titles[0] if isinstance(venue_titles, list) else venue_titles
    authors = []
    for author in work.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = collapse_ws(
            " ".join(
                part
                for part in (
                    author.get("given"),
                    author.get("family"),
                )
                if part
            )
        )
        if name:
            authors.append(name)
    year = crossref_year(work)
    doi = work.get("DOI")
    return {
        "title": collapse_ws(str(title or "")),
        "authors": authors,
        "year": year,
        "venue": collapse_ws(str(venue or "")),
        "doi": normalize_doi(str(doi)) if doi else None,
        "url": work.get("URL") or (f"https://doi.org/{doi}" if doi else None),
    }


def crossref_year(work: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "published", "created"):
        parts = (
            work.get(key, {}).get("date-parts")
            if isinstance(work.get(key), dict)
            else None
        )
        if parts and isinstance(parts, list) and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


def compare_metadata(
    source: Source,
    metadata: dict[str, Any] | None,
    *,
    doi_resolved: bool,
    arxiv_resolved: bool,
    url_alive: bool | None,
    retracted: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if metadata is None and not (doi_resolved or arxiv_resolved):
        issues.append(
            {
                "type": "unverified",
                "detail": "Reference was not found by DOI, arXiv ID, URL, or Crossref title search.",
            }
        )
    if retracted:
        issues.append(
            {"type": "retracted", "detail": "Reference is marked as retracted."}
        )
    if url_alive is False:
        issues.append(
            {
                "type": "url_verification_failed",
                "detail": "Cited URL did not return a live 2xx/3xx response.",
            }
        )

    if metadata is None:
        return issues, warnings

    actual_title = str(metadata.get("title") or "")
    if source.title and actual_title:
        similarity = title_similarity(source.title, actual_title)
        if similarity < TITLE_MATCH_THRESHOLD:
            issues.append(
                {
                    "type": "title_mismatch",
                    "detail": f"Cited title does not match verified metadata (similarity={similarity:.2f}).",
                    "cited": source.title,
                    "actual": actual_title,
                }
            )

    actual_authors = [str(a) for a in metadata.get("authors") or [] if a]
    overlap = author_overlap(source.authors, actual_authors)
    if overlap is not None and overlap < AUTHOR_OVERLAP_THRESHOLD:
        issues.append(
            {
                "type": "author_overlap_below_threshold",
                "detail": f"Only {overlap:.0%} of cited authors match verified metadata.",
                "cited": source.authors,
                "actual": actual_authors,
                "author_overlap": overlap,
            }
        )

    source_year = parse_year(source.year)
    metadata_year = parse_year(metadata.get("year"))
    if source_year and metadata_year:
        diff = abs(source_year - metadata_year)
        if diff > 1:
            issues.append(
                {
                    "type": "year_mismatch",
                    "detail": f"Cited year {source_year} differs from verified year {metadata_year}.",
                    "cited": source_year,
                    "actual": metadata_year,
                }
            )
        elif diff == 1:
            warnings.append(
                {
                    "type": "year_off_by_one",
                    "detail": f"Cited year {source_year} is one year from verified year {metadata_year}.",
                }
            )

    if (
        source.doi
        and metadata.get("doi")
        and normalize_doi(source.doi) != metadata["doi"]
    ):
        issues.append(
            {
                "type": "doi_conflict",
                "detail": f"Cited DOI {source.doi} conflicts with verified DOI {metadata['doi']}.",
            }
        )
    if (
        source.arxiv_id
        and metadata.get("arxiv_id")
        and str(source.arxiv_id).lower() != str(metadata["arxiv_id"]).lower()
    ):
        issues.append(
            {
                "type": "arxiv_conflict",
                "detail": f"Cited arXiv ID {source.arxiv_id} conflicts with verified arXiv ID {metadata['arxiv_id']}.",
            }
        )
    return issues, warnings


def needs_hallucination_check(issues: list[dict[str, Any]]) -> bool:
    return any(issue.get("type") in SUSPICIOUS_ISSUES for issue in issues)


def normalize_assessment(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "verdict": "UNCERTAIN",
            "explanation": "Hallucination assessor returned an invalid response.",
            "link": None,
        }
    verdict = str(raw.get("verdict") or "UNCERTAIN").upper()
    if verdict not in {"LIKELY", "UNLIKELY", "UNCERTAIN"}:
        verdict = "UNCERTAIN"
    return {
        "verdict": verdict,
        "explanation": str(raw.get("explanation") or "").strip(),
        "link": raw.get("link"),
        "found_title": raw.get("found_title"),
        "found_authors": raw.get("found_authors"),
        "found_venue": raw.get("found_venue"),
        "found_year": raw.get("found_year"),
    }


def assessment_verdict(
    issues: list[dict[str, Any]],
    assessment: dict[str, Any] | None,
) -> str:
    if assessment:
        return str(assessment.get("verdict") or "UNCERTAIN").upper()
    return "UNLIKELY" if not issues else "UNCERTAIN"


def confidence_for(
    verdict: str,
    issues: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    assessment: dict[str, Any] | None,
) -> float:
    if assessment and assessment.get("link") and verdict in {"LIKELY", "UNLIKELY"}:
        return 0.99
    if verdict == "UNLIKELY" and not issues:
        return 0.98 if warnings else 1.0
    if verdict == "LIKELY":
        return 0.95
    return 0.5


def status_for(
    issues: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    verdict: str,
) -> str:
    if verdict == "LIKELY":
        return "hallucination"
    if issues:
        return (
            "unverified"
            if any(i.get("type") == "unverified" for i in issues)
            else "error"
        )
    return "warning" if warnings else "verified"


def reverify_llm_metadata(
    source: Source,
    issues: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any] | None,
    matched_source: str | None,
    assessment: dict[str, Any] | None,
) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None, str | None
]:
    if not assessment or assessment.get("verdict") != "UNLIKELY":
        return issues, warnings, metadata, matched_source
    found = {
        "title": assessment.get("found_title"),
        "authors": split_found_authors(assessment.get("found_authors")),
        "venue": assessment.get("found_venue"),
        "year": parse_year(assessment.get("found_year")),
        "url": assessment.get("link"),
    }
    if not any(found.values()):
        return issues, warnings, metadata, matched_source
    rechecked_issues, rechecked_warnings = compare_metadata(
        source,
        found,
        doi_resolved=bool(source.doi),
        arxiv_resolved=bool(source.arxiv_id),
        url_alive=True if assessment.get("link") else None,
        retracted=False,
    )
    if not rechecked_issues:
        return [], rechecked_warnings, found, "llm_verified"
    return rechecked_issues, rechecked_warnings, found, "llm_verified"


def build_corrections(source: Source, metadata: dict[str, Any]) -> dict[str, str]:
    if not metadata:
        return {}
    title = collapse_ws(metadata.get("title") or source.title)
    authors = [str(a) for a in metadata.get("authors") or source.authors]
    year = metadata.get("year") or source.year
    venue = collapse_ws(metadata.get("venue") or source.venue or "")
    doi = metadata.get("doi") or source.doi
    url = metadata.get("url") or source.url or source.pdf_url
    author_text = " and ".join(authors)
    key = (
        re.sub(
            r"[^A-Za-z0-9]+",
            "",
            f"{authors[0].split()[-1] if authors else 'ref'}{year or ''}",
        )
        or source.id
    )
    bibtex_lines = [f"@article{{{key},"]
    if author_text:
        bibtex_lines.append(f"  author = {{{author_text}}},")
    if title:
        bibtex_lines.append(f"  title = {{{title}}},")
    if venue:
        bibtex_lines.append(f"  journal = {{{venue}}},")
    if year:
        bibtex_lines.append(f"  year = {{{year}}},")
    if doi:
        bibtex_lines.append(f"  doi = {{{doi}}},")
    if url:
        bibtex_lines.append(f"  url = {{{url}}},")
    if bibtex_lines[-1].endswith(","):
        bibtex_lines[-1] = bibtex_lines[-1][:-1]
    bibtex_lines.append("}")
    plain_parts = [
        ", ".join(authors),
        f"({year})" if year else "",
        title,
        venue,
        url or "",
    ]
    plain_text = ". ".join(part for part in plain_parts if part).strip(". ") + "."
    bibitem = f"\\bibitem{{{key}}}\n{plain_text}"
    return {
        "bibtex": "\n".join(bibtex_lines),
        "plain_text": plain_text,
        "bibitem": bibitem,
    }


def library_triage(
    source: Source,
    issues: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    verdict: str,
) -> tuple[list[str], str, dict[str, str]]:
    issue_types = {str(issue.get("type")) for issue in issues}
    tags = ["verified" if not issues else "needs-review"]
    if verdict == "LIKELY":
        tags.append("likely-hallucination")
    if "url_verification_failed" in issue_types:
        tags.append("broken-url")
    if "author_overlap_below_threshold" in issue_types:
        tags.append("author-mismatch")
    if "identifier_conflict" in issue_types or "doi_conflict" in issue_types:
        tags.append("identifier-conflict")
    if warnings:
        tags.append("minor-warning")
    folder = "References/Verified" if not issues else "References/Needs Review"
    if verdict == "LIKELY":
        folder = "References/Likely Hallucinations"
    markdown = f"### {source.title}\n\n- Verdict: {verdict}\n- Folder: {folder}\n- Tags: {', '.join(tags)}\n"
    if issues:
        markdown += "\nIssues:\n" + "\n".join(
            f"- {i.get('type')}: {i.get('detail')}" for i in issues
        )
    text = re.sub(r"[#*`]", "", markdown).strip()
    return tags, folder, {"markdown": markdown.strip(), "plain_text": text}


def crossref_indicates_retraction(payload: dict[str, Any]) -> bool:
    candidates: list[dict[str, Any]] = [payload]
    msg = payload.get("message")
    if isinstance(msg, dict):
        candidates.append(msg)

    for body in candidates:
        updates = body.get("update-to")
        if not isinstance(updates, list):
            continue
        for entry in updates:
            if not isinstance(entry, dict):
                continue
            update_type = entry.get("update-type") or entry.get("type")
            if isinstance(update_type, str) and update_type.lower() == "retraction":
                return True
    return False


def author_overlap(cited: list[str], actual: list[str]) -> float | None:
    if len(cited) < 3 or not actual:
        return None
    actual_keys = {author_key(name) for name in actual if author_key(name)}
    cited_keys = [author_key(name) for name in cited if author_key(name)]
    if len(cited_keys) < 3 or not actual_keys:
        return None
    return sum(1 for key in cited_keys if key in actual_keys) / len(cited_keys)


def author_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    if "," in normalized:
        family, given = normalized.split(",", 1)
        family_parts = re.findall(r"[a-z]+", family)
        given_parts = re.findall(r"[a-z]+", given)
        if family_parts and given_parts:
            return f"{family_parts[-1]}:{given_parts[0][0]}"
    parts = re.findall(r"[a-z]+", normalized)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[-1]}:{parts[0][0]}"


def split_found_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if not value:
        return []
    return [
        part.strip()
        for part in re.split(r";|,\s+(?=[A-Z])", str(value))
        if part.strip()
    ]


def parse_year(value: Any) -> int | None:
    match = re.search(r"\d{4}", str(value or ""))
    return int(match.group(0)) if match else None
