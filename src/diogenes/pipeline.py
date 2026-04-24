"""Research pipeline steps.

Each step function takes the accumulated research state and an API client,
calls the appropriate sub-agent for each item, and returns the enriched state.
The coordinator (run command) calls these in sequence.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from diogenes.parallelize import parallelize_process, parallelize_thread
from diogenes.search import SearchProvider, execute_search_plan, fetch_page_extract

if TYPE_CHECKING:
    from diogenes.api_client import APIClient
    from diogenes.events import EventLogger

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts" / "sub-agents"


# Structured, machine-readable disposition reasons for ``rejected_sources``
# entries produced by Step 4. Every raw result returned by the search
# provider must end up either in ``selected_sources`` or in
# ``rejected_sources`` with one of these reasons — dropping a result
# silently breaks the PRISMA accountability invariant that downstream
# reporting and reconciliation rely on.
#
# The enum is intentionally small; when a new drop path is introduced, add
# its reason code here alongside the code that emits it. The allowed-values
# docstring is the single source of truth — search-results.schema.json
# references these reasons by name when validating persisted outputs.
REJECTION_REASON_BELOW_THRESHOLD = "below_relevance_threshold"
"""Result was scored by the LLM relevance scorer but fell below the
configured relevance threshold."""

REJECTION_REASON_DUPLICATE_URL = "duplicate_url"
"""Result URL already appeared in a higher-scored entry; the pipeline
deduplicates by URL and keeps only the first occurrence."""

REJECTION_REASON_SCORER_DID_NOT_SCORE = "scorer_did_not_score"
"""The LLM relevance scorer did not return a score for this URL, even
though it was in the scorer's input batch. Tracked so that scorer
under-reporting is visible rather than silently dropping results."""

REJECTION_REASONS: frozenset[str] = frozenset(
    {
        REJECTION_REASON_BELOW_THRESHOLD,
        REJECTION_REASON_DUPLICATE_URL,
        REJECTION_REASON_SCORER_DID_NOT_SCORE,
    }
)

# Per-sub-agent model overrides are now configurable via .diorc under
# [pipeline.model_overrides]. Each call site uses client.model_for("<name>")
# to resolve: override if configured, default model otherwise. Historical
# testing (#84) showed Haiku produces different verdicts than Sonnet on
# scoring steps — overrides default to empty so behavior matches pre-#76
# unless a user opts in.


def step2_generate_hypotheses(
    research_input: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Generate competing hypotheses for each claim and query.

    Loops over claims and queries from the clarified input. For each item,
    passes the item and axioms to the hypothesis-generator sub-agent. Enriches
    the research state with hypothesis data per item.

    Args:
        research_input: The clarified research input (output of step 1).
        client: Configured API client with common guidelines loaded.

    Returns:
        A dict mapping item IDs to their hypothesis results.

    Raises:
        SubAgentError: If a sub-agent call fails.

    """
    prompt_path = _PROMPTS_DIR / "hypotheses.md"
    axioms = research_input.get("axioms", [])
    results: dict[str, Any] = {}

    claims = research_input.get("claims", [])
    queries = research_input.get("queries", [])

    for claim in claims:
        item_id = claim["id"]
        logger.info(f"  Generating hypotheses for {item_id}: {claim['clarified_text'][:60]}...")

        agent_input = {
            "mode": "claim",
            "item": claim,
            "axioms": axioms,
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="hypotheses.schema.json",
            model=client.model_for("hypothesis_generator"),
        )

        results[item_id] = response
        _print_hypothesis_summary(item_id, response)

    for query in queries:
        item_id = query["id"]
        logger.info(f"  Generating hypotheses for {item_id}: {query['clarified_text'][:60]}...")

        agent_input = {
            "mode": "query",
            "item": query,
            "axioms": axioms,
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="hypotheses.schema.json",
            model=client.model_for("hypothesis_generator"),
        )

        results[item_id] = response
        _print_hypothesis_summary(item_id, response)

    return results


def _print_hypothesis_summary(item_id: str, response: dict[str, Any]) -> None:
    """Print a brief summary of hypothesis generation results."""
    approach = response.get("approach", "unknown")
    if approach == "hypotheses":
        count = len(response.get("hypotheses", []))
        logger.info(f"    {item_id}: {count} hypotheses generated")
    elif approach == "open-ended":
        count = len(response.get("search_themes", []))
        logger.info(f"    {item_id}: open-ended, {count} search themes")
    else:
        logger.info(f"    {item_id}: approach={approach}")


