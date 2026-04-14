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


def _collect_hypothesis_ratings(report: dict[str, Any], synthesis: dict[str, Any]) -> dict[str, str]:
    """Collect hypothesis rating/disposition strings, keyed by hypothesis ID.

    Supports multiple source formats:
    - CLI: report.assessment.hypothesis_ratings[] with probability_term/range
    - Plugin: synthesis.assessment.hypothesis_disposition (id -> disposition string)
    """
    ratings: dict[str, str] = {}

    # CLI format via report
    if isinstance(report, dict):
        assessment = report.get("assessment", {})
        if isinstance(assessment, dict):
            for r in assessment.get("hypothesis_ratings", []):
                hyp_id = r.get("hypothesis_id", "")
                if hyp_id:
                    term = r.get("probability_term", "")
                    rng = r.get("probability_range", "")
                    ratings[hyp_id] = f"{term} ({rng})" if term else rng

    # Plugin format via synthesis
    if isinstance(synthesis, dict):
        assessment = synthesis.get("assessment", {})
        if isinstance(assessment, dict):
            disposition = assessment.get("hypothesis_disposition", {})
            if isinstance(disposition, dict):
                for hyp_id, text in disposition.items():
                    if hyp_id not in ratings:
                        ratings[hyp_id] = str(text)

    return ratings


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

    # Write per-item content first (so run index can count sources etc.)
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
        audit_to_render = item_audit or audit
        if audit_to_render and not audit_to_render.get("id"):
            audit_to_render = {**audit_to_render, "id": item_id}

        _write_item_input(item_dir, item)
        if item_hypotheses:
            _write_hypotheses(item_dir, item_hypotheses, item_report, item_synthesis)
        if item_synthesis:
            _write_assessment(item_dir, item_synthesis, item_report)
        if audit_to_render:
            _write_self_audit(item_dir, audit_to_render)

        _write_searches(item_dir, item_id, item_search_plan, search_results)
        _write_sources(item_dir, item_id, scorecards, search_results)
        _write_reading_list(item_dir, audit_to_render, item_id, scorecards)

        _write_item_index(
            item_dir,
            item,
            item_report,
            item_synthesis,
            item_hypotheses,
            item_search_plan,
            search_results,
            scorecards,
        )

    # Write run index LAST, with full context for cards + collection analysis
    _write_run_index(
        output_dir,
        input_items,
        report_items,
        hypotheses,
        search_plans,
        search_results,
        scorecards,
        synthesis,
        audit,
    )


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


