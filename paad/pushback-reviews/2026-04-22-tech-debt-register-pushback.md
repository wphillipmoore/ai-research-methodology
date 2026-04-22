# Pushback Review: docs/tech-debt-register.md

**Date:** 2026-04-22
**Spec:** `docs/tech-debt-register.md`
**Commit:** d1881ec
**Run context:** First manual PAAD exercise per issue #137 — warm-up to calibrate tone. Reviewer: PAAD `/paad:pushback`. Author of reviewed file: same author as the reviewer (same session). No fresh session used; inter-session critical objectivity is a known limitation we're testing here.

## Source Control Conflicts

None — no conflicts with recent changes.

Cross-checked every claim in the register against `git log --oneline -50 --since="2 weeks ago"` and against current code:

- TD-003's "Resolved by PR #119, commit `c4b1043`, merged 2026-04-21" — verified present in `git log` and verified the state machine is live in `src/diogenes/state_machine.py`.
- TD-002's "#128 shipped process-parallel workaround" — verified at commit `e703420`.
- TD-001's "print-based logging" — verified: 30 `print(` calls in `src/diogenes/pipeline.py`, 47 in `src/diogenes/commands/run.py`, 0 `logging` imports across the package. PR #101 (`pipeline events observability with three-layer capture`) is a separate structured-events layer, not a replacement for print-based progress output; TD-001 framing is still accurate but was flagged for refinement (Issue 2).
- TD-004's `_SCORING_BATCH_SIZE = 1` — verified present in `src/diogenes/pipeline.py`. No GitHub issue exists for scorer parallelization; confirms the register entry's "Tracking issue: —" note.

## Scope Shape

- **Feature cohesion:** Not applicable in the typical sense — this file is a register of independent tech-debt entries, not a feature spec. No bundling problem.
- **Spec size:** 4 active entries + 1 resolved. Not large. Scale-appropriate for alpha / first-use.

## Issues Reviewed

### [1] No enforcement mechanism — register is aspirational

