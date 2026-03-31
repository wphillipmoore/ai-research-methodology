# Changelog

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