def _write_run_index(
    output_dir: Path,
    input_items: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    hypotheses: dict[str, Any],
    search_plans: dict[str, Any],
    search_results: dict[str, Any],
    scorecards: dict[str, Any],
    synthesis: dict[str, Any],
    audit: dict[str, Any],
) -> None:
    """Write the run-level index.md.

    Structure modeled on past research runs (see
    docs/site/docs/research/R0044-*/2026-04-01/index.md as canonical):

    1. Meta table (item counts)
    2. Per-item cards — claim/query text, answer/verdict, hypothesis
       status table, sources/searches counts, Full analysis link
    3. Collection analysis — statistics table and self-audit summary
    """
    lines: list[str] = ["# Run Overview", ""]

    # Meta table
    claims = [i for i in input_items if i.get("type") == "claim"]
    queries = [i for i in input_items if i.get("type") == "query"]
    axioms = [i for i in input_items if i.get("type") == "axiom"]

    lines.extend(
        [
            "| | |",
            "|---|---|",
            f"| **Items** | {len(input_items)} |",
            f"| **Claims** | {len(claims)} |",
            f"| **Queries** | {len(queries)} |",
            f"| **Axioms** | {len(axioms)} |",
            "",
        ]
    )

    # Slug lookup
    slug_by_id: dict[str, str] = {}
    for item in input_items:
        item_id = item.get("id", "")
        clarified = (
            item.get("restated_for_testability") or item.get("clarified_text") or item.get("original_text", "")
        )
        if item_id:
            slug_by_id[item_id] = _item_slug(item_id, clarified)

    # Unwrap step outputs once
    hypotheses_items = _unwrap_items(hypotheses)
    synthesis_items = _unwrap_items(synthesis)
    search_plan_items = _unwrap_items(search_plans)
    execution_log = search_results.get("search_execution_log", []) if isinstance(search_results, dict) else []
    reports_by_id: dict[str, dict[str, Any]] = {r.get("id", ""): r for r in reports}

    # Section heading
    section_label = "Claims & Queries" if (claims and queries) else ("Claims" if claims else "Queries")
    lines.extend([f"## {section_label}", ""])

    # Per-item cards
    for item in input_items:
        item_id = item.get("id", "")
        if not item_id:
            continue
        item_type = item.get("type", "claim")
        slug = slug_by_id.get(item_id, "")

        original = item.get("original_text", "")
        clarified = item.get("restated_for_testability") or item.get("clarified_text") or original

        report = reports_by_id.get(item_id, {})
        item_hypotheses = _item_by_id(hypotheses_items, item_id)
        item_synthesis = _item_by_id(synthesis_items, item_id)
        item_search_plan = _item_by_id(search_plan_items, item_id)

        # Verdict for claims, confidence for queries
        verdict = report.get("verdict") or report.get("confidence") or ""
        heading = f"### {item_id} — {verdict}" if verdict else f"### {item_id}"
        lines.extend([heading, ""])

        # Claim / Query text
        text_label = "Claim" if item_type == "claim" else "Query"
        item_text = original or clarified or report.get("original_query") or report.get("original_claim", "")
        lines.extend([f"**{text_label}:** {item_text}", ""])

        # Answer / verdict summary
        answer = (
            report.get("verdict_summary")
            or report.get("answer_summary")
            or report.get("one_line")
            or ""
        )
        if answer:
            answer_label = "Verdict" if item_type == "claim" else "Answer"
            lines.extend([f"**{answer_label}:** {answer}", ""])

        # Hypothesis status table
        hyp_ratings = _collect_hypothesis_ratings(report, item_synthesis)
        hyps_list = item_hypotheses.get("hypotheses", []) if isinstance(item_hypotheses, dict) else []
        if hyps_list:
            lines.extend(["| Hypothesis | Status |", "|------------|--------|"])
            for h in hyps_list:
                hid = h.get("id", "?")
                short_id = hid.split("-")[-1] if "-" in hid else hid
                label_text = h.get("label", "")
                status = (hyp_ratings.get(hid, "—") or "—")[:80]
                lines.append(f"| {short_id}: *{label_text}* | {status} |")
            lines.append("")

        # Confidence · Sources · Searches metadata line
        source_count = len(_extract_sources_for_item(scorecards, item_id))
        search_count = len(item_search_plan.get("searches", [])) if isinstance(item_search_plan, dict) else 0
        confidence = ""
        if isinstance(item_synthesis, dict):
            assessment = item_synthesis.get("assessment", {})
            if isinstance(assessment, dict):
                confidence = assessment.get("probability_label") or assessment.get("confidence", "")
        meta_parts: list[str] = []
        if confidence:
            meta_parts.append(f"**Confidence:** {confidence}")
        meta_parts.extend([f"**Sources:** {source_count}", f"**Searches:** {search_count}"])
        lines.append(" · ".join(meta_parts))
        lines.append("")

        if slug:
            lines.extend([f"[Full analysis]({slug}/index.md)", ""])

    # Collection Analysis
    lines.extend(["---", "", "## Collection Analysis", ""])

    # Collection Statistics
    total_sources = len(scorecards.get("sources", [])) if isinstance(scorecards, dict) else 0
    total_searches = len(execution_log)
    total_results = sum(e.get("total_returned", 0) or len(e.get("results", [])) for e in execution_log)
    total_selected = sum(
        sum(1 for r in e.get("results", []) if r.get("disposition") == "selected") for e in execution_log
    )

    lines.extend(
        [
            "### Collection Statistics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Items investigated | {len(input_items)} |",
        ]
    )
    if total_sources:
        lines.append(f"| Sources scored | {total_sources} |")
    if total_searches:
        lines.append(f"| Searches executed | {total_searches} |")
    if total_results:
        rejected = total_results - total_selected
        lines.append(
            f"| Results dispositioned | {total_selected} selected + {rejected} rejected = {total_results} total |"
        )
    lines.append("")

    # Collection Self-Audit (plugin format: global robis_audit)
    robis = audit.get("robis_audit", {}) if isinstance(audit, dict) else {}
    if isinstance(robis, dict) and robis:
        lines.extend(
            [
                "### Collection Self-Audit",
                "",
                "| Domain | Rating |",
                "|--------|--------|",
            ]
        )
        for key in sorted(k for k in robis if k.startswith("domain_")):
            d = robis[key]
            if isinstance(d, dict):
                rating = d.get("risk", "—")
                label_text = key.replace("domain_", "Domain ").replace("_", " ").title()
                lines.append(f"| {label_text} | {rating} |")
        lines.append("")
        if robis.get("overall_risk_of_bias"):
            lines.extend([f"**Overall risk of bias:** {robis['overall_risk_of_bias']}", ""])

    (output_dir / "index.md").write_text("\n".join(lines) + "\n")


