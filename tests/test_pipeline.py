"""Tests for pipeline module."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from diogenes.pipeline import (
    REJECTION_REASON_BELOW_THRESHOLD,
    REJECTION_REASON_DUPLICATE_URL,
    REJECTION_REASON_SCORER_DID_NOT_SCORE,
    REJECTION_REASONS,
    _event_kind_for_reason,
    _extract_evidence_for_item,
    _extract_single_source,
    _fetch_single_source,
    _fetch_sources_for_scoring,
    _filter_and_deduplicate,
    _print_hypothesis_summary,
    _score_results_batched,
    _scorecards_without_content,
    _verify_packet_verbatim,
    step2_generate_hypotheses,
    step3_design_searches,
    step4_execute_searches,
    step5_score_sources,
    step5b_extract_evidence,
    step9_self_audit,
    step10_report,
    step11_archive,
    steps678_synthesize_and_assess,
    validate_search_results_dispositioning,
    write_step_output,
)


class TestVerifyPacketVerbatim:
    """Tests for _verify_packet_verbatim."""

    def test_exact_match(self) -> None:
        packet = {"excerpt": "the exact text"}
        assert _verify_packet_verbatim(packet, "this is the exact text in the source") is True

    def test_no_match(self) -> None:
        packet = {"excerpt": "fabricated text"}
        assert _verify_packet_verbatim(packet, "completely different source content") is False

    def test_whitespace_normalized(self) -> None:
        packet = {"excerpt": "text  with   spaces"}
        assert _verify_packet_verbatim(packet, "text with spaces in source") is True

    def test_ellipsis_segments(self) -> None:
        packet = {"excerpt": "first part...second part"}
        content = "first part of the article and then second part appears"
        assert _verify_packet_verbatim(packet, content) is True

    def test_ellipsis_segment_missing(self) -> None:
        packet = {"excerpt": "first part...missing segment"}
        content = "first part of the article"
        assert _verify_packet_verbatim(packet, content) is False

    def test_empty_excerpt(self) -> None:
        packet = {"excerpt": ""}
        assert _verify_packet_verbatim(packet, "source content") is False

    def test_none_excerpt(self) -> None:
        packet = {"excerpt": None}
        assert _verify_packet_verbatim(packet, "source content") is False

    def test_missing_excerpt(self) -> None:
        packet: dict[str, Any] = {}
        assert _verify_packet_verbatim(packet, "source content") is False

    def test_whitespace_only_excerpt(self) -> None:
        packet = {"excerpt": "   "}
        assert _verify_packet_verbatim(packet, "source content") is False


class TestFilterAndDeduplicate:
    """Tests for _filter_and_deduplicate."""

    def test_basic_filtering(self) -> None:
        results = [
            {"url": "https://a.com", "relevance_score": 8},
            {"url": "https://b.com", "relevance_score": 3},
        ]
        selected, rejected = _filter_and_deduplicate(results, threshold=5)
        assert len(selected) == 1
        assert selected[0]["url"] == "https://a.com"
        assert len(rejected) == 1

    def test_deduplication(self) -> None:
        results = [
            {"url": "https://a.com", "relevance_score": 8},
            {"url": "https://a.com", "relevance_score": 7},
        ]
        selected, rejected = _filter_and_deduplicate(results, threshold=5)
        assert len(selected) == 1

    def test_sorted_by_score(self) -> None:
        results = [
            {"url": "https://a.com", "relevance_score": 5},
            {"url": "https://b.com", "relevance_score": 9},
        ]
        selected, _ = _filter_and_deduplicate(results, threshold=5)
        assert selected[0]["url"] == "https://b.com"

    def test_empty_input(self) -> None:
        selected, rejected = _filter_and_deduplicate([], threshold=5)
        assert selected == []
        assert rejected == []

    def test_threshold_is_parameterized(self) -> None:
        """Raising the threshold changes which sources clear the bar."""
        results = [
            {"url": "https://a.com", "relevance_score": 8},
            {"url": "https://b.com", "relevance_score": 6},
        ]
        # Threshold 7: only the 8-scorer selected
        selected_hi, rejected_hi = _filter_and_deduplicate(list(results), threshold=7)
        assert len(selected_hi) == 1
        assert len(rejected_hi) == 1
        # Threshold 6: both pass
        selected_lo, rejected_lo = _filter_and_deduplicate(list(results), threshold=6)
        assert len(selected_lo) == 2
        assert rejected_lo == []


class TestScorecardsWithoutContent:
    """Tests for _scorecards_without_content."""

    def test_strips_content_extract(self) -> None:
        scorecards = [
            {"url": "https://a.com", "content_extract": "long text", "title": "Title"},
        ]
        result = _scorecards_without_content(scorecards)
        assert "content_extract" not in result[0]
        assert result[0]["title"] == "Title"
        # Original should be unchanged
        assert "content_extract" in scorecards[0]

    def test_empty_list(self) -> None:
        assert _scorecards_without_content([]) == []


class TestWriteStepOutput:
    """Tests for write_step_output."""

    def test_writes_json(self, tmp_path: Path) -> None:
        data = {"key": "value"}
        path = write_step_output(tmp_path, "output.json", data)
        assert path.exists()
        assert json.loads(path.read_text()) == data

    def test_writes_list(self, tmp_path: Path) -> None:
        data = [1, 2, 3]
        path = write_step_output(tmp_path, "output.json", data)
        assert json.loads(path.read_text()) == data


class TestStep11Archive:
    """Tests for step11_archive."""

    def test_creates_archive(self, tmp_path: Path) -> None:
        outputs = {"research_input": {"claims": []}, "hypotheses": {"Q001": {}}}
        path = step11_archive(tmp_path, outputs)
        assert path.exists()
        data = json.loads(path.read_text())
        assert "archived_at" in data
        assert data["pipeline_version"] == "0.1.0"
        assert data["research_input"] == {"claims": []}


class TestFetchSingleSource:
    """Tests for _fetch_single_source."""

    @patch("diogenes.pipeline.fetch_page_extract")
    def test_success(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = "article body"
        result = _fetch_single_source("https://example.com")
        assert result["url"] == "https://example.com"
        assert result["content"] == "article body"

    @patch("diogenes.pipeline.fetch_page_extract")
    def test_raises_on_error(self, mock_fetch: MagicMock) -> None:
        from diogenes.search import FetchError

        mock_fetch.side_effect = FetchError("timeout")
        with pytest.raises(FetchError):
            _fetch_single_source("https://example.com")


class TestFetchSourcesForScoring:
    """Tests for _fetch_sources_for_scoring."""

    @patch("diogenes.pipeline.parallelize_process")
    def test_successful_fetch(self, mock_par: MagicMock) -> None:
        from diogenes.parallelize import ExecutorResults

        mock_par.return_value = ExecutorResults(
            results=[{"url": "https://a.com", "content": "article body"}],
            exceptions=[],
        )
        selected = [{"url": "https://a.com", "title": "Title", "snippet": "S"}]
        result = _fetch_sources_for_scoring("Q001", selected)
        assert len(result) == 1
        assert result[0]["content_extract"] == "article body"
        assert result[0]["title"] == "Title"

    @patch("diogenes.pipeline.parallelize_process")
    def test_fetch_failures_logged(self, mock_par: MagicMock) -> None:
        from diogenes.parallelize import ExecutorResults
        from diogenes.search import FetchError

        mock_par.return_value = ExecutorResults(
            results=[],
            exceptions=[FetchError("Fetch failed for https://fail.com: timeout")],
        )
        mock_logger = MagicMock()
        _fetch_sources_for_scoring("Q001", [{"url": "https://fail.com"}], mock_logger)
        mock_logger.log.assert_called_once()

    @patch("diogenes.pipeline.parallelize_process")
    def test_pdf_fetch_failure_kind(self, mock_par: MagicMock) -> None:
        from diogenes.parallelize import ExecutorResults
        from diogenes.search import FetchError

        # The URL parser splits on "for " then on first ":" — with http:// URLs
        # the extracted "url" is just "https". The .pdf check then looks at the
        # exc_str itself. Use "for paper.pdf" format so the extracted url has .pdf.
        mock_par.return_value = ExecutorResults(
            results=[],
            exceptions=[FetchError("pypdf failed to parse PDF for paper.pdf")],
        )
        mock_logger = MagicMock()
        _fetch_sources_for_scoring("Q001", [{"url": "https://example.com/doc.pdf"}], mock_logger)
        call_kwargs = mock_logger.log.call_args.kwargs
        assert call_kwargs["kind"] == "fetch_failed_pdf"

    @patch("diogenes.pipeline.parallelize_process")
    def test_trafilatura_fetch_failure_kind(self, mock_par: MagicMock) -> None:
        from diogenes.parallelize import ExecutorResults
        from diogenes.search import FetchError

        mock_par.return_value = ExecutorResults(
            results=[],
            exceptions=[FetchError("trafilatura returned no article body")],
        )
        mock_logger = MagicMock()
        _fetch_sources_for_scoring("Q001", [{"url": "https://x.com"}], mock_logger)
        call_kwargs = mock_logger.log.call_args.kwargs
        assert call_kwargs["kind"] == "fetch_failed_html"


class TestPrintHypothesisSummary:
    """Tests for _print_hypothesis_summary."""

    def test_hypotheses_approach(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("INFO", logger="diogenes.pipeline"):
            _print_hypothesis_summary("Q001", {"approach": "hypotheses", "hypotheses": [1, 2, 3]})
        assert "3 hypotheses" in caplog.text

    def test_open_ended_approach(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("INFO", logger="diogenes.pipeline"):
            _print_hypothesis_summary("Q001", {"approach": "open-ended", "search_themes": [1, 2]})
        assert "2 search themes" in caplog.text

    def test_unknown_approach(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("INFO", logger="diogenes.pipeline"):
            _print_hypothesis_summary("Q001", {"approach": "custom"})
        assert "approach=custom" in caplog.text


class TestStep2GenerateHypotheses:
    """Tests for step2_generate_hypotheses."""

    def test_processes_claims_and_queries(self) -> None:
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {"approach": "hypotheses", "hypotheses": []}

        research_input = {
            "claims": [{"id": "C001", "clarified_text": "Test claim"}],
            "queries": [{"id": "Q001", "clarified_text": "Test query"}],
            "axioms": [],
        }
        result = step2_generate_hypotheses(research_input, mock_client)
        assert "C001" in result
        assert "Q001" in result
        assert mock_client.call_sub_agent.call_count == 2

    def test_empty_input(self) -> None:
        mock_client = MagicMock()
        result = step2_generate_hypotheses({"claims": [], "queries": []}, mock_client)
        assert result == {}


class TestStep3DesignSearches:
    """Tests for step3_design_searches."""

    def test_processes_items(self) -> None:
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {"searches": [{"id": "S01"}], "approach": "test"}

        research_input = {
            "claims": [{"id": "C001", "clarified_text": "Test"}],
            "queries": [],
        }
        hypotheses = {"C001": {"approach": "hypotheses", "hypotheses": []}}
        result = step3_design_searches(research_input, hypotheses, mock_client)
        assert "C001" in result
        assert result["C001"]["searches"] == [{"id": "S01"}]


class TestScoreResultsBatched:
    """Tests for _score_results_batched."""

    def test_batched_scoring(self) -> None:
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {"scores": [{"url": "https://a.com", "relevance_score": 8}]}

        from diogenes.search import SearchExecution, SearchResult

        execution = SearchExecution(
            search_id="S01",
            terms=["test"],
            provider="mock",
            date="2026-01-01",
            results=[SearchResult(title="T", url="https://a.com", snippet="S")],
            total_results_available=1,
        )

        item = {"id": "Q001", "clarified_text": "Test"}
        scored, unscored = _score_results_batched(item, [execution], mock_client, Path("/tmp/fake.md"))
        assert len(scored) == 1
        assert scored[0]["search_id"] == "S01"
        assert scored[0]["title"] == "T"
        assert unscored == []


class TestStep5ScoreSources:
    """Tests for step5_score_sources."""

    @patch("diogenes.pipeline._fetch_sources_for_scoring")
    def test_scores_items(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = [
            {"url": "https://a.com", "title": "T", "snippet": "S", "content_extract": "body"},
        ]
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {
            "scorecards": [{"url": "https://a.com", "score": 8}],
        }

        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}
        search_results = {
            "C001": {
                "selected_sources": [{"url": "https://a.com", "title": "T", "snippet": "S"}],
            },
        }
        result = step5_score_sources(research_input, search_results, mock_client)
        assert "C001" in result
        assert len(result["C001"]["scorecards"]) == 1
        # Content should be joined from Python side
        assert result["C001"]["scorecards"][0]["content_extract"] == "body"


class TestExtractSingleSource:
    """Tests for _extract_single_source."""

    def test_with_verified_packets(self) -> None:
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {
            "packets": [
                {"excerpt": "exact text from source", "source_url": "https://a.com"},
                {"excerpt": "fabricated quote", "source_url": "https://a.com"},
            ],
        }

        result = _extract_single_source(
            item_id="Q001",
            item={"id": "Q001", "clarified_text": "test"},
            hypotheses={},
            scorecard={"url": "https://a.com", "content_extract": "the exact text from source is here"},
            prompt_path_str="/tmp/fake.md",
            client=mock_client,
        )
        assert result["url"] == "https://a.com"
        assert result["kept"] == 1
        assert result["dropped"] == 1


class TestExtractEvidenceForItem:
    """Tests for _extract_evidence_for_item."""

    @patch("diogenes.pipeline.parallelize_thread")
    def test_aggregates_results(self, mock_par: MagicMock) -> None:
        from diogenes.parallelize import ExecutorResults

        mock_par.return_value = ExecutorResults(
            results=[
                {"url": "https://a.com", "verified_packets": [{"excerpt": "a"}], "claimed": 2, "kept": 1, "dropped": 1},
            ],
            exceptions=[],
        )

        item = {"id": "Q001", "clarified_text": "test"}
        packets, errors, stats = _extract_evidence_for_item(
            item=item,
            item_hypotheses={},
            substantive=[{"url": "https://a.com", "content_extract": "text"}],
            prompt_path=Path("/tmp/fake.md"),
            client=MagicMock(),
        )
        assert len(packets) == 1
        assert stats["claimed"] == 2
        assert stats["kept"] == 1
        assert stats["dropped"] == 1
        assert errors == []

    @patch("diogenes.pipeline.parallelize_thread")
    def test_collects_errors(self, mock_par: MagicMock) -> None:
        from diogenes.parallelize import ExecutorResults

        mock_par.return_value = ExecutorResults(
            results=[],
            exceptions=[Exception("API failure")],
        )

        item = {"id": "Q001", "clarified_text": "test"}
        packets, errors, stats = _extract_evidence_for_item(
            item=item,
            item_hypotheses={},
            substantive=[{"url": "https://a.com", "content_extract": "text"}],
            prompt_path=Path("/tmp/fake.md"),
            client=MagicMock(),
        )
        assert len(errors) == 1
        assert stats["claimed"] == 0

    @patch("diogenes.pipeline.parallelize_thread")
    def test_logs_events(self, mock_par: MagicMock) -> None:
        from diogenes.parallelize import ExecutorResults

        mock_par.return_value = ExecutorResults(
            results=[
                {"url": "https://a.com", "verified_packets": [], "claimed": 5, "kept": 0, "dropped": 5},
            ],
            exceptions=[Exception("fail")],
        )

        mock_logger = MagicMock()
        item = {"id": "Q001", "clarified_text": "test"}
        _extract_evidence_for_item(
            item=item,
            item_hypotheses={},
            substantive=[{"url": "https://a.com", "content_extract": "text"}],
            prompt_path=Path("/tmp/fake.md"),
            client=MagicMock(),
            event_logger=mock_logger,
        )
        # Should log both dropped packets and API failure
        assert mock_logger.log.call_count == 2


class TestStep5bExtractEvidence:
    """Tests for step5b_extract_evidence."""

    @patch("diogenes.pipeline._extract_evidence_for_item")
    def test_extracts_evidence(self, mock_extract: MagicMock) -> None:
        mock_extract.return_value = (
            [{"excerpt": "test"}],
            [],
            {"claimed": 1, "kept": 1, "dropped": 0},
        )

        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}
        hypotheses: dict[str, Any] = {"C001": {}}
        scorecards = {
            "C001": {
                "scorecards": [{"url": "https://a.com", "content_extract": "x" * 200}],
            },
        }
        result = step5b_extract_evidence(research_input, hypotheses, scorecards, MagicMock())
        assert "C001" in result
        assert len(result["C001"]["packets"]) == 1

    def test_no_scorecards(self) -> None:
        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}
        result = step5b_extract_evidence(research_input, {}, {}, MagicMock())
        assert result["C001"]["packets"] == []

    @patch("diogenes.pipeline._extract_evidence_for_item")
    def test_insufficient_content_skipped(self, mock_extract: MagicMock) -> None:
        mock_extract.return_value = ([], [], {"claimed": 0, "kept": 0, "dropped": 0})

        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}
        hypotheses: dict[str, Any] = {"C001": {}}
        # All sources have short content_extract
        scorecards = {
            "C001": {
                "scorecards": [{"url": "https://a.com", "content_extract": "short"}],
            },
        }
        result = step5b_extract_evidence(research_input, hypotheses, scorecards, MagicMock())
        assert "extraction_notes" in result["C001"]
        assert "sufficient" in result["C001"]["extraction_notes"].lower()
        mock_extract.assert_not_called()

    @patch("diogenes.pipeline._extract_evidence_for_item")
    def test_extraction_notes_with_errors_and_drops(self, mock_extract: MagicMock) -> None:
        mock_extract.return_value = (
            [{"excerpt": "ok"}],
            ["extractor error: timeout"],
            {"claimed": 5, "kept": 1, "dropped": 4},
        )

        research_input = {"claims": [], "queries": [{"id": "Q001", "clarified_text": "Test"}]}
        hypotheses: dict[str, Any] = {"Q001": {}}
        scorecards = {
            "Q001": {
                "scorecards": [
                    {"url": "https://a.com", "content_extract": "x" * 200},
                    {"url": "https://b.com", "content_extract": "short"},  # will be skipped
                ],
            },
        }
        result = step5b_extract_evidence(research_input, hypotheses, scorecards, MagicMock())
        notes = result["Q001"]["extraction_notes"]
        assert "skipped" in notes.lower()
        assert "Extractor failed" in notes
        assert "Verbatim validator dropped" in notes


class TestStep4ExecuteSearches:
    """Tests for step4_execute_searches."""

    def _client_with_defaults(self) -> MagicMock:
        """Mock APIClient whose .pipeline uses the real dataclass defaults."""
        from diogenes.config import PipelineConfig

        client = MagicMock()
        client.pipeline = PipelineConfig()
        client.model_for.return_value = "claude-sonnet-4-6"
        return client

    @patch("diogenes.pipeline.execute_search_plan")
    def test_executes_searches(self, mock_exec: MagicMock) -> None:
        from diogenes.search import SearchExecution, SearchResult

        mock_exec.return_value = [
            SearchExecution(
                search_id="S01",
                terms=["test"],
                provider="mock",
                date="2026-01-01",
                results=[SearchResult(title="T", url="https://a.com", snippet="S")],
                total_results_available=1,
            )
        ]
        mock_client = self._client_with_defaults()
        mock_client.call_sub_agent.return_value = {
            "scores": [{"url": "https://a.com", "relevance_score": 8}],
        }
        mock_provider = MagicMock()
        mock_provider.name = "mock"

        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}
        search_plans = {"C001": {"searches": [{"id": "S01", "terms": ["test"]}]}}

        result = step4_execute_searches(research_input, search_plans, mock_client, mock_provider)
        assert "C001" in result
        assert len(result["C001"]["selected_sources"]) == 1

    @patch("diogenes.pipeline.execute_search_plan")
    def test_logs_rejected_sources(self, mock_exec: MagicMock) -> None:
        from diogenes.search import SearchExecution, SearchResult

        mock_exec.return_value = [
            SearchExecution(
                search_id="S01",
                terms=["test"],
                provider="mock",
                date="2026-01-01",
                results=[SearchResult(title="T", url="https://a.com", snippet="S")],
                total_results_available=1,
            )
        ]
        mock_client = self._client_with_defaults()
        mock_client.call_sub_agent.return_value = {
            "scores": [{"url": "https://a.com", "relevance_score": 2}],  # Below threshold
        }
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_logger = MagicMock()

        research_input = {"claims": [], "queries": [{"id": "Q001", "clarified_text": "Test"}]}
        search_plans = {"Q001": {"searches": [{"id": "S01", "terms": ["test"]}]}}

        result = step4_execute_searches(research_input, search_plans, mock_client, mock_provider, mock_logger)
        assert len(result["Q001"]["rejected_sources"]) == 1
        mock_logger.log.assert_called()


class TestSteps678SynthesizeAndAssess:
    """Tests for steps678_synthesize_and_assess."""

    def test_synthesizes_items(self) -> None:
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {
            "assessment": {"verdict": "Supported", "confidence": "High"},
            "synthesis": "Evidence supports the claim.",
        }

        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}
        hypotheses: dict[str, Any] = {"C001": {}}
        scorecards = {"C001": {"scorecards": [{"url": "https://a.com"}]}}
        evidence = {"C001": {"packets": [{"excerpt": "test"}]}}

        result = steps678_synthesize_and_assess(research_input, hypotheses, scorecards, evidence, mock_client)
        assert "C001" in result
        assert result["C001"]["assessment"]["verdict"] == "Supported"


class TestStep9SelfAudit:
    """Tests for step9_self_audit."""

    def test_audits_items(self) -> None:
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {
            "process_audit": {
                "eligibility_criteria": {"rating": "Pass"},
                "search_comprehensiveness": {"rating": "Pass"},
                "evaluation_consistency": {"rating": "Pass"},
                "synthesis_fairness": {"rating": "Pass"},
            },
        }

        research_input = {"claims": [], "queries": [{"id": "Q001", "clarified_text": "Test"}]}
        result = step9_self_audit(
            research_input,
            {"Q001": {}},
            {"Q001": {}},
            {"Q001": {"scorecards": []}},
            {"Q001": {"packets": []}},
            {"Q001": {}},
            mock_client,
        )
        assert "Q001" in result


class TestPipelineBranchCoverage:
    """Targeted tests for branch partials."""

    def test_score_results_batched_url_mismatch(self) -> None:
        """Covers 295->301, 296->295: scorer returns URL not in batch (no match)."""
        mock_client = MagicMock()
        # Scorer returns a URL that doesn't match any in the batch
        mock_client.call_sub_agent.return_value = {"scores": [{"url": "https://unmatched.com", "relevance_score": 7}]}

        from diogenes.search import SearchExecution, SearchResult

        execution = SearchExecution(
            search_id="S01",
            terms=["test"],
            provider="mock",
            date="2026-01-01",
            results=[SearchResult(title="T", url="https://a.com", snippet="S")],
            total_results_available=1,
        )
        item = {"id": "Q001", "clarified_text": "Test"}
        scored, unscored = _score_results_batched(item, [execution], mock_client, Path("/tmp/fake.md"))
        # Score entry should be present but without title/snippet enrichment
        assert len(scored) == 1
        assert "title" not in scored[0]
        # The batch URL that the scorer didn't score must surface as an
        # unscored reject so the invariant holds.
        assert len(unscored) == 1
        assert unscored[0]["url"] == "https://a.com"

    @patch("diogenes.pipeline._fetch_sources_for_scoring")
    def test_step5_source_without_content_extract(self, mock_fetch: MagicMock) -> None:
        """Covers 491->489: source field is empty/missing, if value: is False."""
        mock_fetch.return_value = [
            {"url": "https://a.com", "title": "", "snippet": "", "content_extract": ""},
        ]
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {
            "scorecards": [{"url": "https://a.com", "score": 8}],
        }

        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}
        search_results = {
            "C001": {"selected_sources": [{"url": "https://a.com"}]},
        }
        result = step5_score_sources(research_input, search_results, mock_client)
        # Empty fields should not be joined
        sc = result["C001"]["scorecards"][0]
        assert "content_extract" not in sc or not sc.get("content_extract")

    @patch("diogenes.pipeline._fetch_sources_for_scoring")
    def test_step5_scorecard_already_has_items(self, mock_fetch: MagicMock) -> None:
        """Covers 493->487: scorecard already has 'items', skip adding."""
        mock_fetch.return_value = [
            {"url": "https://a.com", "title": "T", "snippet": "S", "content_extract": "body"},
        ]
        mock_client = MagicMock()
        # Scorer returns scorecards with items already populated
        mock_client.call_sub_agent.return_value = {
            "scorecards": [{"url": "https://a.com", "score": 8, "items": ["pre-existing"]}],
        }

        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}
        search_results = {
            "C001": {"selected_sources": [{"url": "https://a.com"}]},
        }
        result = step5_score_sources(research_input, search_results, mock_client)
        # Pre-existing items should not be overwritten
        assert result["C001"]["scorecards"][0]["items"] == ["pre-existing"]

    @patch("diogenes.pipeline._fetch_sources_for_scoring")
    def test_step5_sources_exceed_cap(self, mock_fetch: MagicMock) -> None:
        """Covers line 451: len(all_selected) > _MAX_SOURCES_TO_SCORE triggers cap message."""
        mock_fetch.return_value = []
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {"scorecards": []}

        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}
        # 20 selected sources > _MAX_SOURCES_TO_SCORE=15
        search_results = {
            "C001": {"selected_sources": [{"url": f"https://s{i}.com"} for i in range(20)]},
        }
        step5_score_sources(research_input, search_results, mock_client)
        # Fetch should have been called with capped list (15 sources)
        call_args = mock_fetch.call_args
        assert len(call_args.args[1]) == 15

    @patch("diogenes.pipeline.parallelize_thread")
    def test_extract_evidence_no_dropped_prints_verified(self, mock_par: MagicMock) -> None:
        """Covers line 652: else branch when no packets were dropped."""
        from diogenes.parallelize import ExecutorResults

        mock_par.return_value = ExecutorResults(
            results=[
                {
                    "url": "https://a.com",
                    "verified_packets": [{"excerpt": "ok"}],
                    "claimed": 1,
                    "kept": 1,
                    "dropped": 0,
                },
            ],
            exceptions=[],
        )

        item = {"id": "Q001", "clarified_text": "test"}
        packets, _errors, stats = _extract_evidence_for_item(
            item=item,
            item_hypotheses={},
            substantive=[{"url": "https://a.com", "content_extract": "text"}],
            prompt_path=Path("/tmp/fake.md"),
            client=MagicMock(),
        )
        assert stats["dropped"] == 0
        assert len(packets) == 1


class TestStep10Report:
    """Tests for step10_report."""

    def test_generates_report(self) -> None:
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {
            "title": "Sample topic label",
            "assessment_summary": {"verdict": "Supported", "answer": "Yes"},
        }

        research_input = {
            "claims": [{"id": "C001", "clarified_text": "Test claim"}],
            "queries": [{"id": "Q001", "clarified_text": "Test query"}],
        }
        result = step10_report(
            research_input,
            {"C001": {}, "Q001": {}},
            {"C001": {}, "Q001": {}},
            {"C001": {"scorecards": []}, "Q001": {"scorecards": []}},
            {"C001": {}, "Q001": {}},
            {"C001": {}, "Q001": {}},
            mock_client,
        )
        assert "C001" in result
        assert "Q001" in result

    def test_uses_reports_schema(self) -> None:
        """step10_report passes reports.schema.json to the sub-agent (issue #161)."""
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {
            "title": "Topic",
            "assessment_summary": {"verdict": "Supported"},
        }
        research_input = {"claims": [{"id": "C001", "clarified_text": "Test"}], "queries": []}

        step10_report(
            research_input,
            {"C001": {}},
            {"C001": {}},
            {"C001": {"scorecards": []}},
            {"C001": {}},
            {"C001": {}},
            mock_client,
        )

        _args, kwargs = mock_client.call_sub_agent.call_args
        assert kwargs["output_schema"] == "reports.schema.json", (
            "step10_report must declare the reports schema so constrained decoding "
            "enforces the new required `title` field from issue #161"
        )

    def test_preserves_title_field_from_agent_response(self) -> None:
        """The `title` field round-trips from the sub-agent response into results (issue #161).

        The renderer's run-level index cards read `report.title` to build
        their heading. If step10_report ever drops or rewrites the field,
        the index collapses to bare ids — the exact regression #161 fixes.
        """
        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {
            "title": "LLM watermarking techniques survey",
            "assessment_summary": {"verdict": "Supported", "confidence": "High (80-95%)"},
        }

        research_input = {"claims": [{"id": "C001", "clarified_text": "Test claim"}], "queries": []}
        result = step10_report(
            research_input,
            {"C001": {}},
            {"C001": {}},
            {"C001": {"scorecards": []}},
            {"C001": {}},
            {"C001": {}},
            mock_client,
        )

        assert result["C001"]["title"] == "LLM watermarking techniques survey", (
            "step10_report must surface the agent's `title` field verbatim so the "
            "renderer can build run-level index card headings"
        )


class TestReportsSchema:
    """Schema-level tests for reports.schema.json (issue #161)."""

    def test_schema_requires_top_level_title(self) -> None:
        """`title` is a required top-level field on every report.

        The renderer's `_card_heading_for` reads it to build headings like
        `### Q001 — <topic> — <qualifier>`. Missing `title` collapsed R0063's
        run-level index to bare `### Q001` cards (issue #161). Making the
        field required here means constrained-decoding catches the regression
        at the API boundary, not at render time.
        """
        import json as _json
        from pathlib import Path as _Path

        schema_path = _Path(__file__).parent.parent / "src" / "diogenes" / "schemas" / "reports.schema.json"
        schema = _json.loads(schema_path.read_text())
        assert "title" in schema["required"], (
            "reports.schema.json must list `title` as required so constrained "
            "decoding rejects outputs that would collapse the run-level index"
        )
        assert schema["properties"]["title"]["type"] == "string"
        # Hard cap matches the issue spec (~60 chars, ~8-10 words)
        assert schema["properties"]["title"].get("maxLength") == 60

    def test_reports_prompt_describes_title_field(self) -> None:
        """reports.md tells the LLM to produce the `title` field (issue #161)."""
        from pathlib import Path as _Path

        prompt_path = _Path(__file__).parent.parent / "src" / "diogenes" / "prompts" / "sub-agents" / "reports.md"
        prompt_text = prompt_path.read_text()
        assert "title" in prompt_text.lower(), "reports.md must instruct the LLM to emit `title`"
        assert "60 character" in prompt_text or "60 char" in prompt_text, (
            "reports.md must state the 60-character hard cap so the LLM produces headings that fit on one TOC line"
        )


class TestRejectionReasonEnum:
    """Tests for the REJECTION_REASONS enum-like constant (issue #163)."""

    def test_enum_contains_all_documented_reasons(self) -> None:
        """Every reason exported as a module constant is in the enum set."""
        assert REJECTION_REASON_BELOW_THRESHOLD in REJECTION_REASONS
        assert REJECTION_REASON_DUPLICATE_URL in REJECTION_REASONS
        assert REJECTION_REASON_SCORER_DID_NOT_SCORE in REJECTION_REASONS

    def test_enum_values_are_machine_readable_strings(self) -> None:
        """Reasons must be ASCII-safe snake_case strings so downstream tooling can filter."""
        for reason in REJECTION_REASONS:
            assert isinstance(reason, str)
            assert reason == reason.lower()
            assert " " not in reason

    def test_event_kind_for_known_reason(self) -> None:
        """Known reasons map to distinct event kinds — one per reason."""
        kinds = {_event_kind_for_reason(r) for r in REJECTION_REASONS}
        assert len(kinds) == len(REJECTION_REASONS), (
            "each rejection reason must get a distinct event.kind so Step 8 "
            "self-audit can filter events by bucket without string parsing"
        )

    def test_event_kind_for_unknown_reason_falls_back(self) -> None:
        """Unknown reasons fall back to a generic kind rather than raising."""
        assert _event_kind_for_reason("not_a_real_reason") == "rejected"


class TestScoreResultsBatchedScorerOmission:
    """Regression: scorer omissions (issue #163) surface as unscored rejects."""

    def _client_with_defaults(self) -> MagicMock:
        """Mock APIClient whose .pipeline uses the real dataclass defaults.

        Without real PipelineConfig, ``batch_size`` comes back as a
        MagicMock and ``range(0, n, MagicMock)`` loops unpredictably —
        which masks the invariant behavior the test is trying to pin down.
        """
        from diogenes.config import PipelineConfig

        client = MagicMock()
        client.pipeline = PipelineConfig()
        client.model_for.return_value = "claude-sonnet-4-6"
        return client

    def test_scorer_returns_no_scores_all_unscored(self) -> None:
        """Every unscored batch URL surfaces as an unscored reject.

        When the scorer returns an empty scores list, every URL in the
        batch must surface as an unscored reject — the R0063/Q001/S01 case
        in miniature.
        """
        from diogenes.search import SearchExecution, SearchResult

        mock_client = self._client_with_defaults()
        mock_client.call_sub_agent.return_value = {"scores": []}
        execution = SearchExecution(
            search_id="S01",
            terms=["test"],
            provider="mock",
            date="2026-01-01",
            results=[
                SearchResult(title="T1", url="https://a.com", snippet="S1"),
                SearchResult(title="T2", url="https://b.com", snippet="S2"),
            ],
            total_results_available=2,
        )
        scored, unscored = _score_results_batched(
            {"id": "Q001", "clarified_text": "test"},
            [execution],
            mock_client,
            Path("/tmp/fake.md"),
        )
        assert scored == []
        assert len(unscored) == 2
        assert {u["url"] for u in unscored} == {"https://a.com", "https://b.com"}
        for u in unscored:
            assert u["reason"] == REJECTION_REASON_SCORER_DID_NOT_SCORE
            assert u["search_id"] == "S01"
            assert u["relevance_score"] is None

    def test_scorer_returns_partial_scores_unscored_accounted(self) -> None:
        """Mirror of R0063/Q001/S01: 5 returned, scorer returns 4, 1 unscored."""
        from diogenes.search import SearchExecution, SearchResult

        mock_client = self._client_with_defaults()
        # Scorer returns 4 of 5 — exactly the R0063 shape.
        mock_client.call_sub_agent.return_value = {
            "scores": [
                {"url": "https://arxiv.org/html/2602.13962v1", "relevance_score": 8, "rationale": "r1"},
                {"url": "https://www.sciencedirect.com/s", "relevance_score": 7, "rationale": "r2"},
                {"url": "https://arxiv.org/html/2504.04372v1", "relevance_score": 6, "rationale": "r3"},
                {"url": "https://xiaoningdu.github.io/assets/pdf/format.pdf", "relevance_score": 5, "rationale": "r4"},
            ],
        }
        # The fifth URL — the springer link that went missing in R0063 —
        # must land in unscored_rejects so the invariant holds.
        results = [
            SearchResult(title="T1", url="https://arxiv.org/html/2602.13962v1", snippet="s1"),
            SearchResult(title="T2", url="https://www.sciencedirect.com/s", snippet="s2"),
            SearchResult(title="T3", url="https://arxiv.org/html/2504.04372v1", snippet="s3"),
            SearchResult(
                title="T4",
                url="https://link.springer.com/article/10.1007/s10664-026-10858-8",
                snippet="s4",
            ),
            SearchResult(title="T5", url="https://xiaoningdu.github.io/assets/pdf/format.pdf", snippet="s5"),
        ]
        execution = SearchExecution(
            search_id="S01",
            terms=["test"],
            provider="mock",
            date="2026-01-01",
            results=results,
            total_results_available=5,
        )
        scored, unscored = _score_results_batched(
            {"id": "Q001", "clarified_text": "test"},
            [execution],
            mock_client,
            Path("/tmp/fake.md"),
        )
        assert len(scored) == 4
        assert len(unscored) == 1
        assert unscored[0]["url"] == "https://link.springer.com/article/10.1007/s10664-026-10858-8"
        assert unscored[0]["reason"] == REJECTION_REASON_SCORER_DID_NOT_SCORE
        assert "did not return" in unscored[0]["rationale"].lower()


class TestFilterAndDeduplicateReasons:
    """Tests that _filter_and_deduplicate records structured reasons (issue #163)."""

    def test_below_threshold_records_reason(self) -> None:
        results = [{"url": "https://a.com", "relevance_score": 2, "search_id": "S01"}]
        selected, rejected = _filter_and_deduplicate(results, threshold=5)
        assert selected == []
        assert len(rejected) == 1
        assert rejected[0]["reason"] == REJECTION_REASON_BELOW_THRESHOLD

    def test_duplicate_url_recorded_as_rejected(self) -> None:
        """Dedupe must produce a rejected entry for the loser, not drop it."""
        results = [
            {"url": "https://a.com", "relevance_score": 9, "search_id": "S01", "title": "first"},
            {"url": "https://a.com", "relevance_score": 7, "search_id": "S02", "title": "second"},
        ]
        selected, rejected = _filter_and_deduplicate(results, threshold=5)
        assert len(selected) == 1
        assert selected[0]["relevance_score"] == 9
        assert len(rejected) == 1
        assert rejected[0]["reason"] == REJECTION_REASON_DUPLICATE_URL
        # The loser keeps its own search_id so the per-search invariant holds.
        assert rejected[0]["search_id"] == "S02"
        assert "duplicate" in rejected[0]["rationale"].lower()

    def test_none_score_treated_as_lowest(self) -> None:
        """A None relevance_score must not crash sorting.

        An unscored_reject accidentally fed through with
        ``relevance_score=None`` must not raise a TypeError when sorting,
        and must be treated as below any real threshold.
        """
        results: list[dict[str, Any]] = [
            {"url": "https://real.com", "relevance_score": 8, "search_id": "S01"},
            {"url": "https://unscored.com", "relevance_score": None, "search_id": "S01"},
        ]
        selected, rejected = _filter_and_deduplicate(results, threshold=5)
        assert len(selected) == 1
        assert selected[0]["url"] == "https://real.com"
        # The None-score entry lands in rejected with below_threshold reason
        # (since None is normalized to 0 for comparison).
        assert len(rejected) == 1
        assert rejected[0]["reason"] == REJECTION_REASON_BELOW_THRESHOLD

    def test_preserves_existing_reason_on_pass_through(self) -> None:
        """Pre-stamped reasons survive the threshold check.

        If the caller pre-stamped a reason (e.g., scorer_did_not_score),
        the threshold check must not overwrite it.
        """
        # Simulate an entry that somehow made it through with a pre-stamped
        # reason and a low score — the reason must stick.
        results = [
            {
                "url": "https://x.com",
                "relevance_score": 1,
                "search_id": "S01",
                "reason": REJECTION_REASON_SCORER_DID_NOT_SCORE,
            },
        ]
        _selected, rejected = _filter_and_deduplicate(results, threshold=5)
        assert len(rejected) == 1
        assert rejected[0]["reason"] == REJECTION_REASON_SCORER_DID_NOT_SCORE


class TestValidateSearchResultsDispositioning:
    """Tests for the invariant validator (issue #163)."""

    def test_invariant_holds_returns_empty(self) -> None:
        """Validator returns [] when selected + rejected == total_returned per search_id."""
        search_results = {
            "Q001": {
                "id": "Q001",
                "searches_executed": [
                    {"search_id": "S01", "results": [{"url": "a"}, {"url": "b"}]},
                ],
                "selected_sources": [{"url": "a", "search_id": "S01"}],
                "rejected_sources": [{"url": "b", "search_id": "S01", "reason": "below_relevance_threshold"}],
            },
        }
        violations = validate_search_results_dispositioning(search_results)
        assert violations == []

    def test_invariant_violation_r0063_q001_s01_shape(self) -> None:
        """Flags the exact R0063 Q001/S01 silent-drop case.

        Reproduces the shape that triggered #163: 5 returned, 4 selected,
        0 rejected, 1 unaccounted — must be flagged by the validator.
        """
        search_results = {
            "Q001": {
                "id": "Q001",
                "searches_executed": [
                    {
                        "search_id": "S01",
                        "results": [
                            {"url": "https://arxiv.org/html/2602.13962v1"},
                            {"url": "https://www.sciencedirect.com/article"},
                            {"url": "https://arxiv.org/html/2504.04372v1"},
                            {"url": "https://link.springer.com/article/10.1007/s10664-026-10858-8"},
                            {"url": "https://xiaoningdu.github.io/assets/pdf/format.pdf"},
                        ],
                    },
                ],
                "selected_sources": [
                    {"url": "https://arxiv.org/html/2602.13962v1", "search_id": "S01"},
                    {"url": "https://www.sciencedirect.com/article", "search_id": "S01"},
                    {"url": "https://arxiv.org/html/2504.04372v1", "search_id": "S01"},
                    {"url": "https://xiaoningdu.github.io/assets/pdf/format.pdf", "search_id": "S01"},
                ],
                "rejected_sources": [],
            },
        }
        violations = validate_search_results_dispositioning(search_results)
        assert len(violations) == 1
        v = violations[0]
        assert v["item_id"] == "Q001"
        assert v["search_id"] == "S01"
        assert v["total_returned"] == 5
        assert v["selected"] == 4
        assert v["rejected"] == 0
        assert v["unaccounted"] == 1

    def test_invariant_violation_logs_event(self) -> None:
        """Violations write dispositioning_invariant_violated events.

        So Step 8 self-audit can surface them in the final report.
        """
        from diogenes.events import EventLogger

        search_results = {
            "Q001": {
                "id": "Q001",
                "searches_executed": [
                    {"search_id": "S01", "results": [{"url": "a"}, {"url": "b"}]},
                ],
                "selected_sources": [],
                "rejected_sources": [],
            },
        }
        event_logger = EventLogger(run_id="test")
        violations = validate_search_results_dispositioning(search_results, event_logger=event_logger)
        assert len(violations) == 1
        # Event must carry the specific kind so consumers can filter.
        events = [e for e in event_logger.events if e["kind"] == "dispositioning_invariant_violated"]
        assert len(events) == 1
        assert events[0]["item_id"] == "Q001"
        assert events[0]["count"] == 2  # 2 unaccounted
        assert "Q001/S01" in events[0]["detail"]

    def test_invariant_multiple_searches_multiple_violations(self) -> None:
        """Each (item, search) pair is checked independently."""
        search_results = {
            "Q001": {
                "id": "Q001",
                "searches_executed": [
                    {"search_id": "S01", "results": [{"url": "a"}]},
                    {"search_id": "S02", "results": [{"url": "b"}, {"url": "c"}]},
                ],
                "selected_sources": [{"url": "a", "search_id": "S01"}],
                # S02 has two URLs returned but nothing dispositioned — a violation.
                "rejected_sources": [],
            },
        }
        violations = validate_search_results_dispositioning(search_results)
        assert len(violations) == 1
        assert violations[0]["search_id"] == "S02"

    def test_invariant_skips_non_dict_item_data(self) -> None:
        """Validator ignores non-dict entries in search_results.

        A leftover summary blob or similar top-level scalar must be
        ignored rather than crashing the validator.
        """
        search_results = {
            "Q001": "not a dict",
            "Q002": {
                "id": "Q002",
                "searches_executed": [{"search_id": "S01", "results": []}],
                "selected_sources": [],
                "rejected_sources": [],
            },
        }
        # Must not raise; Q001 is skipped, Q002 is clean.
        violations = validate_search_results_dispositioning(search_results)
        assert violations == []

    def test_invariant_handles_missing_fields(self) -> None:
        """Missing fields default cleanly to empty — no KeyError or TypeError.

        Covers the case where an item has no ``searches_executed`` /
        ``selected_sources`` / ``rejected_sources`` at all.
        """
        search_results = {"Q001": {"id": "Q001"}}
        violations = validate_search_results_dispositioning(search_results)
        assert violations == []

    def test_invariant_logger_warning_on_violations(self, caplog: pytest.LogCaptureFixture) -> None:
        """A summary warning is logged when violations are present.

        So operators see the violation count without parsing the events
        file.
        """
        search_results = {
            "Q001": {
                "id": "Q001",
                "searches_executed": [{"search_id": "S01", "results": [{"url": "a"}]}],
                "selected_sources": [],
                "rejected_sources": [],
            },
        }
        with caplog.at_level("INFO", logger="diogenes.pipeline"):
            validate_search_results_dispositioning(search_results)
        assert "dispositioning invariant" in caplog.text.lower()


class TestStep4ExecuteSearchesEndToEndInvariant:
    """Integration: step4_execute_searches produces invariant-holding output (issue #163)."""

    def _client_with_defaults(self) -> MagicMock:
        from diogenes.config import PipelineConfig

        client = MagicMock()
        client.pipeline = PipelineConfig()
        client.model_for.return_value = "claude-sonnet-4-6"
        return client

    @patch("diogenes.pipeline.execute_search_plan")
    def test_scorer_omission_surfaces_as_rejected(self, mock_exec: MagicMock) -> None:
        """R0063-shape regression: 5 results in, scorer returns 4, invariant holds."""
        from diogenes.search import SearchExecution, SearchResult

        # Five raw results
        results = [SearchResult(title=f"T{i}", url=f"https://r{i}.com", snippet=f"s{i}") for i in range(5)]
        mock_exec.return_value = [
            SearchExecution(
                search_id="S01",
                terms=["test"],
                provider="mock",
                date="2026-01-01",
                results=results,
                total_results_available=5,
            )
        ]

        mock_client = self._client_with_defaults()
        # Scorer returns only 4 of the 5
        mock_client.call_sub_agent.return_value = {
            "scores": [
                {"url": "https://r0.com", "relevance_score": 8, "rationale": "r"},
                {"url": "https://r1.com", "relevance_score": 7, "rationale": "r"},
                {"url": "https://r2.com", "relevance_score": 6, "rationale": "r"},
                {"url": "https://r3.com", "relevance_score": 5, "rationale": "r"},
                # https://r4.com is omitted — the R0063 bug shape
            ],
        }
        mock_provider = MagicMock()
        mock_provider.name = "mock"

        research_input = {"claims": [], "queries": [{"id": "Q001", "clarified_text": "t"}]}
        search_plans = {"Q001": {"searches": [{"id": "S01", "terms": ["t"]}]}}

        result = step4_execute_searches(research_input, search_plans, mock_client, mock_provider)

        q001 = result["Q001"]
        selected_s01 = [s for s in q001["selected_sources"] if s.get("search_id") == "S01"]
        rejected_s01 = [s for s in q001["rejected_sources"] if s.get("search_id") == "S01"]
        # Invariant: selected + rejected == total_returned.
        total_returned = len(q001["searches_executed"][0]["results"])
        assert len(selected_s01) + len(rejected_s01) == total_returned, (
            "step4_execute_searches must produce output that satisfies the "
            "per-search dispositioning invariant even when the LLM scorer "
            "omits URLs — the R0063 regression"
        )
        # The unscored URL must be in rejected with the scorer_did_not_score reason.
        unscored = [s for s in rejected_s01 if s["reason"] == REJECTION_REASON_SCORER_DID_NOT_SCORE]
        assert len(unscored) == 1
        assert unscored[0]["url"] == "https://r4.com"

    @patch("diogenes.pipeline.execute_search_plan")
    def test_duplicate_urls_produce_duplicate_url_reason(self, mock_exec: MagicMock) -> None:
        """Same URL in two searches → first wins; second is a structured dedupe reject.

        The duplicate-url reject must land in ``rejected_sources`` with
        ``reason`` = ``duplicate_url`` rather than being silently dropped.
        """
        from diogenes.search import SearchExecution, SearchResult

        # Same URL in two searches
        mock_exec.return_value = [
            SearchExecution(
                search_id="S01",
                terms=["a"],
                provider="mock",
                date="2026-01-01",
                results=[SearchResult(title="T", url="https://dup.com", snippet="s")],
                total_results_available=1,
            ),
            SearchExecution(
                search_id="S02",
                terms=["b"],
                provider="mock",
                date="2026-01-01",
                results=[SearchResult(title="T", url="https://dup.com", snippet="s")],
                total_results_available=1,
            ),
        ]

        mock_client = self._client_with_defaults()
        mock_client.call_sub_agent.side_effect = [
            {"scores": [{"url": "https://dup.com", "relevance_score": 9, "rationale": "a"}]},
            {"scores": [{"url": "https://dup.com", "relevance_score": 6, "rationale": "b"}]},
        ]
        mock_provider = MagicMock()
        mock_provider.name = "mock"

        research_input = {"claims": [], "queries": [{"id": "Q001", "clarified_text": "t"}]}
        search_plans = {"Q001": {"searches": [{"id": "S01", "terms": ["a"]}, {"id": "S02", "terms": ["b"]}]}}

        result = step4_execute_searches(research_input, search_plans, mock_client, mock_provider)

        q001 = result["Q001"]
        dup_rejects = [s for s in q001["rejected_sources"] if s.get("reason") == REJECTION_REASON_DUPLICATE_URL]
        assert len(dup_rejects) == 1
        # The lower-scored duplicate keeps its own search_id so the per-search
        # invariant holds on each search.
        assert dup_rejects[0]["search_id"] == "S02"
        assert dup_rejects[0]["url"] == "https://dup.com"

    @patch("diogenes.pipeline.execute_search_plan")
    def test_invariant_holds_end_to_end(self, mock_exec: MagicMock) -> None:
        """All rejection paths exercised together; invariant validator reports zero violations."""
        from diogenes.events import EventLogger
        from diogenes.search import SearchExecution, SearchResult

        mock_exec.return_value = [
            SearchExecution(
                search_id="S01",
                terms=["a"],
                provider="mock",
                date="2026-01-01",
                results=[
                    SearchResult(title="T1", url="https://hit.com", snippet="s"),
                    SearchResult(title="T2", url="https://miss.com", snippet="s"),
                    SearchResult(title="T3", url="https://omitted.com", snippet="s"),
                ],
                total_results_available=3,
            )
        ]
        mock_client = self._client_with_defaults()
        mock_client.call_sub_agent.return_value = {
            "scores": [
                {"url": "https://hit.com", "relevance_score": 9, "rationale": "good"},
                {"url": "https://miss.com", "relevance_score": 2, "rationale": "bad"},
                # https://omitted.com not scored
            ],
        }
        mock_provider = MagicMock()
        mock_provider.name = "mock"

        event_logger = EventLogger(run_id="test")
        research_input = {"claims": [], "queries": [{"id": "Q001", "clarified_text": "t"}]}
        search_plans = {"Q001": {"searches": [{"id": "S01", "terms": ["a"]}]}}

        result = step4_execute_searches(research_input, search_plans, mock_client, mock_provider, event_logger)

        # Validator should see no violations.
        violations = validate_search_results_dispositioning(result)
        assert violations == []

        # No dispositioning_invariant_violated events should have been
        # emitted by step4's internal validator call either.
        violated_events = [e for e in event_logger.events if e["kind"] == "dispositioning_invariant_violated"]
        assert violated_events == []

        # Rejected bucket should contain both kinds of reasons.
        reasons = {s["reason"] for s in result["Q001"]["rejected_sources"]}
        assert REJECTION_REASON_BELOW_THRESHOLD in reasons
        assert REJECTION_REASON_SCORER_DID_NOT_SCORE in reasons
