"""JSON-to-Markdown renderer for Diogenes research output.

Reads the JSON files produced by the pipeline and writes a directory tree
of linked markdown files. Pure Python, zero LLM tokens. Produces generic
markdown with relative links — no CSS classes, admonitions, or
framework-specific markup.

Output structure (per run):

    run-N/
    ├── index.md                  (run overview + verdict summary)
    └── C001-<slug>/
        ├── index.md              (item overview, BLUF, summary)
        ├── claim.md or query.md  (input details, vocabulary)
        ├── hypotheses.md         (competing hypotheses)
        ├── assessment.md         (full assessment with reasoning)
        ├── self-audit.md         (process audit domains)
        ├── reading-list.md       (prioritized sources)
        ├── searches/
        │   └── S01/search-log.md
        └── sources/
            └── SRC001/scorecard.md

Group-level (run group directory):

    <run-group>/
    ├── index.md                  (group overview)
    ├── synthesis.md              (cross-run synthesis, if multi-run)
    ├── consistency.md            (cross-run metrics, if multi-run)
    └── reading-list.md           (consolidated sources)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SLUG_MAX_LEN = 50


def _slugify(text: str, max_len: int = _SLUG_MAX_LEN) -> str:
    """Convert text to a filesystem-safe slug."""
    # Lowercase, replace non-alphanum with dashes, collapse, trim
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    slug = slug.strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "unnamed"


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file, returning empty dict if missing."""
    if not path.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data


def _item_slug(item_id: str, text: str) -> str:
    """Generate a directory slug for an item (e.g. C001-rlhf-sycophancy)."""
    return f"{item_id}-{_slugify(text, max_len=40)}"


def _unwrap_items(data: dict[str, Any], key: str = "items") -> list[dict[str, Any]]:
    """Extract item list from a pipeline output file.

    Handles both CLI format (dict keyed by item ID) and plugin format
    (wrapped with pipeline_step metadata, items under a key).
    """
    if not data:
        return []
    # Plugin format: metadata wrapper with items list
    if key in data and isinstance(data[key], list):
        items: list[dict[str, Any]] = data[key]
        return items
    # Alternative plugin key
    if "reports" in data and isinstance(data["reports"], list):
        reports: list[dict[str, Any]] = data["reports"]
        return reports
    # CLI format: dict keyed by item ID
    if all(k.startswith(("C", "Q")) for k in data if k not in {"pipeline_step", "step_name", "timestamp"}):
        return [v for k, v in data.items() if k.startswith(("C", "Q")) and isinstance(v, dict)]
    return []


def _item_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    """Find an item by its ID in a list."""
    for item in items:
        if item.get("id") == item_id:
            return item
    return {}