def _write_item_index(
    item_dir: Path,
    item: dict[str, Any],
    report: dict[str, Any],
    synthesis: dict[str, Any],
    hypotheses: dict[str, Any],
    search_plan: dict[str, Any],
    search_results: dict[str, Any],
    scorecards: dict[str, Any],
) -> None:
    """Write the per-item index.md with BLUF, summary tables, and navigation."""
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
    if (item_dir / "hypotheses" / "index.md").exists():
        lines.append("| [Hypotheses](hypotheses/index.md) | Competing hypotheses |")
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

    # Hypothesis summary table (if hypotheses exist)
    ratings_by_hyp = _collect_hypothesis_ratings(report, synthesis)

    if hypotheses and hypotheses.get("hypotheses"):
        lines.extend(
            [
                "## Hypotheses",
                "",
                "| ID | Label | Status |",
                "|----|-------|--------|",
            ]
        )
        for h in hypotheses["hypotheses"]:
            hyp_id = h.get("id", "?")
            short_id = hyp_id.split("-")[-1] if "-" in hyp_id else hyp_id
            label = h.get("label", "")
            status = ratings_by_hyp.get(hyp_id, "—")
            lines.append(f"| [{short_id}](hypotheses/{short_id}.md) | {label} | {status} |")
        lines.append("")

    # Searches summary table
    if search_plan and search_plan.get("searches"):
        execution_log = search_results.get("search_execution_log", []) if isinstance(search_results, dict) else []
        lines.extend(
            [
                "## Searches",
                "",
                "| ID | Target | Returned | Selected |",
                "|----|--------|----------|----------|",
            ]
        )
        for s in search_plan["searches"]:
            search_id = s.get("id", "S??")
            theme = s.get("theme") or s.get("target_hypothesis") or ""
            exec_record = next(
                (e for e in execution_log if e.get("search_id") == search_id or e.get("id") == search_id),
                None,
            )
            returned_str = "?"
            selected_str = "?"
            if exec_record:
                results_list = exec_record.get("results", [])
                returned_str = str(exec_record.get("total_returned") or len(results_list))
                selected_str = str(sum(1 for r in results_list if r.get("disposition") == "selected"))
            lines.append(
                f"| [{search_id}](searches/{search_id}/search-log.md) | {theme[:60]} | "
                f"{returned_str} | {selected_str} |"
            )
        lines.append("")

    # Sources summary table
    sources = _extract_sources_for_item(scorecards, item_id)
    if sources:
        lines.extend(
            [
                "## Sources",
                "",
                "| ID | Title | Reliability | Relevance |",
                "|----|-------|-------------|-----------|",
            ]
        )
        for i, s in enumerate(sources, 1):
            src_id = s.get("id") or f"SRC{i:03d}"
            title = (s.get("title") or s.get("url", ""))[:60]
            rel_value = s.get("reliability", "")
            relev_value = s.get("relevance", "")
            rel_str = rel_value.get("rating", "—") if isinstance(rel_value, dict) else (rel_value or "—")
            relev_str = relev_value.get("rating", "—") if isinstance(relev_value, dict) else (relev_value or "—")
            lines.append(f"| [{src_id}](sources/{src_id}/scorecard.md) | {title} | {rel_str} | {relev_str} |")
        lines.append("")

    # Evidence quality snapshot from synthesis
    if synthesis:
        syn = synthesis.get("synthesis") or synthesis
        snapshot_rows: list[str] = []
        eq = syn.get("evidence_quality") if isinstance(syn, dict) else None
        sa = syn.get("source_agreement") if isinstance(syn, dict) else None
        ipcc = syn.get("ipcc_combined") if isinstance(syn, dict) else None
        if isinstance(eq, dict) and eq.get("rating"):
            snapshot_rows.append(f"| Evidence quality | {eq['rating']} |")
        if isinstance(sa, dict) and sa.get("rating"):
            snapshot_rows.append(f"| Source agreement | {sa['rating']} |")
        if ipcc:
            snapshot_rows.append(f"| IPCC assessment | {ipcc} |")
        if snapshot_rows:
            lines.extend(
                ["## Evidence Snapshot", "", "| Dimension | Rating |", "|-----------|--------|", *snapshot_rows, ""]
            )

    # Revisit triggers from report
    if report:
        triggers = report.get("revisit_triggers", [])
        if triggers:
            lines.extend(["## Revisit Triggers", ""])
            for t in triggers:
                if isinstance(t, dict):
                    trigger_text = t.get("trigger", "")
                    trigger_type = t.get("type", "")
                    if trigger_type:
                        lines.append(f"- **[{trigger_type}]** {trigger_text}")
                    else:
                        lines.append(f"- {trigger_text}")
                else:
                    lines.append(f"- {t}")
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


