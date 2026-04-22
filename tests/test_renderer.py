"""Tests for renderer module."""

import json
from pathlib import Path

import pytest

from diogenes.renderer import (
    _item_by_id,
    _item_slug,
    _load_json,
    _pipeline_notes_section,
    _pipeline_status_line,
    _slugify,
    _unwrap_items,
    render_run,
    render_run_group,
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

    def test_valid(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "data.json"  # type: ignore[operator]
        path.write_text('{"key": "value"}')
        assert _load_json(path) == {"key": "value"}

    def test_missing(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "missing.json"  # type: ignore[operator]
        assert _load_json(path) == {}

    def test_invalid(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "bad.json"  # type: ignore[operator]
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
        assert "https://a.com" in text


def _create_realistic_run(run_dir: Path) -> None:
    """Create a realistic run directory with all step outputs."""
    # Research input — includes both a claim and a query to exercise both paths
    ri = {
        "claims": [
            {
                "id": "C001",
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
                "text": "AI watermarking techniques",
                "clarified_text": "What techniques exist for embedding watermarks in AI-generated text?",
            },
        ],
        "axioms": [{"text": "Peer-reviewed sources preferred"}],
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
                "reasoning": "Multiple studies show improvement but sample sizes are small.",
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

    # Self-audit — both items
    sa = {
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
            "assessment_summary": {
                "verdict": "Supported with caveats — evidence supports reduction but more studies needed",
                "confidence": "Moderate",
            },
            "methodology": "Systematic review of RLHF studies",
            "evidence_quality": "Moderate — small sample sizes",
            "key_findings": ["RLHF reduces sycophancy in controlled settings"],
            "gaps_and_limitations": ["Small sample sizes", "Limited to English"],
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

    def test_renders_markdown_files(self, tmp_path: pytest.TempPathFactory) -> None:
        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        _create_realistic_run(run_dir)

        output_dir = tmp_path / "md"  # type: ignore[operator]
        render_run(run_dir, output_dir)

        # Check that index.md was created
        assert (output_dir / "index.md").exists()
        index_content = (output_dir / "index.md").read_text()
        # Index should have content from the run
        assert "Run Overview" in index_content

        # Check that markdown files were created
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) >= 1

    def test_empty_run_dir(self, tmp_path: pytest.TempPathFactory) -> None:
        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        output_dir = tmp_path / "md"  # type: ignore[operator]
        # Should not crash with empty dir
        render_run(run_dir, output_dir)
        assert (output_dir / "index.md").exists()


class TestRenderRunGroup:
    """Tests for render_run_group."""

    def test_renders_group(self, tmp_path: pytest.TempPathFactory) -> None:
        group_dir = tmp_path / "group"  # type: ignore[operator]
        group_dir.mkdir()

        run1 = group_dir / "run-1"
        run1.mkdir()
        _create_realistic_run(run1)

        # Copy research input to group level (renderer expects this)
        ri_path = run1 / "research-input-clarified.json"
        (group_dir / "research-input-clarified.json").write_text(ri_path.read_text())

        output_dir = tmp_path / "md"  # type: ignore[operator]
        render_run_group(group_dir, output_dir)

        assert (output_dir / "index.md").exists()
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) >= 2