def render_run(run_dir: Path, output_dir: Path) -> None:
    """Render a single run's JSON output to a markdown tree.

    Args:
        run_dir: Directory containing the JSON step outputs.
        output_dir: Where to write the markdown tree.

    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load all pipeline outputs
    research_input = _load_json(run_dir / "research-input.json")
    hypotheses = _load_json(run_dir / "hypotheses.json")
    search_plans = _load_json(run_dir / "search-plans.json")
    search_results = _load_json(run_dir / "search-results.json")
    scorecards = _load_json(run_dir / "source-scorecards.json")
    synthesis = _load_json(run_dir / "synthesis.json")
    audit = _load_json(run_dir / "self-audit.json")
    reports = _load_json(run_dir / "reports.json")

    # Extract items
    input_items = _unwrap_items(research_input)
    report_items = _unwrap_items(reports, key="reports")

    # Write run index
    _write_run_index(output_dir, input_items, report_items)

    # Write per-item content
    for item in input_items:
        item_id = item.get("id", "")
        if not item_id:
            continue

        clarified = item.get("restated_for_testability") or item.get("clarified_text") or item.get("original_text", "")
        slug = _item_slug(item_id, clarified)
        item_dir = output_dir / slug
        item_dir.mkdir(parents=True, exist_ok=True)

        item_hypotheses = _item_by_id(_unwrap_items(hypotheses), item_id)
        item_search_plan = _item_by_id(_unwrap_items(search_plans), item_id)
        item_synthesis = _item_by_id(_unwrap_items(synthesis), item_id)
        item_audit = _item_by_id(_unwrap_items(audit), item_id)
        item_report = _item_by_id(report_items, item_id)

        # Plugin format has a single global audit (not per-item).
        # Use it when no per-item audit exists.
        audit_to_render = item_audit or audit
        # Tag with item id so the writer's heading is correct
        if audit_to_render and not audit_to_render.get("id"):
            audit_to_render = {**audit_to_render, "id": item_id}

        # Write all content files first
        _write_item_input(item_dir, item)
        if item_hypotheses:
            _write_hypotheses(item_dir, item_hypotheses)
        if item_synthesis:
            _write_assessment(item_dir, item_synthesis, item_report)
        if audit_to_render:
            _write_self_audit(item_dir, audit_to_render)

        _write_searches(item_dir, item_id, item_search_plan, search_results)
        _write_sources(item_dir, item_id, scorecards, search_results)
        _write_reading_list(item_dir, audit_to_render, item_id, scorecards)

        # Write index LAST so existence checks see the actual files
        _write_item_index(item_dir, item, item_report, item_synthesis)


def render_run_group(group_dir: Path, output_dir: Path) -> None:
    """Render an entire run group (possibly multiple runs) to markdown.

    Args:
        group_dir: Run group directory containing run-N/ subdirs and
            optionally group-level JSON files.
        output_dir: Where to write the rendered markdown tree.

    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Render each run
    run_dirs = sorted(d for d in group_dir.iterdir() if d.is_dir() and d.name.startswith("run-"))
    for run_dir in run_dirs:
        run_output = output_dir / run_dir.name
        render_run(run_dir, run_output)

    # Render group-level content if present
    group_synthesis = _load_json(group_dir / "group-synthesis.json")
    group_consistency = _load_json(group_dir / "group-consistency.json")
    group_reading_list = _load_json(group_dir / "group-reading-list.json")

    if group_synthesis:
        _write_group_synthesis(output_dir, group_synthesis)
    if group_consistency:
        _write_group_consistency(output_dir, group_consistency)
    if group_reading_list:
        _write_group_reading_list(output_dir, group_reading_list)

    # Write index LAST so existence checks see the actual files
    _write_group_index(output_dir, run_dirs, group_synthesis)


# ---------------------------------------------------------------------------
# Writers for individual markdown files
# ---------------------------------------------------------------------------


def _write_run_index(output_dir: Path, input_items: list[dict[str, Any]], reports: list[dict[str, Any]]) -> None:
    """Write the run-level index.md with a verdict summary table."""
    lines: list[str] = ["# Run Overview", ""]
    lines.append(f"Items investigated: {len(input_items)}")
    lines.append("")

    # Build a lookup from item ID to the slug used by input items (for consistent links)
    slug_by_id: dict[str, str] = {}
    for item in input_items:
        item_id = item.get("id", "")
        clarified = item.get("restated_for_testability") or item.get("clarified_text") or item.get("original_text", "")
        if item_id:
            slug_by_id[item_id] = _item_slug(item_id, clarified)

    if reports:
        lines.extend(
            ["## Verdict Summary", "", "| ID | Type | Verdict | Summary |", "|----|------|---------|---------|"]
        )
        for report in reports:
            item_id = report.get("id", "?")
            item_type = report.get("type", "?")
            verdict = report.get("verdict", "—")
            summary = (report.get("verdict_summary") or report.get("one_line") or "")[:120]
            slug = slug_by_id.get(item_id) or _item_slug(item_id, report.get("title", ""))
            lines.append(f"| [{item_id}]({slug}/index.md) | {item_type} | {verdict} | {summary} |")
        lines.append("")

    lines.extend(["## Items", ""])
    for item in input_items:
        item_id = item.get("id", "?")
        clarified = item.get("restated_for_testability") or item.get("clarified_text") or item.get("original_text", "")
        slug = _item_slug(item_id, clarified)
        lines.append(f"- [{item_id} — {clarified[:100]}]({slug}/index.md)")

    (output_dir / "index.md").write_text("\n".join(lines) + "\n")