- **Category:** omissions
- **Severity:** serious
- **Issue:** The register says pushback, alignment, and agentic-review should consult it, and that reviewers should flag code changes that deepen an active entry. Nothing enforces any of this — no CI check, no PR template, no pre-commit hook. A PR can add 50 new `print()` calls and deepen TD-001 silently. In a repo that already gates on `--cov-fail-under=100` and a Docker-matched local validator, a human-read-only register is the weakest link. Predictable outcome: the register becomes documentation nobody consults, and the same debt is rediscovered each quarter.
- **Options presented (best to worst):**
  - (a) **PR-template checkbox + CI linkage check** — one line in `.github/pull_request_template.md` ("Does this PR interact with any active TD-NNN entry?"), plus a CI check that fails any PR which modifies files listed in an active entry's `Affects:` line without mentioning `TD-NNN` somewhere in commits or PR body. Degrades gracefully (reviewer can override with an explicit note in the PR body).
  - (b) Pre-commit hook that warns (doesn't fail) when touching `Affects:` files. Cheap but easy to miss; no reviewer-seen-it record.
  - (c) Process-only PR-template checkbox, no CI gate.
  - (d) Manual periodic review ("Last reviewed" bump). Status quo; does not scale.
  - (e) Accept the register is aspirational. Honest but pointless.
- **Recommendation:** (a).
- **Resolution:** Accepted (a). Author confirmed this direction fits the project's automation-first posture. Additional context captured: tech-debt review should become part of release-cycle planning — historically, a new release cycle opens with (i) dependency update, (ii) full test sweep, (iii) feature planning; register-walk would fit between (ii) and (iii). Enforcement at PR level (Issue 1 (a)) and release-cycle review together make the register self-reinforcing. Follow-up PR will add the PR-template line and the CI check (likely modeled on `st-pr-issue-linkage`).

### [2] No lifecycle policy for partial resolution or drift

- **Category:** omissions
- **Severity:** serious
- **Issue:** Schema has three states — `Active | Resolved | Obsolete` — and "don't delete, mark Obsolete." Adequate for the binary case. Real debt erodes; the register has no answer for four cases that will happen: (i) **partial resolution** (TD-001 is the live example — PR #101's pipeline-events layer covers part of what TD-001 names; register says "Active" as if #101 never happened); (ii) **scope narrowing/widening** (if progress prints are later deemed fine, the right move is to narrow TD-001, not close it); (iii) **reasoning falsified** (upstream ships a thread-safe trafilatura → TD-002's rationale becomes false); (iv) **affected code deleted** (TD-001's code rewritten → does the entry auto-resolve or zombie-on?). Without a policy, each reviewer patches ad hoc; the register becomes internally inconsistent.
- **Options presented (best to worst):**
  - (a) **Per-entry `Last verified:` date + explicit update rules.** Add `**Last verified:**` beside `**Accepted:**`. Rule: whenever a referenced file/issue/assumption changes, update the entry text to match reality and bump the date. Keep Status binary; the date forces reviewers to act. Natural pairing with release-cycle review.
  - (b) (a) plus a new `Partial` state. More honest; more schema surface. Defer until Partial turns out to be the common case.
  - (c) Split-on-progress — TD-NNN becomes TD-NNN-a (Resolved) and TD-NNN-b (Active). ID sprawl; history loss. Not recommended.
  - (d) Policy by convention, not schema. Weaker than (a); no date forces the conversation.
  - (e) Do nothing.
- **Recommendation:** (a), with companion action to re-describe TD-001 immediately so it acknowledges PR #101's pipeline-events layer (the drift is already present at minute zero).
- **Resolution:** Accepted (a) + companion action. Follow-up PR will (i) add `**Last verified:**` field and update rule to the Entry schema section; (ii) bump each existing entry's `Last verified` to 2026-04-22; (iii) re-describe TD-001 to explicitly note PR #101's coverage scope so the entry reflects current reality.

### [3] ID assignment and ordering rules are under-specified

- **Category:** ambiguity
- **Severity:** moderate
- **Issue:** Entry schema says *"ID is monotonically increasing (TD-NNN); entries are listed newest-first."* Both rules ambiguous. "Newest" by what — ID? Accepted date? Current practice is ID-descending within sections; "newest by Accepted date" would contradict actual layout (TD-003 has the earliest concrete Accepted date but appears after TD-004 by ID). "Monotonically increasing" in what sense — creation-order of the debt, or creation-order of the entry in the register? Current practice is register-write-order (TD-003 describes older debt but got a higher ID than TD-001/TD-002 because it was written into the register last among those three). Scale-tolerable today, unmaintainable at TD-050.
- **Options presented:**
  - (a) **Adopt and state two explicit rules:** (i) `TD-NNN` is assigned in register-write-order (ID tags when we wrote the entry, not when the debt started); (ii) within each section, entries are listed highest-ID-first. One line of clarification under Entry schema.
  - (b) Rekey IDs by Accepted date. Destroys existing cross-references.
  - (c) Drop the ordering claim; sort alphabetically on summary.
  - (d) Add a `Created:` field distinct from `Accepted:`.
  - (e) Do nothing.
- **Recommendation:** (a).
- **Resolution:** Accepted (a). Author also acknowledged the whole register design is alpha — plausible future direction is file-per-entry with richer structure, which would change data model entirely. For now, explicit rules on current flat-file form are the scale-appropriate fix. Larger redesign deferred (see F2 under Future Decisions).

### [4] Cross-document R-ID references are brittle under spec revision

- **Category:** feasibility / ambiguity
- **Severity:** moderate
- **Issue:** Register points at specs by positional number (`execution-model.md R13`, `parallelization.md R1`, `reliability-guarantees.md R5–R8`). R-IDs are sequence numbers; inserting a new requirement mid-spec shifts every downstream R-ID, silently breaking register references. No rule in any spec header or in the register says "don't renumber." This is a convention question for **all seven locked specs**, not only the register.
- **Options presented:**
  - (a) **ADR-style "IDs are permanent" rule.** Once assigned, an R-ID is never reused or renumbered. Deleted requirements become tombstones (`R5. [DELETED 2026-06-01 — superseded by R12]`). Best home: a new `docs/specs/README.md` ("spec conventions") so it's a single source of truth.
  - (b) Switch to slug anchors (`execution-model.md#threads-default`). Stable by default; churn to retrofit.
  - (c) Accept drift; re-verify at each release.
  - (d) Do nothing.
- **Recommendation:** (a).
- **Resolution:** Accepted (a). Follow-up PR will add `docs/specs/README.md` with the permanence rule and link each spec's header at it. No retroactive renumbering needed — the existing R1..RN layouts become the canonical baseline from which tombstones start.

### [5] Active register entry without a GitHub tracking issue (TD-004)

- **Category:** omissions
- **Severity:** moderate
- **Issue:** TD-004 has `Tracking issue: —` with a note "to be filed as part of the 2.0 runway." The register entry is the only record. `gh issue list` / issue search misses TD-004; scorer-adjacent code reviewers who don't read the register don't know the debt exists. File-per-entry migration (likely future per author) would also risk orphaning register-only records if file layout changes.
- **Options presented:**
  - (a) **Require a GitHub tracking issue per Active register entry.** Entry ↔ issue cross-link. File stub issue for TD-004 now.
  - (b) Make the register itself the authoritative tracking surface; no issue required.
  - (c) Keep it optional.
  - (d) Do nothing.
- **Recommendation:** (a), plus file TD-004 stub in the same PR that applies the register fixes.
- **Resolution:** Accepted (a). Author's reasoning: tech-debt entries often describe a category where multiple instances need remediation over time — GitHub issues handle long-running work, comments, and PR linkage better than a file does. This acceptance raised a larger strategic question (see F1 under Future Decisions): if every entry requires a tracking issue anyway, the register-as-file may be redundant with `gh issue list --label tech-debt`. For now, take (a); revisit the file's existence as a separate decision.

### [6] Single "Last reviewed" at top vs per-entry drift

- **Category:** ambiguity
- **Severity:** minor — **subsumed by Issue 2 (a)**
- **Issue:** Top-of-file `**Last reviewed:**` is a single claim; per-entry review state can diverge from it over time.
- **Resolution:** No separate action — Issue 2's acceptance of `**Last verified:**` per entry makes the top-of-file line a human summary ("last walk-through") rather than a per-entry truth claim. Re-label the top-of-file line's meaning explicitly as part of the Issue 2 follow-up PR.

### [7] "Obsolete entries" category semantics are unclear

- **Category:** ambiguity
- **Severity:** minor
- **Issue:** `Obsolete` status currently bundles two different situations: "re-decided as acceptable-by-design" (probably belongs in `docs/decisions/` as an ADR) and "affected subsystem removed" (tombstone-only record). Mixed reasons hide why the entry ended up terminal.
- **Options presented:**
  - (a) Split into two terminal statuses: `Superseded` (re-decided) and `Gone` (code removed). Add mandatory fields (ADR link; commit SHA).
  - (b) Keep `Obsolete` as one status but require `Obsolete reason:` sub-field.
  - (c) **Do nothing until the first Obsolete entry appears.**
- **Recommendation:** (c).
- **Resolution:** Accepted (c). Premature given the alpha status and the file's possible non-existence in the longer term.

### [8] Resolved status double-signaling

- **Category:** ambiguity
- **Severity:** minor
- **Issue:** TD-003 carries `Status: Resolved` AND is placed under a `## Resolved entries` section. Two encodings of the same fact; disagreement (mid-edit, bad merge) has no canonical tie-breaker.
- **Options presented:**
  - (a) State Status wins; sections are render-time convenience.
  - (b) Drop Status when an entry moves to Resolved section.
  - (c) Drop sections, rely on Status sort.
  - (d) **Do nothing.**
- **Recommendation:** (d).
- **Resolution:** Accepted (d). Same reasoning as Issue 7. Revisit only if it causes friction.

### [9] Cross-repo reusability of the register pattern

- **Category:** omissions / scope
- **Severity:** minor — **skipped**
- **Issue:** The register schema could be promoted to `standards-and-conventions` as a shared pattern. Meta-question about the file's existence at all (Issue 5, F1) makes this moot.
- **Resolution:** Skipped. Not worth cycles on reusability of something we're questioning.

## Unresolved Issues

None — all nine were either resolved with an agreed action or intentionally deferred ("do nothing for now" with documented rationale).

## Follow-up Actions

All follow-ups to be handled in separate PRs per the rules of engagement in #137 ("do not merge pushback reports into spec files in this PR; each integration is its own PR per finding").

- **FU-1** (Issue 1): Add PR-template checkbox and CI linkage check for active register entries.
- **FU-2** (Issue 2): Add `**Last verified:**` field and update rule to the Entry schema; bump existing entries' dates to 2026-04-22; re-describe TD-001 to acknowledge PR #101's pipeline-events layer.
- **FU-3** (Issue 3): Add explicit ID-assignment and ordering rules to the Entry schema (register-write-order for IDs; highest-ID-first within each section).
- **FU-4** (Issue 4): Create `docs/specs/README.md` with the ADR-style "requirement IDs are permanent; deleted requirements become tombstones" convention; link each spec header to it.
- **FU-5** (Issue 5): File GitHub issue for TD-004 scorer parallelization; update TD-004's `Tracking issue:` field; state the "every active entry has an issue" rule explicitly in the Entry schema.

Suggested bundling: FU-2, FU-3, FU-5 can ship as one small register-revision PR (single file touched). FU-1 is separate (touches `.github/` + CI). FU-4 is separate (new file under `docs/specs/`).

## Future Decisions

Captured for explicit revisit; **not** acted on in this run.

- **F1** — **Does the tech-debt register-as-file primitive make sense at all?** Once every Active entry requires a GitHub tracking issue (FU-5), the issue could be the entry, with a `tech-debt` label providing what the flat file currently provides. File uniquely offers: co-located spec cross-links, single-file scannability, schema enforcement, no network dependency. Issues uniquely offer: PR linkage, out-of-band discussion, label-based querying, notifications, lower-cost updates, assignees, milestones. Deciding gate: list what the file uniquely gives us that a well-labeled issue stream doesn't. If that list is thin, the file goes. **This pushback run producing "delete the file" as its ultimate output is a valid outcome of objective review.**
- **F2** — **File-per-entry format if the flat file is kept.** Author's stated intuition is that tech debt of any real complexity doesn't fit in a paragraph or two. When scale forces a break, likely destination is `docs/tech-debt/TD-NNN-<slug>.md` per entry with a generated index. Resolve only after F1 resolves in favor of keeping the file.
- **F3** — **Release-cycle integration.** Historical author pattern for new release cycles: (i) incremental dependency update, (ii) full test sweep against updated dependencies, (iii) feature planning. Register-walk fits between (ii) and (iii). Codify as a release checklist item when the release model stabilizes.
- **F4** — **Obsolete status refinement** (`Superseded` vs `Gone`). Defer until the first Obsolete entry actually arrives.
- **F5** — **Resolved double-signaling.** Defer until it causes friction.

## Summary

- **Issues found:** 9
- **Issues resolved** (agreed action, follow-up queued): 5
- **Issues resolved** (intentional "do nothing for now"): 3 (Issues 6, 7, 8)
- **Issues skipped** (made moot by F1): 1 (Issue 9)
- **Unresolved:** 0
- **Future decisions captured:** 5 (F1–F5)
- **Spec status:** needs further work — five follow-up PRs queued (FU-1..FU-5). Register is not blocked for further use during follow-up work; enforcement gap (Issue 1) is the highest-priority fix.

## Notes on the Run Itself (for PAAD workflow calibration — #137 dry-run data)

- **Reviewer/author conflict:** reviewer and author of the reviewed file are the same Claude session. Genuine critical objectivity is a known limitation. The findings still included uncomfortable ones (F1 — "maybe the file shouldn't exist"), so the conflict didn't fully suppress criticism, but readers should weight "this looks fine, no issues" with suspicion when author == reviewer.
- **Dialogue overhead:** nine issues took ~nine back-and-forths. Tractable for a single-session alpha exercise; at scale, might be worth grouping minor issues to reduce round-trips (the skill says "one at a time" but the user can invite bundling).
- **Token usage:** not instrumented in this run. Subjective value for the cost: high — at least two findings (F1 existential question, TD-001 drift at minute zero) were genuinely useful and probably wouldn't have surfaced without the critique pass.