def step3_design_searches(
    research_input: dict[str, Any],
    hypotheses: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Design discriminating searches for each claim and query.

    For each item, passes the clarified item (with vocabulary) and its
    hypotheses to the search-designer sub-agent to produce a concrete
    search plan.

    Args:
        research_input: The clarified research input (output of step 1).
        hypotheses: The hypothesis results keyed by item ID (output of step 2).
        client: Configured API client with common guidelines loaded.

    Returns:
        A dict mapping item IDs to their search plan results.

    Raises:
        SubAgentError: If a sub-agent call fails.

    """
    prompt_path = _PROMPTS_DIR / "search-plans.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        item_hypotheses = hypotheses.get(item_id, {})
        logger.info(f"  Designing searches for {item_id}...")

        agent_input = {
            "item": item,
            "hypotheses": item_hypotheses,
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="search-plans.schema.json",
            model=client.model_for("search_designer"),
        )

        results[item_id] = response
        search_count = len(response.get("searches", []))
        approach = response.get("approach", "unknown")
        logger.info(f"    {item_id}: {search_count} searches planned ({approach})")

    return results


def step4_execute_searches(
    research_input: dict[str, Any],
    search_plans: dict[str, Any],
    client: APIClient,
    search_provider: SearchProvider,
    event_logger: EventLogger | None = None,
) -> dict[str, Any]:
    """Execute search plans and score results for each claim and query.

    Three phases:
    - 4A (Python): Execute searches via search provider. Zero LLM tokens.
    - 4B (LLM, batched): Score relevance 0-10 in batches. Tiny calls.
    - 4C (Python): Sort by score, filter by threshold, deduplicate.

    Pipeline tunables read from ``client.pipeline``:
    - ``results_per_search`` controls how many results each search query returns
    - ``scoring_batch_size`` controls how many results are scored per LLM call
    - ``relevance_threshold`` controls the inclusion cut-off for Step 4C

    Args:
        research_input: The clarified research input (output of step 1).
        search_plans: The search plans keyed by item ID (output of step 3).
        client: Configured API client with common guidelines loaded.
        search_provider: Search provider for executing web searches.
        event_logger: Pipeline event logger for recording threshold rejects.

    Returns:
        A dict mapping item IDs to their search results.

    Raises:
        SubAgentError: If a sub-agent call fails.

    """
    scorer_prompt = _PROMPTS_DIR / "search-results.md"
    results: dict[str, Any] = {}
    threshold = client.pipeline.relevance_threshold

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        item_plan = search_plans.get(item_id, {})
        searches = item_plan.get("searches", [])
        logger.info(f"  Executing {len(searches)} searches for {item_id} via {search_provider.name}...")

        # Phase 4A: Python executes searches
        executions = execute_search_plan(
            item_plan,
            search_provider,
            max_results_per_search=client.pipeline.results_per_search,
        )
        total_results = sum(len(e.results) for e in executions)
        logger.info(f"    {total_results} raw results from {len(executions)} searches")

        # Phase 4B: LLM scores relevance in batches. Scorer omissions
        # (URLs in the batch the scorer didn't score) come back as
        # pre-built rejected entries with reason = scorer_did_not_score.
        all_scored, unscored_rejects = _score_results_batched(
            item,
            executions,
            client,
            scorer_prompt,
        )

        # Phase 4C: Python filters and deduplicates. Threshold rejects get
        # reason = below_relevance_threshold; dedupe drops get reason =
        # duplicate_url. Merging unscored_rejects in at the end keeps all
        # rejection paths in one list with structured reasons.
        selected, filter_rejected = _filter_and_deduplicate(all_scored, threshold=threshold)
        rejected = filter_rejected + unscored_rejects
        logger.info(
            f"    {len(selected)} sources selected (score >= {threshold}), "
            f"{len(rejected)} rejected ({len(filter_rejected)} by threshold/dedupe, "
            f"{len(unscored_rejects)} unscored)"
        )

        if event_logger:
            for rej in rejected:
                reason = rej.get("reason", "unknown")
                event_logger.log(
                    step="step4_execute_searches",
                    kind=_event_kind_for_reason(reason),
                    detail=(
                        f"Result rejected with reason={reason}: "
                        f"score={rej.get('relevance_score', '?')}, threshold={threshold}"
                    ),
                    url=rej.get("url", ""),
                    item_id=item_id,
                    score=rej.get("relevance_score"),
                    threshold=float(threshold),
                    layer="pipeline",
                )

        results[item_id] = {
            "id": item_id,
            "searches_executed": [e.to_dict() for e in executions],
            "selected_sources": selected,
            "rejected_sources": rejected,
            "summary": {
                "total_searches": len(executions),
                "total_results_found": total_results,
                "total_selected": len(selected),
                "total_rejected": len(rejected),
                "relevance_threshold": threshold,
            },
        }

    # Run the dispositioning invariant after all items are processed.
    # Violations become structured events the Step 8 self-audit picks
    # up. We do not hard-fail the pipeline — previous silent drops would
    # have made R0063 unverifiable even with perfect-looking outputs, so
    # visibility is the upgrade; stricter enforcement can follow.
    validate_search_results_dispositioning(results, event_logger=event_logger)

    return results


def _score_results_batched(
    item: dict[str, Any],
    executions: list[Any],
    client: APIClient,
    scorer_prompt: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Score all search results in batches via the relevance-scorer sub-agent.

    Returns two lists:

    - ``scored``: entries the scorer returned, enriched with metadata from
      the original search result (title, snippet, search_id, page_age) and
      a ``relevance_score``. These feed the threshold/dedupe filter.
    - ``unscored_rejects``: entries the scorer did NOT return scores for —
      e.g., the model returned fewer score entries than the batch size, or
      returned a URL not present in the batch (leaving some batch URLs
      unscored). Each has ``reason`` = ``scorer_did_not_score`` and a
      placeholder ``rationale``. This keeps the PRISMA dispositioning
      invariant intact rather than silently dropping scorer omissions.
    """
    scored: list[dict[str, Any]] = []
    unscored_rejects: list[dict[str, Any]] = []
    batch_size = client.pipeline.scoring_batch_size
    terms_per_query = client.pipeline.search_terms_per_query

    for execution in executions:
        results_list = execution.results
        search_id = execution.search_id

        # Determine search intent from the execution
        search_intent = f"Search {search_id}: {' '.join(execution.terms[:terms_per_query])}"

        # Process in batches
        for i in range(0, len(results_list), batch_size):
            batch = results_list[i : i + batch_size]
            batch_input = {
                "item_id": item["id"],
                "clarified_text": item.get("clarified_text", ""),
                "search_intent": search_intent,
                "results": [{"url": r.url, "title": r.title, "snippet": r.snippet} for r in batch],
            }

            response = client.call_sub_agent(
                prompt_path=scorer_prompt,
                user_input=batch_input,
                output_schema="relevance-scores.schema.json",
                include_guidelines=False,
                model=client.model_for("relevance_scorer"),
            )

            scored_urls_in_batch: set[str] = set()

            # Enrich scores with metadata from original results
            for score_entry in response.get("scores", []):
                score_entry["search_id"] = search_id
                # Find the original result for title/snippet
                for r in batch:
                    if r.url == score_entry["url"]:
                        score_entry["title"] = r.title
                        score_entry["snippet"] = r.snippet
                        score_entry["page_age"] = r.page_age
                        break
                scored_urls_in_batch.add(score_entry.get("url", ""))
                scored.append(score_entry)

            # Any URL in the batch that the scorer didn't return becomes a
            # rejected entry with a structured reason. Silent omission is
            # exactly the invariant-violating behavior this function was
            # changed to stop producing.
            for r in batch:
                if r.url in scored_urls_in_batch:
                    continue
                unscored_rejects.append(
                    {
                        "url": r.url,
                        "title": r.title,
                        "snippet": r.snippet,
                        "page_age": r.page_age,
                        "search_id": search_id,
                        "relevance_score": None,
                        "reason": REJECTION_REASON_SCORER_DID_NOT_SCORE,
                        "rationale": (
                            "Relevance scorer did not return a score for this "
                            "URL in its batch response."
                        ),
                    }
                )

    return scored, unscored_rejects


def _filter_and_deduplicate(
    scored_results: list[dict[str, Any]],
    *,
    threshold: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter by relevance threshold and deduplicate by URL.

    Sorts scored results by relevance_score descending, then walks the
    list. The first occurrence of each URL is bucketed by threshold —
    ``selected`` if ``score >= threshold``, else ``rejected`` with
    ``reason`` = ``below_relevance_threshold``. Subsequent occurrences of
    the same URL are recorded in ``rejected`` with ``reason`` =
    ``duplicate_url``, preserving the invariant that every input entry is
    accounted for in exactly one output bucket.
    """
    # Sort by score descending; tie-break by url so ordering is stable
    # across Python implementations when duplicate URLs arrive with
    # identical scores. None scores (from scorer_did_not_score fallbacks)
    # must not raise TypeError against real ints — treat as -1.
    scored_results.sort(key=lambda x: (x.get("relevance_score") or -1, x.get("url", "")), reverse=True)

    seen_urls: set[str] = set()
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for result in scored_results:
        url = result.get("url", "")
        score = result.get("relevance_score") or 0

        if url in seen_urls:
            # Preserve the duplicate as a rejected entry with a structured
            # reason rather than dropping it silently. The first occurrence
            # (higher-scored, since we sorted) stays in selected/rejected
            # under its own disposition; this lower-ranked copy is marked
            # as a dedupe loser.
            dup_entry = dict(result)
            dup_entry["reason"] = REJECTION_REASON_DUPLICATE_URL
            existing_rationale = dup_entry.get("rationale") or ""
            dup_entry["rationale"] = (
                f"Duplicate URL dropped by deduplication; a higher-scored copy "
                f"of {url} was kept. " + existing_rationale
            ).strip()
            rejected.append(dup_entry)
            continue
        seen_urls.add(url)

        if score >= threshold:
            selected.append(result)
        else:
            # Make the threshold reason explicit on the persisted entry.
            # Prior behavior relied on the *bucket* (rejected) to imply
            # the reason, which meant downstream filters couldn't tell a
            # below-threshold reject from a deduped or scorer-omission
            # reject.
            reject_entry = dict(result)
            reject_entry.setdefault("reason", REJECTION_REASON_BELOW_THRESHOLD)
            rejected.append(reject_entry)

    return selected, rejected


# Map each rejection reason to a structured event ``kind`` so downstream
# tooling (Step 8 self-audit, the reconciler) can filter events by bucket
# without inspecting free-text detail strings. Reasons not listed fall
# back to a generic ``rejected`` kind — the reason field itself still
# carries the specific cause.
_REASON_EVENT_KINDS: dict[str, str] = {
    REJECTION_REASON_BELOW_THRESHOLD: "below_threshold",
    REJECTION_REASON_DUPLICATE_URL: "duplicate_url",
    REJECTION_REASON_SCORER_DID_NOT_SCORE: "scorer_did_not_score",
}


def _event_kind_for_reason(reason: str) -> str:
    """Return the event-log ``kind`` corresponding to a rejection reason."""
    return _REASON_EVENT_KINDS.get(reason, "rejected")


def validate_search_results_dispositioning(
    search_results: dict[str, Any],
    *,
    event_logger: EventLogger | None = None,
) -> list[dict[str, Any]]:
    """Verify the PRISMA dispositioning invariant for Step 4 output.

    For every (item_id, search_id) pair, the number of raw results
    returned by the provider must equal the number of entries bucketed
    into ``selected_sources`` + ``rejected_sources`` filtered to that
    search_id. Anything else is a silent drop — the R0063/Q001/S01 case
    (5 returned, 4 selected, 0 rejected, 1 unaccounted) is exactly the
    shape this check catches.

    Violations are appended to ``event_logger`` as
    ``kind=dispositioning_invariant_violated`` events so the Step 8
    self-audit can surface them in the final report. The returned list
    contains one dict per violation so callers (and tests) can assert
    against the specific missing counts.

    This validator does **not** raise — silent drops have been shipping
    long enough that failing hard on first sight would block every
    in-progress run. Visibility is the upgrade; hard enforcement is a
    follow-up once historical runs are drained.

    Args:
        search_results: The dict returned by ``step4_execute_searches``
            (keyed by item_id).
        event_logger: Optional event logger to record violations.

    Returns:
        A list of violation dicts; empty if the invariant holds.

    """
    violations: list[dict[str, Any]] = []

    for item_id, item_data in search_results.items():
        if not isinstance(item_data, dict):
            continue

        # Count selected/rejected by search_id in O(n) per item.
        selected_by_sid: dict[str, int] = {}
        rejected_by_sid: dict[str, int] = {}
        for src in item_data.get("selected_sources", []) or []:
            sid = src.get("search_id", "")
            selected_by_sid[sid] = selected_by_sid.get(sid, 0) + 1
        for src in item_data.get("rejected_sources", []) or []:
            sid = src.get("search_id", "")
            rejected_by_sid[sid] = rejected_by_sid.get(sid, 0) + 1

        for execution in item_data.get("searches_executed", []) or []:
            sid = execution.get("search_id", "")
            total_returned = len(execution.get("results", []) or [])
            n_sel = selected_by_sid.get(sid, 0)
            n_rej = rejected_by_sid.get(sid, 0)
            accounted = n_sel + n_rej
            if accounted == total_returned:
                continue

            missing = total_returned - accounted
            violation = {
                "item_id": item_id,
                "search_id": sid,
                "total_returned": total_returned,
                "selected": n_sel,
                "rejected": n_rej,
                "unaccounted": missing,
            }
            violations.append(violation)

            if event_logger is not None:
                event_logger.log(
                    step="step4_execute_searches",
                    kind="dispositioning_invariant_violated",
                    detail=(
                        f"Dispositioning invariant violated for {item_id}/{sid}: "
                        f"{total_returned} results returned but only "
                        f"{n_sel} selected + {n_rej} rejected = {accounted} "
                        f"accounted ({missing} unaccounted)."
                    ),
                    item_id=item_id,
                    count=missing,
                    layer="pipeline",
                )

    if violations:
        logger.info(
            "    WARNING: %d dispositioning invariant violation(s) detected in search results.",
            len(violations),
        )

    return violations


_SCORING_BATCH_SIZE = 1
_MAX_SOURCES_TO_SCORE = 15


# Uses ProcessPoolExecutor (not threads) because lxml/trafilatura
# crashes with SIGABRT under thread contention. Separate processes
# each get their own lxml instance — thread-safety is irrelevant.
_FETCH_WORKERS = 4


def _fetch_single_source(url: str) -> dict[str, Any]:
    """Fetch a single source's article body. Process-safe (picklable args/return).

    Returns a dict with url + content, or raises FetchError.
    """
    return {"url": url, "content": fetch_page_extract(url)}


def _fetch_sources_for_scoring(
    item_id: str,
    selected: list[dict[str, Any]],
    event_logger: EventLogger | None = None,
) -> list[dict[str, Any]]:
    """Fetch article bodies for selected sources in parallel processes.

    Uses parallelize_process (not threads) because lxml/trafilatura
    crashes with SIGABRT under thread contention. Each process gets
    its own lxml instance in separate memory — thread-safety irrelevant.
    """
    logger.info(f"    Fetching {len(selected)} sources ({_FETCH_WORKERS} processes)...")
    kwargs_list = [{"url": s.get("url", "")} for s in selected]
    results = parallelize_process(
        func=_fetch_single_source,
        kwargs_list=kwargs_list,
        max_workers=_FETCH_WORKERS,
    )

    # Log fetch failures as events
    if results.exceptions and event_logger:
        for exc in results.exceptions:
            exc_str = str(exc)
            # Try to extract URL from the FetchError message
            url = ""
            if "for " in exc_str:
                url = exc_str.split("for ", 1)[1].split(":", maxsplit=1)[0].strip()
            kind = "fetch_failed"
            if ".pdf" in url.lower():
                kind = "fetch_failed_pdf"
            elif "trafilatura" in exc_str.lower():
                kind = "fetch_failed_html"
            event_logger.log(
                step="step5_score_sources",
                kind=kind,
                detail=exc_str,
                url=url,
                item_id=item_id,
                layer="pipeline",
            )

    if results.error_count:
        logger.info(f"    {item_id}: {results.error_count} of {len(selected)} sources dropped due to fetch failures.")

    # Build enriched sources from successful fetches, matching back to
    # original source metadata (title, snippet)
    source_by_url = {s.get("url", ""): s for s in selected}
    enriched_sources: list[dict[str, Any]] = []
    for fetch_result in results.results:
        url = fetch_result["url"]
        source = source_by_url.get(url, {})
        enriched_sources.append(
            {
                "url": url,
                "title": source.get("title", ""),
                "snippet": source.get("snippet", ""),
                "content_extract": fetch_result["content"],
            }
        )

    logger.info(f"    {len(enriched_sources)} sources fetched successfully.")
    return enriched_sources


def step5_score_sources(
    research_input: dict[str, Any],
    search_results: dict[str, Any],
    client: APIClient,
    event_logger: EventLogger | None = None,
) -> dict[str, Any]:
    """Score each selected source with reliability, relevance, and bias assessment.

    For each item, fetches page content (Python, zero tokens), then scores
    sources in batches of 3 via the source-scorer sub-agent.

    Args:
        research_input: The clarified research input (output of step 1).
        search_results: The search results keyed by item ID (output of step 4).
        client: Configured API client with common guidelines loaded.
        event_logger: Pipeline event logger for recording fetch failures.

    Returns:
        A dict mapping item IDs to their source scorecards.

    Raises:
        SubAgentError: If a sub-agent call fails.

    """
    scorer_prompt = _PROMPTS_DIR / "scorecards.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        item_results = search_results.get(item_id, {})
        all_selected = item_results.get("selected_sources", [])
        # Cap at top N by relevance score to control cost
        selected = all_selected[:_MAX_SOURCES_TO_SCORE]
        if len(all_selected) > _MAX_SOURCES_TO_SCORE:
            logger.info(f"  Scoring top {len(selected)} of {len(all_selected)} sources for {item_id}...")
        else:
            logger.info(f"  Scoring {len(selected)} sources for {item_id}...")

        # Phase A: Python fetches page content.
        enriched_sources = _fetch_sources_for_scoring(item_id, selected, event_logger)

        # Phase B: LLM scores in batches
        all_scorecards: list[dict[str, Any]] = []
        for i in range(0, len(enriched_sources), _SCORING_BATCH_SIZE):
            batch = enriched_sources[i : i + _SCORING_BATCH_SIZE]
            batch_input = {
                "item_id": item_id,
                "clarified_text": item.get("clarified_text", ""),
                "sources": batch,
            }

            response = client.call_sub_agent(
                prompt_path=scorer_prompt,
                user_input=batch_input,
                output_schema="scorecards.schema.json",
                max_tokens=client.pipeline.max_output_tokens,
                model=client.model_for("source_scorer"),
            )

            all_scorecards.extend(response.get("scorecards", []))

        # Attach title/snippet/content_extract/items from the Python-side
        # copy of the input. The scorer's output schema explicitly forbids
        # these fields (see scorecards.schema.json and the
        # source-scorer prompt) — they are Python-coordinator metadata,
        # joined here to produce the persisted source-scorecards format
        # that downstream steps read. Requiring the scorer to transcribe a
        # 60KB article body through the LLM was the root cause of
        # max_tokens overruns and invalid JSON on long sources.
        input_by_url = {src["url"]: src for src in enriched_sources}
        for sc in all_scorecards:
            src = input_by_url.get(sc.get("url"), {})
            for field in ("title", "snippet", "content_extract"):
                value = src.get(field)
                if value:
                    sc[field] = value
            if "items" not in sc:
                sc["items"] = [item_id]

        logger.info(f"    {item_id}: {len(all_scorecards)} sources scored")
        results[item_id] = {"id": item_id, "scorecards": all_scorecards}

    return results


# Sources with content_extract shorter than this are not passed to the
# evidence-extractor — there is nothing substantive to quote, and handing
# the LLM a near-empty source is a direct invitation for it to fabricate
# plausible-sounding quotes from training-data memory.
_MIN_CONTENT_EXTRACT_CHARS = 100


_WHITESPACE_RE = re.compile(r"\s+")


def _verify_packet_verbatim(
    packet: dict[str, Any],
    content_extract: str,
) -> bool:
    """Return True iff the packet's excerpt is a verbatim substring of the source.

    The extractor prompt and schema both mandate verbatim excerpts. In
    practice frontier LLMs partially obey this instruction — they anchor
    on real phrases from the source, then smooth the continuation from
    training-data knowledge of the article, producing plausible-looking
    "quotes" that are not actually substrings of what was fetched. This
    function is the deterministic backstop: whatever the model claimed,
    we accept the packet only if the excerpt actually occurs in the
    source text.

    Matching is whitespace-normalized. Ellipses ('...') in the excerpt
    are treated as permitted trims: each dot-delimited segment must
    independently appear in the normalized content_extract.
    """
    excerpt = packet.get("excerpt") or ""
    if not excerpt.strip():
        return False

    norm_source = _WHITESPACE_RE.sub(" ", content_extract)
    segments = [_WHITESPACE_RE.sub(" ", seg).strip() for seg in excerpt.split("...") if seg.strip()]
    return bool(segments) and all(seg in norm_source for seg in segments)


_EXTRACT_WORKERS = 4


def _extract_single_source(
    item_id: str,
    item: dict[str, Any],
    hypotheses: dict[str, Any],
    scorecard: dict[str, Any],
    prompt_path_str: str,
    client: APIClient,
) -> dict[str, Any]:
    """Extract evidence packets from a single source. Thread-safe.

    Returns a dict with url, verified_packets, claimed_count, dropped_count.
    Raises SubAgentError on API failure.
    """
    url = scorecard.get("url", "<unknown URL>")
    source_extract = scorecard.get("content_extract") or ""

    response = client.call_sub_agent(
        prompt_path=Path(prompt_path_str),
        user_input={
            "id": item_id,
            "item": item,
            "hypotheses": hypotheses,
            "scorecards": [scorecard],
        },
        output_schema="evidence-packets.schema.json",
        max_tokens=client.pipeline.max_output_tokens,
        model=client.model_for("evidence_extractor"),
    )

    claimed_packets = response.get("packets", []) or []
    verified: list[dict[str, Any]] = []
    dropped = 0
    for pk in claimed_packets:
        if _verify_packet_verbatim(pk, source_extract):
            verified.append(pk)
        else:
            dropped += 1

    return {
        "url": url,
        "verified_packets": verified,
        "claimed": len(claimed_packets),
        "kept": len(verified),
        "dropped": dropped,
    }


def _extract_evidence_for_item(
    item: dict[str, Any],
    item_hypotheses: dict[str, Any],
    substantive: list[dict[str, Any]],
    prompt_path: Path,
    client: APIClient,
    event_logger: EventLogger | None = None,
) -> tuple[list[dict[str, Any]], list[str], dict[str, int]]:
    """Extract evidence packets from all sources in parallel threads.

    Uses parallelize_thread with _EXTRACT_WORKERS concurrent API calls.
    Each call handles one source — keeping input bounded and the task
    framing crisp. After each call, verbatim verification drops
    non-substring packets.

    Returns (aggregated verified packets, list of per-source error
    messages, verbatim stats dict with keys 'claimed', 'kept', 'dropped').
    """
    kwargs_list = [
        {
            "item_id": item["id"],
            "item": item,
            "hypotheses": item_hypotheses,
            "scorecard": sc,
            "prompt_path_str": str(prompt_path),
            "client": client,
        }
        for sc in substantive
    ]

    logger.info(f"    Extracting from {len(substantive)} sources ({_EXTRACT_WORKERS} threads)...")
    results = parallelize_thread(
        func=_extract_single_source,
        kwargs_list=kwargs_list,
        max_workers=_EXTRACT_WORKERS,
    )

    # Aggregate results
    aggregated_packets: list[dict[str, Any]] = []
    errors: list[str] = []
    stats = {"claimed": 0, "kept": 0, "dropped": 0}

    for res in results.results:
        url = res["url"]
        aggregated_packets.extend(res["verified_packets"])
        stats["claimed"] += res["claimed"]
        stats["kept"] += res["kept"]
        stats["dropped"] += res["dropped"]

        if res["dropped"] and event_logger:
            event_logger.log(
                step="step5b_extract_evidence",
                kind="packet_dropped_non_verbatim",
                detail=f"{res['dropped']} of {res['claimed']} claimed packets failed verbatim verification",
                url=url,
                item_id=item["id"],
                count=res["dropped"],
                layer="pipeline",
            )

        if res["dropped"]:
            logger.info(f"      {res['url'][:60]}: {res['kept']} verified / {res['dropped']} dropped")
        else:
            logger.info(f"      {res['url'][:60]}: {res['kept']} packet(s) verified")

    # Log API failures from the parallel run
    for exc in results.exceptions:
        err = f"extractor error: {exc}"
        errors.append(err)
        logger.info(f"      extractor FAILED: {exc}")
        if event_logger:
            event_logger.log(
                step="step5b_extract_evidence",
                kind="subagent_failed",
                detail=f"Evidence-extractor failure: {exc}",
                item_id=item["id"],
                layer="pipeline",
            )

    return aggregated_packets, errors, stats


def _scorecards_without_content(scorecards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return scorecards with `content_extract` stripped.

    Used to avoid passing full article bodies to downstream sub-agents
    (synthesizer, self-auditor) whose contracts call for scorecards as
    source-meta inputs, not as evidence text. After Step 5b the verbatim
    article text is represented in the evidence packets; the scorecards
    only need to carry url/title/authors/date/scoring/content_summary for
    those steps. Stripping the (potentially 100+ KB) content_extract field
    is what keeps downstream calls from blowing past the 200 K context
    limit when many sources have substantive bodies.

    The persisted scorecards in scorecards.json still carry
    content_extract — this only affects what is passed to the LLM.
    """
    return [{k: v for k, v in sc.items() if k != "content_extract"} for sc in scorecards]


def step5b_extract_evidence(
    research_input: dict[str, Any],
    hypotheses: dict[str, Any],
    scorecards: dict[str, Any],
    client: APIClient,
    event_logger: EventLogger | None = None,
) -> dict[str, Any]:
    """Extract verbatim evidence packets tying source excerpts to hypotheses.

    Bridges source scoring and evidence synthesis so that downstream verdicts
    are grounded in inspectable quotations rather than the synthesizer's
    paraphrased memory of the sources. Calls the extractor **once per
    source** (not once per item) — long combined inputs cause the model to
    drop instructions, echo synthesis-style prose instead of JSON, and
    exceed context bounds. Per-source calls keep inputs bounded and the
    task framing crisp.

    Sources whose content_extract is missing, empty, or shorter than
    ``_MIN_CONTENT_EXTRACT_CHARS`` are filtered out before any LLM call;
    their URLs are recorded in ``extraction_notes`` for auditability. An
    empty content_extract cannot yield a verbatim quote, and passing such a
    source to the extractor invites fabrication.

    Args:
        research_input: The clarified research input (output of step 1).
        hypotheses: Hypothesis results keyed by item ID (output of step 2).
        scorecards: Source scorecards keyed by item ID (output of step 5).
        client: Configured API client with common guidelines loaded.
        event_logger: Pipeline event logger for recording extractor failures
            and verbatim validator drops.

    Returns:
        A dict mapping item IDs to their evidence packet results, shape:
        ``{"id": "<ItemID>", "packets": [...], "extraction_notes": "..."}``.

    """
    prompt_path = _PROMPTS_DIR / "evidence-packets.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        item_hypotheses = hypotheses.get(item_id, {})
        item_scorecards = scorecards.get(item_id, {}).get("scorecards", [])

        if not item_scorecards:
            logger.info(f"  No scorecards for {item_id}; skipping evidence extraction.")
            results[item_id] = {"id": item_id, "packets": []}
            continue

        substantive: list[dict[str, Any]] = []
        skipped: list[str] = []
        for sc in item_scorecards:
            extract = sc.get("content_extract") or ""
            if len(extract.strip()) < _MIN_CONTENT_EXTRACT_CHARS:
                skipped.append(sc.get("url", "<unknown URL>"))
            else:
                substantive.append(sc)

        logger.info(
            f"  Extracting evidence for {item_id} "
            f"({len(substantive)} sources, one call each; "
            f"{len(skipped)} skipped for insufficient content)..."
        )

        if not substantive:
            note = (
                "No sources had a content_extract of sufficient length "
                f"(>= {_MIN_CONTENT_EXTRACT_CHARS} chars) to extract verbatim "
                f"evidence from. Skipped {len(skipped)} source(s): " + ", ".join(skipped)
            )
            results[item_id] = {
                "id": item_id,
                "packets": [],
                "extraction_notes": note,
            }
            logger.info(f"    {item_id}: 0 evidence packets (all sources insufficient)")
            continue

        aggregated_packets, extractor_errors, verbatim_stats = _extract_evidence_for_item(
            item=item,
            item_hypotheses=item_hypotheses,
            substantive=substantive,
            prompt_path=prompt_path,
            client=client,
            event_logger=event_logger,
        )

        response: dict[str, Any] = {
            "id": item_id,
            "packets": aggregated_packets,
            "verbatim_stats": verbatim_stats,
        }

        notes_parts: list[str] = []
        if skipped:
            notes_parts.append(
                f"Python pre-filter skipped {len(skipped)} source(s) for "
                f"insufficient content_extract (< {_MIN_CONTENT_EXTRACT_CHARS} chars): " + ", ".join(skipped)
            )
        if extractor_errors:
            notes_parts.append(
                f"Extractor failed on {len(extractor_errors)} of {len(substantive)} "
                "source(s): " + "; ".join(extractor_errors)
            )
        if verbatim_stats["dropped"]:
            adherence = 100.0 * verbatim_stats["kept"] / max(verbatim_stats["claimed"], 1)
            notes_parts.append(
                f"Verbatim validator dropped {verbatim_stats['dropped']} of "
                f"{verbatim_stats['claimed']} claimed packets "
                f"(extractor adherence: {adherence:.1f}%)."
            )
        if notes_parts:
            response["extraction_notes"] = " ".join(notes_parts)

        results[item_id] = response
        logger.info(f"    {item_id}: {len(aggregated_packets)} evidence packets total")

    return results


def steps678_synthesize_and_assess(
    research_input: dict[str, Any],
    hypotheses: dict[str, Any],
    scorecards: dict[str, Any],
    evidence_packets: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Synthesize evidence, assess, and identify gaps (Steps 6+7+8 combined).

    One LLM call per item. These steps are tightly coupled — synthesis informs
    assessment, assessment reveals gaps. Takes the evidence packets from
    Step 5b as the primary grounded-quote input; scorecards remain available
    for meta-judgments about reliability and source agreement.

    Args:
        research_input: The clarified research input (output of step 1).
        hypotheses: Hypothesis results keyed by item ID (output of step 2).
        scorecards: Source scorecards keyed by item ID (output of step 5).
        evidence_packets: Evidence packets keyed by item ID (output of step 5b).
        client: Configured API client with common guidelines loaded.

    Returns:
        A dict mapping item IDs to their synthesis/assessment/gaps results.

    """
    prompt_path = _PROMPTS_DIR / "synthesis.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        item_hypotheses = hypotheses.get(item_id, {})
        item_scorecards = scorecards.get(item_id, {}).get("scorecards", [])
        item_packets = evidence_packets.get(item_id, {}).get("packets", [])
        logger.info(f"  Synthesizing {item_id} ({len(item_scorecards)} sources, {len(item_packets)} packets)...")

        agent_input = {
            "item": item,
            "hypotheses": item_hypotheses,
            # Strip content_extract — packets carry the verbatim text the
            # synthesizer should reason from. Including the full article
            # bodies here was both wasteful and a context-limit risk.
            "scorecards": _scorecards_without_content(item_scorecards),
            "evidence_packets": item_packets,
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="synthesis.schema.json",
            max_tokens=16384,
            model=client.model_for("synthesizer"),
        )

        results[item_id] = response
        assessment = response.get("assessment", {})
        verdict = assessment.get("verdict", assessment.get("answer", ""))
        logger.info(f"    {item_id}: {verdict[:80]}")

    return results


def step9_self_audit(
    research_input: dict[str, Any],
    hypotheses: dict[str, Any],
    search_results: dict[str, Any],
    scorecards: dict[str, Any],
    evidence_packets: dict[str, Any],
    synthesis: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Self-audit, source-back verification, and reading list (Steps 9+9b+9c).

    One LLM call per item. Reviews the entire research chain.

    Args:
        research_input: Clarified research input (step 1).
        hypotheses: Hypothesis results (step 2).
        search_results: Search results (step 4).
        scorecards: Source scorecards (step 5).
        evidence_packets: Evidence packets (step 5b).
        synthesis: Synthesis/assessment/gaps (steps 6-8).
        client: Configured API client.

    Returns:
        A dict mapping item IDs to their audit results.

    """
    prompt_path = _PROMPTS_DIR / "self-audit.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        logger.info(f"  Auditing {item_id}...")

        agent_input = {
            "item": item,
            "hypotheses": hypotheses.get(item_id, {}),
            "search_results": search_results.get(item_id, {}),
            # Strip content_extract — Step 9b verifies assessment→packet
            # linkage, not assessment→source. The packets are the ground
            # truth for what was quoted; the auditor reads them directly.
            # Including the full article bodies blew past the 200 K context
            # on multi-source runs (smoke test 2026-04-15: 190 K input).
            "scorecards": _scorecards_without_content(scorecards.get(item_id, {}).get("scorecards", [])),
            "evidence_packets": evidence_packets.get(item_id, {}).get("packets", []),
            "synthesis": synthesis.get(item_id, {}),
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="self-audit.schema.json",
            max_tokens=16384,
            model=client.model_for("self_auditor"),
        )

        results[item_id] = response
        audit = response.get("process_audit", {})
        ratings = [
            audit.get("evaluation_consistency", {}).get("rating", "?"),
            audit.get("synthesis_fairness", {}).get("rating", "?"),
        ]
        logger.info(f"    {item_id}: audit [{', '.join(ratings)}]")

    return results


def step10_report(
    research_input: dict[str, Any],
    hypotheses: dict[str, Any],
    search_results: dict[str, Any],
    scorecards: dict[str, Any],
    synthesis: dict[str, Any],
    audit: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Assemble the final research report (Step 10).

    One LLM call per item. Pulls together all prior steps into a structured report.

    Args:
        research_input: Clarified research input (step 1).
        hypotheses: Hypothesis results (step 2).
        search_results: Search results (step 4).
        scorecards: Source scorecards (step 5).
        synthesis: Synthesis/assessment/gaps (steps 6-8).
        audit: Self-audit results (step 9).
        client: Configured API client.

    Returns:
        A dict mapping item IDs to their final reports.

    """
    prompt_path = _PROMPTS_DIR / "reports.md"
    results: dict[str, Any] = {}

    claims = research_input.get("claims", [])
    queries = research_input.get("queries", [])
    items = [*claims, *queries]

    for item in items:
        item_id = item["id"]
        mode = "claim" if item_id.startswith("C") else "query"
        logger.info(f"  Assembling report for {item_id} ({mode})...")

        agent_input = {
            "item": item,
            "hypotheses": hypotheses.get(item_id, {}),
            "search_results": search_results.get(item_id, {}),
            # Strip content_extract — report assembly formats what the
            # earlier steps produced (synthesis + audit), using scorecards
            # only for source-meta (title / url / authors / date /
            # content_summary / scoring). The full article bodies are not
            # needed here and push the combined input past the 200 K
            # context limit on multi-source runs.
            "scorecards": _scorecards_without_content(scorecards.get(item_id, {}).get("scorecards", [])),
            "synthesis": synthesis.get(item_id, {}),
            "self_audit": audit.get(item_id, {}),
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="reports.schema.json",
            max_tokens=16384,
            model=client.model_for("reporter"),
        )

        results[item_id] = response
        verdict = response.get("assessment_summary", {}).get(
            "verdict",
            response.get("assessment_summary", {}).get("answer", ""),
        )
        logger.info(f"    {item_id}: {verdict[:80]}")

    return results


def step11_archive(output_dir: Path, all_outputs: dict[str, Any]) -> Path:
    """Archive all research outputs for temporal revisitation (Step 11).

    Pure Python — no LLM call. Writes a single archive JSON with all
    pipeline outputs and metadata.

    Args:
        output_dir: The run directory to write to.
        all_outputs: Dict containing all pipeline step outputs.

    Returns:
        Path to the archive file.

    """
    archive = {
        "archived_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline_version": "0.1.0",
        **all_outputs,
    }

    path = output_dir / "archive.json"
    path.write_text(json.dumps(archive, indent=2) + "\n")
    return path


def write_step_output(
    output_dir: Path,
    filename: str,
    data: dict[str, Any] | list[Any],
) -> Path:
    """Write a pipeline step's output to a JSON file.

    Args:
        output_dir: Directory to write to.
        filename: Name of the JSON file.
        data: The data to serialize.

    Returns:
        Path to the written file.

    """
    path = output_dir / filename
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path