def _write_item_index(
    item_dir: Path,
    item: dict[str, Any],
    report: dict[str, Any],
    synthesis: dict[str, Any],
) -> None:
    """Write the per-item index.md with BLUF and summary."""
    item_id = item.get("id", "?")
    item_type = item.get("type", "claim")
    input_filename = "claim.md" if item_type == "claim" else "query.md"

    clarified = item.get("restated_for_testability") or item.get("clarified_text") or item.get("original_text", "")

    lines = [f"# {item_id}", "", f"**{clarified}**", ""]

    # BLUF from report
    if report:
        verdict = report.get("verdict", "")
        summary = report.get("verdict_summary") or report.get("one_line") or ""
        if verdict:
            lines.extend([f"**Verdict:** {verdict}", ""])
        if summary:
            lines.extend(["## Bottom Line", "", summary, ""])

    # Summary of what's in this directory — only link to files that exist
    lines.extend(["## Contents", "", "| Section | Description |", "|---------|-------------|"])
    if (item_dir / input_filename).exists():
        lines.append(f"| [Input]({input_filename}) | Original text, clarification, scope, vocabulary |")
    if (item_dir / "hypotheses.md").exists():
        lines.append("| [Hypotheses](hypotheses.md) | Competing hypotheses |")
    if (item_dir / "assessment.md").exists():
        lines.append("| [Assessment](assessment.md) | Evidence synthesis, probability assessment, gaps |")
    if (item_dir / "self-audit.md").exists():
        lines.append("| [Self-Audit](self-audit.md) | Process audit across 4 ROBIS domains |")
    if (item_dir / "reading-list.md").exists():
        lines.append("| [Reading List](reading-list.md) | Prioritized source list |")
    if (item_dir / "searches" / "index.md").exists():
        lines.append("| [Searches](searches/index.md) | Search plans and execution logs |")
    if (item_dir / "sources" / "index.md").exists():
        lines.append("| [Sources](sources/index.md) | Source scorecards |")
    lines.append("")

    # Evidence quality snapshot
    if synthesis:
        syn = synthesis.get("synthesis") or synthesis
        evidence_quality = syn.get("evidence_quality", {})
        source_agreement = syn.get("source_agreement", {})
        if evidence_quality or source_agreement:
            lines.extend(["## Evidence Snapshot", "", "| Dimension | Rating |", "|-----------|--------|"])
            if isinstance(evidence_quality, dict) and evidence_quality.get("rating"):
                lines.append(f"| Evidence quality | {evidence_quality.get('rating')} |")
            if isinstance(source_agreement, dict) and source_agreement.get("rating"):
                lines.append(f"| Source agreement | {source_agreement.get('rating')} |")
            lines.append("")

    lines.append("[← Back to run overview](../index.md)")
    (item_dir / "index.md").write_text("\n".join(lines) + "\n")


def _write_item_input(item_dir: Path, item: dict[str, Any]) -> None:
    """Write claim.md or query.md with input details."""
    item_type = item.get("type", "claim")
    filename = "claim.md" if item_type == "claim" else "query.md"

    lines = [f"# {item.get('id', '?')} — Input", ""]

    original = item.get("original_text", "")
    clarified = item.get("restated_for_testability") or item.get("clarified_text", "")

    if original:
        lines.extend(["## Original Text", "", original, ""])
    if clarified and clarified != original:
        lines.extend(["## Clarified for Testability", "", clarified, ""])

    assumptions = item.get("embedded_assumptions") or item.get("assumptions_surfaced", [])
    if assumptions:
        lines.extend(["## Embedded Assumptions Surfaced", ""])
        for a in assumptions:
            lines.append(f"- {a}")
        lines.append("")

    scope = item.get("scope", {})
    if isinstance(scope, dict) and scope:
        lines.extend(["## Scope", "", "| Dimension | Value |", "|-----------|-------|"])
        for k, v in scope.items():
            lines.append(f"| {k.capitalize()} | {v} |")
        lines.append("")

    vocab = item.get("vocabulary_map") or item.get("vocabulary", {})
    if isinstance(vocab, dict) and vocab:
        lines.extend(["## Vocabulary Map", ""])
        for section, terms in vocab.items():
            if isinstance(terms, list) and terms:
                lines.append(f"**{section.replace('_', ' ').title()}**: " + ", ".join(str(t) for t in terms))
                lines.append("")

    lines.append("[← Back to item overview](index.md)")
    (item_dir / filename).write_text("\n".join(lines) + "\n")


