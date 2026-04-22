"""Tests for pipeline module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from diogenes.pipeline import (
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
    step5_score_sources,
    step5b_extract_evidence,
    step11_archive,
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
        packet = {}
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
        selected, rejected = _filter_and_deduplicate(results)
        assert len(selected) == 1
        assert selected[0]["url"] == "https://a.com"
        assert len(rejected) == 1

    def test_deduplication(self) -> None:
        results = [
            {"url": "https://a.com", "relevance_score": 8},
            {"url": "https://a.com", "relevance_score": 7},
        ]
        selected, rejected = _filter_and_deduplicate(results)
        assert len(selected) == 1

    def test_sorted_by_score(self) -> None:
        results = [
            {"url": "https://a.com", "relevance_score": 5},
            {"url": "https://b.com", "relevance_score": 9},
        ]
        selected, _ = _filter_and_deduplicate(results)
        assert selected[0]["url"] == "https://b.com"

    def test_empty_input(self) -> None:
        selected, rejected = _filter_and_deduplicate([])
        assert selected == []
        assert rejected == []


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

    def test_writes_json(self, tmp_path: pytest.TempPathFactory) -> None:
        data = {"key": "value"}
        path = write_step_output(tmp_path, "output.json", data)  # type: ignore[arg-type]
        assert path.exists()
        assert json.loads(path.read_text()) == data

    def test_writes_list(self, tmp_path: pytest.TempPathFactory) -> None:
        data = [1, 2, 3]
        path = write_step_output(tmp_path, "output.json", data)  # type: ignore[arg-type]
        assert json.loads(path.read_text()) == data


class TestStep11Archive:
    """Tests for step11_archive."""

    def test_creates_archive(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs = {"research_input": {"claims": []}, "hypotheses": {"Q001": {}}}
        path = step11_archive(tmp_path, outputs)  # type: ignore[arg-type]
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

    def test_hypotheses_approach(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_hypothesis_summary("Q001", {"approach": "hypotheses", "hypotheses": [1, 2, 3]})
        assert "3 hypotheses" in capsys.readouterr().out

    def test_open_ended_approach(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_hypothesis_summary("Q001", {"approach": "open-ended", "search_themes": [1, 2]})
        assert "2 search themes" in capsys.readouterr().out

    def test_unknown_approach(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_hypothesis_summary("Q001", {"approach": "custom"})
        assert "approach=custom" in capsys.readouterr().out


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
        results = _score_results_batched(item, [execution], mock_client, Path("/tmp/fake.md"))
        assert len(results) == 1
        assert results[0]["search_id"] == "S01"
        assert results[0]["title"] == "T"


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
        hypotheses = {"C001": {}}
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
        hypotheses = {"C001": {}}
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
        hypotheses = {"Q001": {}}
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