def _write_hypotheses(
    item_dir: Path, data: dict[str, Any], report: dict[str, Any], synthesis: dict[str, Any]
) -> None:
    """Write hypotheses/ directory with per-hypothesis files and an index.

    Creates:
        hypotheses/
            index.md    — summary table of all hypotheses
            H1.md       — one file per hypothesis
            H2.md
            ...
    """
    item_id = data.get("id", "?")
    hyps_dir = item_dir / "hypotheses"
    hyps_dir.mkdir(parents=True, exist_ok=True)

    approach = data.get("approach", "hypotheses")

    # Collect status string per hypothesis id (handles both CLI and plugin schemas)
    ratings_by_hyp = _collect_hypothesis_ratings(report, synthesis)

    if approach == "open-ended":
        # For open-ended queries there are no discrete hypotheses; write themes instead.
        index_lines = [f"# {item_id} — Search Themes (open-ended)", ""]
        rationale = data.get("rationale", "")
        if rationale:
            index_lines.extend([rationale, ""])

        themes = data.get("search_themes", [])
        if themes:
            index_lines.extend(["| ID | Theme | Derived from |", "|----|-------|--------------|"])
            for t in themes:
                theme_id = t.get("id", "?")
                theme = t.get("theme", "")
                derived = t.get("derived_from", "")
                index_lines.append(f"| [{theme_id}]({theme_id}.md) | {theme} | {derived} |")
            index_lines.append("")

        for t in themes:
            theme_id = t.get("id", "?")
            theme_lines = [f"# {item_id} — {theme_id}: {t.get('theme', '')}", ""]
            derived = t.get("derived_from", "")
            if derived:
                theme_lines.extend([f"**Derived from**: {derived}", ""])
            look_for = t.get("look_for", [])
            if look_for:
                theme_lines.append("**Look for:**")
                for lf in look_for:
                    theme_lines.append(f"- {lf}")
                theme_lines.append("")
            perspectives = t.get("perspectives", [])
            if perspectives:
                theme_lines.append("**Perspectives:**")
                for p in perspectives:
                    theme_lines.append(f"- {p}")
                theme_lines.append("")
            theme_lines.append("[← Back to hypotheses index](index.md)")
            (hyps_dir / f"{theme_id}.md").write_text("\n".join(theme_lines) + "\n")
    else:
        hyps = data.get("hypotheses", [])

        index_lines = [
            f"# {item_id} — Competing Hypotheses",
            "",
            "| ID | Label | Statement | Status |",
            "|----|-------|-----------|--------|",
        ]
        for h in hyps:
            hyp_id = h.get("id", "?")
            # Support both "H1" and "C001-H1" ID styles; use short ID for filename
            short_id = hyp_id.split("-")[-1] if "-" in hyp_id else hyp_id
            label = h.get("label", "")
            statement = (h.get("statement") or "")[:100]
            status = ratings_by_hyp.get(hyp_id, "—")
            index_lines.append(f"| [{short_id}]({short_id}.md) | {label} | {statement} | {status[:60]} |")
        index_lines.append("")

        # Discriminating questions in the index
        disc = data.get("discriminating_questions", [])
        if disc:
            index_lines.extend(["## Discriminating Questions", ""])
            for q in disc:
                index_lines.append(f"- {q}")
            index_lines.append("")

        # Per-hypothesis file
        for h in hyps:
            hyp_id = h.get("id", "?")
            short_id = hyp_id.split("-")[-1] if "-" in hyp_id else hyp_id
            _write_hypothesis_file(hyps_dir / f"{short_id}.md", item_id, h, ratings_by_hyp.get(hyp_id, ""))

    index_lines.append("[← Back to item overview](../index.md)")
    (hyps_dir / "index.md").write_text("\n".join(index_lines) + "\n")