def _write_hypotheses(item_dir: Path, data: dict[str, Any]) -> None:
    """Write hypotheses.md with the competing hypotheses table."""
    lines = [f"# {data.get('id', '?')} — Competing Hypotheses", ""]

    approach = data.get("approach", "hypotheses")
    if approach == "open-ended":
        rationale = data.get("rationale", "")
        themes = data.get("search_themes", [])
        lines.extend(["## Approach: Open-ended", "", rationale, "", "## Search Themes", ""])
        for t in themes:
            lines.append(f"### {t.get('id', '?')} — {t.get('theme', '')}")
            lines.append("")
            derived = t.get("derived_from", "")
            if derived:
                lines.append(f"**Derived from**: {derived}")
                lines.append("")
            look_for = t.get("look_for", [])
            if look_for:
                lines.append("**Look for:**")
                for lf in look_for:
                    lines.append(f"- {lf}")
                lines.append("")
    else:
        hyps = data.get("hypotheses", [])
        for h in hyps:
            lines.append(f"## {h.get('id', '?')} — {h.get('statement', '')}")
            lines.append("")
            supporting = h.get("supporting_evidence", [])
            eliminating = h.get("eliminating_evidence", [])
            if supporting:
                lines.append("**Supporting evidence would show:**")
                for s in supporting:
                    lines.append(f"- {s}")
                lines.append("")
            if eliminating:
                lines.append("**Eliminating evidence would show:**")
                for e in eliminating:
                    lines.append(f"- {e}")
                lines.append("")

        disc = data.get("discriminating_questions", [])
        if disc:
            lines.extend(["## Discriminating Questions", ""])
            for q in disc:
                lines.append(f"- {q}")
            lines.append("")

    lines.append("[← Back to item overview](index.md)")
    (item_dir / "hypotheses.md").write_text("\n".join(lines) + "\n")


def _write_assessment(item_dir: Path, synthesis: dict[str, Any], report: dict[str, Any]) -> None:
    """Write assessment.md with evidence synthesis, probability assessment, gaps."""
    lines = [f"# {synthesis.get('id', '?')} — Assessment", ""]

    # Verdict from report
    if report:
        verdict = report.get("verdict", "")
        summary = report.get("verdict_summary") or report.get("one_line") or ""
        if verdict:
            lines.extend([f"**Verdict:** {verdict}", ""])
        if summary:
            lines.extend([summary, ""])
        reasoning = report.get("reasoning") or report.get("reasoning_chain", "")
        if reasoning:
            lines.extend(["## Reasoning", "", reasoning, ""])

    # Synthesis section
    syn = synthesis.get("synthesis") or synthesis
    if isinstance(syn, dict):
        lines.extend(["## Evidence Synthesis", ""])

        # Plugin format: evidence_summary text + IPCC axes
        if syn.get("evidence_summary"):
            lines.append(syn["evidence_summary"])
            lines.append("")
        if syn.get("ipcc_combined"):
            lines.append(f"**IPCC assessment**: {syn['ipcc_combined']}")
            lines.append("")
        if syn.get("ipcc_agreement_axis"):
            lines.append(f"- **Agreement**: {syn['ipcc_agreement_axis']}")
        if syn.get("ipcc_evidence_axis"):
            lines.append(f"- **Evidence**: {syn['ipcc_evidence_axis']}")
        lines.append("")

        # CLI format: rated fields with rationale
        eq = syn.get("evidence_quality", {})
        sa = syn.get("source_agreement", {})
        if isinstance(eq, dict) and eq.get("rating"):
            lines.append(f"**Evidence quality**: {eq.get('rating')} — {eq.get('rationale', '')}")
            lines.append("")
        if isinstance(sa, dict) and sa.get("rating"):
            lines.append(f"**Source agreement**: {sa.get('rating')} — {sa.get('rationale', '')}")
            lines.append("")
        indep = syn.get("independence", {})
        if isinstance(indep, dict) and indep.get("assessment"):
            lines.append(f"**Independence**: {indep.get('assessment')}")
            lines.append("")
        outliers = syn.get("outliers", [])
        if outliers:
            lines.extend(["### Outliers", ""])
            for o in outliers:
                lines.append(f"- **{o.get('source_url', '')}**: {o.get('divergence', '')} — {o.get('explanation', '')}")
            lines.append("")

    # Assessment section (probability/confidence)
    assessment = synthesis.get("assessment", {})
    if isinstance(assessment, dict) and assessment:
        lines.extend(["## Probability Assessment", ""])

        # Plugin format
        if assessment.get("scale"):
            lines.append(f"**Scale**: {assessment['scale']}")
        if assessment.get("probability_label"):
            lines.append(
                f"**Probability**: {assessment['probability_label']} ({assessment.get('probability_range', '')})"
            )
        if assessment.get("rationale"):
            lines.append("")
            lines.append(assessment["rationale"])
        lines.append("")

        # CLI format: per-hypothesis ratings
        ratings = assessment.get("hypothesis_ratings", [])
        for r in ratings:
            lines.append(
                f"- **{r.get('hypothesis_id', '?')}**: {r.get('probability_term', '')} ({r.get('probability_range', '')})"
            )
            if r.get("reasoning"):
                lines.append(f"  - {r.get('reasoning')}")
        if assessment.get("verdict"):
            lines.append(f"**Verdict**: {assessment['verdict']}")
        if assessment.get("confidence"):
            lines.append(f"**Confidence**: {assessment['confidence']}")
        lines.append("")

    # Gaps
    gaps = synthesis.get("gaps")
    if gaps:
        lines.extend(["## Evidence Gaps", ""])
        # Plugin format: flat list of strings
        if isinstance(gaps, list):
            for g in gaps:
                lines.append(f"- {g}")
            lines.append("")
        # CLI format: structured dict
        elif isinstance(gaps, dict):
            expected = gaps.get("expected_not_found", [])
            if expected:
                lines.append("**Expected but not found:**")
                for e in expected:
                    lines.append(f"- {e}")
                lines.append("")
            unanswered = gaps.get("unanswered_questions", [])
            if unanswered:
                lines.append("**Unanswered questions:**")
                for u in unanswered:
                    lines.append(f"- {u}")
                lines.append("")
            impact = gaps.get("impact_on_confidence", "")
            if impact:
                lines.append(f"**Impact on confidence**: {impact}")
                lines.append("")

    lines.append("[← Back to item overview](index.md)")
    (item_dir / "assessment.md").write_text("\n".join(lines) + "\n")


