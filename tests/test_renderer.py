"""Tests for renderer module."""

import json
from pathlib import Path
from typing import Any

from diogenes.renderer import (
    _add_toc,
    _card_heading_for,
    _collect_hypothesis_ratings,
    _extract_sources_for_item,
    _item_by_id,
    _item_slug,
    _load_json,
    _pipeline_notes_section,
    _pipeline_status_line,
    _slugify,
    _unwrap_items,
    render_run,
)


class TestSlugify:
    """Tests for _slugify."""

    def test_basic(self) -> None:
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert _slugify("What's the Cost?") == "what-s-the-cost"

    def test_max_len(self) -> None:
        result = _slugify("a" * 100, max_len=10)
        assert len(result) <= 10

    def test_empty_input(self) -> None:
        assert _slugify("") == "unnamed"

    def test_all_special(self) -> None:
        assert _slugify("!@#$%") == "unnamed"

    def test_trailing_dashes(self) -> None:
        result = _slugify("hello---")
        assert not result.endswith("-")


class TestLoadJson:
    """Tests for _load_json."""

    def test_valid(self, tmp_path: Path) -> None:
        path = tmp_path / "data.json"
        path.write_text('{"key": "value"}')
        assert _load_json(path) == {"key": "value"}

    def test_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.json"
        assert _load_json(path) == {}

    def test_invalid(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json")
        assert _load_json(path) == {}


class TestItemSlug:
    """Tests for _item_slug."""

    def test_basic(self) -> None:
        result = _item_slug("C001", "AI watermarking techniques")
        assert result.startswith("C001-")
        assert "ai-watermarking" in result


class TestUnwrapItems:
    """Tests for _unwrap_items."""

    def test_empty(self) -> None:
        assert _unwrap_items({}) == []

    def test_cli_format(self) -> None:
        data = {"Q001": {"id": "Q001", "text": "test"}}
        items = _unwrap_items(data)
        assert len(items) == 1
        assert items[0]["id"] == "Q001"

    def test_plugin_format(self) -> None:
        data = {"items": [{"id": "Q001", "text": "test"}]}
        items = _unwrap_items(data)
        assert len(items) == 1

    def test_reports_format(self) -> None:
        data = {"reports": [{"id": "Q001"}]}
        items = _unwrap_items(data)
        assert len(items) == 1


class TestItemById:
    """Tests for _item_by_id."""

    def test_found(self) -> None:
        items = [{"id": "Q001"}, {"id": "C001"}]
        assert _item_by_id(items, "Q001") == {"id": "Q001"}

    def test_not_found(self) -> None:
        items = [{"id": "Q001"}]
        assert _item_by_id(items, "C999") == {}


class TestPipelineStatusLine:
    """Tests for _pipeline_status_line."""

    def test_no_events(self) -> None:
        assert "✅" in _pipeline_status_line({})

    def test_empty_events(self) -> None:
        assert "✅" in _pipeline_status_line({"events": []})

    def test_warnings(self) -> None:
        events = {
            "events": [
                {"kind": "fetch_failed", "detail": "timeout"},
            ],
            "summary": {
                "by_kind": {"fetch_failed": 1},
                "coverage": {},
            },
        }
        result = _pipeline_status_line(events)
        assert "⚠️" in result
        assert "1 sources dropped" in result

    def test_structural_failure(self) -> None:
        events = {
            "events": [
                {"kind": "subagent_failed", "detail": "error"},
            ],
            "summary": {
                "by_kind": {"subagent_failed": 1},
                "coverage": {},
            },
        }
        result = _pipeline_status_line(events)
        assert "❌" in result

    def test_verbatim_drops_with_adherence(self) -> None:
        events = {
            "events": [
                {"kind": "packet_dropped_non_verbatim", "count": 5},
            ],
            "summary": {
                "by_kind": {"packet_dropped_non_verbatim": 1},
                "coverage": {"verbatim_adherence_pct": 60.0},
            },
        }
        result = _pipeline_status_line(events)
        assert "60%" in result

    def test_verbatim_drops_without_adherence(self) -> None:
        events = {
            "events": [
                {"kind": "packet_dropped_non_verbatim", "count": 3},
            ],
            "summary": {
                "by_kind": {"packet_dropped_non_verbatim": 1},
                "coverage": {},
            },
        }
        result = _pipeline_status_line(events)
        assert "3 packets dropped" in result


class TestPipelineNotesSection:
    """Tests for _pipeline_notes_section."""

    def test_empty(self) -> None:
        assert _pipeline_notes_section({}) == []
        assert _pipeline_notes_section({"events": []}) == []

    def test_produces_markdown(self) -> None:
        events = {
            "events": [
                {"kind": "fetch_failed", "detail": "timeout", "url": "https://a.com", "item_id": "Q001"},
                {"kind": "fetch_failed", "detail": "404", "url": "https://b.com"},
                {"kind": "packet_dropped_non_verbatim", "detail": "verbatim fail", "count": 3},
            ],
        }
        lines = _pipeline_notes_section(events)
        text = "\n".join(lines)
        assert "## Pipeline Notes" in text
        assert "Fetch failures" in text
        # Renderer wraps URLs in backticks — assert the full rendered pattern
        # to avoid CodeQL's incomplete-URL-substring false positive.
        assert "`https://a.com`" in text


def _create_realistic_run(run_dir: Path) -> None:
    """Create a realistic run directory with all step outputs."""
    # Research input — includes both a claim and a query to exercise both paths
    ri = {
        "claims": [
            {
                "id": "C001",
                "type": "claim",
                "text": "RLHF reduces sycophancy",
                "clarified_text": "RLHF training reduces sycophantic behavior in LLMs",
                "original_text": "RLHF reduces sycophancy",
                "restated_for_testability": "RLHF training reduces sycophantic behavior in LLMs",
                "vocabulary": {"RLHF": "Reinforcement Learning from Human Feedback"},
            },
        ],
        "queries": [
            {
                "id": "Q001",
                "type": "query",
                "text": "AI watermarking techniques",
                "clarified_text": "What techniques exist for embedding watermarks in AI-generated text?",
            },
        ],
        "axioms": [{"id": "A001", "type": "axiom", "text": "Peer-reviewed sources preferred"}],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri, indent=2))

    # Hypotheses — claim uses hypotheses approach, query uses open-ended
    hyp = {
        "C001": {
            "id": "C001",
            "approach": "hypotheses",
            "hypotheses": [
                {"id": "H1", "text": "RLHF reduces sycophancy through reward shaping", "direction": "supports"},
                {
                    "id": "H2",
                    "text": "RLHF increases sycophancy due to human preference bias",
                    "direction": "contradicts",
                },
            ],
        },
        "Q001": {
            "id": "Q001",
            "approach": "open-ended",
            "search_themes": [
                {"theme": "Statistical watermarking", "description": "Token distribution modification"},
            ],
        },
    }
    (run_dir / "hypotheses.json").write_text(json.dumps(hyp, indent=2))

    # Search plans
    sp = {
        "C001": {
            "id": "C001",
            "searches": [{"id": "S01", "terms": ["RLHF sycophancy"]}],
            "approach": "hypotheses",
        },
        "Q001": {
            "id": "Q001",
            "searches": [{"id": "S01", "terms": ["AI text watermarking"]}],
            "approach": "open-ended",
        },
    }
    (run_dir / "search-plans.json").write_text(json.dumps(sp, indent=2))

    # Search results — both C001 and Q001
    sr = {
        "C001": {
            "id": "C001",
            "searches_executed": [
                {
                    "search_id": "S01",
                    "terms_used": ["RLHF sycophancy"],
                    "provider": "serper",
                    "date": "2026-04-21T00:00:00Z",
                    "results_found": 1,
                    "total_available": 50,
                    "results": [
                        {"title": "RLHF Study", "url": "https://example.com/rlhf", "snippet": "Study on RLHF..."},
                    ],
                }
            ],
            "selected_sources": [
                {"url": "https://example.com/rlhf", "title": "RLHF Study", "relevance_score": 8},
            ],
            "rejected_sources": [
                {"url": "https://example.com/low", "title": "Low Relevance", "relevance_score": 2},
            ],
            "summary": {
                "total_searches": 1,
                "total_results_found": 2,
                "total_selected": 1,
                "total_rejected": 1,
                "relevance_threshold": 5,
            },
        },
        "Q001": {
            "id": "Q001",
            "searches_executed": [
                {
                    "search_id": "S01",
                    "terms_used": ["AI text watermarking"],
                    "provider": "serper",
                    "date": "2026-04-21T00:00:00Z",
                    "results_found": 1,
                    "total_available": 100,
                    "results": [
                        {"title": "Paper on Watermarking", "url": "https://example.com/paper", "snippet": "A study..."},
                    ],
                }
            ],
            "selected_sources": [
                {"url": "https://example.com/paper", "title": "Paper on Watermarking", "relevance_score": 9},
            ],
            "rejected_sources": [],
            "summary": {
                "total_searches": 1,
                "total_results_found": 1,
                "total_selected": 1,
                "total_rejected": 0,
                "relevance_threshold": 5,
            },
        },
    }
    (run_dir / "search-results.json").write_text(json.dumps(sr, indent=2))

    # Scorecards — both items
    sc = {
        "C001": {
            "id": "C001",
            "scorecards": [
                {
                    "url": "https://example.com/rlhf",
                    "title": "RLHF Study",
                    "authors": "Jones et al.",
                    "publication_date": "2025-03",
                    "content_summary": "Study on RLHF and sycophancy.",
                    "reliability_score": 7,
                    "relevance_score": 8,
                    "bias_assessment": "Some selection bias",
                    "items": ["C001"],
                },
            ],
        },
        "Q001": {
            "id": "Q001",
            "scorecards": [
                {
                    "url": "https://example.com/paper",
                    "title": "Paper on Watermarking",
                    "authors": "Smith et al.",
                    "publication_date": "2025-01",
                    "content_summary": "A comprehensive study on watermarking.",
                    "reliability_score": 8,
                    "relevance_score": 9,
                    "bias_assessment": "Low bias",
                    "items": ["Q001"],
                },
            ],
        },
    }
    (run_dir / "scorecards.json").write_text(json.dumps(sc, indent=2))

    # Evidence packets — both items
    ep = {
        "C001": {
            "id": "C001",
            "packets": [
                {
                    "excerpt": "RLHF training showed reduced sycophantic responses",
                    "source_url": "https://example.com/rlhf",
                    "relevance": "Directly tests the claim",
                    "hypothesis_support": "Supports H1",
                },
            ],
            "verbatim_stats": {"claimed": 3, "kept": 1, "dropped": 2},
        },
        "Q001": {
            "id": "Q001",
            "packets": [
                {
                    "excerpt": "Watermarking modifies token distributions",
                    "source_url": "https://example.com/paper",
                    "relevance": "Directly addresses the query",
                    "hypothesis_support": "Supports statistical approach",
                },
            ],
            "verbatim_stats": {"claimed": 2, "kept": 1, "dropped": 1},
        },
    }
    (run_dir / "evidence-packets.json").write_text(json.dumps(ep, indent=2))

    # Synthesis — both items
    syn = {
        "C001": {
            "id": "C001",
            "synthesis": "Evidence supports that RLHF training reduces sycophancy.",
            "assessment": {
                "verdict": "Supported with caveats",
                "confidence": "Moderate",
                "probability_label": "Likely (70-85%)",
                "reasoning": "Multiple studies show improvement but sample sizes are small.",
            },
            "evidence_quality": {
                "source_agreement": "Moderate agreement among sources",
                "evidence_grade": "B — consistent but small samples",
            },
            "gaps": ["Larger sample sizes needed"],
            "outliers": [{"source": "https://example.com/counter", "observation": "One study found opposite"}],
        },
        "Q001": {
            "id": "Q001",
            "synthesis": "Watermarking techniques primarily use statistical methods.",
            "assessment": {
                "verdict": "Well-established techniques exist for statistical watermarking",
                "confidence": "High",
            },
            "gaps": ["Limited research on robustness against paraphrasing"],
            "outliers": [],
        },
    }
    (run_dir / "synthesis.json").write_text(json.dumps(syn, indent=2))

    # Self-audit — both items (includes robis_audit for collection self-audit rendering)
    sa = {
        "robis_audit": {
            "domain_1_eligibility": {"risk": "Low", "notes": "All studies meet inclusion criteria"},
            "domain_2_identification": {"risk": "Low", "notes": "Comprehensive search"},
            "overall_risk_of_bias": "Low",
        },
        "C001": {
            "id": "C001",
            "process_audit": {
                "eligibility_criteria": {"rating": "Pass", "notes": "Sources meet criteria"},
                "search_comprehensiveness": {"rating": "Fail", "notes": "Limited search scope"},
                "evaluation_consistency": {"rating": "Pass", "notes": "Consistent"},
                "synthesis_fairness": {"rating": "Pass", "notes": "Fair"},
            },
            "reading_list": [
                {
                    "title": "RLHF Study",
                    "url": "https://example.com/rlhf",
                    "authors": "Jones et al.",
                    "relevance": "Primary evidence",
                    "priority": "high",
                },
            ],
        },
        "Q001": {
            "id": "Q001",
            "process_audit": {
                "eligibility_criteria": {"rating": "Pass", "notes": "All sources peer-reviewed"},
                "search_comprehensiveness": {"rating": "Pass", "notes": "Multiple databases searched"},
                "evaluation_consistency": {"rating": "Pass", "notes": "Consistent scoring"},
                "synthesis_fairness": {"rating": "Pass", "notes": "Balanced assessment"},
            },
            "reading_list": [
                {
                    "title": "Paper on Watermarking",
                    "url": "https://example.com/paper",
                    "authors": "Smith et al.",
                    "relevance": "Primary source",
                    "priority": "high",
                },
            ],
        },
    }
    (run_dir / "self-audit.json").write_text(json.dumps(sa, indent=2))

    # Reports — both items (claim uses "verdict", query uses "answer")
    rp = {
        "C001": {
            "id": "C001",
            "mode": "claim",
            "topic": "RLHF reduces sycophancy",
            "verdict_summary": "Supported with caveats",
            "assessment_summary": {
                "verdict": "Supported with caveats — evidence supports reduction but more studies needed",
                "confidence": "Moderate",
            },
            "methodology": "Systematic review of RLHF studies",
            "evidence_quality": "Moderate — small sample sizes",
            "key_findings": ["RLHF reduces sycophancy in controlled settings"],
            "gaps_and_limitations": ["Small sample sizes", "Limited to English"],
            "source_back_verification": [
                {"claim": "RLHF reduces sycophancy", "source": "https://example.com/rlhf", "verified": True},
            ],
        },
        "Q001": {
            "id": "Q001",
            "mode": "query",
            "topic": "AI watermarking techniques",
            "assessment_summary": {
                "answer": "Statistical watermarking is the dominant approach",
                "confidence": "High",
            },
            "methodology": "Systematic literature review",
            "evidence_quality": "Strong peer-reviewed evidence base",
            "key_findings": ["Statistical methods are most common"],
            "gaps_and_limitations": ["Robustness testing is limited"],
        },
    }
    (run_dir / "reports.json").write_text(json.dumps(rp, indent=2))

    # Pipeline events
    pe = {
        "run_id": "run-1",
        "events": [
            {"kind": "fetch_failed", "detail": "timeout on https://slow.com", "step": "step5", "layer": "pipeline"},
        ],
        "summary": {
            "total_events": 1,
            "by_kind": {"fetch_failed": 1},
            "coverage": {
                "sources_selected": 2,
                "sources_scored": 1,
                "verbatim_adherence_pct": 50.0,
            },
        },
    }
    (run_dir / "pipeline-events.json").write_text(json.dumps(pe, indent=2))