def _write_hypothesis_file(path: Path, item_id: str, h: dict[str, Any], status: str) -> None:
    """Write a single hypothesis detail file."""
    hyp_id = h.get("id", "?")
    short_id = hyp_id.split("-")[-1] if "-" in hyp_id else hyp_id
    label = h.get("label", "")
    statement = h.get("statement", "")

    lines = [f"# {item_id} — {short_id}: {label}", "", f"**Statement**: {statement}", ""]

    if status:
        lines.extend(["## Status", "", status, ""])

    falsification = h.get("falsification_target")
    if falsification:
        lines.extend(["## Falsification Target", "", falsification, ""])

    supporting = h.get("supporting_evidence", [])
    if supporting:
        lines.extend(["## Supporting Evidence Would Show", ""])
        for s in supporting:
            lines.append(f"- {s}")
        lines.append("")

    eliminating = h.get("eliminating_evidence", [])
    if eliminating:
        lines.extend(["## Eliminating Evidence Would Show", ""])
        for e in eliminating:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("[← Back to hypotheses index](index.md)")
    path.write_text("\n".join(lines) + "\n")


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
    index_lines = [
        f"# {item_id} — Searches",
        "",
        "| ID | Target | Terms | Returned | Selected | Rejected |",
        "|----|--------|-------|----------|----------|----------|",
    ]

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
        # Write per-result files and build selected/rejected tables
        selected_count = 0
        rejected_count = 0
        total_returned = 0
        if exec_record:
            query_str = exec_record.get("query", "")
            if query_str:
                lines.extend([f"**Query**: `{query_str}`", ""])

            results_list = exec_record.get("results", [])
            total_returned = exec_record.get("total_returned") or len(results_list)
            selected_count = sum(1 for r in results_list if r.get("disposition") == "selected")
            rejected_count = sum(1 for r in results_list if r.get("disposition") != "selected")

            lines.extend(
                [
                    "## Execution Summary",
                    "",
                    f"- Results returned: {total_returned}",
                    f"- Selected: {selected_count}",
                    f"- Rejected: {rejected_count}",
                    "",
                ]
            )

            # Per-result files + tables
            results_subdir = search_subdir / "results"
            if results_list:
                results_subdir.mkdir(parents=True, exist_ok=True)

            selected_rows: list[str] = []
            rejected_rows: list[str] = []
            for idx, r in enumerate(results_list, 1):
                result_id = f"R{idx:02d}"
                disposition = r.get("disposition", "rejected")
                title = r.get("title") or r.get("url", "")
                url = r.get("url", "")
                score = r.get("relevance_score", "?")
                reason = r.get("reason", "")

                # Write detail file
                rlines = [
                    f"# {search_id} — {result_id}",
                    "",
                    f"**Title**: {title}",
                    "",
                    f"**URL**: <{url}>",
                    "",
                    f"**Relevance score**: {score}",
                    "",
                    f"**Disposition**: {disposition}",
                    "",
                ]
                if reason:
                    rlines.extend([f"**Rationale**: {reason}", ""])
                rlines.append("[← Back to search log](../search-log.md)")
                (results_subdir / f"{result_id}.md").write_text("\n".join(rlines) + "\n")

                row = f"| [{result_id}](results/{result_id}.md) | {title[:60]} | {score} | {reason[:80]} |"
                if disposition == "selected":
                    selected_rows.append(row)
                else:
                    rejected_rows.append(row)

            if selected_rows:
                lines.extend(
                    [
                        "## Selected Results",
                        "",
                        "| ID | Title | Score | Rationale |",
                        "|----|-------|-------|-----------|",
                        *selected_rows,
                        "",
                    ]
                )
            if rejected_rows:
                lines.extend(
                    [
                        "## Rejected Results",
                        "",
                        "| ID | Title | Score | Rationale |",
                        "|----|-------|-------|-----------|",
                        *rejected_rows,
                        "",
                    ]
                )

        lines.append("[← Back to searches index](../index.md)")
        (search_subdir / "search-log.md").write_text("\n".join(lines) + "\n")

        # Add to index with counts
        terms_short = ", ".join(f"`{t}`" for t in terms[:3])
        index_lines.append(
            f"| [{search_id}]({search_id}/search-log.md) | {theme[:60]} | {terms_short} | "
            f"{total_returned} | {selected_count} | {rejected_count} |"
        )

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

        # Handle both CLI-style (rated object) and plugin-style (simple string) ratings
        rel_value = s.get("reliability", "")
        relev_value = s.get("relevance", "")
        rel_str = rel_value.get("rating", "—") if isinstance(rel_value, dict) else (rel_value or "—")
        relev_str = relev_value.get("rating", "—") if isinstance(relev_value, dict) else (relev_value or "—")
        index_lines.append(f"| [{src_id}]({src_id}/scorecard.md) | {title[:60]} | {rel_str} | {relev_str} |")

        # Per-source scorecard
        lines = [f"# {src_id} — {title}", ""]

        # Metadata table
        meta_rows: list[str] = []
        if url:
            meta_rows.append(f"| URL | <{url}> |")
        if s.get("authors"):
            meta_rows.append(f"| Authors | {s['authors']} |")
        if s.get("date"):
            meta_rows.append(f"| Date | {s['date']} |")
        if s.get("items"):
            items_refs = ", ".join(str(i) for i in s["items"])
            meta_rows.append(f"| Referenced by | {items_refs} |")
        if meta_rows:
            lines.extend(["## Metadata", "", "| Field | Value |", "|-------|-------|", *meta_rows, ""])

        # Content summary
        if s.get("content_summary"):
            lines.extend(["## Content Summary", "", s["content_summary"], ""])

        # Reliability
        if rel_str and rel_str != "—":
            lines.append(f"## Reliability: {rel_str}")
            lines.append("")
            rationale = (
                rel_value.get("rationale") if isinstance(rel_value, dict) else s.get("reliability_rationale", "")
            )
            if rationale:
                lines.extend([rationale, ""])

        # Relevance
        if relev_str and relev_str != "—":
            lines.append(f"## Relevance: {relev_str}")
            lines.append("")
            rationale = (
                relev_value.get("rationale") if isinstance(relev_value, dict) else s.get("relevance_rationale", "")
            )
            if rationale:
                lines.extend([rationale, ""])

        # Bias assessment
        bias = s.get("bias_assessment", {})
        if isinstance(bias, dict) and bias:
            lines.extend(
                ["## Bias Assessment", "", "| Domain | Rating | Rationale |", "|--------|--------|-----------|"]
            )
            for domain, d in bias.items():
                domain_label = domain.replace("_", " ").title()
                # Plugin format: value is a string like "Low risk — rationale"
                # CLI format: value is a dict with rating + rationale
                if isinstance(d, dict):
                    rating = d.get("rating", "—")
                    rationale = (d.get("rationale") or "")[:200]
                elif isinstance(d, str):
                    # Try to split "Rating — rationale"
                    parts = d.split("—", 1) if "—" in d else d.split("-", 1) if " - " in d else [d, ""]
                    rating = parts[0].strip()
                    rationale = parts[1].strip()[:200] if len(parts) > 1 else ""
                else:
                    rating = str(d)
                    rationale = ""
                lines.append(f"| {domain_label} | {rating} | {rationale} |")
            lines.append("")

        lines.append("[← Back to sources index](../index.md)")
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