def _write_self_audit(item_dir: Path, audit: dict[str, Any]) -> None:
    """Write self-audit.md with ROBIS 4-domain audit + source verification.

    Handles both per-item audit (CLI format with 'process_audit') and
    per-run global audit (plugin format with 'robis_audit' at top level).
    """
    lines = [f"# {audit.get('id', '?')} — Self-Audit", ""]

    # CLI format: process_audit with named domains
    process = audit.get("process_audit", {})
    if isinstance(process, dict) and process:
        lines.extend(
            [
                "## Process Audit (ROBIS 4 Domains)",
                "",
                "| Domain | Rating | Rationale |",
                "|--------|--------|-----------|",
            ]
        )
        for domain_key in (
            "eligibility_criteria",
            "search_comprehensiveness",
            "evaluation_consistency",
            "synthesis_fairness",
        ):
            d = process.get(domain_key, {})
            if isinstance(d, dict):
                rating = d.get("rating", "—")
                rationale = (d.get("rationale") or "")[:200]
                lines.append(f"| {domain_key.replace('_', ' ').title()} | {rating} | {rationale} |")
        lines.append("")

    # Plugin format: robis_audit with domain_N_* keys (global, not per-item)
    robis = audit.get("robis_audit", {})
    if isinstance(robis, dict) and robis:
        lines.extend(
            [
                "## ROBIS Audit (4 Domains)",
                "",
                "| Domain | Risk | Assessment |",
                "|--------|------|------------|",
            ]
        )
        for key in sorted(k for k in robis if k.startswith("domain_")):
            d = robis[key]
            if isinstance(d, dict):
                risk = d.get("risk", "—")
                assessment_text = (d.get("assessment") or "")[:300]
                domain_label = key.replace("_", " ").replace("domain ", "Domain ").title()
                lines.append(f"| {domain_label} | {risk} | {assessment_text} |")
        lines.append("")
        if robis.get("overall_risk_of_bias"):
            lines.append(f"**Overall risk of bias**: {robis['overall_risk_of_bias']}")
            lines.append("")
        if robis.get("overall_assessment"):
            lines.append("### Overall Assessment")
            lines.append("")
            lines.append(robis["overall_assessment"])
            lines.append("")

    # Source-back verification (CLI format)
    verification = audit.get("source_verification", {})
    if isinstance(verification, dict) and verification:
        count = verification.get("sources_verified", 0)
        discrepancies = verification.get("discrepancies", [])
        lines.extend(["## Source-Back Verification", "", f"Sources verified: {count}", ""])
        if discrepancies:
            lines.append("### Discrepancies")
            lines.append("")
            for d in discrepancies:
                lines.append(f"- **{d.get('severity', '?')}** at {d.get('source_url', '')}")
                lines.append(f"  - Assessment claims: {d.get('claim_in_assessment', '')}")
                lines.append(f"  - Source actually says: {d.get('actual_source_says', '')}")
            lines.append("")
        else:
            lines.append("No discrepancies found.")
            lines.append("")

    # Plugin format: source_interpretation_verification (different field name)
    plugin_verification = audit.get("source_interpretation_verification", {})
    if isinstance(plugin_verification, dict) and plugin_verification:
        lines.extend(["## Source Interpretation Verification", ""])
        if plugin_verification.get("sources_checked"):
            lines.append(f"Sources checked: {plugin_verification['sources_checked']}")
            lines.append("")
        if plugin_verification.get("findings"):
            lines.append(plugin_verification["findings"])
            lines.append("")
        if plugin_verification.get("assessment"):
            lines.append(plugin_verification["assessment"])
            lines.append("")

    lines.append("[← Back to item overview](index.md)")
    (item_dir / "self-audit.md").write_text("\n".join(lines) + "\n")