class TestRenderRun:
    """Tests for render_run."""

    def test_renders_markdown_files(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_realistic_run(run_dir)

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        # Check that index.md was created
        assert (output_dir / "index.md").exists()
        index_content = (output_dir / "index.md").read_text()
        # Index should have content from the run
        assert "Run Overview" in index_content

        # Check that markdown files were created
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) >= 1

    def test_empty_run_dir(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        output_dir = tmp_path / "md"
        # Should not crash with empty dir
        render_run(run_dir, output_dir)
        assert (output_dir / "index.md").exists()


class TestCardHeadingFor:
    """Tests for _card_heading_for."""

    def test_full_heading(self) -> None:
        item = {"id": "C001"}
        report = {"title": "My Topic", "verdict": "Supported"}
        assert _card_heading_for(item, report) == "C001 — My Topic — Supported"

    def test_no_topic(self) -> None:
        item = {"id": "Q001"}
        report = {"title": "", "confidence": "High"}
        assert _card_heading_for(item, report) == "Q001 — High"

    def test_no_qualifier(self) -> None:
        item = {"id": "C002"}
        report = {"title": "Topic Here"}
        assert _card_heading_for(item, report) == "C002 — Topic Here"

    def test_empty_report(self) -> None:
        item = {"id": "C003"}
        assert _card_heading_for(item, {}) == "C003"

    def test_qualifier_falls_back_to_assessment_summary_confidence(self) -> None:
        """Issue #161: pipeline emits confidence nested under `assessment_summary`.

        When the top-level `confidence`/`verdict` fields are absent, the heading
        must still pick up the nested qualifier so the TOC stays readable.
        """
        item = {"id": "Q001"}
        report = {
            "title": "LLM watermarking techniques",
            "assessment_summary": {"confidence": "Medium (55-80%)"},
        }
        assert _card_heading_for(item, report) == "Q001 — LLM watermarking techniques — Medium (55-80%)"

    def test_qualifier_falls_back_to_assessment_summary_verdict(self) -> None:
        """Claim-mode reports: nested `assessment_summary.verdict` feeds the qualifier."""
        item = {"id": "C001"}
        report = {
            "title": "Homophily in AI safety ethics",
            "assessment_summary": {"verdict": "Likely (55-80%)"},
        }
        assert _card_heading_for(item, report) == "C001 — Homophily in AI safety ethics — Likely (55-80%)"

    def test_title_missing_renders_id_only_for_backwards_compatibility(self) -> None:
        """Older runs lacking `title` must still render without crashing (issue #161).

        Older run JSONs (R0063 and earlier) do not carry `title`. The
        renderer must degrade to id-only rather than raise — there is no
        way to re-run those old LLM calls cheaply until #162 ships.
        """
        item = {"id": "Q001"}
        report = {"assessment_summary": {"confidence": "High"}}
        # No title → id plus nested qualifier only, no crash
        assert _card_heading_for(item, report) == "Q001 — High"

    def test_top_level_overrides_nested_qualifier(self) -> None:
        """Top-level `verdict`/`confidence` win when present (forward compatibility)."""
        item = {"id": "C001"}
        report = {
            "title": "Topic",
            "verdict": "Strongly supported",
            "assessment_summary": {"verdict": "ignored"},
        }
        assert _card_heading_for(item, report) == "C001 — Topic — Strongly supported"

    def test_nested_qualifier_non_string_is_ignored(self) -> None:
        """Defensive: a non-string nested verdict/confidence does not crash or leak.

        Guards against malformed older run JSONs where the nested
        `assessment_summary.verdict` might be something structured (a
        dict/list) instead of a plain string.
        """
        item = {"id": "Q001"}
        report = {
            "title": "Topic",
            # Non-string nested values — the helper must fall through to id+topic only.
            "assessment_summary": {"verdict": {"unexpected": "shape"}},
        }
        assert _card_heading_for(item, report) == "Q001 — Topic"


class TestAddToc:
    """Tests for _add_toc."""

    def test_adds_toc_with_two_sections(self) -> None:
        lines = ["# Title", "", "## Section One", "", "text", "", "## Section Two", "", "text"]
        result = _add_toc(lines)
        assert any("<!-- TOC START -->" in l for l in result)
        assert any("Section One" in l for l in result)

    def test_idempotent(self) -> None:
        lines = ["# Title", "", "<!-- TOC START -->", "## Contents", "", "<!-- TOC END -->", "", "## A", "", "## B"]
        result = _add_toc(lines)
        assert result == lines

    def test_no_title(self) -> None:
        lines = ["## Section One", "", "## Section Two"]
        result = _add_toc(lines)
        assert result == lines

    def test_too_few_sections(self) -> None:
        lines = ["# Title", "", "## Only One"]
        result = _add_toc(lines)
        assert result == lines

    def test_existing_anchor(self) -> None:
        lines = ["# Title", "", '<a id="my-anchor"></a>', "", "## Section A", "", "## Section B"]
        result = _add_toc(lines)
        assert any("my-anchor" in l for l in result)


class TestCollectHypothesisRatings:
    """Tests for _collect_hypothesis_ratings."""

    def test_cli_format(self) -> None:
        report = {
            "assessment": {
                "hypothesis_ratings": [
                    {"hypothesis_id": "H1", "probability_term": "Likely", "probability_range": "70-85%"},
                ]
            }
        }
        result = _collect_hypothesis_ratings(report, {})
        assert result["H1"] == "Likely (70-85%)"

    def test_plugin_format(self) -> None:
        synthesis = {"assessment": {"hypothesis_disposition": {"H1": "Supported", "H2": "Refuted"}}}
        result = _collect_hypothesis_ratings({}, synthesis)
        assert result["H1"] == "Supported"
        assert result["H2"] == "Refuted"

    def test_cli_takes_precedence(self) -> None:
        report = {
            "assessment": {
                "hypothesis_ratings": [
                    {"hypothesis_id": "H1", "probability_term": "Likely", "probability_range": "70-85%"},
                ]
            }
        }
        synthesis = {"assessment": {"hypothesis_disposition": {"H1": "Plugin value"}}}
        result = _collect_hypothesis_ratings(report, synthesis)
        assert result["H1"] == "Likely (70-85%)"

    def test_no_term_returns_range(self) -> None:
        report = {
            "assessment": {
                "hypothesis_ratings": [
                    {"hypothesis_id": "H1", "probability_term": "", "probability_range": "50-70%"},
                ]
            }
        }
        result = _collect_hypothesis_ratings(report, {})
        assert result["H1"] == "50-70%"


class TestExtractSourcesForItem:
    """Tests for _extract_sources_for_item."""

    def test_plugin_format_sources_list(self) -> None:
        scorecards = {"sources": [{"item_id": "C001", "title": "A"}, {"item_id": "Q001", "title": "B"}]}
        result = _extract_sources_for_item(scorecards, "C001")
        assert len(result) == 1
        assert result[0]["title"] == "A"

    def test_sources_without_item_id(self) -> None:
        scorecards = {"sources": [{"title": "A"}, {"title": "B"}]}
        result = _extract_sources_for_item(scorecards, "C001")
        assert len(result) == 2

    def test_cli_format_by_item_id(self) -> None:
        scorecards = {"C001": {"scorecards": [{"title": "A"}]}}
        result = _extract_sources_for_item(scorecards, "C001")
        assert len(result) == 1

    def test_empty(self) -> None:
        assert _extract_sources_for_item({}, "C001") == []

    def test_no_match_returns_empty(self) -> None:
        scorecards = {"sources": [{"item_id": "Q999", "title": "X"}]}
        result = _extract_sources_for_item(scorecards, "C001")
        assert result == []


# ---------------------------------------------------------------------------
# Plugin-format fixture and integration tests
# ---------------------------------------------------------------------------


def _create_plugin_format_run(run_dir: Path) -> None:
    """Create a run directory using plugin-format data with all optional fields populated."""
    # Research input — plugin format with items list
    ri = {
        "items": [
            {
                "id": "A001",
                "type": "axiom",
                "text": "Peer-reviewed sources preferred",
                "original_text": "Peer-reviewed sources preferred",
            },
            {
                "id": "C001",
                "type": "claim",
                "text": "RLHF reduces sycophancy",
                "original_text": "RLHF reduces sycophancy",
                "restated_for_testability": "RLHF training reduces sycophantic behavior in LLMs",
                "clarified_text": "RLHF training reduces sycophantic behavior in LLMs",
                "embedded_assumptions": ["LLMs exhibit sycophantic behavior", "RLHF is applied post-training"],
                "scope": {"temporal": "2020-2026", "geographic": "Global", "domain": "NLP"},
                "vocabulary_map": {
                    "technical_terms": ["RLHF", "sycophancy", "reward model"],
                    "acronyms": ["LLM", "PPO"],
                },
            },
            {
                "id": "Q001",
                "type": "query",
                "text": "AI watermarking techniques",
                "original_text": "AI watermarking techniques",
                "clarified_text": "What techniques exist for embedding watermarks in AI-generated text?",
            },
        ],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri, indent=2))

    # Hypotheses — claim uses hypotheses approach with rich detail; query uses open-ended
    hyp = {
        "items": [
            {
                "id": "C001",
                "approach": "hypotheses",
                "hypotheses": [
                    {
                        "id": "C001-H1",
                        "label": "RLHF reduces sycophancy via reward shaping",
                        "text": "RLHF reduces sycophancy through reward shaping",
                        "statement": "Reward signals penalize sycophantic outputs",
                        "direction": "supports",
                        "falsification_target": "Finding that RLHF reward models favor agreement",
                        "supporting_evidence": ["Reward models trained on diverse preferences"],
                        "eliminating_evidence": ["Reward models converge on agreement-seeking"],
                    },
                    {
                        "id": "C001-H2",
                        "label": "RLHF increases sycophancy",
                        "text": "RLHF increases sycophancy due to human preference bias",
                        "statement": "Human raters prefer agreeable responses, biasing RLHF",
                        "direction": "contradicts",
                        "falsification_target": "Finding that raters reward disagreement",
                        "supporting_evidence": ["Human raters prefer confirmation"],
                        "eliminating_evidence": ["Raters prefer accuracy over agreement"],
                    },
                ],
            },
            {
                "id": "Q001",
                "approach": "open-ended",
                "search_themes": [
                    {
                        "id": "T1",
                        "theme": "Statistical watermarking",
                        "description": "Token distribution modification",
                        "derived_from": "Initial query analysis",
                        "look_for": ["Distribution shifting techniques", "Detectability rates"],
                        "perspectives": ["Pro-watermarking", "Anti-watermarking"],
                    },
                ],
            },
        ],
    }
    (run_dir / "hypotheses.json").write_text(json.dumps(hyp, indent=2))

    # Search plans — plugin format with items list and extra fields
    sp = {
        "items": [
            {
                "id": "C001",
                "searches": [
                    {
                        "id": "S01",
                        "terms": ["RLHF sycophancy"],
                        "theme": "RLHF reward shaping",
                        "target_hypothesis": "H1",
                        "sources": ["Google Scholar", "Semantic Scholar"],
                    },
                ],
                "approach": "hypotheses",
            },
            {
                "id": "Q001",
                "searches": [{"id": "S01", "terms": ["AI text watermarking"], "theme": "Statistical methods"}],
                "approach": "open-ended",
            },
        ],
    }
    (run_dir / "search-plans.json").write_text(json.dumps(sp, indent=2))

    # Search results — plugin format with search_execution_log
    sr = {
        "search_execution_log": [
            {
                "search_id": "S01",
                "item_id": "C001",
                "query": "RLHF sycophancy reduction studies",
                "total_returned": 3,
                "results": [
                    {
                        "title": "RLHF Study",
                        "url": "https://example.com/rlhf",
                        "snippet": "Study on RLHF...",
                        "relevance_score": 8,
                        "disposition": "selected",
                        "reason": "Directly relevant to claim",
                    },
                    {
                        "title": "Tangential Paper",
                        "url": "https://example.com/tangential",
                        "snippet": "Some tangent...",
                        "relevance_score": 3,
                        "disposition": "rejected",
                        "reason": "Below relevance threshold",
                    },
                    {
                        "title": "Another Paper",
                        "url": "https://example.com/another",
                        "snippet": "More info...",
                        "relevance_score": 7,
                        "disposition": "selected",
                        "reason": "Good secondary source",
                    },
                ],
            },
        ],
        "items": [
            {
                "id": "C001",
                "searches_executed": [
                    {
                        "search_id": "S01",
                        "terms_used": ["RLHF sycophancy"],
                        "provider": "serper",
                        "date": "2026-04-21T00:00:00Z",
                        "results_found": 3,
                        "total_available": 50,
                        "results": [
                            {
                                "title": "RLHF Study",
                                "url": "https://example.com/rlhf",
                                "snippet": "Study on RLHF...",
                            },
                        ],
                    }
                ],
                "selected_sources": [{"url": "https://example.com/rlhf", "title": "RLHF Study", "relevance_score": 8}],
                "rejected_sources": [],
                "summary": {
                    "total_searches": 1,
                    "total_results_found": 3,
                    "total_selected": 2,
                    "total_rejected": 1,
                    "relevance_threshold": 5,
                },
            },
            {
                "id": "Q001",
                "searches_executed": [
                    {
                        "search_id": "S01",
                        "terms_used": ["AI text watermarking"],
                        "provider": "serper",
                        "date": "2026-04-21T00:00:00Z",
                        "results_found": 1,
                        "total_available": 100,
                        "results": [
                            {
                                "title": "Watermark Paper",
                                "url": "https://example.com/paper",
                                "snippet": "A study...",
                            },
                        ],
                    }
                ],
                "selected_sources": [
                    {"url": "https://example.com/paper", "title": "Watermark Paper", "relevance_score": 9},
                ],
                "rejected_sources": [],
                "summary": {
                    "total_searches": 1,
                    "total_results_found": 1,
                    "total_selected": 1,
                    "total_rejected": 0,
                    "relevance_threshold": 5,
                },
            },
        ],
    }
    (run_dir / "search-results.json").write_text(json.dumps(sr, indent=2))

    # Scorecards — plugin format with sources list and detailed ratings
    sc = {
        "sources": [
            {
                "id": "SRC001",
                "item_id": "C001",
                "url": "https://example.com/rlhf",
                "title": "RLHF Study",
                "authors": "Jones et al.",
                "date": "2025-03",
                "content_summary": "Study on RLHF and sycophancy.",
                "reliability": {"rating": "High", "rationale": "Peer-reviewed, large sample"},
                "relevance": {"rating": "Very High", "rationale": "Directly addresses the claim"},
                "bias_assessment": {
                    "selection_bias": {"rating": "Low", "rationale": "Random sampling used"},
                    "funding_bias": "Low risk — independent funding",
                },
                "items": ["C001"],
            },
            {
                "id": "SRC002",
                "item_id": "Q001",
                "url": "https://example.com/paper",
                "title": "Paper on Watermarking",
                "authors": "Smith et al.",
                "date": "2025-01",
                "content_summary": "A comprehensive study on watermarking.",
                "reliability": 8,
                "relevance": 9,
                "bias_assessment": "Low bias overall",
                "items": ["Q001"],
            },
        ],
    }
    (run_dir / "scorecards.json").write_text(json.dumps(sc, indent=2))

    # Evidence packets
    ep = {
        "items": [
            {
                "id": "C001",
                "packets": [
                    {
                        "excerpt": "RLHF training showed reduced sycophantic responses",
                        "source_url": "https://example.com/rlhf",
                        "relevance": "Directly tests the claim",
                    },
                ],
            },
        ],
    }
    (run_dir / "evidence-packets.json").write_text(json.dumps(ep, indent=2))

    # Synthesis — with all optional fields for assessment coverage
    syn = {
        "items": [
            {
                "id": "C001",
                "synthesis": {
                    "evidence_summary": "Strong evidence supports RLHF reducing sycophancy.",
                    "ipcc_combined": "High confidence, high agreement",
                    "ipcc_agreement_axis": "High agreement among sources",
                    "ipcc_evidence_axis": "Robust evidence base",
                    "evidence_quality": {"rating": "A", "rationale": "Peer-reviewed with large samples"},
                    "source_agreement": {"rating": "High", "rationale": "All sources concur"},
                    "independence": {"assessment": "Sources are methodologically independent"},
                    "outliers": [
                        {
                            "source_url": "https://example.com/counter",
                            "divergence": "Found opposite effect",
                            "explanation": "Small sample size",
                        },
                    ],
                },
                "assessment": {
                    "scale": "IPCC likelihood scale",
                    "probability_label": "Very Likely",
                    "probability_range": "85-95%",
                    "rationale": "Multiple independent studies confirm the finding.",
                    "hypothesis_ratings": [
                        {
                            "hypothesis_id": "C001-H1",
                            "probability_term": "Likely",
                            "probability_range": "70-85%",
                            "reasoning": "Supported by three independent studies",
                        },
                        {
                            "hypothesis_id": "C001-H2",
                            "probability_term": "Unlikely",
                            "probability_range": "10-30%",
                        },
                    ],
                    "hypothesis_disposition": {"C001-H1": "Supported", "C001-H2": "Refuted"},
                    "verdict": "Supported with caveats",
                    "confidence": "Moderate",
                },
                "gaps": {
                    "expected_not_found": ["Longitudinal studies over 1 year"],
                    "unanswered_questions": ["Does RLHF effect persist after further fine-tuning?"],
                    "impact_on_confidence": "Moderate — lack of longitudinal data limits certainty",
                },
                "outliers": [
                    {"source": "https://example.com/counter", "observation": "One study found opposite"},
                ],
            },
            {
                "id": "Q001",
                "synthesis": "Watermarking techniques primarily use statistical methods.",
                "assessment": {
                    "verdict": "Well-established techniques exist",
                    "confidence": "High",
                },
                "gaps": ["Limited research on robustness against paraphrasing"],
                "outliers": [],
            },
        ],
    }
    (run_dir / "synthesis.json").write_text(json.dumps(syn, indent=2))

    # Self-audit — plugin format with robis_audit + source verification
    sa = {
        "robis_audit": {
            "domain_1_eligibility": {
                "risk": "Low",
                "notes": "All studies meet inclusion criteria",
                "assessment": "Comprehensive eligibility screening applied",
            },
            "domain_2_identification": {
                "risk": "Low",
                "notes": "Comprehensive search",
                "assessment": "Multiple databases searched systematically",
            },
            "overall_risk_of_bias": "Low",
            "overall_assessment": "The review process followed systematic methodology with minimal bias risk.",
        },
        "items": [
            {
                "id": "C001",
                "process_audit": {
                    "eligibility_criteria": {"rating": "Pass", "rationale": "Clear inclusion criteria applied"},
                    "search_comprehensiveness": {"rating": "Fail", "rationale": "Only one database searched"},
                    "evaluation_consistency": {"rating": "Pass", "rationale": "Consistent scoring methodology"},
                    "synthesis_fairness": {"rating": "Pass", "rationale": "Balanced weighing of evidence"},
                },
                "source_verification": {
                    "sources_verified": 3,
                    "discrepancies": [
                        {
                            "severity": "minor",
                            "source_url": "https://example.com/rlhf",
                            "claim_in_assessment": "RLHF fully eliminates sycophancy",
                            "actual_source_says": "RLHF reduces but does not eliminate sycophancy",
                        },
                    ],
                },
                "source_interpretation_verification": {
                    "sources_checked": 5,
                    "findings": "All sources interpreted correctly with minor nuance loss.",
                    "assessment": "Interpretation fidelity is high.",
                },
                "reading_list": [
                    {
                        "title": "RLHF Study",
                        "url": "https://example.com/rlhf",
                        "authors": "Jones et al.",
                        "date": "2025-03",
                        "content_summary": "Comprehensive study on RLHF and sycophancy reduction.",
                        "reason": "Primary evidence for the claim",
                        "priority": "must read",
                    },
                    {
                        "title": "Counter Study",
                        "url": "https://example.com/counter",
                        "authors": "Doe et al.",
                        "date": "2025-06",
                        "content_summary": "Study finding opposite effect.",
                        "summary": "Shows alternative perspective",
                        "priority": "should read",
                    },
                    {
                        "title": "Background Paper",
                        "url": "https://example.com/bg",
                        "priority": "reference",
                    },
                ],
            },
            {
                "id": "Q001",
                "process_audit": {
                    "eligibility_criteria": {"rating": "Pass", "rationale": "All sources peer-reviewed"},
                    "search_comprehensiveness": {"rating": "Pass", "rationale": "Multiple databases"},
                    "evaluation_consistency": {"rating": "Pass", "rationale": "Consistent"},
                    "synthesis_fairness": {"rating": "Pass", "rationale": "Balanced"},
                },
                "reading_list": [
                    {
                        "title": "Paper on Watermarking",
                        "url": "https://example.com/paper",
                        "authors": "Smith et al.",
                        "relevance": "Primary source",
                        "priority": "must read",
                    },
                ],
            },
        ],
    }
    (run_dir / "self-audit.json").write_text(json.dumps(sa, indent=2))

    # Reports — with all optional fields for item index coverage
    rp = {
        "reports": [
            {
                "id": "C001",
                "mode": "claim",
                "title": "RLHF and Sycophancy",
                "topic": "RLHF reduces sycophancy",
                "verdict": "Supported with caveats",
                "confidence": "Moderate",
                "verdict_summary": "RLHF training reduces sycophantic behavior with caveats",
                "one_line": "RLHF reduces sycophancy in controlled settings",
                "reasoning": "Multiple peer-reviewed studies confirm the finding with small sample caveats.",
                "assessment": {
                    "verdict": "Supported with caveats",
                    "confidence": "Moderate",
                    "hypothesis_ratings": [
                        {
                            "hypothesis_id": "C001-H1",
                            "probability_term": "Likely",
                            "probability_range": "70-85%",
                            "reasoning": "Three independent studies support this",
                        },
                    ],
                },
                "methodology": "Systematic review",
                "evidence_quality": "Moderate",
                "key_findings": ["RLHF reduces sycophancy"],
                "gaps_and_limitations": ["Small sample sizes"],
                "source_back_verification": [
                    {"claim": "RLHF reduces sycophancy", "source": "https://example.com/rlhf", "verified": True},
                ],
                "revisit_triggers": [
                    {"trigger": "New large-scale RLHF study published", "type": "evidence"},
                    {"trigger": "Major methodology update", "type": "methodology"},
                    {"trigger": "Dict trigger without type"},
                    "Simple string trigger without type",
                ],
            },
            {
                "id": "Q001",
                "mode": "query",
                "title": "AI Watermarking",
                "topic": "AI watermarking techniques",
                "answer_summary": "Statistical watermarking is the dominant approach",
                "confidence": "High",
                "assessment": {
                    "answer": "Statistical watermarking is the dominant approach",
                    "confidence": "High",
                },
                "methodology": "Literature review",
                "evidence_quality": "Strong",
                "key_findings": ["Statistical methods most common"],
                "gaps_and_limitations": ["Robustness testing limited"],
            },
        ],
    }
    (run_dir / "reports.json").write_text(json.dumps(rp, indent=2))

    # Pipeline events — with item-specific events
    pe = {
        "run_id": "run-1",
        "events": [
            {
                "kind": "fetch_failed",
                "detail": "timeout on https://slow.com",
                "step": "step5",
                "layer": "pipeline",
                "item_id": "C001",
                "url": "https://slow.com",
            },
        ],
        "summary": {
            "total_events": 1,
            "by_kind": {"fetch_failed": 1},
            "coverage": {
                "sources_selected": 2,
                "sources_scored": 1,
                "verbatim_adherence_pct": 50.0,
            },
        },
    }
    (run_dir / "pipeline-events.json").write_text(json.dumps(pe, indent=2))


