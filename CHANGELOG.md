# Changelog

## v1.9.1 — 2026-04-07

### Changes

- **Parameter renamed**: `n` → `runs` (no single-character variables)
- **Timestamp precision**: YYYY-MM-DD-HHMMSS (was HHMM). Seconds
  prevent collision when launching multiple runs in the same minute.

## v1.9.0 — 2026-04-07

### Changes

- **n-run default**: Research runs now execute n=3 independent runs by
  default. Each run is blind to the others. A synthesis step produces
  aggregate results with consistency metrics after all runs complete.
- **Timestamp precision**: Run directories now use YYYY-MM-DD-HHMM
  (was YYYY-MM-DD). Supports multiple runs per day.
- **Run groups**: Directory structure adds run-1/ through run-n/
  subdirectories within each timestamped group.
- **Synthesis artifacts**: synthesis.md (aggregate verdict), consistency.md
  (similarity metrics), consolidated reading-list.md and resources.md
  at the run group level.
- **n parameter**: `n=1` for quick runs, `n=3` default, larger n supported.

## v1.8.0 — 2026-04-06

### Changes

- **Fact-check scorecard**: Collection-level scorecard as first section of
  Collection Analysis for claim runs. Distribution table, pass rate, and
  corrections needed.
- **Rerun difference report**: Automatically generated after every rerun.
  Compares new run against most recent prior run with per-entity and
  collection-level comparison tables plus article impact summary. Preserves
  isolation — diff is produced after rerun completes, not during.

## v1.7.0 — 2026-04-03

### Changes

- **Source reading list**: New per-entity artifact (reading-list.md) with
  prioritized sources ranked Must Read / Should Read / Reference based on
  reliability × relevance scores. Placed after self-audit as the last
  per-entity artifact.
- **Consolidated reading list**: Run-level reading-list.md deduplicates
  sources across all claims/queries with entity cross-references.
- **Resources factored out**: Resources consumed moved from inline in
  index.md to separate resources.md file. Keeps index focused on
  analytical content.
- **Collection Analysis restructured**: Source Reading List and Resources
  Consumed linked from dedicated subsections with descriptions at the top
  of Collection Analysis.

## v1.6.0 — 2026-04-03

### Changes

- **Candidate evidence**: Claims may now optionally include researcher-provided
  URLs as candidate evidence. Scored on equal terms with search-discovered
  sources. Appears in search logs as CE## entries with Origin: Researcher-provided
  in source scorecards.
- **Pre-fact-check gate**: Fact-check command audits the References section
  before extraction, flagging unscored evidence references.
- **Output format updates**: Both default and custom formats updated with
  candidate evidence sections and Origin field in scorecards.
- **Repo structure**: Added develop branch, branch protection ruleset
  (no direct push to main/develop), PR-based workflow.

## v1.5.0 — 2026-04-01

### Changes

- **Repo restructure**: Plugin content moved to `ai-research-methodology/`
  subdirectory matching documented marketplace layout.
- **Version management**: Version managed via marketplace.json only (removed
  from plugin.json per docs).
- **Install/update docs**: README rewritten with verified commands and
  documentation links.
- **fact-check command**: Extract claims and verify in one step.
- **extract command**: Extract verifiable claims from a document.
- **confirm=no batch mode**: Skip all interactive prompts.
- **Extended probability scale**: Nine points including 0% and 100%
  deterministic endpoints.

## v1.1.0 — 2026-03-31

### Changes

- **Unified prompt**: Merged claim.md and query.md into single research.md
- **Axiom support**: Three input types — axioms (assumed true), claims
  (tested), queries (answered). Backward-compatible with Choe's approach.
- **Revisit triggers**: Mandatory assessment section with specific, testable
  conditions for re-research
- **Removed citation chain analysis**: Not producing value in web-based
  research; silently skipped or rubber-stamped in practice
- **Standalone prompt**: standalone/research.md — single file for any Claude
  interface, includes HTML output mode for web chat
- **Minimum-not-maximum rule**: Required sections are the floor, additional
  analysis is encouraged
- **11-step process** (was 14): renumbered after citation chain removal and
  step consolidation
- All URLs must be clickable links (Rule 8 in output format)

## v1.0.0 — 2026-03-30

Initial public release.

### Research Methodology

- 14-step evidence-based research process
- Nine source frameworks: ICD 203, GRADE, IPCC, PRISMA, Cochrane/RoB 2,
  CONSORT (evaluated, not included), Chamberlin/Platt, ROBIS, NAS
- Three net-new features: vocabulary exploration, citation chain analysis,
  temporal revisitation
- Claim verification mode and query answering mode
- Anti-sycophancy behavioral constraints (12 rules in 4 groups)
- Researcher profile as calibration instrument
- Five-domain self-audit (4 ROBIS process domains + source-back verification)

### Plugin

- Claude Code plugin with `/research` skill
- Commands: `claim`, `query`, `rerun`
- Default output format (portable markdown)
- Run isolation for reproducible reruns
- Claim extraction blindness rule