def _write_reading_list(
    item_dir: Path,
    audit: dict[str, Any],
    item_id: str,
    scorecards: dict[str, Any],
) -> None:
    """Write reading-list.md with prioritized sources."""
    lines = [f"# {item_id} — Reading List", ""]

    reading_list = audit.get("reading_list", []) if isinstance(audit, dict) else []

    if reading_list:
        by_priority: dict[str, list[dict[str, Any]]] = {"must read": [], "should read": [], "reference": []}
        for entry in reading_list:
            priority = entry.get("priority", "reference")
            if priority in by_priority:
                by_priority[priority].append(entry)
        for priority_label in ("must read", "should read", "reference"):
            entries = by_priority[priority_label]
            if entries:
                lines.extend([f"## {priority_label.title()}", ""])
                for e in entries:
                    title = e.get("title") or e.get("url", "")
                    summary = e.get("summary", "")
                    url = e.get("url", "")
                    lines.append(f"- **[{title}]({url})**")
                    if summary:
                        lines.append(f"  - {summary}")
                lines.append("")
    else:
        # Fall back to scorecards directly
        sources = _extract_sources_for_item(scorecards, item_id)
        if sources:
            lines.extend(
                ["## Sources", "", "| Source | Reliability | Relevance |", "|--------|-------------|-----------|"]
            )
            for s in sources:
                url = s.get("url", "")
                title = s.get("title") or url
                rel = s.get("reliability", {})
                relev = s.get("relevance", {})
                rel_rating = rel.get("rating", "?") if isinstance(rel, dict) else str(rel)
                relev_rating = relev.get("rating", "?") if isinstance(relev, dict) else str(relev)
                lines.append(f"| [{title}]({url}) | {rel_rating} | {relev_rating} |")
            lines.append("")

    lines.append("[← Back to item overview](index.md)")
    (item_dir / "reading-list.md").write_text("\n".join(lines) + "\n")


def _extract_sources_for_item(scorecards: dict[str, Any], item_id: str) -> list[dict[str, Any]]:
    """Pull out scorecards relevant to a specific item ID."""
    sources_list = scorecards.get("sources", []) if isinstance(scorecards, dict) else []
    if isinstance(sources_list, list):
        matching = [s for s in sources_list if s.get("item_id") == item_id or not s.get("item_id")]
        if matching:
            return matching
    # CLI style: dict keyed by item ID
    item_data = scorecards.get(item_id, {})
    if isinstance(item_data, dict):
        scores: list[dict[str, Any]] = item_data.get("scorecards", [])
        return scores
    return []