class TestRenderRunPluginFormat:
    """Tests for render_run with plugin-format data covering uncovered branches."""

    def test_renders_all_plugin_format_files(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_plugin_format_run(run_dir)

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        # Index exists
        assert (output_dir / "index.md").exists()
        index_content = (output_dir / "index.md").read_text()
        assert "Run Overview" in index_content
        # Axiom rendered in index
        assert "Peer-reviewed sources preferred" in index_content
        # Collection self-audit rendered
        assert "Collection Self-Audit" in index_content
        assert "Overall risk of bias" in index_content

    def test_claim_item_files(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_plugin_format_run(run_dir)

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        # Find C001 directory
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        assert len(c001_dirs) == 1
        c001_dir = c001_dirs[0]

        # claim.md — input with assumptions, scope, vocabulary
        claim_content = (c001_dir / "claim.md").read_text()
        assert "Embedded Assumptions" in claim_content
        assert "LLMs exhibit sycophantic behavior" in claim_content
        assert "Scope" in claim_content
        assert "Vocabulary" in claim_content

        # assessment.md — full synthesis with IPCC, outliers, gaps
        assessment_content = (c001_dir / "assessment.md").read_text()
        assert "Evidence Synthesis" in assessment_content
        assert "IPCC assessment" in assessment_content
        assert "Agreement" in assessment_content
        assert "Evidence quality" in assessment_content
        assert "Source agreement" in assessment_content
        assert "Independence" in assessment_content
        assert "Outliers" in assessment_content
        assert "Probability Assessment" in assessment_content
        assert "Scale" in assessment_content or "scale" in assessment_content.lower()
        # Gaps as dict (expected_not_found, unanswered_questions, impact_on_confidence)
        assert "Expected but not found" in assessment_content
        assert "Unanswered questions" in assessment_content
        assert "Impact on confidence" in assessment_content
        # Hypothesis ratings in assessment
        assert "C001-H1" in assessment_content

        # self-audit.md — process audit + source verification + plugin verification
        audit_content = (c001_dir / "self-audit.md").read_text()
        assert "Process Audit" in audit_content
        assert "Source-Back Verification" in audit_content
        assert "Discrepancies" in audit_content
        assert "Source Interpretation Verification" in audit_content
        assert "Sources checked: 5" in audit_content

        # reading-list.md — entries by priority
        rl_content = (c001_dir / "reading-list.md").read_text()
        assert "Must Read" in rl_content
        assert "Should Read" in rl_content
        assert "Reference" in rl_content
        assert "Why read:" in rl_content
        assert "Jones et al." in rl_content

        # hypotheses — H1 and H2 detail files
        h1_path = c001_dir / "hypotheses" / "H1.md"
        assert h1_path.exists()
        h1_content = h1_path.read_text()
        assert "Statement" in h1_content
        assert "Falsification Target" in h1_content
        assert "Supporting Evidence" in h1_content
        assert "Eliminating Evidence" in h1_content

        # searches — S01 with execution log, selected/rejected tables
        search_log_path = c001_dir / "searches" / "S01" / "search-log.md"
        assert search_log_path.exists()
        search_content = search_log_path.read_text()
        assert "Query" in search_content
        assert "Execution Summary" in search_content
        assert "Selected Results" in search_content
        assert "Rejected Results" in search_content
        # Individual result files
        assert (c001_dir / "searches" / "S01" / "results" / "R01.md").exists()

        # sources — SRC001 scorecard with detailed bias, reliability, relevance
        src_path = c001_dir / "sources" / "SRC001" / "scorecard.md"
        assert src_path.exists()
        src_content = src_path.read_text()
        assert "Metadata" in src_content
        assert "Content Summary" in src_content
        assert "Reliability: High" in src_content
        assert "Peer-reviewed" in src_content
        assert "Relevance: Very High" in src_content
        assert "Bias Assessment" in src_content

        # item index.md — Evidence Snapshot, Revisit Triggers, pipeline status
        item_index = (c001_dir / "index.md").read_text()
        assert "Evidence Snapshot" in item_index
        assert "Revisit Triggers" in item_index
        assert "evidence" in item_index.lower()

    def test_query_item_files(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_plugin_format_run(run_dir)

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        # Find Q001 directory
        q001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("Q001")]
        assert len(q001_dirs) == 1
        q001_dir = q001_dirs[0]

        # Open-ended themes — T1 file
        t1_path = q001_dir / "hypotheses" / "T1.md"
        assert t1_path.exists()
        t1_content = t1_path.read_text()
        assert "Statistical watermarking" in t1_content
        assert "Derived from" in t1_content
        assert "Look for" in t1_content
        assert "Perspectives" in t1_content


class TestRenderRunWithoutSourceVerificationDiscrepancies:
    """Test self-audit branch where source_verification has no discrepancies."""

    def test_no_discrepancies(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_plugin_format_run(run_dir)

        # Override self-audit with no discrepancies
        sa = json.loads((run_dir / "self-audit.json").read_text())
        for item in sa["items"]:
            if item["id"] == "C001":
                item["source_verification"] = {
                    "sources_verified": 3,
                    "discrepancies": [],
                }
        (run_dir / "self-audit.json").write_text(json.dumps(sa, indent=2))

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        audit_content = (c001_dirs[0] / "self-audit.md").read_text()
        assert "No discrepancies found" in audit_content


class TestRenderRunFallbackReadingList:
    """Test reading-list fallback to scorecards when no reading_list in audit."""

    def test_falls_back_to_scorecards(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_plugin_format_run(run_dir)

        # Override self-audit to remove reading_list
        sa = json.loads((run_dir / "self-audit.json").read_text())
        for item in sa["items"]:
            item.pop("reading_list", None)
        (run_dir / "self-audit.json").write_text(json.dumps(sa, indent=2))

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        rl_content = (c001_dirs[0] / "reading-list.md").read_text()
        # Should fall back to sources table
        assert "Sources" in rl_content
        assert "Reliability" in rl_content


class TestRenderRunCollectionStatsPluginFormat:
    """Test collection statistics from search_execution_log (plugin format)."""

    def test_execution_log_stats(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_plugin_format_run(run_dir)

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        index_content = (output_dir / "index.md").read_text()
        # Plugin format should show searches executed and results dispositioned
        assert "Searches executed" in index_content
        assert "Results dispositioned" in index_content


class TestSourceScorecardBiasFormats:
    """Test bias_assessment rendering for dict, string, and other formats."""

    def test_bias_as_other_type(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_plugin_format_run(run_dir)

        # Override scorecards to have a numeric bias assessment
        sc = json.loads((run_dir / "scorecards.json").read_text())
        sc["sources"][0]["bias_assessment"] = {
            "selection_bias": 42,
            "another_bias": "Medium - some concerns present",
        }
        (run_dir / "scorecards.json").write_text(json.dumps(sc, indent=2))

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        src_content = (c001_dirs[0] / "sources" / "SRC001" / "scorecard.md").read_text()
        assert "Bias Assessment" in src_content
        assert "42" in src_content


class TestReliabilityRelevanceRationale:
    """Test reliability and relevance with string rationale fields."""

    def test_string_reliability_with_rationale(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_plugin_format_run(run_dir)

        # Override scorecards to have string reliability with separate rationale field
        sc = json.loads((run_dir / "scorecards.json").read_text())
        sc["sources"][0]["reliability"] = "High"
        sc["sources"][0]["reliability_rationale"] = "From a top journal"
        sc["sources"][0]["relevance"] = "Very High"
        sc["sources"][0]["relevance_rationale"] = "Core topic match"
        (run_dir / "scorecards.json").write_text(json.dumps(sc, indent=2))

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        src_content = (c001_dirs[0] / "sources" / "SRC001" / "scorecard.md").read_text()
        assert "Reliability: High" in src_content
        assert "From a top journal" in src_content
        assert "Relevance: Very High" in src_content
        assert "Core topic match" in src_content


class TestRenderRunRobisAuditFallback:
    """Test that per-item self-audit falls back to global robis_audit when item has no audit."""

    def test_robis_audit_on_item_page(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        _create_plugin_format_run(run_dir)

        # Override audit to remove the per-item audit for C001 so it falls back to global
        sa = {
            "robis_audit": {
                "domain_1_eligibility": {
                    "risk": "Low",
                    "assessment": "Good eligibility screening",
                },
                "overall_risk_of_bias": "Low",
                "overall_assessment": "Systematic methodology followed.",
            },
            "items": [
                {
                    "id": "Q001",
                    "process_audit": {},
                },
            ],
        }
        (run_dir / "self-audit.json").write_text(json.dumps(sa, indent=2))

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        # C001 should get the global robis_audit since it has no per-item audit
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        assert len(c001_dirs) == 1
        audit_content = (c001_dirs[0] / "self-audit.md").read_text()
        assert "ROBIS Audit" in audit_content
        assert "Overall Assessment" in audit_content
        assert "Systematic methodology" in audit_content


class TestRenderRunItemWithNoId:
    """Test that items with no ID are skipped gracefully."""

    def test_item_without_id_skipped(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()

        ri = {
            "items": [
                {"type": "claim", "text": "No ID claim"},
                {
                    "id": "C001",
                    "type": "claim",
                    "text": "Has ID",
                    "original_text": "Has ID",
                    "clarified_text": "Has ID claim",
                },
            ],
        }
        (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
        for f in [
            "hypotheses.json",
            "search-plans.json",
            "search-results.json",
            "scorecards.json",
            "synthesis.json",
            "self-audit.json",
            "reports.json",
        ]:
            (run_dir / f).write_text("{}")

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        # Only C001 dir should exist, no-id item should be skipped
        item_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
        assert len(item_dirs) == 1
        assert item_dirs[0].name.startswith("C001")


class TestItemIndexWithoutOptionalSections:
    """Test item index when optional sections are absent."""

    def test_minimal_item_index(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()

        # Minimal run with just a query, no hypotheses or synthesis
        ri = {
            "items": [
                {
                    "id": "Q001",
                    "type": "query",
                    "text": "Simple query",
                    "original_text": "Simple query",
                    "clarified_text": "Simple query",
                },
            ],
        }
        (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
        (run_dir / "hypotheses.json").write_text("{}")
        (run_dir / "search-plans.json").write_text("{}")
        (run_dir / "search-results.json").write_text("{}")
        (run_dir / "scorecards.json").write_text("{}")
        (run_dir / "synthesis.json").write_text("{}")
        (run_dir / "self-audit.json").write_text("{}")
        (run_dir / "reports.json").write_text("{}")

        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)

        assert (output_dir / "index.md").exists()
        q001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("Q001")]
        assert len(q001_dirs) == 1
        item_index = (q001_dirs[0] / "index.md").read_text()
        assert "Results" in item_index


def _create_rich_cli_run(run_dir: Path) -> None:
    """Create a CLI-format run with rich optional fields.

    Exercises branches that appear when optional fields are populated:
    - gaps as list (not dict)
    - synthesis with evidence_summary, ipcc_* fields
    - assessment with scale, probability_label, rationale
    - outliers, independence, revisit_triggers
    - search_execution_log at top level
    - audit with robis_audit domain fields
    """
    # Research input — axiom-only item to exercise that branch too
    ri = {
        "claims": [
            {
                "id": "C001",
                "type": "claim",
                "text": "Test claim",
                "clarified_text": "Test claim clarified",
                "original_text": "Test claim",
            },
        ],
        "queries": [],
        "axioms": [{"id": "A001", "type": "axiom", "text": "Peer review preferred"}],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))

    # Hypotheses — with derived_from, look_for, perspectives
    hyp = {
        "C001": {
            "id": "C001",
            "approach": "open-ended",
            "search_themes": [
                {
                    "id": "T01",
                    "theme": "Primary theme",
                    "derived_from": "axiom A001",
                    "look_for": ["evidence A", "evidence B"],
                    "perspectives": ["supports", "contradicts"],
                },
            ],
        },
    }
    (run_dir / "hypotheses.json").write_text(json.dumps(hyp))

    # Search plans
    sp = {
        "C001": {
            "id": "C001",
            "searches": [
                {
                    "id": "S01",
                    "terms": ["test"],
                    "theme": "Primary theme",
                    "sources": ["academic databases"],
                },
            ],
        },
    }
    (run_dir / "search-plans.json").write_text(json.dumps(sp))

    # Search results with top-level execution_log (plugin-format)
    sr = {
        "C001": {
            "id": "C001",
            "searches_executed": [],
            "selected_sources": [{"url": "https://a.com", "title": "Paper A"}],
            "rejected_sources": [],
            "summary": {
                "total_searches": 1,
                "total_results_found": 2,
                "total_selected": 1,
                "total_rejected": 1,
                "relevance_threshold": 5,
            },
        },
        "search_execution_log": [
            {
                "search_id": "S01",
                "id": "S01",
                "query": "test query",
                "results": [
                    {
                        "disposition": "selected",
                        "title": "Good Result",
                        "url": "https://a.com",
                        "relevance_score": 8,
                        "reason": "directly relevant",
                    },
                    {
                        "disposition": "rejected",
                        "title": "Bad Result",
                        "url": "https://b.com",
                        "relevance_score": 2,
                        "reason": "off-topic",
                    },
                ],
                "total_returned": 2,
            }
        ],
    }
    (run_dir / "search-results.json").write_text(json.dumps(sr))

    # Scorecards with plugin format (top-level sources list)
    sc = {
        "sources": [
            {
                "id": "SRC001",
                "item_id": "C001",
                "url": "https://a.com",
                "title": "Paper A",
                "authors": "Author A",
                "publication_date": "2025",
                "content_summary": "Summary A",
                "reliability_score": 8,
                "relevance_score": 9,
                "content_extract": "Extract A",
            },
        ],
    }
    (run_dir / "scorecards.json").write_text(json.dumps(sc))

    # Evidence packets
    ep = {
        "C001": {
            "id": "C001",
            "packets": [{"excerpt": "quote", "source_url": "https://a.com"}],
            "verbatim_stats": {"claimed": 1, "kept": 1, "dropped": 0},
        },
    }
    (run_dir / "evidence-packets.json").write_text(json.dumps(ep))

    # Synthesis with plugin-style fields: evidence_summary, ipcc axes, independence
    syn = {
        "C001": {
            "id": "C001",
            "synthesis": {
                "evidence_summary": "Summary of evidence",
                "ipcc_combined": "Likely (66-100%)",
                "ipcc_agreement_axis": "High agreement",
                "ipcc_evidence_axis": "Robust evidence",
                "evidence_quality": {"rating": "High", "rationale": "Strong sources"},
                "source_agreement": {"rating": "Strong", "rationale": "Consensus"},
                "independence": {"assessment": "Independent sources"},
                "outliers": [
                    {
                        "source_url": "https://outlier.com",
                        "divergence": "disagrees",
                        "explanation": "different methodology",
                    },
                ],
            },
            "assessment": {
                "scale": "IPCC-style",
                "probability_label": "Likely",
                "probability_range": "66-100%",
                "rationale": "Based on multiple studies",
                "hypothesis_disposition": {"H1": "Supported"},
                "verdict": "Supported",
                "confidence": "High",
                "hypothesis_ratings": [
                    {
                        "hypothesis_id": "H1",
                        "probability_term": "Likely",
                        "probability_range": "66-100%",
                        "reasoning": "Evidence chain",
                    },
                ],
            },
            # Plugin format: gaps as list
            "gaps": ["gap one", "gap two"],
        },
    }
    (run_dir / "synthesis.json").write_text(json.dumps(syn))

    # Self-audit with robis_audit (plugin format: global)
    sa = {
        "robis_audit": {
            "domain_1_eligibility": {"risk": "Low"},
            "domain_2_identification": {"risk": "Moderate"},
            "overall_risk_of_bias": "Low",
        },
        "C001": {
            "id": "C001",
            "process_audit": {
                "eligibility_criteria": {"rating": "Pass", "notes": "OK"},
                "search_comprehensiveness": {"rating": "Pass", "notes": "OK"},
                "evaluation_consistency": {"rating": "Pass", "notes": "OK"},
                "synthesis_fairness": {"rating": "Pass", "notes": "OK"},
            },
            "reading_list": [
                {
                    "title": "Paper A",
                    "url": "https://a.com",
                    "authors": "Author A",
                    "relevance": "Primary",
                    "priority": "high",
                },
            ],
        },
    }
    (run_dir / "self-audit.json").write_text(json.dumps(sa))

    # Reports with revisit_triggers, CLI-format gaps dict, and more optional fields
    rp = {
        "C001": {
            "id": "C001",
            "mode": "claim",
            "topic": "Test topic",
            "title": "Paper Title",
            "verdict": "Supported",
            "verdict_summary": "Evidence supports the claim",
            "one_line": "Claim is supported",
            "assessment_summary": {"verdict": "Supported", "answer": "Yes", "confidence": "High"},
            "reasoning": "Reasoning text",
            "reasoning_chain": "Chain of reasoning",
            "methodology": "Method",
            "evidence_quality": "Moderate",
            "key_findings": ["Finding A"],
            "gaps_and_limitations": ["Limit A"],
            "assessment": {
                "hypothesis_ratings": [
                    {
                        "hypothesis_id": "H1",
                        "probability_term": "Likely",
                        "probability_range": "66-100%",
                    },
                ],
            },
            "revisit_triggers": [
                {"trigger": "New study published", "type": "event"},
                {"trigger": "Quarterly review"},  # No type
                "simple string trigger",  # Non-dict trigger
            ],
        },
    }
    (run_dir / "reports.json").write_text(json.dumps(rp))

    # Pipeline events — minimal
    pe = {"events": [], "summary": {"by_kind": {}, "coverage": {}}}
    (run_dir / "pipeline-events.json").write_text(json.dumps(pe))


class TestRenderRunRichCli:
    """Tests for render_run with rich optional fields in CLI format."""

    def test_rich_cli_run(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-rich"
        run_dir.mkdir()
        _create_rich_cli_run(run_dir)
        output_dir = tmp_path / "md-rich"
        render_run(run_dir, output_dir)
        # Verify it produced files
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) >= 3
        # Verify rich synthesis fields rendered
        assessment = (output_dir / "C001-test-claim-clarified" / "assessment.md").read_text()
        assert "IPCC assessment" in assessment
        assert "Summary of evidence" in assessment


class TestCollectHypothesisRatingsEdgeCases:
    """Cover branches in _collect_hypothesis_ratings."""

    def test_non_dict_report(self) -> None:
        """Covers 322->333: isinstance(report, dict) is False."""
        result = _collect_hypothesis_ratings("not a dict", {})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        assert result == {}

    def test_non_dict_synthesis(self) -> None:
        """Covers the False path for synthesis being non-dict."""
        result = _collect_hypothesis_ratings({}, "not a dict")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        assert result == {}

    def test_non_dict_assessment_in_report(self) -> None:
        """Covers 324->333: assessment is not a dict."""
        result = _collect_hypothesis_ratings({"assessment": "not a dict"}, {})
        assert result == {}

    def test_disposition_non_dict(self) -> None:
        """Covers the False path when hypothesis_disposition is not a dict."""
        synthesis = {"assessment": {"hypothesis_disposition": "not a dict"}}
        result = _collect_hypothesis_ratings({}, synthesis)
        assert result == {}

    def test_rating_without_probability_term(self) -> None:
        """Covers the else branch: no probability_term, just range."""
        report = {
            "assessment": {
                "hypothesis_ratings": [
                    {"hypothesis_id": "H1", "probability_range": "50-75%"},
                ],
            }
        }
        result = _collect_hypothesis_ratings(report, {})
        assert result["H1"] == "50-75%"

    def test_rating_without_hypothesis_id(self) -> None:
        """Covers the False branch when hyp_id is empty/missing."""
        report = {
            "assessment": {
                "hypothesis_ratings": [
                    {"probability_term": "Likely"},  # Missing hypothesis_id
                ],
            }
        }
        result = _collect_hypothesis_ratings(report, {})
        assert result == {}

    def test_plugin_disposition_preserves_cli(self) -> None:
        """Covers the 'hyp_id not in ratings' check — CLI rating wins over plugin."""
        report = {
            "assessment": {
                "hypothesis_ratings": [
                    {"hypothesis_id": "H1", "probability_term": "Certain", "probability_range": "95-100%"},
                ],
            }
        }
        synthesis = {"assessment": {"hypothesis_disposition": {"H1": "Overridden"}}}
        result = _collect_hypothesis_ratings(report, synthesis)
        assert "Certain" in result["H1"]


class TestExtractSourcesForItemExtra:
    """Additional edge cases for _extract_sources_for_item."""

    def test_empty_sources_list(self) -> None:
        """Covers the branch where sources_list exists but no matches."""
        scorecards: dict[str, Any] = {"sources": []}
        result = _extract_sources_for_item(scorecards, "C001")
        assert result == []

    def test_cli_item_not_dict(self) -> None:
        """Covers False branch: item_data is not a dict."""
        scorecards = {"C001": "not a dict"}
        result = _extract_sources_for_item(scorecards, "C001")
        assert result == []


class TestWriteHypothesesEmpty:
    """Cover the early-return path in _write_hypotheses."""

    def test_empty_hypotheses(self, tmp_path: Path) -> None:
        """Covers line 1021: `return` when hyps is empty."""
        from diogenes.renderer import _write_hypotheses

        item_dir = tmp_path / "item"
        item_dir.mkdir()
        # Empty hypotheses list
        _write_hypotheses(item_dir, {"id": "C001", "approach": "hypotheses", "hypotheses": []}, {}, {})
        # No hypotheses/ directory should have been created
        assert not (item_dir / "hypotheses").exists()


class TestWriteSearchesEmpty:
    """Cover the early-return path in _write_searches."""

    def test_empty_searches(self, tmp_path: Path) -> None:
        """Covers line 1417: `return` when searches is empty."""
        from diogenes.renderer import _write_searches

        item_dir = tmp_path / "item"
        item_dir.mkdir()
        _write_searches(item_dir, "C001", {"searches": []}, {}, {}, {})
        assert not (item_dir / "searches").exists()

    def test_no_item_plan(self, tmp_path: Path) -> None:
        """Covers `if not item_plan` branch."""
        from diogenes.renderer import _write_searches

        item_dir = tmp_path / "item"
        item_dir.mkdir()
        _write_searches(item_dir, "C001", {}, {}, {}, {})
        assert not (item_dir / "searches").exists()


def _create_minimal_run(run_dir: Path) -> None:
    """Create a run with minimal/absent optional fields to flip conditionals to False.

    Exercises branches where optional data is missing: no gaps, no outliers,
    no revisit_triggers, no ipcc, no evidence_quality rating, no scale, etc.
    Also uses plugin-style flat output for items.
    """
    ri = {
        "claims": [
            {
                "id": "C001",
                "type": "claim",
                "text": "Minimal claim",
                "clarified_text": "Minimal claim clarified",
                "original_text": "Minimal claim",
            },
        ],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))

    # Hypotheses with no optional fields
    hyp = {
        "C001": {
            "id": "C001",
            "approach": "hypotheses",
            "hypotheses": [
                {"id": "H1", "text": "H1 text"},  # No direction, no label
            ],
        },
    }
    (run_dir / "hypotheses.json").write_text(json.dumps(hyp))

    sp = {"C001": {"id": "C001", "searches": []}}
    (run_dir / "search-plans.json").write_text(json.dumps(sp))

    sr = {
        "C001": {
            "id": "C001",
            "searches_executed": [],
            "selected_sources": [],
            "rejected_sources": [],
            "summary": {
                "total_searches": 0,
                "total_results_found": 0,
                "total_selected": 0,
                "total_rejected": 0,
                "relevance_threshold": 5,
            },
        },
    }
    (run_dir / "search-results.json").write_text(json.dumps(sr))

    sc = {"C001": {"id": "C001", "scorecards": []}}
    (run_dir / "scorecards.json").write_text(json.dumps(sc))

    ep = {
        "C001": {
            "id": "C001",
            "packets": [],
        },
    }
    (run_dir / "evidence-packets.json").write_text(json.dumps(ep))

    # Synthesis: evidence_quality/source_agreement have NO rating
    syn = {
        "C001": {
            "id": "C001",
            "synthesis": {
                "evidence_quality": {"rationale": "no rating here"},
                "source_agreement": {"rationale": "no rating here"},
                "independence": {},
                "outliers": [],
            },
            "assessment": {
                "verdict": "Inconclusive",
                "confidence": "Low",
            },
            # Empty gaps list
            "gaps": [],
        },
    }
    (run_dir / "synthesis.json").write_text(json.dumps(syn))

    sa = {
        "C001": {
            "id": "C001",
            "process_audit": {},
            "reading_list": [],
        },
    }
    (run_dir / "self-audit.json").write_text(json.dumps(sa))

    # Reports with no verdict, no summary, no reasoning, no key findings
    rp = {
        "C001": {
            "id": "C001",
            "mode": "claim",
            "assessment_summary": {},
            "revisit_triggers": [],
        },
    }
    (run_dir / "reports.json").write_text(json.dumps(rp))


def _create_cli_dict_gaps_run(run_dir: Path) -> None:
    """Create a run with CLI-style gaps as dict (expected_not_found, unanswered_questions)."""
    ri = {
        "claims": [
            {
                "id": "C001",
                "type": "claim",
                "text": "Gap test",
                "clarified_text": "Gap test",
                "original_text": "Gap test",
            },
        ],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))

    # CLI-format gaps as dict
    syn = {
        "C001": {
            "id": "C001",
            "synthesis": "synthesis as string",
            "gaps": {
                "expected_not_found": ["study A", "study B"],
                "unanswered_questions": ["question 1"],
                "impact_on_confidence": "Moderate impact",
            },
            "assessment": {"verdict": "Unclear"},
        },
    }
    (run_dir / "synthesis.json").write_text(json.dumps(syn))

    sa = {"C001": {"id": "C001", "process_audit": {}, "reading_list": []}}
    (run_dir / "self-audit.json").write_text(json.dumps(sa))
    rp = {"C001": {"id": "C001", "mode": "claim", "assessment_summary": {}}}
    (run_dir / "reports.json").write_text(json.dumps(rp))


class TestRenderRunMinimal:
    """Tests for render_run with minimal optional fields (False branches)."""

    def test_minimal_run_renders(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-min"
        run_dir.mkdir()
        _create_minimal_run(run_dir)
        output_dir = tmp_path / "md-min"
        render_run(run_dir, output_dir)
        # Should produce at least index.md
        assert (output_dir / "index.md").exists()


class TestRenderRunCliDictGaps:
    """Tests for render_run with CLI-format dict gaps."""

    def test_cli_dict_gaps(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-gaps"
        run_dir.mkdir()
        _create_cli_dict_gaps_run(run_dir)
        output_dir = tmp_path / "md-gaps"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        assessment = (c001_dirs[0] / "assessment.md").read_text()
        assert "Expected but not found" in assessment
        assert "Unanswered questions" in assessment
        assert "Impact on confidence" in assessment


class TestAddTocEdgeCases:
    """Target remaining branches in _add_toc."""

    def test_anchor_from_preceding_line(self) -> None:
        """Cover 257->267: anchor found in preceding line (no new anchor needed)."""
        lines = [
            "# Title",
            "",
            '<a id="custom-anchor"></a>',
            "## Section One",
            "",
            "text",
            "",
            "## Section Two",
            "",
            "more text",
        ]
        result = _add_toc(lines)
        # Should include the custom anchor in TOC
        assert any("custom-anchor" in l for l in result)

    def test_no_blank_after_title(self) -> None:
        """Cover 291->294: result[insert_at].strip() is truthy (no blank line)."""
        lines = ["# Title", "## Section One", "", "## Section Two", "", "text"]
        result = _add_toc(lines)
        assert "<!-- TOC START -->" in "\n".join(result)


class TestCollectHypothesisRatingsCompletion:
    """Cover remaining _collect_hypothesis_ratings branches."""

    def test_hyp_id_already_in_ratings_from_cli(self) -> None:
        """Cover 335->342: plugin disposition skipped because hyp_id already in ratings."""
        report = {
            "assessment": {
                "hypothesis_ratings": [
                    {"hypothesis_id": "H1", "probability_term": "Likely", "probability_range": "66%"},
                ],
            },
        }
        synthesis = {"assessment": {"hypothesis_disposition": {"H1": "overridden", "H2": "only-plugin"}}}
        result = _collect_hypothesis_ratings(report, synthesis)
        # H1 comes from CLI, H2 comes from plugin
        assert "Likely" in result["H1"]
        assert result["H2"] == "only-plugin"


def _create_run_with_assessment_variants(
    run_dir: Path,
    *,
    include_report: bool = True,
    include_verdict_chain: bool = False,
    assessment_empty: bool = False,
    gaps_dict_empty: bool = False,
) -> None:
    """Build a configurable fixture for assessment rendering variants."""
    from typing import Any

    ri = {
        "claims": [
            {
                "id": "C001",
                "type": "claim",
                "text": "Test",
                "clarified_text": "Test",
                "original_text": "Test",
            },
        ],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))

    syn_data: dict[str, Any] = {"id": "C001"}
    if assessment_empty:
        syn_data["assessment"] = {}
    else:
        syn_data["assessment"] = {"verdict": "V", "confidence": "C"}
    if gaps_dict_empty:
        syn_data["gaps"] = {}
    else:
        syn_data["gaps"] = []

    (run_dir / "synthesis.json").write_text(json.dumps({"C001": syn_data}))
    (run_dir / "self-audit.json").write_text(
        json.dumps({"C001": {"id": "C001", "process_audit": {}, "reading_list": []}})
    )

    if include_report:
        rp_item = {"id": "C001", "mode": "claim", "assessment_summary": {}}
        if include_verdict_chain:
            rp_item["verdict"] = "verdict string"
            rp_item["reasoning_chain"] = "chain of reasoning"
        (run_dir / "reports.json").write_text(json.dumps({"C001": rp_item}))
    else:
        (run_dir / "reports.json").write_text(json.dumps({}))


class TestAssessmentRenderingVariants:
    """Cover branches in _write_assessment for various data shapes."""

    def test_no_report(self, tmp_path: Path) -> None:
        """Cover 1100->1112: report is falsy, skip verdict section."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_assessment_variants(run_dir, include_report=False)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        # Should still render assessment.md without report-based sections
        assert (c001_dirs[0] / "assessment.md").exists()

    def test_verdict_chain_reasoning(self, tmp_path: Path) -> None:
        """Cover reasoning_chain branch (vs just `reasoning`)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_assessment_variants(run_dir, include_verdict_chain=True)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        assessment = (c001_dirs[0] / "assessment.md").read_text()
        assert "verdict string" in assessment
        assert "chain of reasoning" in assessment

    def test_empty_assessment_dict(self, tmp_path: Path) -> None:
        """Cover 1151->1181: assessment dict exists but is empty."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_assessment_variants(run_dir, assessment_empty=True)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        # Should render but without Probability Assessment section
        assessment = (c001_dirs[0] / "assessment.md").read_text()
        assert "Probability Assessment" not in assessment

    def test_empty_gaps_dict(self, tmp_path: Path) -> None:
        """Cover 1190->1208: gaps is dict but empty (no expected/unanswered/impact)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_assessment_variants(run_dir, gaps_dict_empty=True)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        # Should render without crashing


def _create_run_with_search_variants(run_dir: Path) -> None:
    """Build a fixture with search variants to flip _write_searches branches."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )

    # Multiple searches with variants: no terms, no theme, no target_hypothesis
    sp = {
        "C001": {
            "id": "C001",
            "searches": [
                {"id": "S01"},  # No terms, no theme
                {"id": "S02", "terms": [], "theme": ""},  # Empty terms, empty theme
                {"id": "S03", "terms": ["t1"], "sources": []},  # Empty planned sources
            ],
        },
    }
    (run_dir / "search-plans.json").write_text(json.dumps(sp))

    # search_execution_log variants: empty query, no results, all selected, all rejected
    sr = {
        "C001": {
            "id": "C001",
            "searches_executed": [],
            "selected_sources": [],
            "rejected_sources": [],
            "summary": {
                "total_searches": 3,
                "total_results_found": 0,
                "total_selected": 0,
                "total_rejected": 0,
                "relevance_threshold": 5,
            },
        },
        "search_execution_log": [
            {"id": "S01", "query": "", "results": []},  # No results, empty query
            {
                "id": "S02",
                "query": "q2",
                "results": [
                    {"disposition": "selected", "title": "Sel", "url": "u1", "relevance_score": 9},  # no reason
                ],
            },
            {
                "id": "S03",
                "query": "q3",
                "results": [
                    {"disposition": "rejected", "title": "Rej", "url": "u2", "relevance_score": 1, "reason": "off"},
                ],
            },
        ],
    }
    (run_dir / "search-results.json").write_text(json.dumps(sr))

    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))
    (run_dir / "synthesis.json").write_text(json.dumps({"C001": {"id": "C001", "gaps": []}}))
    (run_dir / "self-audit.json").write_text(
        json.dumps({"C001": {"id": "C001", "process_audit": {}, "reading_list": []}})
    )
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestSearchRenderingVariants:
    """Cover branches in _write_searches."""

    def test_search_variants(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_search_variants(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        # Each search should have its own log
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        searches_dir = c001_dirs[0] / "searches"
        assert (searches_dir / "S01").exists()
        assert (searches_dir / "S02").exists()
        assert (searches_dir / "S03").exists()


def _create_run_with_sources_variants(run_dir: Path) -> None:
    """Build a fixture with source scorecard variants to flip _write_sources branches."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )

    # Scorecards with variants: minimal (just url), full, with bias dict, dict reliability
    sc = {
        "C001": {
            "id": "C001",
            "scorecards": [
                {"url": "https://a.com"},  # Minimal
                {
                    "url": "https://b.com",
                    "title": "Paper B",
                    "authors": "A. Author",
                    "publication_date": "2025",
                    "content_summary": "Summary",
                    "reliability_score": 8,
                    "relevance_score": 9,
                    "bias_assessment": "Low bias",
                    "content_extract": "Full extract text",
                },
                {
                    "url": "https://c.com",
                    "title": "Paper C",
                    # Dict bias instead of string
                    "bias_assessment": {"rating": "Medium", "rationale": "known issue"},
                    # Dict reliability/relevance instead of int
                    "reliability_score": {"rating": 7, "rationale": "peer-reviewed"},
                    "relevance_score": {"rating": 6, "rationale": "tangential"},
                },
            ],
        },
    }
    (run_dir / "scorecards.json").write_text(json.dumps(sc))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))
    (run_dir / "synthesis.json").write_text(json.dumps({"C001": {"id": "C001", "gaps": []}}))
    (run_dir / "self-audit.json").write_text(
        json.dumps({"C001": {"id": "C001", "process_audit": {}, "reading_list": []}})
    )
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestSourcesRenderingVariants:
    """Cover branches in _write_sources."""

    def test_sources_variants(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_sources_variants(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        sources_dir = c001_dirs[0] / "sources"
        assert sources_dir.exists()
        # Should have SRC001, SRC002, SRC003 scorecards
        scorecards = list(sources_dir.rglob("scorecard.md"))
        assert len(scorecards) == 3


def _create_run_with_self_audit_variants(run_dir: Path) -> None:
    """Build a fixture with self-audit variants to flip _write_self_audit branches."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))
    (run_dir / "synthesis.json").write_text(json.dumps({"C001": {"id": "C001", "gaps": []}}))

    # Self-audit with source_verification, sensitivity_analysis, and robis_audit
    sa = {
        "C001": {
            "id": "C001",
            "process_audit": {
                "eligibility_criteria": {"rating": "Pass", "notes": ""},  # Empty notes
                "search_comprehensiveness": {"rating": "", "notes": "notes only"},  # No rating
            },
            "source_verification": {
                "sources_verified": 5,
                "discrepancies": [
                    {"source_url": "https://a.com", "issue": "wrong quote"},
                ],
            },
            "sensitivity_analysis": {
                "robustness": "Good",
                "alternative_interpretations": ["alt 1", "alt 2"],
            },
            "robis_audit": {
                "domain_1_eligibility": {"risk": "Low"},
            },
            "reading_list": [
                {"title": "P", "url": "https://x.com"},  # Minimal reading list entry
            ],
        },
    }
    (run_dir / "self-audit.json").write_text(json.dumps(sa))
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestSelfAuditVariants:
    """Cover branches in _write_self_audit and related writers."""

    def test_self_audit_variants(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_self_audit_variants(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        audit = (c001_dirs[0] / "self-audit.md").read_text()
        # Should include discrepancies section and sensitivity
        assert "discrepancies" in audit.lower() or "Source Verification" in audit


def _create_run_no_synthesis_or_audit(run_dir: Path) -> None:
    """Fixture where synthesis and audit are absent per-item, so assessment.md/self-audit.md don't get written."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(json.dumps({}))  # Empty hypotheses
    (run_dir / "search-plans.json").write_text(json.dumps({}))
    (run_dir / "search-results.json").write_text(json.dumps({}))
    (run_dir / "scorecards.json").write_text(json.dumps({}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({}))
    (run_dir / "synthesis.json").write_text(json.dumps({}))  # No per-item synthesis
    (run_dir / "self-audit.json").write_text(json.dumps({}))  # No per-item audit
    (run_dir / "reports.json").write_text(json.dumps({}))


class TestItemWithoutSynthesisOrAudit:
    """Cover branches where assessment.md/self-audit.md don't exist."""

    def test_no_synthesis_or_audit(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_no_synthesis_or_audit(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        # Should still render the index
        assert (output_dir / "index.md").exists()


def _create_run_minimal_item(run_dir: Path) -> None:
    """Item with no clarified/original text at all, to flip has_summary False."""
    ri = {
        "claims": [{"id": "C001", "type": "claim"}],  # No text fields at all
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(json.dumps({}))
    (run_dir / "search-plans.json").write_text(json.dumps({}))
    (run_dir / "search-results.json").write_text(json.dumps({}))
    (run_dir / "scorecards.json").write_text(json.dumps({}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({}))
    (run_dir / "synthesis.json").write_text(json.dumps({}))
    (run_dir / "self-audit.json").write_text(json.dumps({}))
    (run_dir / "reports.json").write_text(json.dumps({}))


class TestItemWithoutAnyText:
    """Cover has_summary=False branch."""

    def test_item_without_text(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_minimal_item(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        assert (output_dir / "index.md").exists()


class TestRenderRunEmptyItems:
    """Cover branches when the run has no items at all."""

    def test_render_run_no_items(self, tmp_path: Path) -> None:
        """Covers 563->572: toc_entries empty, no card sections."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        ri: dict[str, Any] = {"claims": [], "queries": [], "axioms": []}
        (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
        for fname in (
            "hypotheses.json",
            "search-plans.json",
            "search-results.json",
            "scorecards.json",
            "evidence-packets.json",
            "synthesis.json",
            "self-audit.json",
            "reports.json",
        ):
            (run_dir / fname).write_text("{}")
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        assert (output_dir / "index.md").exists()


def _create_run_with_item_no_id(run_dir: Path) -> None:
    """Item without an id field to hit 644->575 (continue branch in card loop)."""
    ri = {
        "claims": [
            {"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"},
            {"type": "claim", "text": "No id"},  # No id - should be skipped
        ],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    for fname in (
        "hypotheses.json",
        "search-plans.json",
        "search-results.json",
        "scorecards.json",
        "evidence-packets.json",
        "synthesis.json",
        "self-audit.json",
        "reports.json",
    ):
        (run_dir / fname).write_text("{}")


class TestRenderRunItemWithoutIdInCards:
    """Cover 644->575: continue on item without id."""

    def test_item_no_id_in_cards(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_item_no_id(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        # Only C001 should render as a card
        index = (output_dir / "index.md").read_text()
        assert "C001" in index


def _create_run_with_robis_no_overall(run_dir: Path) -> None:
    """Self-audit with robis_audit missing overall_risk_of_bias to hit 699->703 False."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))
    (run_dir / "synthesis.json").write_text(json.dumps({"C001": {"id": "C001", "gaps": []}}))

    # Global robis_audit with no overall_risk_of_bias, with a non-dict domain value
    sa = {
        "robis_audit": {
            "domain_1_eligibility": {"risk": "Low"},
            "domain_2_bad": "not a dict",  # Hits 694->692 False
            # No overall_risk_of_bias — hits 699->703 False
        },
        "C001": {"id": "C001", "process_audit": {}, "reading_list": []},
    }
    (run_dir / "self-audit.json").write_text(json.dumps(sa))
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestRobisAuditBranches:
    """Cover robis_audit rendering branches."""

    def test_robis_no_overall_and_bad_domain(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_robis_no_overall(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        index = (output_dir / "index.md").read_text()
        # Should render the domain_1 rating but not the overall risk line
        assert "Domain 1 Eligibility" in index
        assert "Overall risk of bias" not in index


def _create_run_report_no_bluf_no_verdict(run_dir: Path) -> None:
    """Report dict exists but has no verdict_summary/answer_summary/one_line AND no verdict/confidence.

    Hits 811->813 and 818->820 False branches.
    """
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))
    (run_dir / "synthesis.json").write_text(json.dumps({"C001": {"id": "C001", "gaps": []}}))
    (run_dir / "self-audit.json").write_text(
        json.dumps({"C001": {"id": "C001", "process_audit": {}, "reading_list": []}})
    )
    # Report dict exists but missing verdict/summary fields
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim", "topic": "T"}}))


class TestReportWithoutBlufOrVerdict:
    """Cover 811->813 and 818->820: report dict without bluf/verdict fields."""

    def test_no_bluf_no_verdict(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_report_no_bluf_no_verdict(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        index = (c001_dirs[0] / "index.md").read_text()
        # Should not have Bottom Line or Verdict lines
        assert "Bottom Line:" not in index
        # Verdict may or may not appear depending on other sources


def _create_run_assessment_verdict_no_confidence(run_dir: Path) -> None:
    """Synthesis assessment has verdict but no confidence to hit 1174->1176 False."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))

    # Synthesis with verdict but NO confidence
    syn = {
        "C001": {
            "id": "C001",
            "assessment": {"verdict": "Supported"},  # No confidence key
            "gaps": [],
        },
    }
    (run_dir / "synthesis.json").write_text(json.dumps(syn))
    (run_dir / "self-audit.json").write_text(
        json.dumps({"C001": {"id": "C001", "process_audit": {}, "reading_list": []}})
    )
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestAssessmentVerdictNoConfidence:
    """Cover 1174->1176: verdict present, confidence absent."""

    def test_verdict_no_confidence(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_assessment_verdict_no_confidence(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        assessment = (c001_dirs[0] / "assessment.md").read_text()
        assert "Verdict**: Supported" in assessment
        assert "Confidence**" not in assessment


def _create_run_source_no_url_no_metadata(run_dir: Path) -> None:
    """Source with no URL and no other metadata to hit 1577->1579, 1586->1590 False."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )

    # Scorecard with no URL, no authors, no date, no items
    sc = {
        "C001": {
            "id": "C001",
            "scorecards": [
                {"title": "Bare source"},  # No URL, no metadata
            ],
        },
    }
    (run_dir / "scorecards.json").write_text(json.dumps(sc))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))
    (run_dir / "synthesis.json").write_text(json.dumps({"C001": {"id": "C001", "gaps": []}}))
    (run_dir / "self-audit.json").write_text(
        json.dumps({"C001": {"id": "C001", "process_audit": {}, "reading_list": []}})
    )
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestSourceBareMinimum:
    """Cover 1577->1579 and 1586->1590: source with no metadata fields."""

    def test_bare_source(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_source_no_url_no_metadata(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        # Should still produce a scorecard without crashing
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        scorecards = list((c001_dirs[0] / "sources").rglob("scorecard.md"))
        assert len(scorecards) == 1
        content = scorecards[0].read_text()
        # No metadata table since all fields absent
        assert "## Metadata" not in content


def _create_run_with_partial_gaps(run_dir: Path) -> None:
    """CLI-dict gaps with only SOME fields populated (expected empty, unanswered empty, etc.)."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))

    # gaps dict with ONLY impact_on_confidence (no expected_not_found, no unanswered)
    syn = {
        "C001": {
            "id": "C001",
            "gaps": {"impact_on_confidence": "Low impact"},
        },
    }
    (run_dir / "synthesis.json").write_text(json.dumps(syn))
    (run_dir / "self-audit.json").write_text(
        json.dumps({"C001": {"id": "C001", "process_audit": {}, "reading_list": []}})
    )
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestPartialGaps:
    """Cover 1192->1197, 1198->1203 False branches."""

    def test_only_impact_in_gaps(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_partial_gaps(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        assessment = (c001_dirs[0] / "assessment.md").read_text()
        assert "Impact on confidence" in assessment
        assert "Expected but not found" not in assessment
        assert "Unanswered questions" not in assessment


def _create_run_with_plugin_source_verification(run_dir: Path) -> None:
    """Audit with source_interpretation_verification (plugin format) varied fields."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))
    (run_dir / "synthesis.json").write_text(json.dumps({"C001": {"id": "C001", "gaps": []}}))

    # Self-audit with plugin-style source_interpretation_verification
    sa = {
        "C001": {
            "id": "C001",
            "process_audit": {},
            "source_interpretation_verification": {
                "sources_checked": 3,
                "findings": "Key findings text",
                "assessment": "Overall assessment text",
            },
            "reading_list": [],
        },
    }
    (run_dir / "self-audit.json").write_text(json.dumps(sa))
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestPluginSourceVerification:
    """Cover 1296->1299, 1299->1302, 1302->1306 branches."""

    def test_plugin_verification(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_plugin_source_verification(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        audit = (c001_dirs[0] / "self-audit.md").read_text()
        assert "Source Interpretation Verification" in audit
        assert "Sources checked: 3" in audit
        assert "Key findings text" in audit
        assert "Overall assessment text" in audit


def _create_run_with_empty_plugin_verification(run_dir: Path) -> None:
    """Audit with source_interpretation_verification that has NO sub-fields."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(json.dumps({"C001": {"id": "C001", "scorecards": []}}))
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))
    (run_dir / "synthesis.json").write_text(json.dumps({"C001": {"id": "C001", "gaps": {}}}))  # Empty gaps dict

    # Self-audit with empty source_interpretation_verification
    sa = {
        "C001": {
            "id": "C001",
            "process_audit": {},
            "source_interpretation_verification": {"other": "value"},  # No sources_checked/findings/assessment
            "reading_list": [],
        },
    }
    (run_dir / "self-audit.json").write_text(json.dumps(sa))
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestEmptyPluginVerificationAndGaps:
    """Cover 1204->1208, 1296->1299, 1299->1302, 1302->1306 False branches."""

    def test_empty_plugin_verification_fields(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_empty_plugin_verification(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        audit = (c001_dirs[0] / "self-audit.md").read_text()
        # The Source Interpretation Verification header is rendered but no sub-fields
        assert "Source Interpretation Verification" in audit
        assert "Sources checked:" not in audit


def _create_run_with_no_synthesis_for_item(run_dir: Path) -> None:
    """Item has scorecards but NO synthesis — assessment.md shouldn't be written."""
    ri = {
        "claims": [{"id": "C001", "type": "claim", "text": "T", "clarified_text": "T", "original_text": "T"}],
        "queries": [],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(ri))
    (run_dir / "hypotheses.json").write_text(
        json.dumps({"C001": {"id": "C001", "approach": "hypotheses", "hypotheses": []}})
    )
    (run_dir / "search-plans.json").write_text(json.dumps({"C001": {"id": "C001", "searches": []}}))
    (run_dir / "search-results.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "searches_executed": [],
                    "selected_sources": [],
                    "rejected_sources": [],
                    "summary": {
                        "total_searches": 0,
                        "total_results_found": 0,
                        "total_selected": 0,
                        "total_rejected": 0,
                        "relevance_threshold": 5,
                    },
                }
            }
        )
    )
    (run_dir / "scorecards.json").write_text(
        json.dumps(
            {
                "C001": {
                    "id": "C001",
                    "scorecards": [
                        {"url": "https://x.com", "title": "X", "reliability_score": 5, "relevance_score": 5},
                    ],
                }
            }
        )
    )
    (run_dir / "evidence-packets.json").write_text(json.dumps({"C001": {"id": "C001", "packets": []}}))
    # Synthesis: empty dict (no C001 key) — so item_synthesis is {} — falsy — _write_assessment NOT called
    (run_dir / "synthesis.json").write_text(json.dumps({}))
    (run_dir / "self-audit.json").write_text(
        json.dumps({"C001": {"id": "C001", "process_audit": {}, "reading_list": []}})
    )
    (run_dir / "reports.json").write_text(json.dumps({"C001": {"id": "C001", "mode": "claim"}}))


class TestItemWithoutSynthesis:
    """Cover 831->833: assessment.md NOT existing in Results table."""

    def test_no_synthesis_item(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_run_with_no_synthesis_for_item(run_dir)
        output_dir = tmp_path / "md"
        render_run(run_dir, output_dir)
        c001_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("C001")]
        # assessment.md should NOT have been written
        assert not (c001_dirs[0] / "assessment.md").exists()
        # Results table in index should not include Assessment link
        index = (c001_dirs[0] / "index.md").read_text()
        assert "[Assessment](assessment.md)" not in index


class TestRendererDefensiveGuards:
    """Cover isinstance defensive branches by direct function calls with malformed data.

    These branches exist as defensive guards and normally cannot be triggered
    from well-formed pipeline output. We exercise them by calling the writer
    functions directly with deliberately-malformed dict values.
    """

    # Note: 811->813 and 818->820 (isinstance(report, dict) False) cannot be
    # exercised via direct call because _card_heading_for is called earlier
    # in _write_item_index and would crash on non-dict report. Those branches
    # are legitimately unreachable defensive guards.

    def test_write_assessment_synthesis_non_dict(self, tmp_path: Path) -> None:
        """Cover 633->637, 635->637 inside _write_run_index.

        Similar defensive isinstance guards in run-index card rendering.
        """
        from diogenes.renderer import _write_run_index

        items = [{"id": "C001", "type": "claim", "clarified_text": "Test", "original_text": "Test"}]
        # synthesis for C001 is a non-dict — guards should short-circuit
        _write_run_index(tmp_path, items, [], {}, {}, {}, {}, {"C001": "not a dict"}, {})
        assert (tmp_path / "index.md").exists()

    def test_collect_ratings_non_dict_synthesis_param(self) -> None:
        """Cover outer isinstance(synthesis, dict) False via direct call."""
        from diogenes.renderer import _collect_hypothesis_ratings

        result = _collect_hypothesis_ratings({}, None)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        assert result == {}

    def test_collect_ratings_synthesis_assessment_non_dict(self) -> None:
        """Cover 335->342: synthesis is dict but assessment is not a dict."""
        from diogenes.renderer import _collect_hypothesis_ratings

        # synthesis is dict (passes outer isinstance) but "assessment" value is a string
        result = _collect_hypothesis_ratings({}, {"assessment": "not a dict"})
        assert result == {}

    def test_write_self_audit_process_non_dict_domain(self, tmp_path: Path) -> None:
        """Cover the `not a dict` skip branch in the process_audit domain loop."""
        from diogenes.renderer import _write_self_audit

        item_dir = tmp_path / "item"
        item_dir.mkdir()
        audit = {
            "id": "C001",
            "process_audit": {
                "evaluation_consistency": "not a dict",  # Skip this one
                "synthesis_fairness": {"rating": "Pass"},  # Include this one
            },
        }
        _write_self_audit(item_dir, audit, {})
        content = (item_dir / "self-audit.md").read_text()
        assert "Synthesis Fairness" in content

    def test_write_assessment_gaps_non_list_non_dict(self, tmp_path: Path) -> None:
        """Cover 1190->1208: gaps is truthy but neither list nor dict.

        A string "gaps" value would trigger this defensive else-skip.
        """
        from diogenes.renderer import _write_assessment

        item_dir = tmp_path / "item"
        item_dir.mkdir()
        synthesis = {"id": "C001", "gaps": "a string not a list or dict"}
        _write_assessment(item_dir, synthesis, {})
        content = (item_dir / "assessment.md").read_text()
        # Evidence Gaps header may render but no list/dict content
        assert "Evidence Gaps" in content

    def test_write_assessment_gaps_dict_no_impact(self, tmp_path: Path) -> None:
        """Cover 1204->1208: gaps dict with expected but no impact_on_confidence."""
        from diogenes.renderer import _write_assessment

        item_dir = tmp_path / "item"
        item_dir.mkdir()
        synthesis = {
            "id": "C001",
            "gaps": {"expected_not_found": ["A"], "unanswered_questions": ["Q"]},  # No impact
        }
        _write_assessment(item_dir, synthesis, {})
        content = (item_dir / "assessment.md").read_text()
        assert "Expected but not found" in content
        assert "Impact on confidence" not in content


class TestMoreDefensiveBranches:
    """Additional targeted tests for remaining branches."""

    def test_reading_list_unusual_priority(self, tmp_path: Path) -> None:
        """Cover 1353->1351: reading_list entry with priority outside the standard set."""
        from diogenes.renderer import _write_reading_list

        item_dir = tmp_path / "item"
        item_dir.mkdir()
        audit = {
            "reading_list": [
                {"title": "Primary", "url": "https://a.com", "priority": "must read"},
                {"title": "Unknown", "url": "https://b.com", "priority": "archival"},  # Not in by_priority
            ],
        }
        _write_reading_list(item_dir, audit, "C001", {}, {})
        content = (item_dir / "reading-list.md").read_text()
        assert "Primary" in content
        # "Unknown" with non-standard priority should not appear
        assert "Unknown" not in content

    def test_extract_sources_non_list_sources_value(self) -> None:
        """Cover 1387->1392: scorecards.sources is not a list (malformed)."""
        from diogenes.renderer import _extract_sources_for_item

        # "sources" key exists but value is not a list — falls through to CLI path
        scorecards = {"sources": "not a list", "C001": {"scorecards": [{"url": "https://a.com"}]}}
        result = _extract_sources_for_item(scorecards, "C001")
        assert len(result) == 1

    def test_assessment_confidence_without_verdict(self, tmp_path: Path) -> None:
        """Cover 1174->1176: assessment has confidence but no verdict.

        (1174 is `if assessment.get("verdict"):` — False path skips verdict, still
        processes confidence at 1176.)
        """
        from diogenes.renderer import _write_assessment

        item_dir = tmp_path / "item"
        item_dir.mkdir()
        synthesis = {"id": "C001", "assessment": {"confidence": "High", "hypothesis_ratings": []}}
        _write_assessment(item_dir, synthesis, {})
        content = (item_dir / "assessment.md").read_text()
        assert "Confidence" in content
        assert "Verdict**:" not in content


def _create_cli_format_regression_fixture(run_dir: Path) -> None:
    """Regression fixture for #156 — CLI-format clarified JSON, no `type` fields.

    The real CLI pipeline writes `research-input-clarified.json` as
    `{claims: [...], queries: [...], axioms: [...]}` with items that do
    NOT carry a `type` field. Commit 91bbc9c3 added a fallback in
    `render_run` that handles this shape for the per-item render loop
    but forgot to (a) attach `type` to each item and (b) include axioms.
    `_write_run_index` filters items by `type` to build its card
    sections, so under this shape every filter matches nothing and the
    entire per-item card section is silently dropped from the rendered
    run-level `index.md`.

    This fixture reproduces the shape. `reports.json` is populated so
    tests can assert substantive card-body content (verdicts and
    answers), not just section headings. Other pipeline-step files are
    omitted — `_load_json` returns `{}` for missing files and the
    downstream `_write_*` calls are guarded.
    """
    clarified = {
        "claims": [
            {
                "id": "C001",
                "original_text": "Sample claim text",
                "clarified_text": "Sample claim clarified for testability",
            },
        ],
        "queries": [
            {
                "id": "Q001",
                "original_text": "Sample query text",
                "clarified_text": "Sample query clarified",
            },
        ],
        "axioms": [
            {
                "id": "A001",
                "original_text": "Sample axiom statement",
                "text": "Sample axiom statement",
            },
        ],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(clarified))

    reports = {
        "C001": {"id": "C001", "verdict_summary": "Claim supported by evidence"},
        "Q001": {"id": "Q001", "answer_summary": "Query answered with caveats"},
    }
    (run_dir / "reports.json").write_text(json.dumps(reports))


class TestRunIndexCliFormatRegression:
    """Regression tests for issue #156.

    Pre-fix behavior: `_write_run_index` silently emits a run-level
    `index.md` with no per-item card section whenever the clarified
    input uses the `{claims, queries, axioms}` top-level grouping
    (items lack `type` fields) — which is what the CLI pipeline
    actually produces.

    These tests MUST fail against the buggy code and pass after the
    fix. Together they assert on substantive content of the rendered
    run-level `index.md` — not on file existence or the `Run Overview`
    header string, which both pass even on a fully-broken render.
    """

    def test_run_index_has_per_item_card_anchors(self, tmp_path: Path) -> None:
        """Every item — axiom, claim, query — appears as an anchored card."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_regression_fixture(run_dir)

        render_run(run_dir, run_dir)

        index = (run_dir / "index.md").read_text()
        assert 'id="card-A001"' in index, "axiom A001 card missing from run index"
        assert 'id="card-C001"' in index, "claim C001 card missing from run index"
        assert 'id="card-Q001"' in index, "query Q001 card missing from run index"

    def test_run_index_has_full_analysis_links_for_claim_and_query(self, tmp_path: Path) -> None:
        """Claim and query cards include a `[Full analysis](<slug>/index.md)` link."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_regression_fixture(run_dir)

        render_run(run_dir, run_dir)

        index = (run_dir / "index.md").read_text()
        # Slug format is `<id>-<first-chars-of-clarified>`. Anchor the
        # assertion on the id-prefix segment so renderer slug tweaks
        # don't break the test, but the presence of the full-analysis
        # link itself is the thing under test.
        assert "[Full analysis](C001-" in index, "claim C001 missing Full analysis link"
        assert "[Full analysis](Q001-" in index, "query Q001 missing Full analysis link"

    def test_run_index_toc_lists_all_three_type_sections(self, tmp_path: Path) -> None:
        """TOC includes Axioms + Claims + Queries sections plus per-item entries."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_regression_fixture(run_dir)

        render_run(run_dir, run_dir)

        index = (run_dir / "index.md").read_text()
        assert "#sec-axioms" in index, "TOC missing Axioms section entry"
        assert "#sec-claims" in index, "TOC missing Claims section entry"
        assert "#sec-queries" in index, "TOC missing Queries section entry"
        assert "#card-A001" in index, "TOC missing axiom A001 sub-entry"
        assert "#card-C001" in index, "TOC missing claim C001 sub-entry"
        assert "#card-Q001" in index, "TOC missing query Q001 sub-entry"

    def test_run_index_renders_claim_verdict_and_query_answer(self, tmp_path: Path) -> None:
        """Card bodies include the reports.json verdict/answer text, not just headings."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_regression_fixture(run_dir)

        render_run(run_dir, run_dir)

        index = (run_dir / "index.md").read_text()
        assert "Claim supported by evidence" in index, "claim verdict missing from card body"
        assert "Query answered with caveats" in index, "query answer missing from card body"

    def test_run_index_collection_statistics_counts_all_three_items(self, tmp_path: Path) -> None:
        """`Items investigated` stats row reflects all three items, not a subset.

        Catches the secondary 91bbc9c3 bug: the fallback at L363-367 only
        unpacks `claims + queries` from the clarified JSON and omits
        `axioms` entirely. A correct fix includes all three top-level
        keys, so the stats row must equal 3.
        """
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_regression_fixture(run_dir)

        render_run(run_dir, run_dir)

        index = (run_dir / "index.md").read_text()
        assert "Items investigated | 3" in index, (
            "Collection Statistics row missing or undercounting — expected 'Items investigated | 3'"
        )


class TestRunIndexTitleHeadingRegression:
    """Regression tests for issue #161.

    Pre-fix behavior (R0063): the per-query cards in the run-level
    `index.md` collapsed to bare `### Q001`, `### Q002`, … because the
    pipeline's report-generation step did not emit a `title` field.
    With 8+ queries the TOC became an opaque list of ids.

    These tests assert that once `title` is populated at the report
    level and the qualifier falls back to `assessment_summary` when
    needed, the rendered run-level `index.md` carries the full
    `### Q001 — <title> — <qualifier>` three-part heading format.
    """

    def test_run_index_card_heading_is_three_part_for_query(self, tmp_path: Path) -> None:
        """Query card heading includes id, title, and nested confidence qualifier."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        clarified = {
            "claims": [],
            "queries": [
                {
                    "id": "Q001",
                    "original_text": "Query text",
                    "clarified_text": "Clarified query",
                },
            ],
            "axioms": [],
        }
        (run_dir / "research-input-clarified.json").write_text(json.dumps(clarified))
        reports = {
            "Q001": {
                "id": "Q001",
                "mode": "query",
                "title": "LLM watermarking techniques survey",
                "assessment_summary": {
                    "answer": "Several techniques documented.",
                    "confidence": "Medium (55-80%)",
                },
            },
        }
        (run_dir / "reports.json").write_text(json.dumps(reports))

        render_run(run_dir, run_dir)

        index = (run_dir / "index.md").read_text()
        assert "### Q001 — LLM watermarking techniques survey — Medium (55-80%)" in index, (
            "run-level index card heading missing three-part format from issue #161 fix"
        )

    def test_run_index_card_heading_is_three_part_for_claim(self, tmp_path: Path) -> None:
        """Claim card heading uses nested `assessment_summary.verdict` as qualifier."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        clarified = {
            "claims": [
                {
                    "id": "C001",
                    "original_text": "Claim text",
                    "clarified_text": "Clarified claim",
                },
            ],
            "queries": [],
            "axioms": [],
        }
        (run_dir / "research-input-clarified.json").write_text(json.dumps(clarified))
        reports = {
            "C001": {
                "id": "C001",
                "mode": "claim",
                "title": "AI safety ethics homophily",
                "assessment_summary": {
                    "verdict": "Likely (55-80%)",
                    "confidence": "Medium",
                },
            },
        }
        (run_dir / "reports.json").write_text(json.dumps(reports))

        render_run(run_dir, run_dir)

        index = (run_dir / "index.md").read_text()
        # The R0058-era target format from the issue
        assert "### C001 — AI safety ethics homophily — Likely (55-80%)" in index, (
            "run-level index claim heading missing three-part format from issue #161 fix"
        )

    def test_run_index_toc_entry_includes_title(self, tmp_path: Path) -> None:
        """TOC sub-entries carry the topic title, not just bare ids.

        This is the observable bug from R0063: an 8-query TOC rendered as
        an opaque list of `Q001 … Q008` with no context. Post-fix, every
        TOC entry carries its topic.
        """
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        clarified = {
            "claims": [],
            "queries": [
                {"id": "Q001", "clarified_text": "q1"},
                {"id": "Q002", "clarified_text": "q2"},
            ],
            "axioms": [],
        }
        (run_dir / "research-input-clarified.json").write_text(json.dumps(clarified))
        reports = {
            "Q001": {
                "id": "Q001",
                "mode": "query",
                "title": "Topic one",
                "assessment_summary": {"confidence": "High"},
            },
            "Q002": {
                "id": "Q002",
                "mode": "query",
                "title": "Topic two",
                "assessment_summary": {"confidence": "Low"},
            },
        }
        (run_dir / "reports.json").write_text(json.dumps(reports))

        render_run(run_dir, run_dir)

        index = (run_dir / "index.md").read_text()
        # TOC lines are `    - [<heading>](#card-<id>)`; assert topic appears in the link text
        assert "Topic one" in index, "TOC missing title `Topic one` for Q001"
        assert "Topic two" in index, "TOC missing title `Topic two` for Q002"


def _create_cli_format_realistic_run(run_dir: Path) -> None:
    """Fixture matching what the real CLI pipeline writes (as of R0063).

    Schema differences from `_create_rich_cli_run`:

    - Items in `research-input-clarified.json` do NOT carry `type` fields;
      the top-level grouping key conveys type. (See #156 / 91bbc9c3.)
    - Each search-plan entry uses `target_theme` (a theme id, e.g. `"T1"`),
      not `theme` (free text) — the theme text must be dereferenced from
      `hypotheses[item_id].search_themes[]`.
    - `search-results.json` stores execution records per-item under
      `search_results[item_id].searches_executed`, NOT at top-level
      `search_execution_log`.
    - Individual result records inside `searches_executed[N].results`
      have no `disposition` field — disposition lives in the item-level
      `selected_sources` / `rejected_sources` arrays keyed by `search_id`.
    - `scorecards.json` is CLI-keyed (`scorecards[item_id].scorecards`).

    Counts picked to allow unambiguous assertions:
    - S01 targets T1, returns 5, 2 selected, 3 rejected.
    - S02 targets T2, returns 3, 1 selected, 2 rejected.
    """
    clarified = {
        "claims": [],
        "queries": [
            {
                "id": "Q001",
                "original_text": "Sample query",
                "clarified_text": "Sample query clarified for testability",
            },
        ],
        "axioms": [],
    }
    (run_dir / "research-input-clarified.json").write_text(json.dumps(clarified))

    hypotheses = {
        "Q001": {
            "id": "Q001",
            "approach": "open-ended",
            "search_themes": [
                {"id": "T1", "theme": "Statistical watermarking", "description": "Token distribution"},
                {"id": "T2", "theme": "Embedding-based watermarking", "description": "Semantic perturbation"},
            ],
        },
    }
    (run_dir / "hypotheses.json").write_text(json.dumps(hypotheses))

    search_plans = {
        "Q001": {
            "id": "Q001",
            "searches": [
                {
                    "id": "S01",
                    "target_theme": "T1",
                    "perspective": "academic",
                    "terms": ["watermarking", "LLM"],
                    "sources": ["arXiv"],
                },
                {
                    "id": "S02",
                    "target_theme": "T2",
                    "perspective": "industry",
                    "terms": ["watermark embedding"],
                    "sources": ["ACM"],
                },
            ],
        },
    }
    (run_dir / "search-plans.json").write_text(json.dumps(search_plans))

    search_results = {
        "Q001": {
            "id": "Q001",
            "searches_executed": [
                {
                    "search_id": "S01",
                    "terms_used": ["watermarking", "LLM"],
                    "provider": "serper",
                    "date": "2026-04-23T13:18:41Z",
                    "results_found": 5,
                    "total_available": 5,
                    "results": [
                        {"title": f"S1 Paper {i}", "url": f"https://ex.com/s1/{i}", "snippet": ""} for i in range(5)
                    ],
                },
                {
                    "search_id": "S02",
                    "terms_used": ["watermark embedding"],
                    "provider": "serper",
                    "date": "2026-04-23T13:18:45Z",
                    "results_found": 3,
                    "total_available": 3,
                    "results": [
                        {"title": f"S2 Paper {i}", "url": f"https://ex.com/s2/{i}", "snippet": ""} for i in range(3)
                    ],
                },
            ],
            "selected_sources": [
                {
                    "url": "https://ex.com/s1/0",
                    "search_id": "S01",
                    "title": "S1 Paper 0",
                    "snippet": "",
                    "relevance_score": 8,
                    "rationale": "directly relevant",
                },
                {
                    "url": "https://ex.com/s1/1",
                    "search_id": "S01",
                    "title": "S1 Paper 1",
                    "snippet": "",
                    "relevance_score": 7,
                    "rationale": "supporting evidence",
                },
                {
                    "url": "https://ex.com/s2/0",
                    "search_id": "S02",
                    "title": "S2 Paper 0",
                    "snippet": "",
                    "relevance_score": 9,
                    "rationale": "strong match",
                },
            ],
            "rejected_sources": [
                {
                    "url": "https://ex.com/s1/2",
                    "search_id": "S01",
                    "title": "S1 Paper 2",
                    "relevance_score": 2,
                    "rationale": "off-topic",
                },
                {
                    "url": "https://ex.com/s1/3",
                    "search_id": "S01",
                    "title": "S1 Paper 3",
                    "relevance_score": 3,
                    "rationale": "tangential",
                },
                {
                    "url": "https://ex.com/s1/4",
                    "search_id": "S01",
                    "title": "S1 Paper 4",
                    "relevance_score": 1,
                    "rationale": "irrelevant",
                },
                {
                    "url": "https://ex.com/s2/1",
                    "search_id": "S02",
                    "title": "S2 Paper 1",
                    "relevance_score": 4,
                    "rationale": "weak",
                },
                {
                    "url": "https://ex.com/s2/2",
                    "search_id": "S02",
                    "title": "S2 Paper 2",
                    "relevance_score": 3,
                    "rationale": "unrelated",
                },
            ],
            "summary": {
                "total_searches": 2,
                "total_results_found": 8,
                "total_selected": 3,
                "total_rejected": 5,
                "relevance_threshold": 5,
            },
        },
    }
    (run_dir / "search-results.json").write_text(json.dumps(search_results))

    scorecards = {
        "Q001": {
            "id": "Q001",
            "scorecards": [
                {
                    "id": "SRC001",
                    "url": "https://ex.com/s1/0",
                    "title": "S1 Paper 0",
                    "authors": "Smith, Jones",
                    "date": "2025",
                    "content_summary": "Peer-reviewed study on statistical watermarking.",
                    "reliability": {"rating": "High", "rationale": "Peer-reviewed venue"},
                    "relevance": {"rating": "Very High", "rationale": "Core methodology paper"},
                    "bias_assessment": {
                        "funding_source": {"rating": "Low risk", "rationale": "Publicly funded"},
                    },
                },
            ],
        },
    }
    (run_dir / "scorecards.json").write_text(json.dumps(scorecards))

    reports = {
        "Q001": {
            "id": "Q001",
            "assessment_summary": {
                "answer": "Multiple watermarking techniques documented.",
                "confidence": "Medium — surveyed only major vendors.",
                "conclusion": "Several techniques exist; adoption varies by deployment.",
                "reasoning": "Analysis of surveyed literature.",
            },
            "synthesis_summary": {
                "evidence_quality": "Limited — small sample of surveyed papers.",
                "source_agreement": "High on vocabulary, moderate on taxonomy.",
            },
        },
    }
    (run_dir / "reports.json").write_text(json.dumps(reports))


def _q001_dir(run_dir: Path) -> Path:
    """Return the slugged Q001 output directory under run_dir."""
    return next(d for d in run_dir.iterdir() if d.is_dir() and d.name.startswith("Q001-"))


def _searches_table_rows(index_content: str, search_id_prefix: str) -> list[str]:
    """Extract `| [<search_id>...` rows from the `## Searches` table."""
    after = index_content.split("## Searches", 1)[1]
    table = after.split("##", 1)[0]
    return [line for line in table.splitlines() if line.startswith(f"| [{search_id_prefix}")]


class TestItemIndexSearchesTableCliFormat:
    """Content tests for the per-item `## Searches` summary table (CLI format).

    The observable bug (#157 round 1): every row emitted as
    `| [SNN](...) |  | ? | ? |` — empty Target, literal `?` in Returned and
    Selected — because the renderer's joins assumed plugin-format schema.
    These tests assert the table carries real data, not placeholders.
    """

    def test_target_column_resolves_theme_id_to_theme_text(self, tmp_path: Path) -> None:
        """Target column contains theme text (dereferenced from `target_theme` id)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        index = (_q001_dir(run_dir) / "index.md").read_text()
        assert "Statistical watermarking" in index, (
            "Searches table missing theme text for S01 (target_theme=T1 → 'Statistical watermarking')"
        )
        assert "Embedding-based watermarking" in index, (
            "Searches table missing theme text for S02 (target_theme=T2 → 'Embedding-based watermarking')"
        )

    def test_returned_column_has_numeric_count_not_placeholder(self, tmp_path: Path) -> None:
        """Returned column contains a non-zero integer, never the `?` placeholder."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        index = (_q001_dir(run_dir) / "index.md").read_text()
        for prefix in ("S01", "S02"):
            rows = _searches_table_rows(index, prefix)
            assert len(rows) == 1, f"expected 1 {prefix} row, got {len(rows)}"
            cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
            returned = cells[-2]
            assert returned.isdigit(), f"{prefix} Returned cell is not numeric: {returned!r}"
            assert int(returned) > 0, f"{prefix} Returned cell is not positive: {returned!r}"

    def test_selected_column_has_numeric_count_not_placeholder(self, tmp_path: Path) -> None:
        """Selected column contains an integer, never the `?` placeholder."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        index = (_q001_dir(run_dir) / "index.md").read_text()
        for prefix in ("S01", "S02"):
            rows = _searches_table_rows(index, prefix)
            assert len(rows) == 1, f"expected 1 {prefix} row, got {len(rows)}"
            cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
            selected = cells[-1]
            assert selected.isdigit(), f"{prefix} Selected cell is not numeric: {selected!r}"

    def test_returned_and_selected_counts_match_fixture(self, tmp_path: Path) -> None:
        """Exact counts: S01 returns 5 / selects 2; S02 returns 3 / selects 1."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        index = (_q001_dir(run_dir) / "index.md").read_text()
        s01_cells = [c.strip() for c in _searches_table_rows(index, "S01")[0].strip().strip("|").split("|")]
        s02_cells = [c.strip() for c in _searches_table_rows(index, "S02")[0].strip().strip("|").split("|")]
        assert s01_cells[-2] == "5", f"S01 Returned: expected 5, got {s01_cells[-2]}"
        assert s01_cells[-1] == "2", f"S01 Selected: expected 2, got {s01_cells[-1]}"
        assert s02_cells[-2] == "3", f"S02 Returned: expected 3, got {s02_cells[-2]}"
        assert s02_cells[-1] == "1", f"S02 Selected: expected 1, got {s02_cells[-1]}"


class TestItemIndexSourcesTableCliFormat:
    """Content tests for the per-item `## Sources` summary table (CLI format).

    Not a regression fix — this table was already correct in R0063 — but part
    of #157 round 1 to lock the behavior with a strong assertion, so future
    schema shifts don't silently drop this column set the same way the
    Searches table did.
    """

    def test_sources_table_has_id_title_reliability_relevance(self, tmp_path: Path) -> None:
        """Every row carries id, title, and non-placeholder reliability/relevance."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        index = (_q001_dir(run_dir) / "index.md").read_text()
        assert "## Sources" in index
        assert "[SRC001](sources/SRC001/scorecard.md)" in index
        assert "S1 Paper 0" in index
        # Row format: | [SRC001](...) | <title> | <reliability> | <relevance> |
        sources_after = index.split("## Sources", 1)[1].split("##", 1)[0]
        rows = [line for line in sources_after.splitlines() if line.startswith("| [SRC")]
        assert len(rows) == 1
        cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
        assert cells[-2] == "High", f"Reliability: expected 'High', got {cells[-2]!r}"
        assert cells[-1] == "Very High", f"Relevance: expected 'Very High', got {cells[-1]!r}"


class TestSearchLogMdCliFormat:
    """Content tests for per-search `search-log.md` under CLI-format runs.

    The observable bug (#157 round 1): search-log.md for a CLI-format run
    contained only Title/Terms/Planned sources — no Target, no Query, no
    Execution Summary, no Selected/Rejected Results tables — because
    `_write_searches` looked for execution records at top-level
    `search_execution_log` (empty in CLI format) and for `theme` (not
    `target_theme`) on the plan entry.
    """

    def test_search_log_has_target_theme_line(self, tmp_path: Path) -> None:
        """`**Target**: <theme text>` line resolved from target_theme id."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        s01 = (_q001_dir(run_dir) / "searches" / "S01" / "search-log.md").read_text()
        assert "**Target**: Statistical watermarking" in s01, "search-log.md missing Target line with theme text"

    def test_search_log_has_execution_summary_block(self, tmp_path: Path) -> None:
        """Execution Summary section with returned/selected/rejected counts."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        s01 = (_q001_dir(run_dir) / "searches" / "S01" / "search-log.md").read_text()
        assert "## Execution Summary" in s01, "search-log.md missing ## Execution Summary"
        assert "Results returned: 5" in s01, "Execution Summary missing returned count"
        assert "Selected: 2" in s01, "Execution Summary missing selected count"
        assert "Rejected: 3" in s01, "Execution Summary missing rejected count"

    def test_search_log_has_selected_results_table(self, tmp_path: Path) -> None:
        """`## Selected Results` section lists items with titles and scores."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        s01 = (_q001_dir(run_dir) / "searches" / "S01" / "search-log.md").read_text()
        assert "## Selected Results" in s01
        assert "S1 Paper 0" in s01
        assert "S1 Paper 1" in s01
        assert "directly relevant" in s01

    def test_search_log_has_rejected_results_table(self, tmp_path: Path) -> None:
        """`## Rejected Results` section lists rejected items with rationales."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        s01 = (_q001_dir(run_dir) / "searches" / "S01" / "search-log.md").read_text()
        assert "## Rejected Results" in s01
        assert "S1 Paper 2" in s01
        assert "off-topic" in s01

    def test_search_log_results_subdir_contains_per_result_files(self, tmp_path: Path) -> None:
        """results/RNN.md per-result files written with Title / URL / Score / Disposition."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        results_dir = _q001_dir(run_dir) / "searches" / "S01" / "results"
        assert results_dir.exists(), "per-search results/ subdir not created"
        r_files = sorted(f for f in results_dir.iterdir() if f.suffix == ".md")
        assert len(r_files) == 5, f"expected 5 per-result files for S01, got {len(r_files)}"
        r01 = (results_dir / "R01.md").read_text()
        assert "**Title**:" in r01
        assert "**URL**:" in r01
        assert "**Disposition**: selected" in r01 or "**Disposition**: rejected" in r01


class TestSourcesScorecardMdCliFormat:
    """Content tests for per-source `scorecard.md` under CLI-format runs.

    Scorecard rendering was already largely correct for CLI format in R0063,
    but prior tests asserted only directory existence. Lock the behavior so
    schema shifts can't silently drop the substantive fields.
    """

    def test_scorecard_has_metadata_table(self, tmp_path: Path) -> None:
        """Metadata table with URL, Authors, Date rows populated from scorecard fields."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        sc = (_q001_dir(run_dir) / "sources" / "SRC001" / "scorecard.md").read_text()
        assert "## Metadata" in sc
        assert "| URL | <https://ex.com/s1/0> |" in sc
        assert "| Authors | Smith, Jones |" in sc
        assert "| Date | 2025 |" in sc

    def test_scorecard_has_reliability_section_with_rationale(self, tmp_path: Path) -> None:
        """`## Reliability: High` heading plus rationale body."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        sc = (_q001_dir(run_dir) / "sources" / "SRC001" / "scorecard.md").read_text()
        assert "## Reliability: High" in sc
        assert "Peer-reviewed venue" in sc

    def test_scorecard_has_relevance_section_with_rationale(self, tmp_path: Path) -> None:
        """`## Relevance: Very High` heading plus rationale body."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        sc = (_q001_dir(run_dir) / "sources" / "SRC001" / "scorecard.md").read_text()
        assert "## Relevance: Very High" in sc
        assert "Core methodology paper" in sc

    def test_scorecard_has_bias_assessment_row(self, tmp_path: Path) -> None:
        """Bias Assessment table has at least one populated row."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        sc = (_q001_dir(run_dir) / "sources" / "SRC001" / "scorecard.md").read_text()
        assert "## Bias Assessment" in sc
        assert "Funding Source" in sc
        assert "Low risk" in sc
        assert "Publicly funded" in sc


class TestAnswerSummaryCliFormat:
    """Content tests for the per-query answer/verdict summary resolution.

    Observed bug: the run-level index's per-item cards showed only
    `**Query:**` and `**Confidence:**` with no Answer line between them.
    R0063's `reports.json` stores the answer under
    `assessment_summary.answer` (CLI format); the renderer only checked
    the plugin-format `verdict_summary` / `answer_summary` / `one_line`
    fields, so the lookup returned empty and the `**Answer:**` line
    was silently dropped across every card and also from the per-item
    index's Bottom Line.
    """

    def test_run_index_card_renders_answer_line_for_query(self, tmp_path: Path) -> None:
        """`**Answer:** <text>` appears inside the query's card in run index."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        index = (run_dir / "index.md").read_text()
        # Isolate Q001 card section (between card anchor and the next anchor / section)
        card = index.split('<a id="card-Q001"></a>', 1)[1].split('<a id="', 1)[0]
        assert "**Answer:** Multiple watermarking techniques documented." in card, (
            "Q001 card is missing the **Answer:** line with assessment_summary.answer text"
        )

    def test_per_item_index_renders_bottom_line_from_assessment_summary(
        self,
        tmp_path: Path,
    ) -> None:
        """Per-item `index.md` `**Bottom Line:**` falls back to `assessment_summary.answer`."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _create_cli_format_realistic_run(run_dir)

        render_run(run_dir, run_dir)

        per_item = (_q001_dir(run_dir) / "index.md").read_text()
        assert "**Bottom Line:** Multiple watermarking techniques documented." in per_item, (
            "Per-item index.md missing **Bottom Line:** from assessment_summary.answer"
        )


class TestSchemaHelpersDefensiveBranches:
    """Direct unit tests for the #157 round-1 schema-resolution helpers.

    Each helper has narrow defensive guards for malformed or unexpected
    JSON shapes (non-dict item data, non-list themes, missing label
    fields, etc.). Exercised here by unit-calling the helper with the
    specific shape that triggers each branch. Keeping the assertions
    behavioral — what the helper returns — rather than purely structural
    (avoids the `# pragma: no branch` pattern called out in #157).
    """

    def test_execution_log_returns_empty_when_item_data_not_dict(self) -> None:
        """CLI fallback returns [] when search_results[item_id] is non-dict."""
        from diogenes.renderer import _get_item_execution_log

        assert _get_item_execution_log({"Q001": "not a dict"}, "Q001") == []

    def test_disposition_index_returns_empty_when_item_data_not_dict(self) -> None:
        """CLI fallback returns {} when search_results[item_id] is non-dict."""
        from diogenes.renderer import _get_item_disposition_index

        assert _get_item_disposition_index({"Q001": 42}, "Q001") == {}

    def test_disposition_index_skips_non_dict_entries_in_source_list(self) -> None:
        """Non-dict entries inside selected_sources / rejected_sources are skipped."""
        from diogenes.renderer import _get_item_disposition_index

        search_results = {
            "Q001": {
                "selected_sources": [
                    "not a dict",
                    {"search_id": "S01", "url": "https://a"},
                ],
                "rejected_sources": [
                    None,
                    {"search_id": "S01", "url": "https://b"},
                ],
            },
        }
        index = _get_item_disposition_index(search_results, "Q001")
        assert list(index.keys()) == ["S01"]
        assert len(index["S01"]["selected"]) == 1
        assert index["S01"]["selected"][0]["url"] == "https://a"
        assert len(index["S01"]["rejected"]) == 1
        assert index["S01"]["rejected"][0]["url"] == "https://b"

    def test_resolve_search_theme_falls_through_when_themes_not_list(self) -> None:
        """Non-list `search_themes` falls back to `target_hypothesis`."""
        from diogenes.renderer import _resolve_search_theme

        search = {"target_theme": "T1", "target_hypothesis": "H-fallback"}
        hypotheses = {"search_themes": "not a list"}
        assert _resolve_search_theme(search, hypotheses) == "H-fallback"

    def test_resolve_search_theme_empty_themes_list_falls_through(self) -> None:
        """Empty `search_themes` list never enters the loop, falls back."""
        from diogenes.renderer import _resolve_search_theme

        search = {"target_theme": "T1", "target_hypothesis": "H-fallback"}
        hypotheses: dict[str, Any] = {"search_themes": []}
        assert _resolve_search_theme(search, hypotheses) == "H-fallback"

    def test_resolve_search_theme_matching_id_but_no_label_continues(self) -> None:
        """Matching id with no label/description continues the loop."""
        from diogenes.renderer import _resolve_search_theme

        search = {"target_theme": "T1"}
        hypotheses = {
            "search_themes": [
                {"id": "T1"},  # match, but no label or description
                {"id": "T1", "theme": "Recovered theme"},  # match with label
            ],
        }
        assert _resolve_search_theme(search, hypotheses) == "Recovered theme"

    def test_resolve_confidence_label_synthesis_not_dict_uses_report(self) -> None:
        """Non-dict synthesis falls through to report.assessment_summary.confidence."""
        from diogenes.renderer import _resolve_confidence_label

        report = {"assessment_summary": {"confidence": "Medium"}}
        # Pass a non-dict synthesis — the helper's type is dict[str, Any] but
        # the `isinstance` guard defends against real-world malformed JSON.
        assert _resolve_confidence_label(report, None) == "Medium"  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]

    def test_resolve_confidence_label_assessment_not_dict_uses_report(self) -> None:
        """Dict synthesis with non-dict assessment falls through to report."""
        from diogenes.renderer import _resolve_confidence_label

        report = {"assessment_summary": {"confidence": "High"}}
        synthesis = {"assessment": "not a dict"}
        assert _resolve_confidence_label(report, synthesis) == "High"