def _write_searches(
    item_dir: Path,
    item_id: str,
    item_plan: dict[str, Any],
    search_results: dict[str, Any],
) -> None:
    """Write searches/ subdirectory with per-search logs and an index."""
    if not item_plan:
        return
    searches_dir = item_dir / "searches"
    searches_dir.mkdir(parents=True, exist_ok=True)

    searches = item_plan.get("searches", [])
    execution_log = search_results.get("search_execution_log", []) if isinstance(search_results, dict) else []

    # Write per-search logs and collect index entries
    index_lines = [f"# {item_id} — Searches", "", "| ID | Target | Terms |", "|----|--------|-------|"]

    for s in searches:
        search_id = s.get("id", "S??")
        search_subdir = searches_dir / search_id
        search_subdir.mkdir(parents=True, exist_ok=True)

        lines = [f"# {item_id} — {search_id}", ""]
        theme = s.get("theme") or s.get("target_hypothesis") or ""
        if theme:
            lines.append(f"**Target**: {theme}")
            lines.append("")
        terms = s.get("terms", [])
        if terms:
            lines.append("**Terms**: " + ", ".join(f"`{t}`" for t in terms))
            lines.append("")
        sources_planned = s.get("sources", [])
        if sources_planned:
            lines.append("**Planned sources**: " + ", ".join(sources_planned))
            lines.append("")

        # Match execution record
        exec_record = next(
            (e for e in execution_log if e.get("search_id") == search_id or e.get("id") == search_id),
            None,
        )
        if exec_record:
            lines.extend(["## Execution", ""])
            results = exec_record.get("results_returned") or exec_record.get("results_found", 0)
            selected = exec_record.get("results_selected", 0)
            rejected = exec_record.get("results_rejected", 0)
            lines.append(f"- Results returned: {results}")
            lines.append(f"- Selected: {selected}")
            lines.append(f"- Rejected: {rejected}")
            lines.append("")

        lines.append("[← Back to item overview](../../index.md)")
        (search_subdir / "search-log.md").write_text("\n".join(lines) + "\n")

        # Add to index
        terms_short = ", ".join(f"`{t}`" for t in terms[:3])
        index_lines.append(f"| [{search_id}]({search_id}/search-log.md) | {theme[:60]} | {terms_short} |")

    index_lines.extend(["", "[← Back to item overview](../index.md)"])
    (searches_dir / "index.md").write_text("\n".join(index_lines) + "\n")


def _write_sources(
    item_dir: Path,
    item_id: str,
    scorecards: dict[str, Any],
    search_results: dict[str, Any],  # noqa: ARG001
) -> None:
    """Write sources/ subdirectory with per-source scorecards."""
    sources = _extract_sources_for_item(scorecards, item_id)
    if not sources:
        return

    sources_dir = item_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    index_lines = [
        f"# {item_id} — Sources",
        "",
        "| ID | Title | Reliability | Relevance |",
        "|----|-------|-------------|-----------|",
    ]

    for i, s in enumerate(sources, 1):
        src_id = s.get("id") or f"SRC{i:03d}"
        src_subdir = sources_dir / src_id
        src_subdir.mkdir(parents=True, exist_ok=True)

        url = s.get("url", "")
        title = s.get("title") or url

        # Index entry
        rel_rating = s.get("reliability", {})
        relev_rating = s.get("relevance", {})
        rel_str = rel_rating.get("rating", "—") if isinstance(rel_rating, dict) else str(rel_rating)
        relev_str = relev_rating.get("rating", "—") if isinstance(relev_rating, dict) else str(relev_rating)
        index_lines.append(f"| [{src_id}]({src_id}/scorecard.md) | {title[:60]} | {rel_str} | {relev_str} |")

        lines = [f"# {src_id} — {title}", ""]
        if url:
            lines.append(f"URL: <{url}>")
            lines.append("")

        for field in ("reliability", "relevance"):
            val = s.get(field, {})
            if isinstance(val, dict):
                rating = val.get("rating", "—")
                rationale = val.get("rationale", "")
                lines.append(f"**{field.capitalize()}**: {rating}")
                if rationale:
                    lines.append(f"- {rationale}")
                lines.append("")

        bias = s.get("bias_assessment", {})
        if isinstance(bias, dict) and bias:
            lines.extend(
                ["## Bias Assessment", "", "| Domain | Rating | Rationale |", "|--------|--------|-----------|"]
            )
            for domain, d in bias.items():
                if isinstance(d, dict):
                    rating = d.get("rating", "—")
                    rationale = (d.get("rationale") or "")[:150]
                    lines.append(f"| {domain.replace('_', ' ').title()} | {rating} | {rationale} |")
            lines.append("")

        lines.append("[← Back to item overview](../../index.md)")
        (src_subdir / "scorecard.md").write_text("\n".join(lines) + "\n")

    index_lines.extend(["", "[← Back to item overview](../index.md)"])
    (sources_dir / "index.md").write_text("\n".join(index_lines) + "\n")


# ---------------------------------------------------------------------------
# Group-level writers
# ---------------------------------------------------------------------------


def _write_group_index(
    output_dir: Path,
    run_dirs: list[Path],
    group_synthesis: dict[str, Any],  # noqa: ARG001
) -> None:
    """Write the run group index.md."""
    lines = ["# Research Run Group", ""]
    lines.append(f"Runs: {len(run_dirs)}")
    lines.append("")

    if run_dirs:
        lines.extend(["## Runs", ""])
        for rd in run_dirs:
            lines.append(f"- [{rd.name}]({rd.name}/index.md)")
        lines.append("")

    group_links = [
        ("synthesis.md", "Cross-run synthesis"),
        ("consistency.md", "Cross-run consistency metrics"),
        ("reading-list.md", "Consolidated reading list"),
    ]
    existing_links = [(f, lab) for f, lab in group_links if (output_dir / f).exists()]
    if existing_links:
        lines.extend(["## Group-Level Reports", ""])
        for filename, label in existing_links:
            lines.append(f"- [{label}]({filename})")
        lines.append("")

    (output_dir / "index.md").write_text("\n".join(lines) + "\n")


def _write_group_synthesis(output_dir: Path, data: dict[str, Any]) -> None:
    """Write group-level synthesis.md."""
    lines = ["# Cross-Run Synthesis", ""]

    total_runs = data.get("total_runs", 0)
    if total_runs:
        lines.append(f"**Total runs**: {total_runs}")
        lines.append("")
    note = data.get("note")
    if note:
        lines.extend([f"> {note}", ""])

    items = data.get("items", [])
    if items:
        lines.extend(["## Consensus Per Item", ""])
        for item in items:
            item_id = item.get("id", "?")
            verdict = item.get("consensus_verdict", "—")
            summary = item.get("summary", "")
            lines.append(f"### {item_id} — {verdict}")
            lines.append("")
            if summary:
                lines.append(summary)
                lines.append("")
            divergences = item.get("divergences", [])
            if divergences:
                lines.append("**Divergences across runs:**")
                for d in divergences:
                    lines.append(f"- {d}")
                lines.append("")
            sources_count = item.get("sources_union_count")
            if sources_count is not None:
                lines.append(f"Sources (union across runs): {sources_count}")
                lines.append("")

    lines.append("[← Back to group overview](index.md)")
    (output_dir / "synthesis.md").write_text("\n".join(lines) + "\n")


def _write_group_consistency(output_dir: Path, data: dict[str, Any]) -> None:
    """Write group-level consistency.md."""
    lines = ["# Cross-Run Consistency Metrics", ""]

    total_runs = data.get("total_runs", 0)
    if total_runs:
        lines.append(f"**Total runs**: {total_runs}")
        lines.append("")
    note = data.get("note")
    if note:
        lines.extend([f"> {note}", ""])

    metrics = data.get("metrics", {})
    if isinstance(metrics, dict) and metrics:
        lines.extend(["## Metrics", "", "| Metric | Value |", "|--------|-------|"])
        for k, v in metrics.items():
            label = k.replace("_", " ").title()
            lines.append(f"| {label} | {v} |")
        lines.append("")

    diagnostic = data.get("diagnostic")
    if diagnostic:
        lines.extend(["## Diagnostic", "", diagnostic, ""])

    lines.append("[← Back to group overview](index.md)")
    (output_dir / "consistency.md").write_text("\n".join(lines) + "\n")


def _write_group_reading_list(output_dir: Path, data: dict[str, Any]) -> None:
    """Write group-level reading-list.md."""
    lines = ["# Consolidated Reading List", ""]

    reading_list = data.get("reading_list", [])
    if not reading_list:
        lines.append("No sources recorded.")
        lines.append("")
        (output_dir / "reading-list.md").write_text("\n".join(lines) + "\n")
        return

    # Group by priority
    by_priority: dict[str, list[dict[str, Any]]] = {"must read": [], "should read": [], "reference": []}
    for entry in reading_list:
        priority = entry.get("priority", "reference")
        if priority in by_priority:
            by_priority[priority].append(entry)

    for priority_label in ("must read", "should read", "reference"):
        entries = by_priority[priority_label]
        if not entries:
            continue
        lines.extend([f"## {priority_label.title()}", ""])
        for e in entries:
            title = e.get("title") or e.get("url", "")
            url = e.get("url", "")
            summary = e.get("summary", "")
            items_refs = e.get("items", [])
            runs_found = e.get("found_in_runs", [])
            lines.append(f"- **[{title}]({url})**")
            if summary:
                lines.append(f"  - {summary}")
            if items_refs:
                lines.append(f"  - Referenced by: {', '.join(items_refs)}")
            if runs_found:
                lines.append(f"  - Found in runs: {', '.join(runs_found)}")
        lines.append("")

    lines.append("[← Back to group overview](index.md)")
    (output_dir / "reading-list.md").write_text("\n".join(lines) + "\n")
